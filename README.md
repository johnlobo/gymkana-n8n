# Gymkana Framework — bot de gymkanas urbanas en Telegram

Framework para montar gymkanas urbanas guiadas por un bot de Telegram, construido sobre [n8n](https://n8n.io/) (lógica del juego) y Firestore (persistencia), pensado desde el diseño para ser **multi-tenant**: cada gymkana es un conjunto de documentos independiente bajo `gymkanas/<id>/...` en Firestore, con su propio workflow de n8n clonado y su propio bot de Telegram.

## Cómo funciona una gymkana

Cada equipo empieza en un enclave (o "estación", "testimonio"... el término es configurable por gymkana) distinto, repartido por turnos (round-robin) para evitar que todos vayan en procesión. Resuelven los retos en su propio orden, van reconstruyendo una pista final fragmento a fragmento (por paso, no por estación física), y todos terminan en el mismo punto secreto.

Los parámetros del juego (tolerancia GPS, pesos de penalización por pista/mapa/rescate, nº de pistas, nº de estaciones, terminología) son configuración de cada gymkana en Firestore, no números fijos en el código — es lo que permite que el mismo workflow sirva para gymkanas de contenido y ambientación completamente distintos.

Otras piezas del juego, iguales para cualquier gymkana montada con este framework:

- Comando oculto `/admin` (no aparece en `/ayuda`), restringido al chat_id del organizador de esa gymkana, con un resumen en vivo de todos los equipos: progreso, tiempo, pistas/mapas/rescates usados y penalización.
- Cada partida completada queda registrada (append-only, sobrevive a un `/reboot`) en `gymkanas/<id>/eventos`, con tiempos, pistas/mapas/rescates usados, penalización y rango obtenido — para análisis posterior al evento, separado del estado en vivo de `equipos`.
- `/pausa`/`/reanudar` para detener y reanudar el propio cronómetro de un equipo; mientras están en pausa, el resto de comandos de juego quedan bloqueados y el tiempo en pausa no cuenta para el resultado final.
- Al terminar, cada equipo recibe un certificado personalizado (imagen tipo diploma con el nombre del equipo, el tiempo oficial y el rango obtenido), generado al vuelo con GraphicsMagick — no depende de ningún servicio externo. Se reenvía también cada vez que el equipo escribe `/repetir` tras haber terminado.

## Montar una gymkana nueva

Ver [`doc/crear_gymkana_nueva.md`](./doc/crear_gymkana_nueva.md) para la guía paso a paso completa, incluidos los pasos manuales que no se pueden automatizar (crear el bot en Telegram, etc.).

En resumen: el contenido de una gymkana (estaciones, acertijos, pistas, imágenes) se define en un fichero YAML dentro de [`content/`](./content/), y [`provisioning/provision_gymkana.py`](./provisioning/README.md) crea todos los documentos en Firestore y clona el workflow de n8n apuntando a la gymkana nueva. `provisioning/export_gymkana.py` hace el camino inverso, para volcar a YAML una gymkana ya desplegada.

Gymkanas ya definidas en [`content/`](./content/), a modo de ejemplo:

- `linaje_olvidado.yaml` — "El Linaje Olvidado" (Santillana del Mar), la gymkana de referencia sobre la que se construyó el workflow.
- `el_testimonio_de_piedra_salamanca.yml` — "El Testimonio de Piedra" (Salamanca).

## Documentación técnica

Arquitectura del workflow, comandos, esquema completo de los datos en Firestore y código de los nodos clave: ver [`documentacion_gymkana.html`](./documentacion_gymkana.html) — ábrelo en cualquier navegador, incluye un diagrama interactivo. Documenta el workflow **plantilla**, común a todas las gymkanas montadas con este framework.

El mismo contenido, en Markdown dentro de [`doc/`](./doc/) (sin interactividad, pero legible directamente en GitHub):

- [`doc/diagrama_arquitectura.md`](./doc/diagrama_arquitectura.md) — diagrama de arquitectura (imagen estática) y lista de flujos.
- [`doc/comandos.md`](./doc/comandos.md) — comandos públicos, de depuración y el panel de organizador.
- [`doc/datos_firestore.md`](./doc/datos_firestore.md) — esquema completo de `gymkanas/<id>/...`.
- [`doc/codigo_nodos.md`](./doc/codigo_nodos.md) — código de los nodos Code clave del workflow.
- [`doc/infraestructura.md`](./doc/infraestructura.md) — despliegue, credenciales, `docker-compose.yml` y el detalle de `provisioning/`.

## Estructura del proyecto

```
.
├── docker-compose.yml              # Despliegue del contenedor n8n
├── workflow.json                   # Export del workflow plantilla de n8n (estado en producción)
├── documentacion_gymkana.html      # Documentación técnica interactiva (autocontenida)
├── El_Linaje_Olvidado_Guia_Historica.pdf  # Guía histórica de la gymkana de referencia
├── test_n8n_api.sh                 # Script de prueba de la API REST de n8n
├── provisioning/                   # Scripts para montar/exportar gymkanas
├── content/                        # Definiciones YAML de cada gymkana
├── doc/                            # Guías paso a paso (p.ej. crear una gymkana nueva)
├── backup/                         # Snapshots históricos del workflow y exports de Firestore
├── secrets/                        # Credenciales (NO versionado, ver .gitignore)
├── n8n_data/                       # Datos internos de n8n (NO versionado, ver .gitignore)
└── .env                            # Variables de entorno (NO versionado, ver .gitignore)
```

### `workflow.json`

Export del workflow de n8n que sirve de **plantilla** para todas las gymkanas: `provisioning/provision_gymkana.py` lo clona para cada gymkana nueva, reapuntando solo las rutas de Firestore y regenerando los `webhookId`. Ahora mismo está desplegado en producción como el bot de "El Linaje Olvidado" (53 nodos: comandos, estados, entrega de mensajes/fotos/documentos/diplomas). Para actualizarlo tras un cambio en el editor de n8n:

```bash
API_KEY="$(cat secrets/n8n_api_key)"
CONTAINER_IP="$(docker inspect gymkana_n8n --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')"
curl -sS -H "X-N8N-API-KEY: $API_KEY" "http://${CONTAINER_IP}:5678/api/v1/workflows/spt1kZxCOE9LCBbz" -o workflow.json
```

### `backup/`

Copias del workflow de n8n (`backup_spt1kZxCOE9LCBbz_<fecha>_<hora>_pre_<cambio>.json`) tomadas automáticamente antes de cada cambio relevante, a modo de historial/checkpoints — el nombre indica qué cambio se iba a aplicar justo después de esa copia. También incluye exports puntuales de la colección `estaciones` de Firestore (`estaciones_export.json`, `estaciones_firestore_backup_*.json`).

### Archivos no versionados (`.gitignore`)

- **`secrets/`** — credenciales de la cuenta de servicio de Firebase (`firebase-service-account.json`), la API key de administración de n8n (`n8n_api_key`), y el chat_id de organizador por defecto (`admin_chat_id`) usado por `provision_gymkana.py`.
- **`.env`** — variables de entorno del despliegue (dominio, timezone, clave de cifrado de n8n...).
- **`n8n_data/`** — volumen de datos de n8n: workflows activos, credenciales cifradas, historial de ejecuciones.

Estos nunca deben subirse al repositorio.

## Infraestructura

- Contenedor Docker `gymkana_n8n` (imagen oficial `n8nio/n8n`), definido en `docker-compose.yml`. Cada gymkana es un workflow adicional dentro de esta misma instancia de n8n.
- Proyecto Firebase `gymkana-linaje-olvidado` (Firestore nativo), compartido por todas las gymkanas. Estructura multi-tenant: cada una vive bajo `gymkanas/<id>/...` (subcolecciones `estaciones`, `equipos`, `updates_telegram`, `config`, `eventos`), como documentos hermanos dentro de `gymkanas/`.
- Un bot de Telegram por gymkana, como interfaz única para los jugadores (sin app propia).

Detalles de arquitectura, flujos, comandos (públicos y de depuración) y esquema completo de los datos en Firestore: ver [`documentacion_gymkana.html`](./documentacion_gymkana.html).
