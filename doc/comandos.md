# Comandos del bot

Se aceptan con o sin barra inicial y sin distinguir mayúsculas/tildes (p.ej. `pista` y `/PISTA` son equivalentes) gracias a la normalización de texto en `Normalizar mensaje` / `Decidir acción`.

## Comandos públicos (listados en `/ayuda`)

| Comando | Dónde se procesa | Qué hace |
|---|---|---|
| /start | Decidir acción | Crea el equipo (si no existe) y pide el nombre. Si ya existe, avisa de que la partida sigue en curso. |
| (texto libre tras /start) | Decidir acción → Procesar estación y comandos | Se interpreta como el nombre del equipo; se le asigna un enclave de inicio ALEATORIO (1-8) y se envía su foto + nombre + mapa como punto de partida. |
| /ayuda | Decidir acción | Muestra la lista de comandos públicos (no incluye /move, /reboot ni /admin), con el término del enclave (gymkanaConfig.termino_enclave) y los pesos de penalización ya sustituidos en el texto. |
| /destino | Decidir acción → Procesar estación y comandos | Pide compartir ubicación real; con ubicación adjunta, calcula la distancia Haversine al enclave actual (tolerancia 50 m). |
| /pista | Procesar estación y comandos | Da la siguiente pista (máx. 3 por enclave; +peso_pista min cada una, 1 por defecto); pasadas las 3, sugiere /rescate o /mapa. |
| /mapa | Procesar estación y comandos | Envía station.mapa_url; la primera vez penaliza +peso_mapa min (3 por defecto) y cuenta como mapa usado. |
| /rescate | Procesar estación y comandos | Si el acertijo no se había mostrado aún: lo revela (sin fragmento). Si ya se había mostrado: da la respuesta, cobra el fragmento de ESE PASO y avanza al siguiente enclave de su ruta. Cada uso (revelar o resolver) suma +1 a rescates_usados, penalizado a +peso_rescate min (5 por defecto) en el cálculo final. |
| /repetir | Procesar estación y comandos (o Decidir acción si finalizado) | Repite el acertijo actual. Si el equipo ya terminó la gymkana, reenvía el resumen final guardado (con la guía histórica en PDF) en vez de un acertijo. |
| /estado | Decidir acción → Procesar estación y comandos | Resumen del progreso: paso actual (1-8) de SU ruta, tiempo transcurrido, fragmentos del códice conseguidos, pistas/mapas/rescates usados y la penalización ponderada (calculada al vuelo, no acumulada). |

## Comandos de depuración (NO listados en `/ayuda`)

Pensados para probar la gymkana sin recorrer físicamente las estaciones.

| Comando | Dónde se procesa | Qué hace |
|---|---|---|
| /move 0 | Decidir acción → Procesar estación y comandos | Sitúa al equipo justo después de registrar el nombre (esperando_inicio) en SU enclave de inicio ya asignado (o le asigna uno por round-robin, vía el contador, si aún no tenía). |
| /move 1 … /move 9 | Decidir acción → Procesar estación y comandos | Teletransporta al equipo directamente a esa estación física (en_juego, acertijo sin ver) y muestra el acertijo automáticamente, como un /repetir inmediato — al margen de la rotación por paso. Arranca el cronómetro si aún no había empezado. |
| /reboot | Decidir acción → Borrar equipo → Decrementar contador inicio | Borra por completo el documento del equipo en Firestore. Hace falta volver a escribir /start (y se le asignará el siguiente enclave de inicio por round-robin). Decrementa en 1 el contador de round-robin (con suelo en 0) para no perder ese hueco — así rebootear un equipo de pruebas no desplaza el enclave de inicio del resto. |

## Entradas que no son comandos

| Entrada | Qué hace |
|---|---|
| Ubicación GPS (no en tiempo real) | Calcula la distancia al enclave físico actual. Si es la primera vez que se confirma la llegada a SU enclave de inicio estando esperando_inicio: arranca el cronómetro. Si el acertijo aún no se había mostrado: lo revela. Si ya se había mostrado: confirma "lugar correcto" sin repetirlo. |
| Cualquier otro texto (durante en_juego) | Se normaliza y se compara contra station.respuestas.split('\|'). Si coincide: cápsula + fragmentos del paso + próximo enclave de SU ruta (nombre+mapa, calculado dinámicamente) o el aviso de código completo / cierre final en la estación 9. Si no coincide: cuenta como intento fallido y sugiere PISTA. |

## Comando de organizador (oculto, NO listado en `/ayuda`)

Restringido por chat_id: solo responde si `msg.chat_id === gymkanaConfig.admin_chat_id`. Para cualquier otro chat, `/admin` se trata como texto normal (intento de respuesta fallido).

| Comando | Dónde se procesa | Qué hace |
|---|---|---|
| /admin | Decidir acción → Listar equipos (admin) → Formatear resumen admin | Solo responde si el chat_id coincide con gymkanaConfig.admin_chat_id. Trae TODOS los documentos de gymkanas/linaje-olvidado/equipos (Firestore getAll), los ordena (finalizados primero por tiempo oficial, luego en_juego por paso descendente) y envía un resumen: nombre, estado, enclave/paso, tiempo (en curso u oficial), pistas/mapas/rescates y penalización ponderada de cada equipo. |
