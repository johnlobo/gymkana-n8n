#!/usr/bin/env python3
"""
Genera locuciones (Kokoro TTS) para las capsulas/acertijos de una gymkana,
las sube a Firebase Storage y actualiza audio_url / acertijo_audio_url en
Firestore.

Requiere el venv con kokoro/torch/misaki[es]/soundfile ya instalado (ver
PROGRESO_AUDIO_KOKORO.md) -- este script se ejecuta con ese intérprete, no
con el python3 del sistema:

    .venv-kokoro/bin/python3 provisioning/generar_audio.py descubre-aranda-duero \
        --carpeta Aranda --prefijo aranda

(venv en disco, Python 3.12 via `uv`, no en /tmp -- ver PROGRESO_AUDIO_KOKORO.md)

Uso:
    python3 generar_audio.py <gymkana_id> --carpeta <Carpeta> --prefijo <prefijo> [--voz ef_dora] [--dry-run]
"""
import argparse
import re
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import requests
import soundfile as sf

from firestore_lib import Firestore, access_token

STORAGE_SCOPE = "https://www.googleapis.com/auth/devstorage.full_control"
BUCKET = "gymkana-linaje-olvidado.firebasestorage.app"
SAMPLE_RATE = 24000

_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002190-\U000021FF"
    "\U00002B00-\U00002BFF"
    "\U0000FE0F"
    "]+",
    flags=re.UNICODE,
)


def limpiar_texto(t):
    """Quita emojis y marcado Markdown de Telegram, deja texto fluido para TTS."""
    t = re.sub(r"[*_`]", "", t)
    t = _EMOJI_RE.sub("", t)
    lineas = [l.strip() for l in t.split("\n") if l.strip()]
    t = " ".join(lineas)
    return re.sub(r"\s+", " ", t).strip()


# --------------------------------------------------------------------------
# TTS
# --------------------------------------------------------------------------
def sintetizar_mp3(pipeline, texto, voz, mp3_path):
    """Genera el audio con Kokoro (WAV en memoria/temp) y lo reencodea a mp3
    mono/24kHz/64kbps con ffmpeg, igual que el formato ya usado en Salamanca."""
    import numpy as np

    trozos = [audio for _, _, audio in pipeline(texto, voice=voz)]
    if not trozos:
        raise RuntimeError(f"Kokoro no generó audio para el texto: {texto[:60]!r}...")
    audio = np.concatenate([t.numpy() if hasattr(t, "numpy") else t for t in trozos])

    with tempfile.NamedTemporaryFile(suffix=".wav") as wav_tmp:
        sf.write(wav_tmp.name, audio, SAMPLE_RATE)
        subprocess.run(
            ["ffmpeg", "-y", "-i", wav_tmp.name, "-ar", str(SAMPLE_RATE), "-ac", "1",
             "-b:a", "64k", str(mp3_path)],
            check=True, capture_output=True,
        )


