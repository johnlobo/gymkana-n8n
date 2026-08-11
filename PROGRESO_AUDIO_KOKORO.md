# Progreso: locuciones (Kokoro TTS) para Salamanca y Aranda

Nota de trabajo en curso, no documentación final. Se actualiza según avanza
la tarea para poder retomarla si la sesión se cae. Bucket de Storage:
`gymkana-linaje-olvidado.firebasestorage.app`. Convención de nombre:
`{Carpeta}/{prefijo}_estacion_{NN}_audio.mp3` y `..._acertijo_audio.mp3`
(estación final: `..._final_audio.mp3` / `..._final_acertijo_audio.mp3`).

## Estado detectado al retomar (2026-08-11, tarde)

### Salamanca (`gymkanas/testimonio-de-piedra`, workflow n8n `vn3nwqbxR5Ur6Zze`)
- Firestore: estaciones 1-8 con `audio_url` + `acertijo_audio_url` OK.
- **Bug encontrado**: la estación final es el doc `9` (= num_regulares+1, ver
  `construir_estacion_final` en `provisioning/provision_gymkana.py`), tiene
  `audio_url` OK pero le falta `acertijo_audio_url`. Ese campo se escribió por
  error en un doc **inexistente/erróneo** `gymkanas/testimonio-de-piedra/estaciones/final`
  (no debería existir, el doc real es `9`).
- `content/el_testimonio_de_piedra_salamanca.yml` (sin commitear) ya tiene
  ambas URLs correctas para el final — es decir, el token de
  `acertijo_audio_url` correcto YA se conoce, solo falta moverlo al doc `9`
  y borrar el doc `final` fantasma.
- Workflow n8n de Salamanca ya tiene los 6 nodos de audio: `¿Hay audio?
  (guardado)`+`Enviar Audio (guardado)`, `¿Hay audio? (resumen)`+`Enviar
  Audio (resumen)`, `¿Hay audio acertijo? (guardado)`+`Enviar Audio Acertijo
  (guardado)`. Backups previos: `backup/backup_vn3nwqbxR5Ur6Zze_20260811_165039_pre_audio.json`
  y `..._173532_pre_acertijo_audio.json`.
- **Pendiente**: aplicar el fix de Firestore de arriba, luego re-exportar YAML
  (o dejarlo, ya está bien) y decidir si commitear.

### Aranda (`gymkanas/descubre-aranda-duero`, workflow n8n `tlFKrYHhqhHnvT2y`)
- Firestore: 7 docs de estaciones (1-6 + final=doc `7`), todas con
  `audio_url` vacío (placeholder) y **sin** campo `acertijo_audio_url` en
  absoluto. **No hay ni un solo audio generado todavía.**
- `content/descubre_aranda_de_duero.yml`: 0 audios.
- Workflow n8n de Aranda solo tiene 2 de los 6 nodos de audio: `¿Hay audio?
  (guardado)` + `Enviar Audio (guardado)`. **Faltan** los 4 nodos de
  `(resumen)` y de `acertijo (guardado)` — replicar el patrón de Salamanca.

### Entorno técnico
- Kokoro-82M v1.0 (soporta español, código de idioma `e`) ya está en caché:
  `~/.cache/huggingface/hub/models--hexgrad--Kokoro-82M`.
- espeak-ng instalado (backend de misaki para español).
- **`pip3` ha desaparecido del sistema** (antes se usaba, ver
  `.claude/settings.local.json` con `pip3 install *` permitido). Hay que
  reinstalarlo (`apt install python3-pip` o `python3 -m ensurepip`) y
  probablemente usar `--break-system-packages` o un venv, porque el entorno
  está marcado `EXTERNALLY-MANAGED`. Cache de pip con ~379MB ya descargado en
  `~/.cache/pip` (probablemente incluye torch).
- No hay GPU (`nvidia-smi` no disponible) → inferencia por CPU.
- No queda ningún script de generación de audio en el repo ni en el sistema
  (se debió generar con un script ad-hoc que ya no existe). Formato de salida
  observado en un mp3 ya subido: mono, 24kHz, mp3 64kbps (nativo de Kokoro +
  reencodeo con ffmpeg, tag `Lavf61.7.100`). No se pudo recuperar qué voz
  española se usó (sin metadata en el mp3).

## Plan de continuación

1. [ ] Fix Firestore Salamanca: copiar `acertijo_audio_url` del doc `final`
   fantasma al doc `9`, borrar el doc `final`.
