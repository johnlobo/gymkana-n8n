# Aprovisionamiento de gymkanas nuevas (Fase 2)

Dos scripts simétricos para trabajar con el contenido de una gymkana como
un fichero YAML en vez de a mano en Firestore:

- **`provision_gymkana.py`**: YAML → Firestore + n8n. Monta una gymkana
  nueva (o la sobrescribe con `--force`) a partir de una definición.
- **`export_gymkana.py`**: Firestore → YAML. Vuelca una gymkana ya
  desplegada al mismo formato — para tener una copia de seguridad legible,
  o como punto de partida para clonarla.

**Lo que `provision_gymkana.py` NO automatiza** (requiere pasos manuales,
ver el final): crear el bot de Telegram en @BotFather, dar de alta su
token como credencial en n8n, y activar el workflow — Telegram no tiene
una API para crear bots.

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

Si la definición no trae `admin_chat_id` (o lo trae vacío), se usa como
respaldo el contenido de `../secrets/admin_chat_id` (gitignoreado) —
así puedes tener tu propio chat_id de organizador sin escribirlo en
ningún YAML que pueda acabar en un repositorio público. Cámbialo con
`--admin-chat-id-file`. Si la definición SÍ trae `admin_chat_id`, ese
valor gana siempre (útil para aprovisionar una gymkana de otra persona).

Si solo quieres tocar Firestore (por ejemplo, para iterar en el contenido de
las estaciones antes de tener el bot listo), usa `--skip-n8n`.

Si la gymkana ya existe en Firestore, el script se niega a sobrescribirla
salvo que pases `--force`.

## Exportar una gymkana existente

```bash
python3 export_gymkana.py linaje-olvidado -o ../content/linaje_olvidado.yaml
```

Lee `gymkanas/<id>` y sus `estaciones` en Firestore y escribe el mismo
formato YAML que espera `provision_gymkana.py` (`fragmentos` se
reconstruye a partir de los `pasoN_fragmento` de la primera estación; los
campos legacy que ya no usa el código, como `siguiente`/`fragmentos_previos`,
no se exportan). No exporta `admin_chat_id` salvo que pases
`--include-admin-chat-id` — por defecto se deja fuera del fichero, igual
que hace `provision_gymkana.py` al leerlo (ver más abajo). El fichero
generado se valida con la misma lógica que usa `provision_gymkana.py` al
cargarlo, así que un export incompleto falla en el momento, no la próxima
vez que alguien intente reaprovisionar.

## El fichero de definición

Ver [`ejemplo_gymkana.yaml`](./ejemplo_gymkana.yaml) (contenido ficticio,
comentado) o [`../content/linaje_olvidado.yaml`](../content/linaje_olvidado.yaml)
(exportación completa y real de "El Linaje Olvidado", las 8 estaciones + la
final — sirve para volver a aprovisionar esta misma gymkana desde cero). En
resumen:

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

`../content/linaje_olvidado.yaml` se validó por separado, aprovisionando
con `--skip-n8n` bajo un id temporal (`linaje-olvidado-test`) y comparando
campo a campo cada estación contra los datos reales en Firestore — 0
diferencias. Los datos de esa prueba también se borraron después.

**Nota:** `../content/linaje_olvidado.yaml` deja `admin_chat_id` vacío a
propósito (el original tenía un chat_id de Telegram real) — al
aprovisionar, el script lo rellena automáticamente desde
`../secrets/admin_chat_id` si ese fichero existe.

`export_gymkana.py` se probó con un ciclo completo: exportó
`linaje-olvidado` real, se reaprovisionó ese YAML bajo un id temporal
(`--skip-n8n`), se volvió a exportar ese id temporal, y el resultado fue
byte a byte idéntico al primer export (aparte del `id`) — confirma que
`Firestore → YAML → Firestore → YAML` no pierde ni altera nada. Los datos
de esa prueba se borraron después.

`firestore_lib.py` es un cliente Firestore mínimo (autenticación con
cuenta de servicio + conversión de tipos) compartido por ambos scripts,
para no duplicar esa lógica.
