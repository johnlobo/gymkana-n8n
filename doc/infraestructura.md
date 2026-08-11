# Infraestructura

## Despliegue

- Contenedor Docker `gymkana_n8n` (imagen oficial `n8nio/n8n`), definido en `docker-compose.yml`. Cada gymkana es un workflow adicional dentro de esta misma instancia de n8n.
- Credenciales de Google/Firebase montadas como secreto de solo lectura: `secrets/firebase-service-account.json` → `/run/secrets/firebase-service-account.json` (variable `GOOGLE_APPLICATION_CREDENTIALS`).
- API key de administración de n8n en `secrets/n8n_api_key` (usada para gestionar los workflows vía la API REST de n8n, no por el propio bot).
- Antes de desplegar cualquier cambio a `Procesar estación y comandos` (el nodo Code con la lógica principal del bot, el de mayor riesgo del workflow): `node provisioning/test_procesar_estacion.js` contra el código nuevo. Un `} else {` duplicado rompió TODOS los comandos en producción el 2026-08-11 durante horas hasta que se detectó; ese script comprueba sintaxis (`node --check`) y ejecuta el código contra una docena de escenarios (move, repetir, rescate, respuesta correcta/incorrecta, estado, pista, mapa, pausa, finalización) antes de tocar producción.
- Datos de n8n (workflows, credenciales cifradas, ejecuciones) persistidos en el volumen `./n8n_data`.
- Expuesto detrás de un reverse proxy externo (red Docker `proxy-network`); n8n habla HTTPS con `N8N_PROXY_HOPS=1`.
- **Importante:** `EXECUTIONS_DATA_SAVE_ON_SUCCESS: none` — las ejecuciones que terminan bien **no** se guardan (solo `EXECUTIONS_DATA_SAVE_ON_ERROR: all`), lo que limita la trazabilidad histórica del bot a los fallos. Se activa temporalmente a `all` cuando hace falta depurar un problema puntual, y se revierte después.

## Proyecto Firebase / credenciales

- Proyecto Firebase: `gymkana-linaje-olvidado` (Firestore en modo nativo), **compartido por todas las gymkanas**. Estructura multi-tenant: cada una vive bajo `gymkanas/<id>/...`, como documentos hermanos dentro de `gymkanas/`.
- Los nodos Firestore de n8n usan `authentication: serviceAccount` con la credencial n8n *"Google Service Account account"*.
- Cada gymkana tiene su propio bot de Telegram y su propia credencial *Telegram API* en n8n, usada tanto por su `Telegram Trigger` como por todos sus nodos `sendMessage`/`sendPhoto`/`sendDocument`.
- Imágenes alojadas externamente: Wikimedia Commons, Firebase Storage (`firebasestorage.googleapis.com/…?alt=media&token=…`, organizadas en una carpeta por gymkana, p.ej. `Santillana/`, `Salamanca/`) y otras webs — nunca subidas al propio proyecto n8n.

## `docker-compose.yml`

```yaml
services:
  n8n:
    image: docker.n8n.io/n8nio/n8n:${N8N_VERSION}
    container_name: gymkana_n8n
    restart: unless-stopped
    environment:
      NODE_ENV: production
      N8N_HOST: ${N8N_EDITOR_DOMAIN}
      N8N_PORT: 5678
      N8N_PROTOCOL: https
      N8N_EDITOR_BASE_URL: https://${N8N_EDITOR_DOMAIN}/
      N8N_WEBHOOK_URL: ${WEBHOOK_URL}
      N8N_PROXY_HOPS: 1
      N8N_ENCRYPTION_KEY: ${N8N_ENCRYPTION_KEY}
      N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS: "true"
      GENERIC_TIMEZONE: ${GENERIC_TIMEZONE}
      TZ: ${TZ}
      GOOGLE_APPLICATION_CREDENTIALS: /run/secrets/firebase-service-account.json
      EXECUTIONS_DATA_SAVE_ON_SUCCESS: none
      EXECUTIONS_DATA_SAVE_ON_ERROR: all
      EXECUTIONS_DATA_SAVE_MANUAL_EXECUTIONS: "true"
      EXECUTIONS_DATA_PRUNE: "true"
      EXECUTIONS_DATA_MAX_AGE: 168
      N8N_DIAGNOSTICS_ENABLED: "false"
      N8N_PERSONALIZATION_ENABLED: "false"
    volumes:
      - ./n8n_data:/home/node/.n8n
      - ./secrets/firebase-service-account.json:/run/secrets/firebase-service-account.json:ro
    networks:
      - proxy-network


networks:
  proxy-network:
    external: true
```