2. [ ] Generar y subir audio Aranda: 7 estaciones x 2 (capsula + acertijo) =
   14 mp3s, subir a Storage bajo `Aranda/`, escribir `audio_url` +
   `acertijo_audio_url` en Firestore, re-exportar YAML con
   `provisioning/export_gymkana.py`.
3. [x] Replicar en el workflow de Aranda (n8n) los 4 nodos de audio que
   faltan (resumen + acertijo guardado), tomando como referencia el workflow
   de Salamanca (`vn3nwqbxR5Ur6Zze`). Backup antes de tocarlo. **HECHO.**
4. [ ] Verificar (dry-run o prueba real) que ambos bots entregan el audio
   correctamente.
5. [ ] Decidir con el usuario si commitear los YAML/scripts pendientes.

## Log de acciones

- 2026-08-11 21:10 — Retomada la sesión. Investigado el estado real
  (Firestore + n8n API + YAMLs) descrito arriba. Nada modificado todavía.
- 2026-08-11 21:20 — **Fix Salamanca aplicado**: copiado `acertijo_audio_url`
  del doc fantasma `gymkanas/testimonio-de-piedra/estaciones/final` al doc
  real `9`, y borrado el doc `final`. Verificado con GET: doc `9` tiene ahora
  `audio_url` + `acertijo_audio_url` correctos. Salamanca queda con todos los
  audios completos en Firestore (`content/el_testimonio_de_piedra_salamanca.yml`
  local ya coincidía, sigue sin commitear). Tarea 1 completada.
- 2026-08-11 21:2x — Lanzados en paralelo dos subagentes en background:
  (a) generación/subida de audio Kokoro para Aranda (tarea 2), (b) réplica de
  nodos de audio faltantes en el workflow de Aranda (tarea 3). Ver sus
  entradas de log más abajo cuando reporten.
- 2026-08-11 21:2x — [Subagente (a), audio Aranda] Confirmado vía Firestore:
  config `gymkanas/descubre-aranda-duero` tiene `num_estaciones_regulares=6`,
  docs `estaciones/1..7` existen (7 = final), todos con `audio_url=''` y sin
  `acertijo_audio_url`. Coincide con el YAML local. Creado venv
  `/tmp/kokoro-venv`, instalado `torch` (CPU, desde
  download.pytorch.org/whl/cpu) y luego `kokoro misaki[es] soundfile` desde
  PyPI normal (el primer intento con `--index-url` de pytorch para los 4
  paquetes a la vez falló porque ese índice no tiene `kokoro`; separar la
  instalación en dos comandos lo arregló). Instalación completada OK
  (numpy se compiló desde fuente porque no hay wheel para cp313, tardó pero
  terminó bien). Creado `provisioning/generar_audio.py` (limpieza de texto +
  síntesis Kokoro + reencode ffmpeg + subida multipart a Storage con token de
  descarga + actualización Firestore), y añadido parámetro `scope` a
  `access_token()` en `firestore_lib.py` (retrocompatible) para poder pedir
  el scope de Storage además del de Firestore. Siguiente paso: prueba corta
  de síntesis antes de lanzar las 14 locuciones completas.
- 2026-08-11 21:2x — **Bloqueo de instalación diagnosticado**: la primera
  instalación de `kokoro misaki[es] soundfile` (en background, cuya salida se
  filtró con `| tail -30`, lo que enmascaró el código de salida y me hizo
  creer erróneamente que había terminado bien) en realidad **falló**:
  `misaki` no tiene ningún extra `[es]` en absoluto (solo `en`, `ja`, `ko`,
  `vi`, `zh` — confirmado leyendo el METADATA del wheel de PyPI), así que
  `misaki[es]` es un no-op. El problema real es que el propio paquete
  `kokoro` depende duro de `misaki[en]>=0.7.16` (arrastra `spacy`,
  `spacy-curated-transformers`, `num2words`, `phonemizer` **siempre**, da
  igual el idioma que se vaya a sintetizar, porque es el pipeline de
  fallback/G2P del inglés). En Python 3.13 no había wheels precompilados
  para las versiones antiguas de `thinc`/`blis` que pip intentaba resolver,
  y compilarlas desde fuente fallaba (`Cython.Compiler.Errors.CompileError:
  blis/py.pyx`). Verificado con `pip download --only-binary=:all:` que SÍ
  existen wheels cp313 para las versiones recientes (`blis 1.3.3`, `thinc
  8.3.13`, `spacy 3.8.15`) — el problema era que el resolver de pip, sin
  forzar preferencia por binarios, se iba por una combinación vieja
  sin wheel. Relanzada la instalación con `pip install --prefer-binary
  kokoro "misaki[es]" soundfile` (log en
  `/tmp/claude-1000/.../scratchpad/pip_install2.log`, proceso vigilado con
  `while kill -0 <pid>; do sleep 10; done` en vez de con pipes que
  enmascaran el exit code). A las ~21:2x sigue en marcha: pip está
  retrocediendo por varias versiones de `kokoro` (0.7.16 → 0.7.4) buscando
  una cuyo pin de `misaki[en]` case con la única versión de `misaki`
  publicada (0.7.4), y en paralelo compilando `numpy==1.26.4` desde fuente
  (kokoro fija esa versión exacta, sin wheel cp313 — esto ya se había visto
  compilar bien una vez antes, tarda pero no falla). Si termina bien: probar
  síntesis corta. Si vuelve a fallar por spacy/thinc/blis con
  `--prefer-binary` puesto, sería necesario un intérprete Python != 3.13
  (no hay ninguno instalado en el sistema aparte de 3.13, ver `ls
  /usr/bin/python3.1*` — habría que decidir con el usuario si se instala uno
  vía apt, lo cual no es "solo venv").
