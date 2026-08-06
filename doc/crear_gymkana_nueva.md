# Cómo crear una gymkana nueva

Guía paso a paso para montar una gymkana nueva sobre esta misma plataforma
(n8n + Firestore), a partir de un fichero de definición YAML en
[`content/`](../content/). Usa como ejemplo real
[`content/el_testimonio_de_piedra_salamanca.yml`](../content/el_testimonio_de_piedra_salamanca.yml),
pero los pasos son los mismos para cualquier gymkana nueva.

Antes de empezar, conviene tener claro qué automatiza esto y qué no:

- **Se automatiza**: todos los documentos de Firestore (config, estaciones,
  contador de reparto) y el clonado del workflow de n8n con las rutas ya
  apuntando a la gymkana nueva.
- **No se automatiza** (Telegram no ofrece una API para esto): crear el
  bot, darlo de alta como credencial en n8n, asignarla en los nodos, y
  activar el workflow. Son los pasos 2 y 5 de esta guía.

## 1. Prepara y valida el fichero de definición

El fichero debe vivir en [`content/`](../content/) y seguir el formato que
espera `provision_gymkana.py` — ver
[`provisioning/README.md`](../provisioning/README.md) para el detalle
completo del esquema (`id`, `nombre`, parámetros de juego opcionales,
`fragmentos`, `estaciones`, `estacion_final`).

Antes de aprovisionar, revisa a mano lo que el script **no** puede
comprobar por ti:

- Las coordenadas (`lat`/`lon`) y que los detalles de cada acertijo sean
  visibles y correctos sobre el terreno.
- Horarios de apertura de cualquier lugar que lo requiera (jardines,
  edificios con horario).
- `tolerancia_metros`: si es más estricto que el valor por defecto (50),
  confirma que el GPS de esos puntos concretos es lo bastante preciso.
- Que las imágenes (`imagen_url`, `imagen_final_url`) carguen. Si están en
  Firebase Storage, cada una necesita su propio token de descarga (ver
  [`README.md`](../README.md) de la raíz sobre cómo listarlas).

Valida sin escribir nada en ningún sitio:

```bash
cd provisioning
python3 provision_gymkana.py ../content/el_testimonio_de_piedra_salamanca.yml --dry-run
```

Si hay errores de esquema (estaciones sin campos obligatorios, `orden` con
huecos, número de `fragmentos` que no coincide con el de estaciones...),
el script los lista todos de una vez.

## 2. Crea el bot de Telegram

1. Habla con [@BotFather](https://t.me/BotFather) en Telegram.
2. `/newbot` → dale un nombre y un username (debe terminar en `bot`).
3. Guarda el **token** que te devuelve (`123456:ABC-...`) — hace falta en
   el paso 5.

## 3. Chat_id del organizador (`admin_chat_id`)

Si ya tienes `secrets/admin_chat_id` de una gymkana anterior con tu propio
chat_id de Telegram, no hace falta tocar nada: `provision_gymkana.py` lo
reutiliza automáticamente en cualquier gymkana cuyo YAML no traiga
`admin_chat_id` explícito. Si es la primera vez, consigue tu chat_id
hablando con [@userinfobot](https://t.me/userinfobot) y guárdalo en ese
fichero (una línea, sin comillas).

## 4. Aprovisiona

Desde `provisioning/`:

```bash
# IP del contenedor de n8n en la red de Docker
docker inspect gymkana_n8n --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'

# Aprovisiona de verdad: Firestore + clona el workflow de n8n
python3 provision_gymkana.py ../content/el_testimonio_de_piedra_salamanca.yml --n8n-url http://<IP>:5678
```

Esto crea:

- `gymkanas/<id>` y todo lo que cuelga de ahí en Firestore (config,
  `config/contador_inicio`, `estaciones/1..N`).
- Un workflow nuevo en n8n, **"Gymkana - 02 Bot principal &lt;nombre&gt;"**,
  clonado del de "El Linaje Olvidado" con las rutas de Firestore ya
  apuntando a la gymkana nueva — pero **inactivo**.

Si algo sale mal a mitad de camino y quieres repetir, añade `--force` para
sobrescribir lo que ya se haya escrito en Firestore.

## 5. Conecta el bot nuevo en n8n

1. Entra en la interfaz de n8n.
2. **Credentials → Add credential → Telegram API** → pega el token del
   paso 2.
3. Abre el workflow clonado en el paso 4.
4. En **cada** nodo de Telegram del workflow (el Trigger y los ~11 nodos
   de envío: mensajes, fotos, cápsulas, guía histórica, diploma, panel
   admin...), cambia la credencial a la nueva.
5. **Activa** el workflow.

## 6. Prueba

Desde el bot nuevo en Telegram:

1. `/start` → nombre del equipo → `/move 0` para confirmar que arranca en
   su enclave/testimonio de inicio.
2. Resuelve (o usa `/rescate`) la primera estación y comprueba que el
   mensaje de "próximo enclave" llega bien.
3. `/admin` desde tu propia cuenta para confirmar el panel de organizador
   (y que **no** responde desde otra cuenta).
4. Si quieres verlo completo, termina la gymkana (o usa `/move 9` +
   responder) y comprueba que llegan el resumen final, la guía histórica
   (si la has puesto) y el diploma.

## 7. Opcional: versionar el workflow nuevo

Esta gymkana vive en un workflow de n8n **distinto** al de "El Linaje
Olvidado" (`spt1kZxCOE9LCBbz`), así que aprovisionarla no toca el
`workflow.json` de la raíz del repo. Si quieres tener también este
workflow nuevo versionado en git con su propio histórico de backups
(mismo patrón que el de "El Linaje Olvidado"), pide que se añada
explícitamente — no se hace automáticamente al aprovisionar.

## Herramientas relacionadas

- [`provisioning/provision_gymkana.py`](../provisioning/provision_gymkana.py) — YAML → Firestore + n8n (lo que usa esta guía).
- [`provisioning/export_gymkana.py`](../provisioning/export_gymkana.py) — el inverso: Firestore → YAML, para volcar una gymkana ya desplegada (copia de seguridad, o punto de partida para clonarla).
- [`provisioning/README.md`](../provisioning/README.md) — documentación completa de ambos scripts y del formato del YAML.
