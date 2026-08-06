#!/usr/bin/env python3
"""
Aprovisiona una gymkana nueva a partir de un fichero de definición YAML:
crea sus documentos en Firestore (config, estaciones, contador de reparto)
y clona el workflow de n8n de una gymkana existente, apuntándolo a la
nueva. No crea el bot de Telegram ni asigna sus credenciales en n8n —
eso requiere pasos manuales (ver el README de esta carpeta).

Uso:
    python3 provision_gymkana.py definicion.yaml
    python3 provision_gymkana.py definicion.yaml --dry-run
    python3 provision_gymkana.py definicion.yaml --force
    python3 provision_gymkana.py definicion.yaml --skip-n8n
    python3 provision_gymkana.py definicion.yaml \
        --template-workflow-id spt1kZxCOE9LCBbz \
        --n8n-url http://172.20.0.5:5678 \
        --n8n-api-key-file ../secrets/n8n_api_key \
        --firebase-key-file ../secrets/firebase-service-account.json
"""
import argparse
import json
import sys
import time
import uuid
from pathlib import Path

import jwt
import requests
import yaml

FIRESTORE_SCOPE = "https://www.googleapis.com/auth/datastore"
DEFAULT_TOLERANCIA_METROS = 50
DEFAULT_MAX_PISTAS = 3
DEFAULT_PESO_PISTA = 1
DEFAULT_PESO_MAPA = 3
DEFAULT_PESO_RESCATE = 5
DEFAULT_TERMINO_ENCLAVE = "Enclave"
NUMEROS_EMOJI = ["", "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


# --------------------------------------------------------------------------
# Definición
# --------------------------------------------------------------------------
def cargar_definicion(path):
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    validar_definicion(data)
    return data


def validar_definicion(data):
    errores = []

    for campo in ("id", "nombre", "estaciones", "estacion_final"):
        if campo not in data:
            errores.append(f"falta el campo obligatorio '{campo}'")

    gymkana_id = data.get("id", "")
    if gymkana_id and not all(c.isalnum() or c == "-" for c in gymkana_id):
        errores.append(
            f"'id' ({gymkana_id!r}) debe usar solo letras, números y guiones "
            "(se usa tal cual como documentId de Firestore)"
        )

    estaciones = data.get("estaciones", [])
    n = len(estaciones)
    if n < 1:
        errores.append("'estaciones' no puede estar vacío")

    fragmentos = data.get("fragmentos", [])
    if len(fragmentos) != n:
        errores.append(
            f"'fragmentos' tiene {len(fragmentos)} elementos pero hay {n} "
            "estaciones regulares (debe haber uno por paso, en el mismo orden)"
        )

    ordenes = sorted(e.get("orden") for e in estaciones)
    if ordenes != list(range(1, n + 1)):
        errores.append(
            f"los campos 'orden' de 'estaciones' deben ser 1..{n} sin huecos "
            f"ni repetidos (se encontró: {ordenes})"
        )

    campos_estacion = ("orden", "nombre", "lat", "lon", "acertijo", "respuestas",
                        "pistas", "capsula", "imagen_url", "mapa_url")
    for e in estaciones:
        faltan = [c for c in campos_estacion if c not in e]
        if faltan:
            errores.append(
                f"estación orden={e.get('orden', '?')}: faltan campos {faltan}"
            )

    campos_final = ("nombre", "lat", "lon", "acertijo", "respuestas", "pistas",
                     "capsula", "imagen_url", "mapa_url", "coordenadas_finales")
    ef = data.get("estacion_final", {})
    faltan_final = [c for c in campos_final if c not in ef]
    if faltan_final:
        errores.append(f"'estacion_final': faltan campos {faltan_final}")

    if errores:
        print("La definición tiene errores:", file=sys.stderr)
        for e in errores:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)


