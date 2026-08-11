"""
Cliente Firestore minimo compartido por provision_gymkana.py y
export_gymkana.py: autenticacion via cuenta de servicio (JWT -> OAuth2,
sin depender de gcloud/las librerias oficiales de Google) y conversion
entre el formato tipado de la API REST de Firestore y valores Python
normales.
"""
import json
import time

import jwt
import requests

FIRESTORE_SCOPE = "https://www.googleapis.com/auth/datastore"


def access_token(service_account_path, scope=FIRESTORE_SCOPE):
    with open(service_account_path, encoding="utf-8") as f:
        sa = json.load(f)
    now = int(time.time())
    payload = {
        "iss": sa["client_email"],
        "sub": sa["client_email"],
        "aud": "https://oauth2.googleapis.com/token",
        "iat": now,
        "exp": now + 3600,
        "scope": scope,
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


def from_firestore_value(v):
    if "stringValue" in v:
        return v["stringValue"]
    if "integerValue" in v:
        return int(v["integerValue"])
    if "doubleValue" in v:
        return v["doubleValue"]
    if "booleanValue" in v:
        return v["booleanValue"]
    if "nullValue" in v:
        return None
    if "arrayValue" in v:
        return [from_firestore_value(x) for x in v["arrayValue"].get("values", [])]
    if "mapValue" in v:
        return simplify_fields(v["mapValue"].get("fields", {}))
    raise TypeError(f"Tipo Firestore no soportado: {v}")


def simplify_fields(fields):
    return {k: from_firestore_value(v) for k, v in fields.items()}


class Firestore:
    def __init__(self, service_account_path):
        self.token, self.project_id = access_token(service_account_path)
        self.base = (
            f"https://firestore.googleapis.com/v1/projects/{self.project_id}"
            "/databases/(default)/documents"
        )

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    def get(self, path):
        """Documento crudo (formato tipado de Firestore), o None si no existe."""
        r = requests.get(f"{self.base}/{path}", headers=self._headers())
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    def get_simple(self, path):
        """Documento como dict Python normal, o None si no existe."""
        doc = self.get(path)
        if doc is None or "fields" not in doc:
            return None
        return simplify_fields(doc["fields"])

    def set_document(self, path, fields):
        """PATCH sin updateMask = sobrescribe el documento entero (crea si no existe)."""
        body = {"fields": {k: to_firestore_value(v) for k, v in fields.items()}}
        r = requests.patch(f"{self.base}/{path}", headers=self._headers(), json=body)
        r.raise_for_status()
        return r.json()

    def delete(self, path):
        r = requests.delete(f"{self.base}/{path}", headers=self._headers())
        r.raise_for_status()