- 2026-08-11 21:14-21:17 — **Tarea 3 completada** (subagente réplica de nodos
  de audio en Aranda):
  - Backup de Aranda pre-cambio: `backup/backup_tlFKrYHhqhHnvT2y_20260811_211452_pre_audio_resumen_acertijo.json`
    (55 nodos, confirmado antes de tocar nada).
  - Descargado Salamanca fresco como referencia (`vn3nwqbxR5Ur6Zze`, 59 nodos,
    sin tocarlo). Localizados los 4 nodos que faltaban en Aranda: `¿Hay
    audio? (resumen)`, `Enviar Audio (resumen)`, `¿Hay audio acertijo?
    (guardado)`, `Enviar Audio Acertijo (guardado)`. Sus `parameters` son
    100% genéricos (referencian `$('Decidir acción')...team.audio_final` y
    `$('Preparar entrega')...audio_acertijo_url`/`audio_url`, nodos que ya
    existen con esos mismos nombres en Aranda) — nada hardcodeado de
    Salamanca, no hizo falta adaptar expresiones.
  - Credenciales usadas: las que ya tenía el `Enviar Audio (guardado)` de
    ARANDA (`telegramApi` id `zVFT3engfy2uPq72`, "Telegram - Descubre Aranda
    de Duero"), no las de Salamanca.
  - Cableado: en Aranda el orden de nodos "guardado" difería un poco del de
    Salamanca (Aranda tiene además `¿Hay guía histórica? (guardado)` después
    de `Enviar respuesta tras guardar`, que Salamanca no tiene). Se insertó
    el par acertijo en el mismo punto relativo que en Salamanca: justo
    después de `Enviar Audio (guardado)` (tanto su salida true como la salida
    false de `¿Hay audio? (guardado)`) y antes de `Enviar respuesta tras
    guardar`, dejando intacto lo que ya colgaba de `Enviar respuesta tras
    guardar` (la guía histórica). Para el resumen, se insertó `¿Hay audio?
    (resumen)` entre `1. Enviar Resumen de la Ruta` y `¿Hay documento?
    (resumen)`, igual que en Salamanca. Decisión de diseño (no había
    ambigüedad real, pero se documenta): posiciones nuevas elegidas en huecos
    libres del canvas: `¿Hay audio? (resumen)` en [560,800], `Enviar Audio
    (resumen)` en [784,800], `¿Hay audio acertijo? (guardado)` en [3584,560],
    `Enviar Audio Acertijo (guardado)` en [3808,640] — no solapan con nodos
    existentes.
  - PUT a `tlFKrYHhqhHnvT2y` con body `{name, nodes, connections, settings}`
    (se comprobó que el GET devuelve más campos como `active`, `versionId`,
    etc. que la API no acepta de vuelta; se filtraron). Respuesta HTTP 200.
  - Verificado con GET posterior: **59 nodos** (55+4, igual que Salamanca),
    los 6 nodos de audio presentes (`¿Hay audio? (guardado)`, `Enviar Audio
    (guardado)`, `¿Hay audio? (resumen)`, `Enviar Audio (resumen)`, `¿Hay
    audio acertijo? (guardado)`, `Enviar Audio Acertijo (guardado)`), y las
    `connections` de las cadenas resumen/guardado coinciden exactamente con
    el patrón esperado. Workflow sigue `active: true`, no se tocó ninguna
    lógica de juego. No se activó/desactivó el workflow.
  - Riesgo/pendiente: no se ha hecho una prueba real end-to-end con el bot de
    Telegram (eso corresponde al punto 4 del plan, y depende de que la tarea
    2 — generación de audios de Aranda — también termine, porque hasta que
    Firestore tenga `audio_url`/`acertijo_audio_url`/`team.audio_final`
    reales, los IF de "¿Hay audio?" siempre darán `false` en Aranda). Tarea 3
    queda completada; falta la prueba funcional conjunta.
- 2026-08-11 ~21:46 — **El servidor se colgó y se reinició en frío** (sin
  shutdown limpio en el log, log corta a las 21:45:48 en medio de timeouts de
  DNS de dockerd, boot nuevo a las 21:46:13). Causa: los 4 `Out of memory:
  Killed process ... python3` de hoy (16:32, 17:12, 17:21, 20:57) eran los
  sucesivos intentos de instalar/compilar el venv de Kokoro (torch + numpy
  1.26.4 compilado desde fuente + spacy/thinc/blis que arrastra
  `misaki[en]`), agravado porque **`/tmp` es tmpfs (RAM), tope 3.8G = 50% de
  los 7.6G totales** — el venv en `/tmp/kokoro-venv` restaba RAM real además
  del propio pico de compilación, sin swap (`Swap: 0B`). `/tmp/kokoro-venv`
  no sobrevivió al reinicio.
  Mitigaciones aplicadas antes de reintentar: (a) swap de 4G creado y
  persistente en `/etc/fstab` (`/swapfile`), (b) venv recreado en **disco**,
  no en tmpfs: `docker/gymkana-n8n/.venv-kokoro/` (añadido a `.gitignore`),
  (c) `TMPDIR` de pip apuntado a `docker/gymkana-n8n/.pip-tmp/` (disco, no
  `/tmp`) para que el build isolation de pip tampoco use tmpfs, (d)
  instalación lanzada con `nice -n 15 ionice -c3` y `MAKEFLAGS=-j2` /
  `NPY_NUM_BUILD_JOBS=2` (mitad de los 4 cores) para no acaparar CPU/RAM
  mientras hay otras sesiones activas. `torch` (wheel, CPU) instalado sin
  incidentes. `pip install --prefer-binary kokoro "misaki[es]" soundfile`
  lanzado en background (nohup, PID en `.pip-tmp/install_kokoro.pid`,
  log en `.pip-tmp/install_kokoro.log`), monitorizado sin bloquear la
  sesión. Comando de referencia para retomar si esta sesión también se cae:
  `tail -f docker/gymkana-n8n/.pip-tmp/install_kokoro.log`.
- 2026-08-11 22:06 — Ese intento falló (rápido, sin riesgo de memoria):
  `blis==0.7.11` (arrastrado por `thinc<9.1.0` que exige
  `spacy-curated-transformers`, dependencia dura de `misaki[en]`, a su vez
  dependencia dura de `kokoro` sea cual sea el idioma) no tiene wheel para
  cp313 y falla al compilar desde fuente (`Cython.Compiler.Errors.CompileError:
  blis/py.pyx`, incompatibilidad de blis 0.7.11 con Cython moderno, no es un
  problema de RAM). Confirmado con `pip download --only-binary` que blis
  0.7.11 SÍ tiene wheel para cp311/cp312. Este sistema (Ubuntu 25.04 "plucky")
  solo trae python3.13 por apt, sin python3.11/3.12 (ni deadsnakes es fiable
  para una release tan nueva). Solución: instalado `uv` (astral, binario en
  `~/.local/bin`, sin sudo) y `uv python install 3.12` (CPython 3.12.13
  portátil, sandboxed en el home). Venv recreado en
  `docker/gymkana-n8n/.venv-kokoro` sobre Python 3.12. `torch` reinstalado
  (wheel, ~8s con `uv`). `uv pip install kokoro "misaki[es]" soundfile`
  lanzado en background (PID en `.pip-tmp/install_kokoro312.pid`, log en
  `.pip-tmp/install_kokoro312.log`) — con wheels cp312 disponibles para toda
  la cadena, no debería necesitar compilar nada.
- 2026-08-11 22:08-22:23 — **Instalación en Python 3.12 OK, sin compilar
  nada** (numpy resuelto a 2.5.2, no al 1.26.4 problemático; kokoro no fija
  esa versión con tanta fuerza cuando el resolver parte de un intérprete con
  wheels disponibles). Añadido `cryptography` a `requirements.txt` (faltaba
  para que PyJWT firme RS256; no estaba listado aunque `firestore_lib.py`
  siempre lo necesitó). Prueba corta (`--solo-estacion 1 --dry-run`): OK,
  sintetiza y sube sin tocar Firestore. **Tarea 2 completada.**
  Lanzada generación completa (sin `--dry-run`, sin `--solo-estacion`) en
  background; monitorizada por Firestore (no por el log, que sale bufferizado
  al no ser una tty). Las 7 estaciones (1-6 + final=7) completadas en ~9
  minutos sin ningún aviso de memoria alta. **Tarea 2 (generación Aranda)
  completada**: 14 mp3s subidos a `Storage/Aranda/`, Firestore actualizado.
  Re-exportado `content/descubre_aranda_de_duero.yml` con
  `provisioning/export_gymkana.py` — 14 URLs de audio confirmadas en el YAML.
  **Tarea 4 completada.**
  Pendiente: tarea 4 del plan original (prueba real/dry-run de entrega en
  ambos bots de Telegram) y decidir con el usuario si commitear
  `content/*.yml`, `provisioning/generar_audio.py`, `firestore_lib.py`
  (scope param) y `requirements.txt` (cryptography añadido).
- 2026-08-11 22:2x — Commiteado (commit `34640b3`, local, sin push):
  `generar_audio.py`, YAMLs de Salamanca/Aranda, fix de `provision_gymkana.py`
  (audio_url/acertijo_audio_url), `requirements.txt`, backups de n8n y esta
  nota. **Único punto pendiente del plan: probar en real la entrega de audio
  en los bots de Telegram de Salamanca y Aranda — lo hará el usuario a
  mano.**
- 2026-08-11 22:3x — **Bug reportado por el usuario**: al terminar de sonar
  una locución, Telegram salta automáticamente a la siguiente (de otra
  estación, o la cápsula tras el acertijo) sin que el usuario la pida.
  Confirmado por búsqueda + inspección del código del nodo
  (`Telegram.node.js` dentro del contenedor `gymkana_n8n`): es un
  comportamiento nativo del cliente de Telegram para mensajes tipo
  audio/voz (los encadena como playlist de la conversación), no hay
  parámetro de la Bot API para desactivarlo. Único fix fiable: enviar el
  mp3 como **documento** (`sendDocument`) en vez de **audio** (`sendAudio`)
  — mismo campo `file`/`chatId`/`additionalFields`, confirmado leyendo el
  esquema del nodo. Contrapartida: se pierde el reproductor inline con forma
  de onda; llega como adjunto descargable.
  Aplicado en los 6 nodos `Enviar Audio*` (3 por workflow × Salamanca +
  Aranda), backup previo en
  `backup/backup_{vn3nwqbxR5Ur6Zze,tlFKrYHhqhHnvT2y}_20260811_223357_pre_sendDocument.json`.
  PUT vía API de n8n confirmado con HTTP 200 en ambos, verificado por GET
  posterior: los 6 nodos en `sendDocument`, ambos workflows siguen
  `active: true`. Pendiente: que el usuario confirme en Telegram que ya no
  encadena.
- 2026-08-11 22:4x — **El usuario confirma que sendDocument NO arregló nada**
  (sigue con onda y sigue encadenando). Investigado más a fondo: Telegram no
  decide por el método de la Bot API, sino que descarga e inspecciona el
  contenido real del fichero (extrae duración, genera forma de onda) cuando
  reconoce un MP3 válido, sea por `sendAudio` o `sendDocument` — confirmado
  por búsqueda web (limitación conocida y sin resolver de Telegram, issue
  abierto en tdesktop pidiendo poder desactivar el autoplay-next, sin
  respuesta oficial). No hay lever del lado servidor/Bot-API para esto sin
  además "disfrazar" el fichero (zip, extensión falsa) hasta el punto de que
  Telegram no pueda parsear el audio — lo cual también le quita al jugador
  la reproducción dentro de la propia app.
  **Revertido a `sendAudio`** en los 6 nodos (decisión del usuario: ya que
  sendDocument no aporta nada, mejor recuperar el reproductor con onda).
  Backup pre-revert en
  `backup/backup_{vn3nwqbxR5Ur6Zze,tlFKrYHhqhHnvT2y}_<TS>_pre_revert_sendAudio.json`.
  PUT confirmado HTTP 200 en ambos, verificado por GET: los 6 nodos de vuelta
  en `sendAudio`, ambos workflows `active: true`.
  **El salto automático entre locuciones queda como limitación conocida y
  sin arreglo del lado servidor.** Opciones no aplicadas, a valorar si se
  retoma: (a) disfrazar el fichero (zip) sacrificando la reproducción
  inline, (b) rediseñar el flujo del juego para que ningún salto automático
  revele contenido de otra estación antes de tiempo (p.ej. no soltar el
  audio de la siguiente estación hasta que el equipo responda el acertijo).
- 2026-08-11 22:5x — **El usuario ató cabos**: el chat de pruebas es el mismo
  para Salamanca y Aranda, y ya tenía audios viejos de pruebas de esta tarde
  — de ahí que "solo se le pasó uno" pero igualmente saltara a otro (Telegram
  encadena con el siguiente audio de TODO el historial del chat, no solo con
  mensajes consecutivos de la misma interacción). Preguntó si se pueden
  borrar los mp3 anteriores al cargar uno nuevo — confirmado que sí
  (`deleteMessage`, un bot puede borrar sus propios mensajes en chats
  privados hasta 48h después). Diseñado e implementado: nuevo campo
  `ultimo_audio_msg_id` en `equipos`, y en cada uno de los 3 puntos de envío
  de audio (guardado/resumen/acertijo_guardado) de Salamanca y Aranda, 4
  nodos nuevos (`¿Hay audio anterior?` → `Borrar Audio Anterior` →
  `Enviar Audio` (ya existía) → `Preparar ID Audio` → `Guardar ID Audio`).
  Backup pre-cambio en
  `backup/backup_{vn3nwqbxR5Ur6Zze,tlFKrYHhqhHnvT2y}_20260811_225202_pre_borrar_audio_anterior.json`.
  Desplegado vía API de n8n, HTTP 200 en ambos, verificado por GET: 71 nodos
  cada uno (59 + 12), `active: true`. **Documentación completa del patrón en
  `doc/audio_locuciones.md`** (nuevo), más los campos nuevos de Firestore
  añadidos a `doc/datos_firestore.md` (`ultimo_audio_msg_id`, y de paso
  `audio_url`/`acertijo_audio_url` que faltaban documentar de antes).
  Pendiente: que el usuario confirme en real que ya no encadena.
- 2026-08-11 23:0x — **El usuario prueba /repetir y /rescate en Salamanca:
  no borra nada.** Sin logs de ejecución disponibles vía API de n8n (executions
  vacío incluso sin filtro, no hay guardado de ejecuciones habilitado).
  Verificado directamente en Firestore: el único equipo de Salamanca
  (chat_id=5770831482, el mismo admin_chat_id — es el propio chat de pruebas)
  tiene `ultimo_audio_msg_id: null` pese a `actualizado_en` reciente. Bug
  encontrado leyendo `Telegram.node.js`: para `resource=message` (sendAudio,
  sendDocument, deleteMessage) el nodo Telegram devuelve la respuesta CRUDA
  de la Bot API (`{ok, result: {message_id, ...}}`) sin desenvolver `result`
  (eso solo pasa para un par de casos especiales como `chat.administrators`
  o descarga de fichero). `Preparar ID Audio (*)` leía `$json.message_id`
  (no existe ahí, vive en `$json.result.message_id`) — por eso
  `ultimo_audio_msg_id` nunca se llegó a escribir, en ningún punto de envío,
  de ningún equipo. No era un problema de rescate/repetir en particular, los
  afecta a los 6 puntos de envío por igual.
  Corregido `$json.message_id` → `$json.result.message_id` en los 3 nodos
  `Preparar ID Audio (*)` de cada workflow. Backup pre-fix en
  `backup/backup_{vn3nwqbxR5Ur6Zze,tlFKrYHhqhHnvT2y}_<TS>_pre_fix_message_id.json`.
  Desplegado vía API, HTTP 200 en ambos, verificado por GET. Pendiente: que
  el usuario vuelva a probar.
- 2026-08-11 23:1x — **Confirmado por el usuario: funciona.** Borrado de
  audio anterior operativo en Salamanca (probado con /repetir y /rescate);
  misma implementación en Aranda, pendiente de que se pruebe allí pero es
  el mismo código ya verificado. Cierra el bug de autoplay-chaining de
  Telegram reportado hoy.
