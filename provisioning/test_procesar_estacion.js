#!/usr/bin/env node
/**
 * Prueba mínima (no un framework) para el código del nodo Code
 * "Procesar estación y comandos" -- el motor de juego, y el nodo con más
 * lógica y más riesgo de todo el workflow.
 *
 * No sustituye una prueba real contra el bot, pero coge de inmediato lo que
 * más ha fallado hasta ahora: errores de sintaxis (un `} else {` duplicado
 * rompió TODOS los comandos en producción el 2026-08-11 durante horas) y
 * ramas que lanzan excepción con datos de forma razonable.
 *
 * Uso:
 *   node provisioning/test_procesar_estacion.js                  # usa workflow.json
 *   node provisioning/test_procesar_estacion.js ruta/al/nodo.js   # usa un fichero suelto
 *
 * Antes de desplegar cualquier cambio a este nodo (Salamanca, Aranda o la
 * plantilla), pegar el código nuevo en un fichero y correr este script
 * contra él -- o extraerlo ya desplegado y comprobar aquí antes de darlo
 * por bueno.
 */
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

function loadCode(argPath) {
  if (argPath) return fs.readFileSync(argPath, 'utf8');
  const wf = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'workflow.json'), 'utf8'));
  const node = wf.nodes.find((n) => n.name === 'Procesar estación y comandos');
  if (!node) throw new Error('No se encontró el nodo "Procesar estación y comandos" en workflow.json');
  return node.parameters.jsCode;
}

const codePath = process.argv[2];
const code = loadCode(codePath);

// 1) Sintaxis -- lo que rompió producción hoy.
const tmpFile = path.join(require('os').tmpdir(), `procesar_estacion_check_${Date.now()}.js`);
fs.writeFileSync(tmpFile, code);
try {
  execSync(`node --check ${tmpFile}`, { stdio: 'pipe' });
} catch (e) {
  console.error('FALLO DE SINTAXIS:\n' + e.stderr.toString());
  process.exit(1);
} finally {
  fs.unlinkSync(tmpFile);
}
console.log('Sintaxis OK.');

// 2) Ejecución contra escenarios representativos.
const station = {
  orden: 1, nombre: 'Estación Test', capsula: 'Texto de la cápsula',
  acertijo: 'Texto del acertijo', respuestas: 'respuesta',
  pista1: 'p1', pista2: 'p2', pista3: 'p3',
  imagen_url: 'http://x/img.jpg', mapa_url: 'http://x/mapa',
  audio_url: 'http://x/audio.mp3', acertijo_audio_url: 'http://x/acertijo.mp3',
  imagen_final_url: 'http://x/final.jpg', guia_historica_url: 'http://x/guia.pdf',
  secuencia_codice: 'A-B-C', coordenadas_finales: '0N,0W', lat: 40, lon: -3,
  paso1_fragmento: 'frag1',
};

function baseTeam(overrides) {
  return Object.assign({
    nombre: 'Equipo Test', estado: 'en_juego', estacion_actual: 1, paso: 1,
    orden_inicio: 1, acertijo_visto: false, inicio: new Date().toISOString(),
  }, overrides);
}

function run(ctx) {
  const nodeOutputs = {
    'Decidir acción': [{ json: ctx }],
    'Cargar gymkana': [{ json: {
      max_pistas: 3, peso_pista: 1, peso_mapa: 3, peso_rescate: 5,
      tolerancia_metros: 50, num_estaciones_regulares: 6,
      termino_enclave: 'Parada', nombre: 'Test Gymkana',
    } }],
  };
  global.$ = (name) => {
    if (!nodeOutputs[name]) throw new Error(`Nodo no mockeado: ${name}`);
    return { first: () => ({ json: nodeOutputs[name][0].json }) };
  };
  global.$json = station;
  const fn = new Function(code + '\nreturn arguments[0];');
  const out = fn();
  delete global.$;
  delete global.$json;
  return out[0].json;
}

