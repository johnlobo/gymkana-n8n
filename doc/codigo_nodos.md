# Código de los nodos clave

Código JavaScript de los nodos `Code` de n8n con la lógica principal del bot. Todos ellos son nodos del workflow **plantilla**, compartido por todas las gymkanas montadas con este framework.

## Decidir acción

Máquina de estados principal: decide qué `action` corresponde a cada mensaje entrante.

```javascript

// Leemos el mensaje directamente desde Telegram Trigger para no depender
// de que los nodos intermedios conserven todos los campos.
const trigger = $('Telegram Trigger').first()?.json ?? {};

const telegramMessage =
  trigger.message ??
  trigger.edited_message ??
  trigger.channel_post ??
  trigger.edited_channel_post ??
  trigger.body?.message ??
  trigger.body ??
  trigger;

function normalizar(texto) {
  return String(texto ?? '')
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .toLowerCase()
    .trim()
    .replace(/[.,;:!?¿¡"'()]/g, '')
    .replace(/\s+/g, ' ');
}

const rawText = String(
  telegramMessage.text ??
  telegramMessage.caption ??
  ''
);

const location = telegramMessage.location ?? null;

const msg = {
  update_id: String(
    trigger.update_id ??
    trigger.body?.update_id ??
    telegramMessage.update_id ??
    ''
  ),
  chat_id: String(telegramMessage.chat?.id ?? ''),
  user_id: String(telegramMessage.from?.id ?? ''),
  nombre_usuario: String(telegramMessage.from?.first_name ?? ''),
  texto_original: rawText,
  text: normalizar(rawText),
  location,
  recibido_en: new Date().toISOString()
};

// El nodo Firestore puede devolver un documento, un objeto vacío o incluso
// conservar datos de entrada. Solo lo consideramos equipo si tiene estado.
const candidate = $json ?? {};
const existing =
  typeof candidate === 'object' &&
  candidate !== null &&
  typeof candidate.estado === 'string'
    ? candidate
    : null;

const now = new Date().toISOString();
const gymkanaConfig = $('Cargar gymkana').first().json;

// Terminología de esta gymkana (Fase 3): "Enclave" es el término por
// defecto, pero cada gymkana puede llamarlo de otra forma (Parada,
// Estación, Checkpoint...) vía gymkanas/{id}.termino_enclave.
const T_ENCLAVE = gymkanaConfig.termino_enclave || 'Enclave';

let team = existing ? {...existing} : null;
let action = '';
let response = '';
let needsStation = false;
let imagenUrl = '';
let justRegistered = false;
let reminderInicio = false;

// Cada equipo empieza en un enclave distinto para que no formen procesión;
// el último enclave (secreto) siempre es el mismo para todos.
function ordenInicioAleatorio() {
  const n = Number(gymkanaConfig.num_estaciones_regulares) || 8;
  return 1 + Math.floor(Math.random() * n);
}

const isStart = msg.text === '/start' || msg.text.startsWith('/start ');
const isAyuda = msg.text === 'ayuda' || msg.text === '/ayuda';
const isReboot = msg.text === 'reboot' || msg.text === '/reboot';
const isAdmin = (msg.text === 'admin' || msg.text === '/admin')
  && !!gymkanaConfig.admin_chat_id
  && msg.chat_id === String(gymkanaConfig.admin_chat_id);
const moveMatch = msg.text.match(/^\/?move\s+(\d+)$/);

if (isAdmin) {
  action = 'admin_list';
} else if (isReboot) {
  action = 'reboot';
  response = '🛠️ *DEBUG*: equipo borrado. Escribid /start para comenzar de nuevo desde cero.';
} else if (moveMatch) {
  if (!team) {
    action = 'send_only';
    response = '🛠️ *DEBUG*: no hay ningún equipo registrado. Usad /start primero.';
  } else {
    const n = Number(moveMatch[1]);
    if (n === 0) {
      // Number(...) es imprescindible aquí: Firestore devuelve los enteros
      // como texto, y la cadena "0" es truthy en JS, así que un `||` a
      // secas nunca reasignaría un orden_inicio que se hubiera quedado a 0.
      team.orden_inicio = Number(team.orden_inicio) || ordenInicioAleatorio();
      team.estado = 'esperando_inicio';
      team.estacion_actual = team.orden_inicio;
      team.paso = 1;
      team.pista_actual = 0;
      team.acertijo_visto = false;
      team.actualizado_en = now;
      action = 'station';
      needsStation = true;
      reminderInicio = true;
    } else {
      team.estado = 'en_juego';
      team.estacion_actual = n;
      team.pista_actual = 0;
      team.acertijo_visto = false;
      if (!team.inicio) team.inicio = now;
      team.actualizado_en = now;
      action = 'station';
      needsStation = true;
    }
  }
} else if (isAyuda) {
  action = 'send_only';
  const maxPistas = Number(gymkanaConfig.max_pistas) || 3;
  const pesoPista = Number(gymkanaConfig.peso_pista) || 1;
  const pesoMapa = Number(gymkanaConfig.peso_mapa) || 3;
  const pesoRescate = Number(gymkanaConfig.peso_rescate) || 5;
  response = `📖 COMANDOS DISPONIBLES