# --------------------------------------------------------------------------
# Firestore
# --------------------------------------------------------------------------
def firestore_access_token(service_account_path):
    with open(service_account_path, encoding="utf-8") as f:
        sa = json.load(f)
    now = int(time.time())
    payload = {
        "iss": sa["client_email"],
        "sub": sa["client_email"],
        "aud": "https://oauth2.googleapis.com/token",
        "iat": now,
        "exp": now + 3600,
        "scope": FIRESTORE_SCOPE,
    }
    token = jwt.encode(payload, sa["private_key"], algorithm="RS256")
    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": token,
        },
    )
    resp.raise_for_status()
    return resp.json()["access_token"], sa["project_id"]


def to_firestore_value(v):
    if v is None:
        return {"nullValue": None}
    if isinstance(v, bool):
        return {"booleanValue": v}
    if isinstance(v, int):
        return {"integerValue": str(v)}
    if isinstance(v, float):
        return {"doubleValue": v}
    if isinstance(v, str):
        return {"stringValue": v}
    if isinstance(v, list):
        return {"arrayValue": {"values": [to_firestore_value(x) for x in v]}}
    if isinstance(v, dict):
        return {"mapValue": {"fields": {k: to_firestore_value(x) for k, x in v.items()}}}
    raise TypeError(f"Tipo no soportado para Firestore: {type(v)}")


class Firestore:
    def __init__(self, service_account_path):
        self.token, self.project_id = firestore_access_token(service_account_path)
        self.base = (
            f"https://firestore.googleapis.com/v1/projects/{self.project_id}"
            "/databases/(default)/documents"
        )

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    def get(self, path):
        r = requests.get(f"{self.base}/{path}", headers=self._headers())
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    def set_document(self, path, fields):
        """PATCH sin updateMask = sobrescribe el documento entero (crea si no existe)."""
        body = {"fields": {k: to_firestore_value(v) for k, v in fields.items()}}
        r = requests.patch(f"{self.base}/{path}", headers=self._headers(), json=body)
        r.raise_for_status()
        return r.json()


# --------------------------------------------------------------------------
# Construcción de documentos a partir de la definición
# --------------------------------------------------------------------------
def construir_config(data):
    return {
        "id": data["id"],
        "nombre": data["nombre"],
        "tolerancia_metros": data.get("tolerancia_metros", DEFAULT_TOLERANCIA_METROS),
        "max_pistas": data.get("max_pistas", DEFAULT_MAX_PISTAS),
        "peso_pista": data.get("peso_pista", DEFAULT_PESO_PISTA),
        "peso_mapa": data.get("peso_mapa", DEFAULT_PESO_MAPA),
        "peso_rescate": data.get("peso_rescate", DEFAULT_PESO_RESCATE),
        "num_estaciones_regulares": len(data["estaciones"]),
        "termino_enclave": data.get("termino_enclave", DEFAULT_TERMINO_ENCLAVE),
        "admin_chat_id": str(data.get("admin_chat_id", "")),
    }


def construir_secuencia_codice(fragmentos):
    partes = []
    for i, frag in enumerate(fragmentos, start=1):
        emoji = NUMEROS_EMOJI[i] if i < len(NUMEROS_EMOJI) else f"({i})"
        partes.append(f"{emoji} `{frag}`")
    return " + ".join(partes)


def construir_estacion_regular(e, fragmentos):
    doc = {
        "id": str(e["orden"]),
        "orden": e["orden"],
        "nombre": e["nombre"],
        "lat": float(e["lat"]),
        "lon": float(e["lon"]),
        "acertijo": e["acertijo"],
        "respuestas": e["respuestas"],
        "capsula": e["capsula"],
        "imagen_url": e["imagen_url"],
        "mapa_url": e["mapa_url"],
    }
    pistas = e["pistas"]
    for i, pista in enumerate(pistas, start=1):
        doc[f"pista{i}"] = pista
    for i, frag in enumerate(fragmentos, start=1):
        doc[f"paso{i}_fragmento"] = frag
    return doc