# --------------------------------------------------------------------------
# Storage
# --------------------------------------------------------------------------
def subir_a_storage(mp3_path, object_name, storage_token):
    token_descarga = str(uuid.uuid4())
    metadata = {"name": object_name, "metadata": {"firebaseStorageDownloadTokens": token_descarga}}
    with open(mp3_path, "rb") as f:
        mp3_bytes = f.read()

    boundary = "gymkana_audio_boundary"
    body = (
        f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
        f'{__import__("json").dumps(metadata)}\r\n'
        f"--{boundary}\r\nContent-Type: audio/mpeg\r\n\r\n"
    ).encode("utf-8") + mp3_bytes + f"\r\n--{boundary}--".encode("utf-8")

    r = requests.post(
        f"https://storage.googleapis.com/upload/storage/v1/b/{BUCKET}/o?uploadType=multipart",
        headers={
            "Authorization": f"Bearer {storage_token}",
            "Content-Type": f"multipart/related; boundary={boundary}",
        },
        data=body,
    )
    r.raise_for_status()

    from urllib.parse import quote
    object_encoded = quote(object_name, safe="")
    url = (
        f"https://firebasestorage.googleapis.com/v0/b/{BUCKET}/o/"
        f"{object_encoded}?alt=media&token={token_descarga}"
    )

    verif = requests.get(url)
    verif.raise_for_status()
    if "audio" not in verif.headers.get("Content-Type", ""):
        raise RuntimeError(f"Subida verificada pero Content-Type inesperado: {verif.headers.get('Content-Type')}")
    return url


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("gymkana_id", help="id de la gymkana en Firestore (gymkanas/<id>)")
    parser.add_argument("--carpeta", required=True, help="carpeta en Storage, p.ej. Aranda")
    parser.add_argument("--prefijo", required=True, help="prefijo de objeto, p.ej. aranda")
    parser.add_argument("--voz", default="ef_dora", help="voz Kokoro (por defecto ef_dora)")
    parser.add_argument("--solo-estacion", type=int, default=None,
                         help="procesa solo esta estación (número de doc, para pruebas)")
    parser.add_argument("--dry-run", action="store_true", help="sintetiza y sube pero no escribe Firestore")
    parser.add_argument("--firebase-key-file",
                         default=str(Path(__file__).parent.parent / "secrets" / "firebase-service-account.json"))
    args = parser.parse_args()

    from kokoro import KPipeline
    pipeline = KPipeline(lang_code="e")

    fs = Firestore(args.firebase_key_file)
    storage_token, _ = access_token(args.firebase_key_file, scope=STORAGE_SCOPE)

    config = fs.get_simple(f"gymkanas/{args.gymkana_id}")
    if config is None:
        print(f"Error: no existe gymkanas/{args.gymkana_id}", file=sys.stderr)
        sys.exit(1)
    num_regulares = int(config["num_estaciones_regulares"])
    num_final = num_regulares + 1

    with tempfile.TemporaryDirectory() as tmpdir:
        for i in range(1, num_final + 1):
            if args.solo_estacion is not None and i != args.solo_estacion:
                continue

            doc_path = f"gymkanas/{args.gymkana_id}/estaciones/{i}"
            doc = fs.get_simple(doc_path)
            if doc is None:
                print(f"Aviso: falta {doc_path}, se omite.", file=sys.stderr)
                continue

            sufijo = "final" if i == num_final else f"estacion_{i:02d}"
            pares = [
                ("capsula", "audio_url", f"{sufijo}_audio"),
                ("acertijo", "acertijo_audio_url", f"{sufijo}_acertijo_audio"),
            ]

            actualizaciones = {}
            for campo_texto, campo_url, nombre_archivo in pares:
                texto = doc.get(campo_texto)
                if not texto:
                    print(f"Aviso: {doc_path} no tiene '{campo_texto}', se omite.", file=sys.stderr)
                    continue
                texto_limpio = limpiar_texto(texto)
                mp3_path = Path(tmpdir) / f"{nombre_archivo}.mp3"
                print(f"[{doc_path}] sintetizando {campo_texto} ({len(texto_limpio)} caracteres)...")
                sintetizar_mp3(pipeline, texto_limpio, args.voz, mp3_path)
                tam = mp3_path.stat().st_size
                if tam == 0:
                    raise RuntimeError(f"mp3 vacío para {doc_path}/{campo_texto}")
                object_name = f"{args.carpeta}/{args.prefijo}_{nombre_archivo}.mp3"
                print(f"  -> subiendo {object_name} ({tam} bytes)...")
                url = subir_a_storage(mp3_path, object_name, storage_token)
                print(f"  -> OK: {url}")
                actualizaciones[campo_url] = url

            if actualizaciones and not args.dry_run:
                nuevo_doc = {**doc, **actualizaciones}
                fs.set_document(doc_path, nuevo_doc)
                print(f"  -> Firestore actualizado: {doc_path}")

    print("Listo.")


if __name__ == "__main__":
    main()