/start — Comenzar la gymkana y registrar el nombre de vuestro equipo.
/estado — Consultar el ${T_ENCLAVE.toLowerCase()} en el que estáis y vuestras estadísticas (pistas, mapas, rescates, penalización).
/pista — Pedir una pista del ${T_ENCLAVE.toLowerCase()} actual (máximo ${maxPistas} pistas, +${pesoPista} min cada una).
/mapa — Pista visual de la ubicación del ${T_ENCLAVE.toLowerCase()} actual (+${pesoMapa} min de penalización).
/rescate — Durante el juego: obtener la solución del ${T_ENCLAVE.toLowerCase()} actual y avanzar (+${pesoRescate} min de penalización).
/repetir — Repetir el enunciado del ${T_ENCLAVE.toLowerCase()} actual. Tras completar la gymkana: volver a ver el resumen de la ruta y el ${T_ENCLAVE.toLowerCase()} secreto.
/destino — Comprobar, compartiendo tu ubicación, si estáis en el lugar correcto.
/pausa — Detener el cronómetro (p.ej. para una parada). El resto de comandos de juego quedan bloqueados hasta /reanudar.
/reanudar — Continuar tras una pausa; el tiempo en pausa no cuenta.
/ayuda — Mostrar este mensaje.`;
} else if (!team) {
  if (isStart) {
    team = {
      id: msg.chat_id,
      chat_id: msg.chat_id,
      nombre: '',
      estado: 'pendiente_nombre',
      estacion_actual: 1,
      orden_inicio: 0,
      paso: 1,
      inicio: '',
      fin: '',
      pistas_usadas: 0,
      mapas_usados: 0,
      penalizacion_minutos: 0,
      fragmentos: '',
      pista_actual: 0,
      mapa_estaciones: '',
      intentos: 0,
      acertijo_visto: false,
      actualizado_en: now
    };
    action = 'save_send';
    response = `📜 Bienvenidos a ${gymkanaConfig.nombre || 'la gymkana'}.\n\nEscribid ahora el nombre de vuestro equipo.\n\nEn cualquier momento podéis escribir /ayuda para ver todos los comandos disponibles.`;
  } else {
    action = 'send_only';
    response = 'Para comenzar la gymkana, enviad /start.\n\nEscribid /ayuda si necesitáis ver todos los comandos disponibles.';
  }
} else if (team.estado === 'pendiente_nombre') {
  team.nombre = msg.texto_original.trim().slice(0, 80) || 'Equipo sin nombre';
  team.estado = 'esperando_inicio';
  team.paso = 1;
  team.actualizado_en = now;
  action = 'station';
  needsStation = true;
  justRegistered = true;
} else if (team.estado === 'esperando_inicio') {
  if (msg.location) {
    action = 'station';
    needsStation = true;
  } else if (msg.text === 'rescate' || msg.text === '/rescate') {
    action = 'station';
    needsStation = true;
  } else if (msg.text === 'destino' || msg.text === '/destino') {
    action = 'send_only';
    response = '📍 Para comprobar que estáis en el punto de inicio, pulsad el icono de adjuntar (📎) en Telegram, elegid "Ubicación" y enviad "Enviar mi ubicación actual" (no la ubicación en tiempo real).';
  } else {
    action = 'station';
    needsStation = true;
    reminderInicio = true;
  }
} else if (team.estado === 'finalizado') {
  if (msg.text === 'repetir' || msg.text === '/repetir') {
    action = 'final_summary';
  } else {
    action = 'send_only';
    response = `🏆 Este equipo ya ha finalizado la gymkana. Escribid REPETIR si queréis volver a ver el resumen y el ${T_ENCLAVE.toLowerCase()} secreto.`;
  }
} else if (isStart) {
  action = 'send_only';
  response = `La partida de ${team.nombre} ya está en curso. Escribid ESTADO para consultar el progreso.`;
} else if (msg.text === 'estado' || msg.text === '/estado') {
  action = 'station';
  needsStation = true;
} else if (msg.text === 'destino' || msg.text === '/destino') {
  action = 'send_only';
  response = '📍 Para comprobar si estáis en el lugar correcto, pulsa el icono de adjuntar (📎) en Telegram, elegid "Ubicación" y enviad "Enviar mi ubicación actual" (no la ubicación en tiempo real).';
} else {
  action = 'station';
  needsStation = true;
}

return [{json:{msg,team,action,response,needsStation,imagen_url:imagenUrl,just_registered:justRegistered,reminder_inicio:reminderInicio}}];
```

## Procesar estación y comandos

Motor del juego: pistas, mapas, rescates, comprobación de respuestas, avance de estación, cierre final.