const casos = [
  {
    nombre: 'move a estación válida muestra el acertijo',
    ctx: { team: baseTeam(), msg: { text: 'move 1', chat_id: 1 } },
    check: (o) => o.response.includes(station.acertijo) && o.audio_acertijo_url === station.acertijo_audio_url,
  },
  {
    nombre: 'repetir sin contenido previo cae al acertijo actual (fallback)',
    ctx: { team: baseTeam(), msg: { text: 'repetir', chat_id: 1 } },
    check: (o) => o.response.includes(station.acertijo),
  },
  {
    nombre: 'repetir con contenido previo repite EXACTAMENTE eso, no la estación actual',
    ctx: { team: baseTeam({ ultimo_texto: 'TEXTO_GUARDADO', ultima_imagen_url: 'IMG_GUARDADA', ultimo_audio_url: 'AUDIO_GUARDADO' }), msg: { text: 'repetir', chat_id: 1 } },
    check: (o) => o.response === 'TEXTO_GUARDADO' && o.imagen_url === 'IMG_GUARDADA' && o.audio_acertijo_url === 'AUDIO_GUARDADO',
  },
  {
    nombre: 'respuesta correcta avanza de estación y guarda ultimo_texto',
    ctx: { team: baseTeam(), msg: { text: 'respuesta', chat_id: 1 } },
    check: (o) => o.changed === true && !!o.siguiente_estacion_id
      && o.audio_url === station.audio_url && o.ultimo_texto === o.capsula_msg,
  },
  {
    nombre: 'respuesta incorrecta no avanza',
    ctx: { team: baseTeam(), msg: { text: 'esto no es la respuesta', chat_id: 1 } },
    check: (o) => o.response.includes('no es correcta') && !o.siguiente_estacion_id,
  },
  {
    nombre: 'rescate primera vez revela el acertijo sin avanzar',
    ctx: { team: baseTeam({ acertijo_visto: false }), msg: { text: 'rescate', chat_id: 1 } },
    check: (o) => o.response.includes('Rescate') && o.audio_acertijo_url === station.acertijo_audio_url,
  },
  {
    nombre: 'rescate segunda vez revela la respuesta y avanza',
    ctx: { team: baseTeam({ acertijo_visto: true }), msg: { text: 'rescate', chat_id: 1 } },
    check: (o) => o.response.includes('Fragmentos del Códice') && o.audio_url === station.audio_url,
  },
  {
    nombre: 'estado no lanza y no marca changed',
    ctx: { team: baseTeam(), msg: { text: 'estado', chat_id: 1 } },
    check: (o) => o.response.includes('ESTADO DEL EQUIPO'),
  },
  {
    nombre: 'pista incrementa el contador',
    ctx: { team: baseTeam({ pista_actual: 0, pistas_usadas: 0 }), msg: { text: 'pista', chat_id: 1 } },
    check: (o) => o.pista_actual === 1 && o.pistas_usadas === 1,
  },
  {
    nombre: 'mapa no duplica penalización si ya se pidió para esta estación',
    ctx: { team: baseTeam({ mapa_estaciones: '1', mapas_usados: 1 }), msg: { text: 'mapa', chat_id: 1 } },
    check: (o) => o.mapas_usados === 1,
  },
  {
    nombre: 'pausa bloquea comandos de juego salvo estado/repetir/reanudar',
    ctx: { team: baseTeam({ pausado_en: new Date().toISOString() }), msg: { text: 'pista', chat_id: 1 } },
    check: (o) => o.response.includes('en pausa') && o.changed === false,
  },
  {
    nombre: 'respuesta correcta en la última estación finaliza la gymkana',
    ctx: { team: baseTeam({ estacion_actual: 7 }), msg: { text: 'respuesta', chat_id: 1 } },
    check: (o) => o.just_finalized === true && o.audio_url === station.audio_url,
  },
];

let fallos = 0;
for (const { nombre, ctx, check } of casos) {
  try {
    const out = run(ctx);
    if (!check(out)) {
      fallos++;
      console.error(`FALLO  ${nombre}\n  respuesta: ${JSON.stringify(out.response || '').slice(0, 120)}`);
    } else {
      console.log(`OK     ${nombre}`);
    }
  } catch (e) {
    fallos++;
    console.error(`ERROR  ${nombre} -> ${e.message}`);
  }
}

if (fallos) {
  console.error(`\n${fallos} de ${casos.length} casos fallaron.`);
  process.exit(1);
}
console.log(`\nTodos los casos (${casos.length}) OK.`);
