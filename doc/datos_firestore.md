# Esquema de datos en Firestore

Estructura multi-tenant: todo vive bajo `gymkanas/<id>/...`, con un documento de configuración en la raíz de cada gymkana y cuatro subcolecciones: `estaciones`, `equipos`, `updates_telegram`, `config`, más `eventos` (log de partidas completadas, Fase 3).

## Documento `gymkanas/<id>` (config)

| Campo | Tipo | Descripción |
|---|---|---|
| id | string | = "linaje-olvidado" en este workflow. Cada gymkana clonada tendría el suyo propio. |
| nombre | string | Nombre mostrado de la gymkana ("El Linaje Olvidado"); se usa p.ej. en el mensaje de bienvenida tras registrar el nombre del equipo. |
| tolerancia_metros | number | Radio de tolerancia GPS para /destino y la llegada a un enclave. Fase 0: antes era 50 fijo en el código. |
| peso_pista | number | Minutos de penalización por cada pista pedida (1 por defecto). Sustituye al antiguo penalizacion_minutos plano. |
| peso_mapa | number | Minutos de penalización por pedir el mapa de un enclave (3 por defecto). |
| peso_rescate | number | Minutos de penalización por cada uso de /rescate — revelar o resolver (5 por defecto). |
| max_pistas | number | Nº máximo de pistas por enclave antes de sugerir /rescate. Fase 0: antes era 3 fijo en el código. |
| num_estaciones_regulares | number | Nº de enclaves "normales" antes del enclave secreto (8 en El Linaje Olvidado). Determina la rotación por paso y en qué estación se dispara el cierre final. |
| admin_chat_id | string | chat_id de Telegram del organizador. Único chat autorizado a usar el comando oculto /admin (Fase 3: panel de organizador). |
| termino_enclave | string | Palabra usada para referirse a una estación/parada de esta gymkana ("Enclave" por defecto). Sustituye los literales "Enclave"/"ENCLAVE" que antes estaban fijos en el código de Decidir acción, Procesar estación y comandos y Construir mensaje siguiente (Fase 3: terminología parametrizada por gymkana). |

## Colección `gymkanas/<id>/equipos`

| Campo | Tipo | Descripción |
|---|---|---|
| id | string | = chat_id de Telegram, en texto. Clave de upsert (updateKey). |
| chat_id | string/number | id del chat de Telegram. |
| nombre | string | Nombre del equipo (máx. 80 caracteres). |
| estado | string | pendiente_nombre \| esperando_inicio \| en_juego \| finalizado. |
| orden_inicio | number | Enclave físico donde empieza ESTE equipo, asignado por round-robin (contador gymkanas/linaje-olvidado/config/contador_inicio) al registrar el nombre. Junto con paso determina estacion_actual. |
| paso | number | Avance del equipo en su propia ruta (1-8; 9 = ya en el enclave secreto). Determina qué fragmento del códice toca (paso{N}_fragmento), no la estación física. |
| estacion_actual | number | Enclave FÍSICO en el que está el equipo ahora mismo, calculado como ((orden_inicio-1+paso-1) % num_estaciones_regulares)+1, o el nº de la estación final si paso > num_estaciones_regulares. Ya no es una simple secuencia 1,2,3… |
| inicio | ISO datetime | Momento en que arrancó el cronómetro (llegada confirmada a SU enclave de inicio). |
| fin | ISO datetime | Momento en que se completó la gymkana. |
| pistas_usadas | number | Contador total de pistas pedidas. |
| mapas_usados | number | Contador de mapas pedidos (solo cuenta la primera vez por enclave). |
| penalizacion_minutos | number | Snapshot de la penalización ponderada en el momento de finalizar (pistas_usadas*peso_pista + mapas_usados*peso_mapa + rescates_usados*peso_rescate). Ya NO se acumula turno a turno: se recalcula desde los contadores cada vez que hace falta (p.ej. en /estado). |
| pista_actual | number | Nº de pistas ya mostradas en el enclave actual (0-3); se resetea al avanzar. |
| mapa_estaciones | string | Lista de nº de enclave separados por coma en los que ya se pidió mapa (evita re-penalizar). |
| intentos | number | Nº de respuestas incorrectas acumuladas. |
| acertijo_visto | boolean | Si el acertijo del enclave actual ya se le mostró al equipo. Determina el comportamiento de /rescate y de la llegada por GPS. |
| actualizado_en | ISO datetime | Marca de tiempo de la última escritura. |
| response | string | Último texto de respuesta enviado (se guarda tal cual, con fines de depuración/auditoría). |
| changed | boolean | Solo se escribe en la rama 'Guardar progreso'; refleja si ese turno modificó el equipo. |
| rescates_usados | number | Contador de usos de /rescate. |
| mensaje_final | string | Mensaje de cierre completo, guardado al finalizar para poder repetirlo con /repetir. |
| tiempo_bruto_segundos | number | Duración real de la partida (sin penalizaciones). |
| tiempo_oficial_segundos | number | Duración + penalizaciones acumuladas. |
| rango_equipo | string | Texto del rango obtenido (Leyenda de la Villa / Maestros Cronistas / Guardianes del Códice / Exploradores Pacientes). |
| imagen_final | string (URL) | Imagen enviada en el mensaje de cierre; se reutiliza al repetir el resumen. |
| documento_final | string (URL) | URL del PDF de la guía histórica; se reutiliza al repetir el resumen (sendDocument). |
| ultimo_audio_msg_id | string | `message_id` de Telegram del último audio (cápsula/acertijo/resumen) enviado a este equipo. Ya en el workflow plantilla (ver [`audio_locuciones.md`](./audio_locuciones.md)), pero solo se llega a escribir si la gymkana tiene audios generados (si no, la rama de audio queda inerte y el campo nunca se crea). Se usa para borrar ese mensaje antes de enviar el siguiente audio y así evitar que Telegram encadene la reproducción. |
| ultimo_texto | string | Texto de la última cápsula o acertijo mostrado (lo que fuera lo último, no necesariamente de la estación actual). Usado por `/repetir` para reenviar literalmente lo último, en vez de reconstruir contenido a partir de `estacion_actual` — ver [`audio_locuciones.md`](./audio_locuciones.md). |
| ultima_imagen_url | string (URL) | Imagen asociada a `ultimo_texto`. |
| ultimo_audio_url | string (URL) | Audio (cápsula o acertijo) asociado a `ultimo_texto`. |