```javascript

const ctx = $('Decidir acción').first().json;
const gymkanaConfig = $('Cargar gymkana').first().json;
const team = {...ctx.team};
const msg = ctx.msg;
const station = $json;
const now = new Date().toISOString();

// Config de la gymkana (Fase 0/1: nada de esto va ya fijo en el código).
const MAX_PISTAS = Number(gymkanaConfig.max_pistas) || 3;
const PESO_PISTA = Number(gymkanaConfig.peso_pista) || 1;
const PESO_MAPA = Number(gymkanaConfig.peso_mapa) || 3;
const PESO_RESCATE = Number(gymkanaConfig.peso_rescate) || 5;
const TOLERANCIA_METROS = Number(gymkanaConfig.tolerancia_metros) || 50;
const NUM_ESTACIONES_REGULARES = Number(gymkanaConfig.num_estaciones_regulares) || 8;
const ESTACION_FINAL = NUM_ESTACIONES_REGULARES + 1;

// Terminología de esta gymkana (Fase 3): "Enclave" es el término por
// defecto, pero cada gymkana puede llamarlo de otra forma (Parada,
// Estación, Checkpoint...) vía gymkanas/{id}.termino_enclave.
const T_ENCLAVE = gymkanaConfig.termino_enclave || 'Enclave';

function norm(s) {
  return String(s ?? '')
    .normalize('NFD').replace(/\p{Diacritic}/gu,'')
    .toLowerCase().trim()
    .replace(/[.,;:!?¿¡"'()]/g,'')
    .replace(/\s+/g,' ');
}

function fmtTiempo(totalSeg) {
  const m = Math.floor(totalSeg / 60);
  const s = totalSeg % 60;
  const h = Math.floor(m / 60);
  const mm = m % 60;
  return h > 0 ? `${h}h ${mm}m ${s}s` : `${mm}m ${s}s`;
}

function calcularRango(minutosOficiales) {
  if (minutosOficiales < 45) {
    return '🥇 *Leyenda de la Villa*\n_¡Velocidad y perspicacia dignas del mismísimo Marqués de Santillana!_';
  } else if (minutosOficiales <= 65) {
    return '🥈 *Maestros Cronistas*\n_Un recorrido impecable observando cada rincón e historia de las piedras._';
  } else if (minutosOficiales <= 90) {
    return '🥉 *Guardianes del Códice*\n_Perseverancia y trabajo en equipo. ¡Ningún sello se os ha resistido!_';
  }
  return '📜 *Exploradores Pacientes*\n_Habéis disfrutado de la villa sin prisas. La historia requiere su tiempo._';
}

// Cada equipo recorre las estaciones regulares en un orden distinto
// (empezando en team.orden_inicio y dando la vuelta), pero los fragmentos
// del códice se entregan por "paso", no por estación física: así todo el
// mundo obtiene la secuencia completa en el orden correcto sin importar
// por dónde empezara. La última estación (ESTACION_FINAL) es siempre la
// misma para todos.
function ordenInicioDe(team) {
  return Number(team.orden_inicio) || 1;
}

function pasoDe(team) {
  return Number(team.paso) || 1;
}

function estacionFisica(ordenInicio, paso) {
  if (paso > NUM_ESTACIONES_REGULARES) return ESTACION_FINAL;
  return ((ordenInicio - 1 + paso - 1) % NUM_ESTACIONES_REGULARES) + 1;
}

// Penalización ponderada: no se acumula turno a turno, se calcula siempre
// a partir de los contadores (pistas_usadas, mapas_usados, rescates_usados).
function penalizacionDe(team) {
  return Number(team.pistas_usadas || 0) * PESO_PISTA
    + Number(team.mapas_usados || 0) * PESO_MAPA
    + Number(team.rescates_usados || 0) * PESO_RESCATE;
}

// Tiempo total en pausa: lo ya acumulado en pausas anteriores, más la
// pausa en curso (si la hay) hasta este instante. Se resta del tiempo
// transcurrido en /estado y en el cierre final, para que las pausas no
// penalicen a los equipos.
function tiempoPausadoTotal(team) {
  let total = Number(team.tiempo_pausado_segundos || 0);
  if (team.pausado_en) {
    const pStart = new Date(team.pausado_en).getTime();
    if (Number.isFinite(pStart)) {
      total += Math.floor((Date.now() - pStart) / 1000);
    }
  }
  return total;
}

function fragmentosHasta(station, n) {
  const partes = [];
  for (let i = 1; i <= n; i++) {
    const v = station['paso' + i + '_fragmento'];
    if (v) partes.push(v);
  }
  return partes.join(' ');
}

function construirMensajeFinal(team, elapsedSeg) {
  const penalizacionMin = penalizacionDe(team);
  team.penalizacion_minutos = penalizacionMin;
  const tiempoOficialSeg = elapsedSeg + penalizacionMin * 60;
  const rango = calcularRango(Math.floor(tiempoOficialSeg / 60));

  team.tiempo_bruto_segundos = elapsedSeg;
  team.tiempo_oficial_segundos = tiempoOficialSeg;
  team.rango_equipo = rango;
  team.imagen_final = station.imagen_final_url || station.imagen_url || '';
  team.documento_final = station.guia_historica_url || '';

  const mensaje = `${station.capsula}

