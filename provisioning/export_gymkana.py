#!/usr/bin/env python3
"""
Exporta una gymkana ya desplegada en Firestore al formato YAML que espera
provision_gymkana.py -- el inverso de ese script. Util para hacer una
copia de seguridad legible del contenido de una gymkana, o para clonarla
como punto de partida de una nueva.

No exporta admin_chat_id por defecto (suele ser un chat_id real de
Telegram, no algo para dejar en un fichero que puede acabar en un
repositorio publico) ni datos en vivo de equipos/eventos -- solo la
configuracion del juego y el contenido de las estaciones.

Uso:
    python3 export_gymkana.py linaje-olvidado
    python3 export_gymkana.py linaje-olvidado -o ../content/linaje_olvidado.yaml
    python3 export_gymkana.py linaje-olvidado --include-admin-chat-id
    python3 export_gymkana.py linaje-olvidado --firebase-key-file ../secrets/firebase-service-account.json
"""
import argparse
import sys
from pathlib import Path

import yaml

from firestore_lib import Firestore
from provision_gymkana import validar_definicion

NUMEROS_EMOJI = ["", "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

CAMPOS_ESTACION = ("nombre", "lat", "lon", "acertijo", "respuestas",
                    "capsula", "imagen_url", "mapa_url")
CAMPOS_ESTACION_FINAL = CAMPOS_ESTACION + (
    "imagen_final_url", "coordenadas_finales", "secuencia_codice", "guia_historica_url",
)


class LiteralStr(str):
    """Marca las cadenas que queremos volcar en YAML con el estilo de
    bloque literal ('|'), para que los textos largos/multilinea (acertijos,
    capsulas...) se lean como en el original en vez de como una sola linea
    con \\n escapados."""


def _literal_str_representer(dumper, data):
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")


yaml.add_representer(LiteralStr, _literal_str_representer)


def _legible(obj):
    if isinstance(obj, str):
        if "\n" in obj or len(obj) > 80:
            return LiteralStr(obj)
        return obj
    if isinstance(obj, list):
        return [_legible(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _legible(v) for k, v in obj.items()}
    return obj


def exportar_estacion(doc, campos):
    faltan = [c for c in campos if c not in doc]
    if faltan:
        print(
            f"Aviso: la estación {doc.get('id', '?')} no tiene {faltan} "
            "(se omiten, provision_gymkana.py los exigirá al reaprovisionar)",
            file=sys.stderr,
        )
    salida = {c: doc[c] for c in campos if c in doc}
    pistas = [doc[f"pista{i}"] for i in (1, 2, 3) if f"pista{i}" in doc]
    if pistas:
        salida["pistas"] = pistas
    return salida


def ordenar_campos_estacion_regular(orden_num, e):
    campos = ("orden", "nombre", "lat", "lon", "acertijo", "respuestas", "pistas",
              "capsula", "imagen_url", "mapa_url")
    e = {**e, "orden": orden_num}
    return {k: e[k] for k in campos if k in e}


def ordenar_campos_estacion_final(e):
    campos = ("nombre", "lat", "lon", "acertijo", "respuestas", "pistas", "capsula",
              "imagen_url", "imagen_final_url", "mapa_url", "coordenadas_finales",
              "secuencia_codice", "guia_historica_url")
    return {k: e[k] for k in campos if k in e}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("gymkana_id", help="id de la gymkana en Firestore (gymkanas/<id>)")
    parser.add_argument("-o", "--output", default=None,
                         help="fichero YAML de salida (por defecto: <gymkana_id>.yaml)")
    parser.add_argument("--include-admin-chat-id", action="store_true",
                         help="incluye admin_chat_id en el YAML (por defecto se omite)")
    parser.add_argument("--firebase-key-file",
                         default=str(Path(__file__).parent.parent / "secrets" / "firebase-service-account.json"))
    args = parser.parse_args()

    fs = Firestore(args.firebase_key_file)

    config = fs.get_simple(f"gymkanas/{args.gymkana_id}")
    if config is None:
        print(f"Error: no existe gymkanas/{args.gymkana_id} en Firestore.", file=sys.stderr)
        sys.exit(1)

    num_regulares = int(config.get("num_estaciones_regulares") or 0)
    if num_regulares < 1:
        print(
            f"Error: gymkanas/{args.gymkana_id}.num_estaciones_regulares "
            f"no es válido ({config.get('num_estaciones_regulares')!r}).",
            file=sys.stderr,
        )
        sys.exit(1)

    estaciones_raw = {}
    for i in range(1, num_regulares + 2):
        doc = fs.get_simple(f"gymkanas/{args.gymkana_id}/estaciones/{i}")
        if doc is None:
            print(
                f"Error: falta gymkanas/{args.gymkana_id}/estaciones/{i} "
                f"(se esperaban {num_regulares} regulares + 1 final).",
                file=sys.stderr,
            )
            sys.exit(1)
        estaciones_raw[i] = doc

    fragmentos = [estaciones_raw[1].get(f"paso{i}_fragmento", "") for i in range(1, num_regulares + 1)]

    estaciones = [
        ordenar_campos_estacion_regular(i, exportar_estacion(estaciones_raw[i], CAMPOS_ESTACION))
        for i in range(1, num_regulares + 1)
    ]

    estacion_final = ordenar_campos_estacion_final(
        exportar_estacion(estaciones_raw[num_regulares + 1], CAMPOS_ESTACION_FINAL)
    )

    definicion = {"id": config["id"], "nombre": config.get("nombre", args.gymkana_id)}
    # Solo se incluyen si están puestos en Firestore: si faltaran, mejor
    # dejar que provision_gymkana.py aplique sus valores por defecto que
    # exportar un `null` literal que los pisaría.
    for campo in ("tolerancia_metros", "max_pistas", "peso_pista", "peso_mapa",
                  "peso_rescate", "termino_enclave"):
        if config.get(campo) is not None:
            definicion[campo] = config[campo]
    if args.include_admin_chat_id:
        definicion["admin_chat_id"] = config.get("admin_chat_id", "")
    definicion["fragmentos"] = fragmentos
    definicion["estaciones"] = estaciones
    definicion["estacion_final"] = estacion_final

    # provision_gymkana.py valida esta misma estructura al leerla; lo
    # comprobamos aquí también para detectar un export incompleto al
    # momento, no la próxima vez que alguien intente reaprovisionar.
    validar_definicion(definicion)

    salida_legible = _legible(definicion)

    output_path = args.output or f"{args.gymkana_id}.yaml"
    header = (
        f"# Definicion de la gymkana '{config.get('nombre', args.gymkana_id)}' "
        f"(id={args.gymkana_id}),\n"
        "# exportada desde Firestore con export_gymkana.py.\n"
        "# Formato para provision_gymkana.py -- ver provisioning/README.md.\n"
    )
    if not args.include_admin_chat_id:
        header += (
            "#\n"
            "# admin_chat_id no se ha exportado (usa --include-admin-chat-id si lo\n"
            "# necesitas); provision_gymkana.py lo rellena solo desde\n"
            "# secrets/admin_chat_id si el YAML no lo trae.\n"
        )
    header += "\n"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(header)
        yaml.dump(salida_legible, f, allow_unicode=True, sort_keys=False,
                  default_flow_style=False, width=100)

    print(f"Exportado: {output_path}")
    print(f"  {num_regulares} estaciones regulares + 1 estación final")


if __name__ == "__main__":
    main()