### Estados posibles de `equipos.estado`

`pendiente_nombre` · `esperando_inicio` · `en_juego` · `finalizado`

*(Inferido leyendo las comparaciones `team.estado === '...'` en el código; no hay un enum declarado explícitamente en Firestore — es Firestore nativo, sin esquema forzado.)*


## Colección `gymkanas/<id>/estaciones`

| Campo | Tipo | Descripción |
|---|---|---|
| id | string | Igual al nombre del documento ("1".."9"). |
| orden | number | Posición del enclave (1-9); coincide con id. |
| nombre | string | Nombre mostrado del enclave. |
| lat / lon | number | Coordenadas GPS del punto exacto; usadas en el cálculo Haversine de /destino. |
| acertijo | string (Markdown) | Texto del "sello" / pregunta a resolver. |
| respuestas | string | Lista de respuestas válidas separadas por "\|" (se comparan ya normalizadas: sin tildes, minúsculas, sin puntuación). |
| pista1 / pista2 / pista3 | string | Las tres pistas progresivas del enclave. |
| paso1_fragmento … pasoN_fragmento | string | Los fragmentos del códice, indexados por PASO (no por estación): mismo valor duplicado en todas las estaciones. Como cada equipo empieza en un enclave distinto, el fragmento que se entrega depende del paso en que se resuelva cada enclave, no de qué estación física sea. |
| capsula | string (Markdown) | Texto narrativo ("Folio del Códice") + un párrafo de dato histórico real, mostrado al resolver o rescatar el enclave. |
| imagen_url | string (URL) | Foto mostrada al llegar/repetir/rescatar ese enclave. |
| mapa_url | string (URL) | Enlace de Google Maps mostrado por /mapa. |
| imagen_final_url | string (URL) — solo estación 9 | Foto distinta usada específicamente en el mensaje de cierre de la gymkana. |
| coordenadas_finales | string — solo estación 9 | Coordenadas ya formateadas ("43.389561N, -4.108084W") para el mensaje de cierre. |
| audio_url | string (URL) | Locución en audio (mp3) de la `capsula`, generada con Kokoro TTS. Campo soportado por el workflow plantilla, pero solo tiene valor real en gymkanas con audio ya generado (Salamanca, Aranda) — el resto (p.ej. Linaje Olvidado) no tienen ni el campo, y la rama de audio del workflow queda inerte hasta que se generen. Ver [`audio_locuciones.md`](./audio_locuciones.md). |
| acertijo_audio_url | string (URL) | Locución en audio (mp3) del `acertijo`. Mismo origen y limitaciones que `audio_url`. |

## Colección `gymkanas/<id>/updates_telegram`

| Campo | Tipo | Descripción |
|---|---|---|
| id | string | = update_id de Telegram. Clave de upsert. |
| update_id | number | Identificador de update de Telegram. |
| chat_id | number | Chat de origen del update. |
| procesado_en | ISO datetime | Marca de tiempo de cuándo se procesó. |