📜 *Secuencia del Códice:*
${station.secuencia_codice} ➔ \`${station.coordenadas_finales}\`

──────────────

📊 *RESUMEN DE LA MISIÓN*

⏱️ *Tiempo de recorrido:* \`${fmtTiempo(elapsedSeg)}\`
💡 *Pistas usadas:* \`${team.pistas_usadas || 0}\`
📍 *Mapas usados:* \`${team.mapas_usados || 0}\`
🆘 *Rescates usados:* \`${team.rescates_usados || 0}\`
⏳ *Penalización total:* \`+${penalizacionMin} min\`
🏆 *TIEMPO OFICIAL FINAL:* \`${fmtTiempo(tiempoOficialSeg)}\`

──────────────

🎖️ *VALORACIÓN DE LA ESCUADRA*
${rango}

🏰 _Gracias por resolver el misterio de la villa. El Linaje Olvidado ya forma parte de vuestra historia._`;

  team.mensaje_final = mensaje;
  return mensaje;
}

let response = '';
let changed = false;
let imagenUrl = '';
let capsulaMsg = '';
let documentoUrl = '';
let siguienteEstacionId = '';
let justFinalized = false;

const moveMatch = msg.text.match(/^\/?move\s+(\d+)$/);
if (moveMatch && Number(moveMatch[1]) >= 1 && Number(moveMatch[1]) <= ESTACION_FINAL) {
  team.acertijo_visto = true;
  imagenUrl = station.imagen_url || '';
  response = `📍 *${T_ENCLAVE.toUpperCase()} ${station.orden} — ${station.nombre}*

${station.acertijo}

📸 Fijaos bien en la foto para confirmar que estáis en el punto exacto — el GPS puede no ser del todo preciso.`;
  team.actualizado_en = now;
  return [{ json: { ...team, response, chat_id: msg.chat_id, changed: true, imagen_url: imagenUrl } }];
}

// Mensaje mostrado justo después de registrar el nombre del equipo:
// dirige al enclave de inicio que le ha tocado a este equipo.
if (ctx.just_registered) {
  // 'station' ya se cargó con el enclave asignado por round-robin (ver
  // 'Calcular orden de inicio'), pero ese cálculo vive en una rama aparte
  // que 'Decidir acción' nunca ve: sin esto, orden_inicio/estacion_actual
  // se quedarían para siempre en su valor de creación (0), aunque el
  // mensaje mostrado al equipo sí fuera el correcto.
  team.orden_inicio = Number(station.orden) || 1;
  team.estacion_actual = team.orden_inicio;
  response = `📜 ¡Equipo registrado, ${team.nombre}!

Antes de que el reloj empiece a correr, dirigíos al punto de partida:
👉 *${station.nombre}*
🗺️ Mapa: ${station.mapa_url}

Cuando estéis allí, escribid /destino para confirmar vuestra ubicación y arrancar oficialmente "${gymkanaConfig.nombre}".`;
  imagenUrl = station.imagen_url || '';
  team.actualizado_en = now;
  return [{ json: { ...team, response, chat_id: msg.chat_id, changed: true, imagen_url: imagenUrl } }];
}

// Recordatorio de "aún no habéis empezado" (o resultado de /move 0):
// también apunta al enclave de inicio propio del equipo.
if (ctx.reminder_inicio) {
  response = `📍 Aún no habéis empezado. Dirigíos al punto de partida:
👉 *${station.nombre}*
🗺️ Mapa: ${station.mapa_url}

Cuando estéis allí, escribid /destino para confirmar vuestra ubicación y arrancar oficialmente la gymkana.`;
  team.actualizado_en = now;
  return [{ json: { ...team, response, chat_id: msg.chat_id, changed: true } }];
}

if (team.estado === 'esperando_inicio' && (msg.text === 'rescate' || msg.text === '/rescate')) {
  team.estado = 'en_juego';
  team.inicio = now;
  team.acertijo_visto = true;
  imagenUrl = station.imagen_url || '';
  response = `📜 *EL CÓDICE DEL LINAJE OLVIDADO*

Bienvenidos, ${team.nombre}. El reloj empieza ahora.

📍 *${T_ENCLAVE.toUpperCase()} ${station.orden} — ${station.nombre}*

${station.acertijo}

📸 Fijaos bien en la foto para confirmar que estáis en el punto exacto — el GPS de las estaciones puede no ser del todo preciso.

Podéis responder directamente o escribir PISTA, MAPA, REPETIR, ESTADO, DESTINO o AYUDA (para ver todos los comandos disponibles en cualquier momento).`;
  team.actualizado_en = now;
  return [{ json: { ...team, response, chat_id: msg.chat_id, changed: true, imagen_url: imagenUrl } }];
}

