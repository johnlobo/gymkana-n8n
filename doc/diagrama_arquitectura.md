# Diagrama de arquitectura

Vista general del flujo del bot: desde que Telegram entrega un mensaje hasta que sale una respuesta (texto, foto, documento o diploma), pasando por deduplicación, la máquina de estados principal y las distintas ramas de entrega.

![Diagrama de arquitectura](./img/diagrama_arquitectura.png)

*(Versión estática. La documentación interactiva — con tooltips por nodo y navegación por flujo — vive en `documentacion_gymkana.html`, pestaña "Diagrama interactivo".)*

## Leyenda de colores

| Color | Tipo de nodo |
|---|---|
| 🩷 Rosa | Cliente (Telegram, el jugador) |
| 🟠 Naranja | Trigger / servicio externo |
| 🔵 Azul | Lógica (Code, IF, Switch) |
| 🟢 Verde | Datos (lectura/escritura en Firestore) |
| 🟣 Morado | Entrega (envío de mensajes/fotos/documentos) |

## Flujos principales

1. Alta de equipo (`/start`)
2. Registro del nombre del equipo (asigna el enclave de inicio por round-robin)
3. Llegar al punto de inicio (ubicación GPS)
4. Responder correctamente a un acertijo
5. Completar el último enclave propio → "¡código completo!"
6. `/rescate` cuando el acertijo aún no se ha mostrado
7. `/rescate` cuando el acertijo ya se había mostrado
8. `/pista`
9. `/mapa`
10. `/estado`
11. Completar la gymkana (acertijo del enclave secreto) — dispara además, en paralelo, la generación del diploma
12. Repetir el resumen tras finalizar (`/repetir`) — regenera y reenvía también el diploma
13. `/move <n>` (depuración)
14. `/reboot` (depuración)
15. Reintento de Telegram (deduplicación)
16. Panel admin (`/admin`, oculto)
