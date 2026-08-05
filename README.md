# El Linaje Olvidado — Gymkana en Telegram

Bot de Telegram que guía una gymkana histórica por Santillana del Mar (Cantabria), construido como un workflow de [n8n](https://n8n.io/) con persistencia en Firestore. Cada equipo empieza en un enclave distinto (1-8), repartido por turnos (round-robin: 1er equipo→enclave 1, 2º→enclave 2...) para evitar que todos vayan en procesión; resuelven los 8 acertijos en su propio orden, van reconstruyendo unas coordenadas fragmento a fragmento (por paso, no por estación física), y todos terminan en el mismo enclave secreto (estación 9).

Documentación técnica completa (arquitectura, comandos, esquema de datos, código de los nodos clave): ver [`documentacion_gymkana.html`](./documentacion_gymkana.html) — ábrelo en cualquier navegador, incluye un diagrama interactivo del workflow.

## Estructura del proyecto

```
.
├── docker-compose.yml              # Despliegue del contenedor n8n
├── workflow.json                   # Export ACTUAL del workflow de n8n (estado en producción)
├── documentacion_gymkana.html      # Documentación técnica interactiva (autocontenida)
├── El_Linaje_Olvidado_Guia_Historica.pdf  # Guía histórica que el bot entrega al terminar la gymkana
├── test_n8n_api.sh                 # Script de prueba de la API REST de n8n
├── backup/                         # Snapshots históricos del workflow y exports de Firestore
├── secrets/                        # Credenciales (NO versionado, ver .gitignore)
├── n8n_data/                       # Datos internos de n8n (NO versionado, ver .gitignore)
└── .env                            # Variables de entorno (NO versionado, ver .gitignore)
```

### `workflow.json`

Export completo y actual del workflow "Gymkana - 02 Bot principal El Linaje Olvidado" tal y como está desplegado en n8n ahora mismo (36 nodos): toda la lógica del bot (comandos, estados, entrega de mensajes/fotos/documentos). Para actualizarlo tras un cambio en el editor de n8n:

```bash
API_KEY="$(cat secrets/n8n_api_key)"
CONTAINER_IP="$(docker inspect gymkana_n8n --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')"
curl -sS -H "X-N8N-API-KEY: $API_KEY" "http://${CONTAINER_IP}:5678/api/v1/workflows/spt1kZxCOE9LCBbz" -o workflow.json
```

### `backup/`

Copias del workflow de n8n (`backup_spt1kZxCOE9LCBbz_<fecha>_<hora>_pre_<cambio>.json`) tomadas automáticamente antes de cada cambio relevante, a modo de historial/checkpoints — el nombre indica qué cambio se iba a aplicar justo después de esa copia. También incluye exports puntuales de la colección `estaciones` de Firestore (`estaciones_export.json`, `estaciones_firestore_backup_*.json`).

### Archivos no versionados (`.gitignore`)

- **`secrets/`** — credenciales de la cuenta de servicio de Firebase (`firebase-service-account.json`) y la API key de administración de n8n (`n8n_api_key`).
- **`.env`** — variables de entorno del despliegue (dominio, timezone, clave de cifrado de n8n...).
- **`n8n_data/`** — volumen de datos de n8n: workflows activos, credenciales cifradas, historial de ejecuciones.

Estos tres nunca deben subirse al repositorio.

## Infraestructura

- Contenedor Docker `gymkana_n8n` (imagen oficial `n8nio/n8n`), definido en `docker-compose.yml`.
- Proyecto Firebase `gymkana-linaje-olvidado` (Firestore nativo) para persistir equipos (`equipos`) y contenido del juego (`estaciones`).
- Bot de Telegram como interfaz única para los jugadores (sin app propia).

Detalles de arquitectura, flujos, comandos (públicos y de depuración) y esquema completo de los datos en Firestore: ver [`documentacion_gymkana.html`](./documentacion_gymkana.html).