// En pausa: solo se admiten /reanudar, /estado y /repetir. El resto de
// comandos de juego (pistas, mapas, rescate, ubicación, respuestas) quedan
// bloqueados hasta reanudar, para que quede claro que el reloj está parado.
const comandosPermitidosEnPausa = ['pausa', '/pausa', 'reanudar', '/reanudar', 'estado', '/estado', 'repetir', '/repetir'];
if (team.pausado_en && (msg.location || !comandosPermitidosEnPausa.includes(msg.text))) {
  response = `⏸️ La partida está en pausa. Escribid /reanudar para continuar (o /estado para ver el resumen).`;
  team.actualizado_en = now;
  return [{ json: { ...team, response, chat_id: msg.chat_id, changed: false } }];
}

if (msg.location) {
  const toRad = g => g * Math.PI / 180;
  const R = 6371000;
  const lat2 = Number(station.lat);
  const lon2 = Number(station.lon);
  const dLat = toRad(lat2 - msg.location.latitude);
  const dLon = toRad(lon2 - msg.location.longitude);
  const a = Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(msg.location.latitude)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  const distancia = Math.round(2 * R * Math.asin(Math.sqrt(a)));

  if (distancia <= TOLERANCIA_METROS) {
    if (team.estado === 'esperando_inicio') {
      team.estado = 'en_juego';
      team.inicio = now;
      team.acertijo_visto = true;
      imagenUrl = station.imagen_url || '';
      response = `📜 *EL CÓDICE DEL LINAJE OLVIDADO*

Bienvenidos, ${team.nombre}. El reloj empieza ahora.

📍 *${T_ENCLAVE.toUpperCase()} ${station.orden} — ${station.nombre}*

${station.acertijo}

📸 Fijaos bien en la foto para confirmar que estáis en el punto exacto — el GPS de las estaciones puede no ser del todo preciso.

Podéis responder directamente o escribir PISTA, MAPA, REPETIR, ESTADO, DESTINO o AYUDA (para ver todos los comandos disponibles en cualquier momento).`;
      team.actualizado_en = now;
      return [{ json: { ...team, response, chat_id: msg.chat_id, changed: true, imagen_url: imagenUrl } }];
    }
    if (!team.acertijo_visto) {
      team.acertijo_visto = true;
      imagenUrl = station.imagen_url || '';
      response = `📍 *${T_ENCLAVE.toUpperCase()} ${station.orden} — ${station.nombre}*

${station.acertijo}

📸 Fijaos bien en la foto para confirmar que estáis en el punto exacto — el GPS puede no ser del todo preciso.`;
      team.actualizado_en = now;
      return [{ json: { ...team, response, chat_id: msg.chat_id, changed: true, imagen_url: imagenUrl } }];
    }
    response = `✅ ¡Estáis en el lugar correcto! (a ${distancia} m del punto exacto)\n\n📸 Comparad con la foto del ${T_ENCLAVE.toLowerCase()} para confirmar que sois exactamente en el sitio.`;
  } else {
    response = `📍 Aún no es el sitio correcto. Os faltan aproximadamente ${distancia} m.\n\n📸 Fijaos bien en la foto del ${T_ENCLAVE.toLowerCase()} para localizar el punto exacto — el GPS puede no ser del todo preciso.`;
  }

  team.actualizado_en = now;
  return [{ json: { ...team, response, chat_id: msg.chat_id, changed: false } }];
}

