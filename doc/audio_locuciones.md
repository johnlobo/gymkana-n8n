# Locuciones de audio (Kokoro TTS)

Estado 2026-08-11. Ya está en el **workflow plantilla** (`spt1kZxCOE9LCBbz`,
"El Linaje Olvidado" — el mismo bot que usa `provisioning/provision_gymkana.py`
como `--template-workflow-id` por defecto para clonar gymkanas nuevas, no un
fichero estático separado; `workflow.json` en la raíz del repo es solo su
export). Toda gymkana clonada a partir de ahora lo lleva de serie: 18 nodos
(71 en total) — los 6 de envío de audio + los 12 del anti-encadenado (ver
más abajo). En el propio Linaje Olvidado la rama de audio queda inerte (sus
estaciones no tienen `audio_url`/`acertijo_audio_url` — el IF `notEmpty` da
`false` de forma segura ante un campo inexistente, confirmado leyendo
`filter-parameter.js` del propio n8n) hasta que se generen locuciones para
esa gymkana también.

Se aplicó primero a mano en Salamanca (`vn3nwqbxR5Ur6Zze`) y Aranda
(`tlFKrYHhqhHnvT2y`) mientras se iba puliendo (incluido el bug del
`message_id` de más abajo), y una vez verificado se trasplantó tal cual al
template el 2026-08-11 — mismos 18 nodos, mismas expresiones (todas
genéricas, referencian nodos por nombre como `Preparar entrega`/`Cargar
equipo`, no hardcodean nada de una gymkana concreta), solo cambian por
workflow la credencial de Telegram y la ruta de la colección Firestore de
`equipos`.

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
         (id: chat_id, ultimo_audio_msg_id: $json.result.message_id
          -- $json es la respuesta CRUDA de la Bot API al envío que acaba de
          pasar, sin desenvolver: {ok, result: {message_id, ...}}. El nodo
          Telegram de n8n solo desenvuelve "result" en un par de casos
          especiales, no para sendAudio/sendDocument/deleteMessage -- usar
          $json.message_id a secas aquí es un bug fácil de cometer, ya
          costó una ronda de "no borra nada" sin dar ningún error visible.)
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

### No basta con los nodos — el motor de juego también tiene que rellenar los campos

`¿Hay audio? (guardado)` y `¿Hay audio acertijo? (guardado)` leen
`$('Preparar entrega').first().json.audio_url` /
`.audio_acertijo_url`. Esos campos NO llegan solos desde Firestore: hay que
rellenarlos explícitamente en el nodo Code `Procesar estación y comandos`
(el motor de juego), a partir de `station.audio_url` /
`station.acertijo_audio_url`, en cada rama donde se muestra una cápsula o
se revela un acertijo nuevo.

**Ojo con las guardas "solo la primera vez"**: varias ramas de
`Procesar estación y comandos` (rescate, llegada normal) ponen
`audioAcertijoUrl` dentro de un `if (!team.acertijo_visto) { ... }` —
tiene sentido para no reenviar el audio en cada mensaje mientras el
acertijo sigue sin resolverse, pero en la rama de `/repetir` esa misma
guarda hacía que el comando NUNCA sonara si el acertijo ya se había
marcado visto por otro medio (p.ej. `/move`, que también marca
`acertijo_visto = true`) — contradice el propio verbo "repetir". Fix
aplicado 2026-08-11: en `/repetir` el audio se rellena siempre, fuera del
`if`; la guarda se queda solo para decidir si hace falta persistir el
cambio de estado (`changed`).

Esto se pasó por alto dos veces el 2026-08-11: al añadir los nodos a Aranda
(se copiaron los nodos de Telegram/IF pero no este código, así que el
acertijo nunca sonaba pese a que el nodo y el dato en Firestore estaban
bien) y al trasplantar el subsistema a la plantilla (Santillana / Linaje
Olvidado) — ahí ni siquiera se copió la parte de `audio_url` (cápsula).
Salamanca es la referencia correcta: `audioAcertijoUrl` se rellena en 6
sitios, siempre justo donde `team.acertijo_visto = true`. Antes de dar por
completo un backport de este subsistema a una gymkana nueva, comparar su
`Procesar estación y comandos` contra el de Salamanca (son idénticos salvo
estas líneas de audio) en vez de asumir que los nodos ya bastan.

Backups de los workflows antes/después de este cambio (y del experimento
fallido con `sendDocument`) en `backup/backup_<workflowId>_<timestamp>_*.json`.
