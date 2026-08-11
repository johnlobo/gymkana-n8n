# Locuciones de audio (Kokoro TTS)

Estado 2026-08-11. **Esto no está en el workflow plantilla** (`workflow.json`,
53 nodos, sin nodos de audio): es un añadido manual, nodo a nodo, aplicado
solo a los workflows en producción de Salamanca (`vn3nwqbxR5Ur6Zze`) y Aranda
(`tlFKrYHhqhHnvT2y`, ambos con 71 nodos). Si se monta una gymkana nueva con
`provisioning/provision_gymkana.py` no lleva nada de esto — habría que
replicarlo a mano siguiendo este documento, o backportearlo primero al
template.

## Generación: `provisioning/generar_audio.py`

Sintetiza con [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) (voz
`ef_dora`, español) el texto de `capsula` y `acertijo` de cada estación, lo
reencodea a mp3 mono/24kHz/64kbps con `ffmpeg`, lo sube a Firebase Storage
(`gymkana-linaje-olvidado.firebasestorage.app`, carpeta `{Carpeta}/`) y
escribe `audio_url` / `acertijo_audio_url` en el doc de esa estación en
Firestore.

```
.venv-kokoro/bin/python3 provisioning/generar_audio.py <gymkana_id> \
    --carpeta Aranda --prefijo aranda [--voz ef_dora] [--solo-estacion N] [--dry-run]
```

Requiere un venv **en disco** (no en `/tmp`, que es tmpfs/RAM — meter ahí un
venv con torch/numpy/spacy fue la causa de varios cuelgues del servidor por
OOM el 2026-08-11) con Python 3.12 vía [`uv`](https://astral.sh/uv/) — Python
3.13 (el único que trae `apt` en este sistema) no tiene wheels precompiladas
para `blis`/`spacy`, y compilarlas desde fuente falla con Cython moderno.
Detalle completo de esa investigación, con los intentos fallidos, en
`PROGRESO_AUDIO_KOKORO.md` (nota de trabajo, no documentación final).

Setup resumido:

```
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.12
uv venv --python 3.12 .venv-kokoro
uv pip install --python .venv-kokoro/bin/python3 torch --index-url https://download.pytorch.org/whl/cpu
uv pip install --python .venv-kokoro/bin/python3 kokoro "misaki[es]" soundfile cryptography
uv pip install --python .venv-kokoro/bin/python3 -r provisioning/requirements.txt
```

## Entrega: por qué no hay forma limpia de evitar el "salto al siguiente"

El bot manda cada locución con el nodo Telegram `Enviar Audio*`
(`sendAudio`). Al terminar de sonar, el cliente de Telegram **salta solo al
siguiente audio que encuentre en el historial de ESE chat**, sea de la
estación que sea y aunque se haya enviado horas antes en otra sesión de
pruebas — no hace falta que sean mensajes consecutivos.

Se probó a mandarlo como `sendDocument` en vez de `sendAudio` pensando que
así Telegram no lo trataría como "audio reproducible". No funcionó: Telegram
descarga e inspecciona el contenido real del fichero (para sacar duración y
dibujar la forma de onda) y lo trata igual venga por el método de la Bot API
que venga. Es una limitación conocida y sin resolver del cliente de Telegram
(no de la Bot API), ver [issue abierto en tdesktop, sin
respuesta oficial](https://github.com/telegramdesktop/tdesktop/issues/3649).
Revertido a `sendAudio` (recupera al menos el reproductor con forma de onda,
ya que `sendDocument` no aportaba nada).

## Mitigación aplicada: borrar el audio anterior antes de enviar el siguiente

Como no se puede evitar que Telegram encadene con "el siguiente audio que
haya en el chat", la mitigación es que **nunca haya más de un audio a la
vez** en el chat de cada equipo: antes de mandar uno nuevo, se borra el
anterior con `deleteMessage` (los bots pueden borrar sus propios mensajes en
chats privados hasta 48h después de enviarlos, tiempo de sobra aquí).

Trade-off asumido: el equipo pierde la posibilidad de volver a escuchar el
audio de una estación ya pasada (solo queda "vivo" el último enviado).

### Patrón aplicado en los 3 puntos de envío de audio

Cada gymkana con este parche tiene 3 puntos donde se manda una locución:
`(guardado)` (cápsula, al llegar/resolver una estación), `(resumen)` (al
repetir con `/repetir`) y `acertijo_guardado` (acertijo, justo después de la
cápsula en la misma ejecución — este par es el caso más propenso al
encadenado, porque se envían casi sin gap). En cada uno se insertaron 4
nodos nuevos, siempre con el mismo patrón:

```
[IF] ¿Hay <audio>?              (ya existía)
  └─true──> [IF] ¿Hay audio anterior?          <- NUEVO
               ├─true──> [Telegram] Borrar Audio Anterior   <- NUEVO (deleteMessage,
               │            │                                  onError: continueRegularOutput
               │            │                                  para no romper el flujo si el
               │            │                                  mensaje ya no existe / >48h)
               │            └──> [Telegram] Enviar Audio    (ya existía, sendAudio)
               └─false─────────> [Telegram] Enviar Audio    (directo, nada que borrar)

[Telegram] Enviar Audio
  └──> [Code] Preparar ID Audio         <- NUEVO
         (id: chat_id, ultimo_audio_msg_id: $json.message_id
          -- $json es la respuesta de Telegram al envío que acaba de pasar)
       └──> [Firestore] Guardar ID Audio   <- NUEVO
              (upsert equipos, updateKey "id", columns "id,ultimo_audio_msg_id")
            └──> (el nodo que ya seguía antes, sin cambios)
```

`¿Hay audio anterior?` y `Borrar Audio Anterior` leen el `message_id` guardado
la vez anterior con `$('Cargar equipo').first().json.ultimo_audio_msg_id`
(el nodo que carga el equipo al principio de la ejecución) — así funciona
aunque `Cargar equipo` esté lejos en el flujo, porque n8n permite referenciar
por nombre la salida de cualquier nodo ya ejecutado en esa misma ejecución,
no hace falta que esté en la cadena inmediatamente anterior.

Nombres exactos de los nodos nuevos (sufijo `guardado` / `resumen` /
`acertijo_guardado` según el punto de envío):

- `¿Hay audio anterior? (<sufijo>)` — IF
- `Borrar Audio Anterior (<sufijo>)` — Telegram, `deleteMessage`
- `Preparar ID Audio (<sufijo>)` — Code
- `Guardar ID Audio (<sufijo>)` — Firestore, `upsert`

Backups de los workflows antes/después de este cambio (y del experimento
fallido con `sendDocument`) en `backup/backup_<workflowId>_<timestamp>_*.json`.