if (msg.text === 'pausa' || msg.text === '/pausa') {
  if (team.pausado_en) {
    response = '⏸️ Ya estabais en pausa. Escribid /reanudar para continuar.';
  } else {
    team.pausado_en = now;
    changed = true;
    response = '⏸️ Partida en pausa. El cronómetro se detiene aquí. Escribid /reanudar cuando queráis continuar.';
  }
} else if (msg.text === 'reanudar' || msg.text === '/reanudar') {
  if (!team.pausado_en) {
    response = 'No estabais en pausa. Si queréis seguir jugando, responded al acertijo o escribid PISTA.';
  } else {
    const pStart = new Date(team.pausado_en).getTime();
    const pausaSeg = Number.isFinite(pStart) ? Math.floor((Date.now() - pStart) / 1000) : 0;
    team.tiempo_pausado_segundos = Number(team.tiempo_pausado_segundos || 0) + pausaSeg;
    team.pausado_en = '';
    changed = true;
    response = '▶️ Partida reanudada. ¡A seguir!';
  }
} else if (msg.text === 'pista' || msg.text === '/pista') {
  const current = Number(team.pista_actual || 0);
  if (current >= MAX_PISTAS) {
    response = `Ya habéis utilizado las ${MAX_PISTAS} pistas de este ${T_ENCLAVE.toLowerCase()}. Escribid RESCATE si queréis la solución de este ${T_ENCLAVE.toLowerCase()} y avanzar (+${PESO_RESCATE} min), o MAPA si solo queréis una pista visual (+${PESO_MAPA} min).`;
  } else {
    const next = current + 1;
    response = `💡 Pista ${next} (+${PESO_PISTA} min): ${station['pista'+next]}`;
    if (next >= MAX_PISTAS) {
      response += `\n\n⚠️ Has agotado las ${MAX_PISTAS} pistas de este ${T_ENCLAVE.toLowerCase()}. Si no lográis dar con la respuesta, podéis usar el comando /rescate para obtener la solución y avanzar (+${PESO_RESCATE} min de penalización).`;
    }
    team.pista_actual = next;
    team.pistas_usadas = Number(team.pistas_usadas || 0) + 1;
    changed = true;
  }
} else if (msg.text === 'mapa' || msg.text === '/mapa') {
  const used = String(team.mapa_estaciones || '').split(',').filter(Boolean);
  const key = String(team.estacion_actual);
  if (!used.includes(key)) {
    used.push(key);
    team.mapa_estaciones = used.join(',');
    team.mapas_usados = Number(team.mapas_usados || 0) + 1;
    changed = true;
    response = `📍 Pista de mapa (+${PESO_MAPA} min): ${station.mapa_url}`;
  } else {
    response = `📍 Ya habíais solicitado este mapa: ${station.mapa_url}`;
  }
} else if (msg.text === 'rescate' || msg.text === '/rescate') {
  if (!team.acertijo_visto) {
    team.acertijo_visto = true;
    team.rescates_usados = Number(team.rescates_usados || 0) + 1;
    changed = true;
    imagenUrl = station.imagen_url || '';
    response = `🆘 Rescate (+${PESO_RESCATE} min): os guiamos hasta el ${T_ENCLAVE.toLowerCase()}.

📍 *${T_ENCLAVE.toUpperCase()} ${station.orden} — ${station.nombre}*

${station.acertijo}

📸 Fijaos bien en la foto para confirmar que estáis en el punto exacto — el GPS puede no ser del todo preciso.`;
  } else {
    team.rescates_usados = Number(team.rescates_usados || 0) + 1;
    changed = true;

    const respuestaCorrecta = String(station.respuestas || '').split('|')[0];

    if (Number(team.estacion_actual) >= ESTACION_FINAL) {
      team.estado = 'finalizado';
      team.fin = now;
      justFinalized = true;
      const startMs = new Date(team.inicio).getTime();
      const rawElapsed = Number.isFinite(startMs) ? Math.floor((Date.now()-startMs)/1000) : 0;
      const elapsed = Math.max(0, rawElapsed - tiempoPausadoTotal(team));
      response = `✅ *La respuesta era:* ${respuestaCorrecta}\n\n` + construirMensajeFinal(team, elapsed);
      imagenUrl = station.imagen_final_url || station.imagen_url || '';
      documentoUrl = station.guia_historica_url || '';
    } else {
      const paso = pasoDe(team);
      const ordenInicio = ordenInicioDe(team);
      const nuevoPaso = paso + 1;
      team.orden_inicio = ordenInicio;
      team.paso = nuevoPaso;
      team.estacion_actual = estacionFisica(ordenInicio, nuevoPaso);
      team.pista_actual = 0;
      team.acertijo_visto = false;
      capsulaMsg = `🆘 Rescate (+${PESO_RESCATE} min)\n\n✅ *La respuesta era:* ${respuestaCorrecta}\n\n${station.capsula}`;
      response = `Fragmentos del Códice: "${fragmentosHasta(station, paso)}"`;
      siguienteEstacionId = String(team.estacion_actual);
    }
  }
} else if (msg.text === 'estado' || msg.text === '/estado') {
  const startMs = new Date(team.inicio).getTime();
  const rawElapsedSec = Number.isFinite(startMs) ? Math.floor((Date.now() - startMs) / 1000) : 0;
  const elapsedSec = Math.max(0, rawElapsedSec - tiempoPausadoTotal(team));
  const fmtEstado = s => `${Math.floor(s / 60)} min ${s % 60} s`;
  const pasoActual = Math.min(pasoDe(team), NUM_ESTACIONES_REGULARES);
  const lineaPausa = team.pausado_en ? '\n⏸️ *EN PAUSA* — escribid /reanudar para continuar' : '';
  response = `📜 ESTADO DEL EQUIPO\n\nEquipo: ${team.nombre}\n${T_ENCLAVE}: ${pasoActual} de ${NUM_ESTACIONES_REGULARES}\n⏱ Tiempo transcurrido: ${fmtEstado(elapsedSec)}\nFragmentos del Códice: "${fragmentosHasta(station, pasoActual - 1)}"\nPistas: ${team.pistas_usadas || 0}\nMapas: ${team.mapas_usados || 0}\nRescates: ${team.rescates_usados || 0}\nPenalización: ${penalizacionDe(team)} min${lineaPausa}`;
} else if (msg.text === 'repetir' || msg.text === '/repetir') {
  if (!team.acertijo_visto) {
    team.acertijo_visto = true;
    changed = true;
  }
  response = `📍 ${T_ENCLAVE} ${station.orden}: ${station.nombre}\n\n🧩 ${station.acertijo}`;
  imagenUrl = station.imagen_url || '';
} else {
  const accepted = String(station.respuestas || '').split('|').map(norm);
  if (accepted.includes(msg.text)) {
    if (Number(team.estacion_actual) >= ESTACION_FINAL) {
      team.estado = 'finalizado';
      team.fin = now;
      justFinalized = true;
      const startMs = new Date(team.inicio).getTime();
      const rawElapsed = Number.isFinite(startMs) ? Math.floor((Date.now()-startMs)/1000) : 0;
      const elapsed = Math.max(0, rawElapsed - tiempoPausadoTotal(team));
      response = construirMensajeFinal(team, elapsed);
      imagenUrl = station.imagen_final_url || station.imagen_url || '';
      documentoUrl = station.guia_historica_url || '';
    } else {
      const paso = pasoDe(team);
      const ordenInicio = ordenInicioDe(team);
      const nuevoPaso = paso + 1;
      team.orden_inicio = ordenInicio;
      team.paso = nuevoPaso;
      team.estacion_actual = estacionFisica(ordenInicio, nuevoPaso);
      team.pista_actual = 0;
      team.acertijo_visto = false;
      capsulaMsg = `✅ ¡Respuesta correcta!\n\n${station.capsula}`;
      response = `Fragmentos del Códice: "${fragmentosHasta(station, paso)}"`;
      siguienteEstacionId = String(team.estacion_actual);
    }
    changed = true;
  } else {
    team.intentos = Number(team.intentos || 0) + 1;
    changed = true;
    response = '❌ Esa respuesta no es correcta. Observad de nuevo o escribid PISTA.';
  }
}