## Aprovisionamiento de gymkanas nuevas — `provisioning/`

Dos scripts Python simétricos para trabajar con el contenido de una gymkana como un fichero YAML en vez de a mano en Firestore, más un cliente Firestore mínimo compartido entre ambos. Ver [`provisioning/README.md`](../provisioning/README.md) y la guía paso a paso en [`crear_gymkana_nueva.md`](./crear_gymkana_nueva.md).

- **`provision_gymkana.py <definicion.yaml>`** — YAML → Firestore + n8n. Crea `gymkanas/<id>` (config), `config/contador_inicio` y todas las `estaciones` (copiando `fragmentos` a `paso1_fragmento`‥`pasoN_fragmento` de cada una, y autogenerando `secuencia_codice` si no se indica). Si se le pasa `--n8n-url`, además descarga el workflow plantilla, sustituye las rutas `gymkanas/<id-plantilla>/…` y el `documentId` de "Cargar gymkana" por el id nuevo (sin tocar `projectId`, el proyecto Firebase compartido), regenera el `webhookId` de cada nodo de Telegram, y lo crea como workflow nuevo **inactivo** vía la API de n8n. Se niega a sobrescribir una gymkana existente salvo `--force`; `--skip-n8n` limita todo a Firestore; `--dry-run` valida sin escribir nada.
- **`export_gymkana.py <id>`** — el inverso: Firestore → YAML. Reconstruye `fragmentos` a partir de los `pasoN_fragmento` de la primera estación, y escribe exactamente el mismo formato que espera `provision_gymkana.py` (validado con su misma función `validar_definicion` antes de guardar). No exporta `admin_chat_id` salvo `--include-admin-chat-id`.
- **`admin_chat_id`**: si la definición no lo trae, `provision_gymkana.py` lo rellena solo desde `secrets/admin_chat_id` (gitignoreado) — así no hace falta escribir un chat_id de Telegram real en un YAML que puede acabar en un repositorio público. Un valor explícito en el YAML siempre gana.
- **`firestore_lib.py`** — autenticación por cuenta de servicio (JWT → OAuth2, sin gcloud ni las librerías oficiales de Google) y conversión de tipos con la API REST de Firestore, compartido por ambos scripts.
- Lo único que **no** automatiza `provision_gymkana.py`: crear el bot en Telegram vía @BotFather, dar de alta su token como credencial en n8n, reasignar esa credencial en los nodos de Telegram del workflow clonado, y activarlo — Telegram no ofrece una API para crear bots.

## Notas / inferencias

- Esta documentación se generó inspeccionando directamente el workflow en ejecución vía la API REST de n8n y el contenido real de Firestore — no a partir de un repositorio de código fuente tradicional para la lógica del bot (sí lo es, en cambio, para los scripts de `provisioning/`).
- Las variables de entorno `N8N_VERSION`, `N8N_EDITOR_DOMAIN` y `N8N_ENCRYPTION_KEY` se referencian en `docker-compose.yml` pero no aparecen en el `.env` visible del proyecto — *probablemente* se inyectan por otra vía (entorno del host, gestor de secretos). Marcado como inferencia.
- Los campos `estaciones.siguiente` y `estaciones.fragmentos_previos` existen todavía en los documentos de Firestore de gymkanas antiguas, pero ninguna rama del código actual los lee ni los escribe: son campos heredados de una versión anterior del juego (antes de que "Construir mensaje siguiente" calculara el próximo enclave dinámicamente). `export_gymkana.py` no los exporta.
