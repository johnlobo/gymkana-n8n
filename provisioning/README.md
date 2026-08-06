# Aprovisionamiento de gymkanas nuevas (Fase 2)

Script para montar una gymkana nueva a partir de un fichero de definición
YAML, sin repetir a mano lo que se hizo para "El Linaje Olvidado": crea sus
documentos en Firestore (config + estaciones + contador de reparto) y clona
el workflow de n8n de una gymkana existente, apuntándolo a la nueva.

**Lo que NO automatiza** (requiere pasos manuales, ver el final): crear el
bot de Telegram en @BotFather, dar de alta su token como credencial en n8n,
y activar el workflow — Telegram no tiene una API para crear bots.

## Uso

```bash
pip3 install -r requirements.txt

# 1. Copia el ejemplo y edita el contenido
cp ejemplo_gymkana.yaml mi_gymkana.yaml

# 2. Valida sin escribir nada
python3 provision_gymkana.py mi_gymkana.yaml --dry-run

# 3. Averigua la IP del contenedor de n8n en la red de Docker
docker inspect gymkana_n8n --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'

# 4. Aprovisiona de verdad (Firestore + clona el workflow de n8n)
python3 provision_gymkana.py mi_gymkana.yaml --n8n-url http://<IP>:5678
```

Por defecto lee las credenciales desde `../secrets/n8n_api_key` y
`../secrets/firebase-service-account.json` (las mismas que usa el resto del
proyecto) y clona el workflow de "El Linaje Olvidado"
(`spt1kZxCOE9LCBbz`). Todo esto se puede cambiar con `--template-workflow-id`,
`--template-gymkana-id`, `--n8n-api-key-file`, `--firebase-key-file`.

Si solo quieres tocar Firestore (por ejemplo, para iterar en el contenido de
las estaciones antes de tener el bot listo), usa `--skip-n8n`.

Si la gymkana ya existe en Firestore, el script se niega a sobrescribirla
salvo que pases `--force`.

## El fichero de definición

Ver [`ejemplo_gymkana.yaml`](./ejemplo_gymkana.yaml), comentado. En resumen:

- **Config del juego**: `id`, `nombre`, y los parámetros opcionales
  (`tolerancia_metros`, `max_pistas`, `peso_pista`, `peso_mapa`,
  `peso_rescate`, `termino_enclave`, `admin_chat_id`) — si se omiten, se
  usan los mismos valores por defecto que tiene el código.
- **`fragmentos`**: un fragmento del códice por cada estación regular, en
  el orden en que se entregan (por paso, no por estación física — cada
  equipo empieza en una estación distinta por reparto round-robin, pero
  todos reconstruyen la misma secuencia). El script los copia
  automáticamente a **todas** las estaciones regulares como
  `paso1_fragmento`..`pasoN_fragmento`; no hace falta repetirlos a mano en
  cada estación.
- **`estaciones`**: la lista de estaciones regulares (`orden` 1..N, sin
  huecos ni repetidos). Cada una necesita `nombre`, `lat`/`lon`,
  `acertijo`, `respuestas` (separadas por `|`), `pistas` (lista, se
  convierten en `pista1`, `pista2`...), `capsula`, `imagen_url`,
  `mapa_url`.
- **`estacion_final`**: la estación secreta a la que llegan todos los
  equipos, con los mismos campos más `coordenadas_finales` y,
  opcionalmente, `imagen_final_url` (si se omite, reutiliza `imagen_url`),
  `secuencia_codice` (si se omite, se genera automáticamente a partir de
  `fragmentos`) y `guia_historica_url` (PDF opcional que se envía al
  terminar).

`num_estaciones_regulares` no se indica: se calcula solo, contando cuántas
`estaciones` hay en la lista.

## Qué hace exactamente con n8n

1. Descarga el workflow plantilla (`--template-workflow-id`).
2. En cada nodo, sustituye las rutas de colección `gymkanas/<id-plantilla>/...`
   y el `documentId` del nodo "Cargar gymkana" por el id de la gymkana
   nueva. **No toca** el campo `projectId` (`gymkana-linaje-olvidado`): es
   el proyecto de Firebase compartido por todas las gymkanas, no cambia.
3. Regenera el `webhookId` de todos los nodos de Telegram (cada uno trae el
   suyo), para que no choquen con los del workflow plantilla al activarse.
4. Crea el workflow nuevo en n8n vía API — **inactivo**, y con las
   credenciales de Telegram del workflow plantilla todavía puestas (no
   pasa nada mientras esté inactivo: n8n solo registra el webhook de un
   workflow activo).

## Pasos manuales pendientes tras ejecutar el script

1. Crear el bot con [@BotFather](https://t.me/BotFather) y guardar su token.
2. En n8n, crear una credencial *Telegram API* nueva con ese token.
3. En el workflow recién creado, reasignar esa credencial en **todos** los
   nodos de Telegram (el Trigger y los ~11 nodos de envío de mensajes,
   fotos y documentos).
4. Activar el workflow.

## Probado

El script se probó de extremo a extremo con `ejemplo_gymkana.yaml`:
Firestore quedó con la config, las 4 estaciones regulares y la estación
final correctamente pobladas (incluida la `secuencia_codice` autogenerada),
y el workflow clonado en n8n tenía las rutas de Firestore y el
`documentId` de "Cargar gymkana" apuntando a la gymkana nueva, con
`projectId` intacto y los `webhookId` regenerados. Los datos y el workflow
de prueba se borraron después de verificarlo.