team.actualizado_en = now;
return [{json:{...team,response,chat_id:msg.chat_id,changed,imagen_url:imagenUrl,capsula_msg:capsulaMsg,documento_url:documentoUrl,siguiente_estacion_id:siguienteEstacionId,estacion_final:ESTACION_FINAL,just_finalized:justFinalized}}];
```

## Construir mensaje siguiente

Añade el bloque de "próximo enclave" (o el aviso de código completo) al mensaje ya construido.

```javascript
const prev = $('Procesar estación y comandos').first().json;
const next = $json;
const gymkanaConfig = $('Cargar gymkana').first().json;
const T_ENCLAVE = gymkanaConfig.termino_enclave || 'Enclave';

let siguienteTexto;
if (String(next.id) === String(prev.estacion_final)) {
  siguienteTexto = `🧩 *¡EL CÓDICE ESTÁ COMPLETO!*\n\nAl unir todos los fragmentos obtenemos unas coordenadas...\n👉 \`${next.coordenadas_finales}\`\n\n📍 Dirigíos hasta ese punto para realizar la última misión.\n\n🚶 *Última misión:*\n1️⃣ Dirigíos hacia el ${T_ENCLAVE.toLowerCase()} secreto: *${next.nombre}*.\n2️⃣ 🗺️ Mapa: ${next.mapa_url}\n\n📍 Al llegar, escribid \`/destino\` para afrontar el desenlace.`;
} else {
  siguienteTexto = `➡️ *Próximo ${T_ENCLAVE.toLowerCase()}:* ${next.nombre}\n🗺️ Mapa: ${next.mapa_url}\n\n📍 Al llegar, escribid \`/destino\`.`;
}
const response = `${prev.response}\n\n${siguienteTexto}`;
return [{ json: { ...prev, response } }];
```

## Formatear resumen admin

Formatea el panel de organizador (`/admin`): progreso, tiempo, pistas/mapas/rescates y penalización de cada equipo.

```javascript
const ctx = $('Decidir acción').first().json;
const gymkanaConfig = $('Cargar gymkana').first().json;
const teams = $input.all().map(item => item.json).filter(t => t && t.id);

const T_ENCLAVE = gymkanaConfig.termino_enclave || 'Enclave';
const PESO_PISTA = Number(gymkanaConfig.peso_pista) || 1;
const PESO_MAPA = Number(gymkanaConfig.peso_mapa) || 3;
const PESO_RESCATE = Number(gymkanaConfig.peso_rescate) || 5;
const NUM_ESTACIONES_REGULARES = Number(gymkanaConfig.num_estaciones_regulares) || 8;

function penalizacionDe(t) {
  return Number(t.pistas_usadas || 0) * PESO_PISTA
    + Number(t.mapas_usados || 0) * PESO_MAPA
    + Number(t.rescates_usados || 0) * PESO_RESCATE;
}

function fmtTiempo(totalSeg) {
  const m = Math.floor(totalSeg / 60);
  const s = totalSeg % 60;
  const h = Math.floor(m / 60);
  const mm = m % 60;
  return h > 0 ? `${h}h ${mm}m ${s}s` : `${mm}m ${s}s`;
}

function estadoEmoji(estado) {
  if (estado === 'finalizado') return '🏁';
  if (estado === 'en_juego') return '🎮';
  if (estado === 'esperando_inicio') return '🚦';
  return '📝';
}