def construir_estacion_final(ef, fragmentos, num_regulares):
    orden_final = num_regulares + 1
    doc = {
        "id": str(orden_final),
        "orden": orden_final,
        "nombre": ef["nombre"],
        "lat": float(ef["lat"]),
        "lon": float(ef["lon"]),
        "acertijo": ef["acertijo"],
        "respuestas": ef["respuestas"],
        "capsula": ef["capsula"],
        "imagen_url": ef["imagen_url"],
        "mapa_url": ef["mapa_url"],
        "imagen_final_url": ef.get("imagen_final_url", ef["imagen_url"]),
        "coordenadas_finales": ef["coordenadas_finales"],
        "secuencia_codice": ef.get("secuencia_codice") or construir_secuencia_codice(fragmentos),
        "guia_historica_url": ef.get("guia_historica_url", ""),
    }
    pistas = ef["pistas"]
    for i, pista in enumerate(pistas, start=1):
        doc[f"pista{i}"] = pista
    for i, frag in enumerate(fragmentos, start=1):
        doc[f"paso{i}_fragmento"] = frag
    return doc


# --------------------------------------------------------------------------
# n8n: clonar el workflow plantilla
# --------------------------------------------------------------------------
def clonar_workflow(n8n_url, api_key, template_workflow_id, old_gymkana_id, new_gymkana_id, nuevo_nombre):
    headers = {"X-N8N-API-KEY": api_key, "Content-Type": "application/json"}
    r = requests.get(f"{n8n_url}/api/v1/workflows/{template_workflow_id}", headers=headers)
    r.raise_for_status()
    wf = r.json()

    prefijo_viejo = f"gymkanas/{old_gymkana_id}"
    prefijo_nuevo = f"gymkanas/{new_gymkana_id}"
    cambios = 0

    for node in wf["nodes"]:
        params = node.get("parameters", {})

        collection = params.get("collection")
        if isinstance(collection, str) and collection.startswith(prefijo_viejo):
            params["collection"] = prefijo_nuevo + collection[len(prefijo_viejo):]
            cambios += 1

        if node.get("name") == "Cargar gymkana" and params.get("documentId") == old_gymkana_id:
            params["documentId"] = new_gymkana_id
            cambios += 1

        # Cada nodo de Telegram trae su propio webhookId; hay que regenerarlos
        # para que no choquen con los del workflow plantilla al activarse.
        if "webhookId" in node:
            node["webhookId"] = str(uuid.uuid4())

    if cambios == 0:
        print(
            "  aviso: no se ha tocado ningún nodo (¿el workflow plantilla ya "
            f"no referencia '{prefijo_viejo}'?) — revísalo a mano.",
            file=sys.stderr,
        )

    payload = {
        "name": nuevo_nombre,
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "settings": {"executionOrder": wf.get("settings", {}).get("executionOrder", "v1")},
    }
    r = requests.post(f"{n8n_url}/api/v1/workflows", headers=headers, json=payload)
    r.raise_for_status()
    return r.json()


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("definicion", help="fichero YAML con la definición de la gymkana")
    parser.add_argument("--dry-run", action="store_true", help="valida y muestra el plan, no escribe nada")
    parser.add_argument("--force", action="store_true", help="sobrescribe si la gymkana ya existe en Firestore")
    parser.add_argument("--skip-n8n", action="store_true", help="solo Firestore, no clona el workflow de n8n")
    parser.add_argument("--template-workflow-id", default="spt1kZxCOE9LCBbz",
                         help="workflow de n8n a clonar (por defecto, El Linaje Olvidado)")
    parser.add_argument("--template-gymkana-id", default="linaje-olvidado",
                         help="id de la gymkana que usa ese workflow plantilla")
    parser.add_argument("--n8n-url", default=None,
                         help="p.ej. http://172.20.0.5:5678 (IP del contenedor en la red de Docker)")
    parser.add_argument("--n8n-api-key-file", default=str(Path(__file__).parent.parent / "secrets" / "n8n_api_key"))
    parser.add_argument("--firebase-key-file",
                         default=str(Path(__file__).parent.parent / "secrets" / "firebase-service-account.json"))
    args = parser.parse_args()

    data = cargar_definicion(args.definicion)
    gymkana_id = data["id"]
    fragmentos = data["fragmentos"]
    num_regulares = len(data["estaciones"])

    config_doc = construir_config(data)
    estacion_docs = [construir_estacion_regular(e, fragmentos) for e in sorted(data["estaciones"], key=lambda e: e["orden"])]
    estacion_final_doc = construir_estacion_final(data["estacion_final"], fragmentos, num_regulares)

    print(f"Gymkana: {data['nombre']!r} (id={gymkana_id})")
    print(f"  {num_regulares} estaciones regulares + 1 estación final")
    print(f"  tolerancia_metros={config_doc['tolerancia_metros']}  max_pistas={config_doc['max_pistas']}")
    print(f"  peso_pista={config_doc['peso_pista']}  peso_mapa={config_doc['peso_mapa']}  peso_rescate={config_doc['peso_rescate']}")
    print(f"  termino_enclave={config_doc['termino_enclave']!r}")
    print()

    if args.dry_run:
        print("(--dry-run: no se ha escrito nada)")
        return

    fs = Firestore(args.firebase_key_file)

    existing = fs.get(f"gymkanas/{gymkana_id}")
    if existing and not args.force:
        print(
            f"Error: ya existe una gymkana con id={gymkana_id!r} en Firestore. "
            "Usa --force para sobrescribirla.",
            file=sys.stderr,
        )
        sys.exit(1)

    print("Escribiendo en Firestore...")
    fs.set_document(f"gymkanas/{gymkana_id}", config_doc)
    print(f"  gymkanas/{gymkana_id} (config)")

    fs.set_document(f"gymkanas/{gymkana_id}/config/contador_inicio", {"id": "contador_inicio", "valor": 0})
    print(f"  gymkanas/{gymkana_id}/config/contador_inicio")

    for doc in estacion_docs:
        fs.set_document(f"gymkanas/{gymkana_id}/estaciones/{doc['id']}", doc)
    print(f"  gymkanas/{gymkana_id}/estaciones/1..{num_regulares}")

    fs.set_document(f"gymkanas/{gymkana_id}/estaciones/{estacion_final_doc['id']}", estacion_final_doc)
    print(f"  gymkanas/{gymkana_id}/estaciones/{estacion_final_doc['id']} (final)")

    if args.skip_n8n:
        print("\n--skip-n8n: no se ha tocado n8n.")
        return

    if not args.n8n_url:
        print(
            "\nAviso: no se ha indicado --n8n-url, así que no se puede clonar el "
            "workflow de n8n. Averígualo con:\n"
            "  docker inspect gymkana_n8n --format "
            "'{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'",
            file=sys.stderr,
        )
        sys.exit(1)

    with open(args.n8n_api_key_file, encoding="utf-8") as f:
        n8n_api_key = f.read().strip()

    print("\nClonando el workflow de n8n...")
    nuevo_nombre = f"Gymkana - 02 Bot principal {data['nombre']}"
    wf = clonar_workflow(
        args.n8n_url, n8n_api_key, args.template_workflow_id,
        args.template_gymkana_id, gymkana_id, nuevo_nombre,
    )
    print(f"  workflow creado: {wf['name']!r} (id={wf['id']})")

    print("\nFaltan pasos manuales antes de que el bot funcione:")
    print(f"  1. Crear el bot de Telegram con @BotFather y guardar su token.")
    print(f"  2. En n8n, crear una credencial 'Telegram API' nueva con ese token.")
    print(f"  3. En el workflow '{wf['name']}', reasignar esa credencial en TODOS los")
    print(f"     nodos de Telegram (Trigger + los ~11 de envío) — hoy apuntan a la")
    print(f"     credencial de la gymkana plantilla.")
    print(f"  4. Activar el workflow.")


if __name__ == "__main__":
    main()