const filas = teams
  .filter(t => t.estado && t.estado !== 'pendiente_nombre')
  .sort((a, b) => {
    const aFin = a.estado === 'finalizado';
    const bFin = b.estado === 'finalizado';
    if (aFin && bFin) return Number(a.tiempo_oficial_segundos || 0) - Number(b.tiempo_oficial_segundos || 0);
    if (aFin) return -1;
    if (bFin) return 1;
    return Number(b.paso || 0) - Number(a.paso || 0);
  })
  .map(t => {
    const paso = Math.min(Number(t.paso || 1), NUM_ESTACIONES_REGULARES);
    let tiempoTxt;
    if (t.estado === 'finalizado') {
      tiempoTxt = `⏱ ${fmtTiempo(Number(t.tiempo_oficial_segundos || 0))} (oficial)`;
    } else if (t.inicio) {
      const startMs = new Date(t.inicio).getTime();
      const elapsed = Number.isFinite(startMs) ? Math.floor((Date.now() - startMs) / 1000) : 0;
      tiempoTxt = `⏱ ${fmtTiempo(elapsed)} (en curso)`;
    } else {
      tiempoTxt = '⏱ sin empezar';
    }
    const penal = penalizacionDe(t);
    return `${estadoEmoji(t.estado)} *${t.nombre || t.id}*\n` +
      `   ${T_ENCLAVE} ${paso}/${NUM_ESTACIONES_REGULARES} · ${tiempoTxt}\n` +
      `   💡${t.pistas_usadas || 0} 📍${t.mapas_usados || 0} 🆘${t.rescates_usados || 0} · ⏳ +${penal} min`;
  });

const response = filas.length
  ? `🛠️ *PANEL ADMIN — ${gymkanaConfig.nombre || ''}*\n\n${filas.join('\n\n')}\n\n_Equipos: ${filas.length}_`
  : '🛠️ *PANEL ADMIN*\n\nNo hay equipos registrados todavía.';

return [{ json: { chat_id: ctx.msg.chat_id, response } }];
```

## Preparar diploma

Calcula los textos y posiciones (centrado aproximado) para el certificado generado con Edit Image / GraphicsMagick.

```javascript
// Genera los campos (texto + posiciones) para el certificado, a partir del
// equipo ya guardado en Firestore (team = $json, salida de 'Guardar
// progreso'). Rama paralela a la entrega normal: si algo falla aquí, no
// debe afectar al resto del turno (los 3 nodos de esta rama llevan
// onError: continueRegularOutput).
const team = $json;
const gymkanaConfig = $('Cargar gymkana').first().json;

function stripDecoracion(s) {
  return String(s || '')
    .split('\n')[0]
    .replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/gu, '')
    .replace(/\*/g, '')
    .trim();
}

function fmtTiempo(totalSeg) {
  const m = Math.floor(totalSeg / 60);
  const s = totalSeg % 60;
  const h = Math.floor(m / 60);
  const mm = m % 60;
  return h > 0 ? `${h}h ${mm}m ${s}s` : `${mm}m ${s}s`;
}

const W = 1600;
function centrarX(texto, fontSize, anchoAprox) {
  const anchoEstimado = String(texto).length * fontSize * anchoAprox;
  return Math.max(70, Math.round((W - anchoEstimado) / 2));
}

let nombreEquipo = String(team.nombre || 'Equipo').toUpperCase();
let equipoFontSize = 78;
if (nombreEquipo.length > 30) nombreEquipo = nombreEquipo.slice(0, 30).trimEnd() + '…';
if (nombreEquipo.length > 22) equipoFontSize = 54;
else if (nombreEquipo.length > 15) equipoFontSize = 64;

const tiempoTexto = `Tiempo oficial: ${fmtTiempo(Number(team.tiempo_oficial_segundos || 0))}`;
const rangoTexto = stripDecoracion(team.rango_equipo);
const gymkanaTexto = String(gymkanaConfig.nombre || '').toUpperCase();
const fechaTexto = new Date().toLocaleDateString('es-ES', { day: 'numeric', month: 'long', year: 'numeric' });
const tituloTexto = 'CERTIFICADO DE FINALIZACIÓN';
const sub1Texto = 'Se certifica que el equipo';
const sub2Texto = 'ha completado la gymkana';

return [{
  json: {
    chat_id: team.chat_id,
    tituloTexto, tituloPosX: centrarX(tituloTexto, 48, 0.50),
    gymkanaTexto, gymkanaPosX: centrarX(gymkanaTexto, 30, 0.48),
    sub1Texto, sub1PosX: centrarX(sub1Texto, 28, 0.48),
    equipoTexto: nombreEquipo, equipoFontSize, equipoPosX: centrarX(nombreEquipo, equipoFontSize, 0.56),
    sub2Texto, sub2PosX: centrarX(sub2Texto, 28, 0.48),
    tiempoTexto, tiempoPosX: centrarX(tiempoTexto, 38, 0.48),
    rangoTexto, rangoPosX: centrarX(rangoTexto, 44, 0.50),
    fechaTexto, fechaPosX: centrarX(fechaTexto, 26, 0.46),
  }
}];
```

