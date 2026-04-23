# PROJECT_NOTES.md — Microspeed

Documento de referencia mantenido por Devin. Se consulta al inicio de cada tarea y se actualiza con cada PR.

---

## 1. Resumen del proyecto

Juego **arcade de carreras top-down** tipo *Micro Machines* / naves estilo *Asteroids*, renderizado en un único `<canvas>` 2D. Soporta **contrarreloj en solitario** y **carreras online P2P** (hasta 7 pilotos) vía PeerJS. Estética sci‑fi / HUD futurista con Tailwind CSS.

El `package.json` está todavía con el nombre genérico `react-example` (scaffold de AI Studio). El nombre real del proyecto, según `metadata.json`, es **"Micro Machines Prototype"** y en GitHub el repo es **`ivanmunozmoreno46/Microspeed`**.

- Repo: `ivanmunozmoreno46/Microspeed`
- Rama principal: `main`
- Rama de trabajo actual: `online`
- AI Studio app: `https://ai.studio/apps/8ae17a3a-396a-4f7c-a3dd-fa95647ff3e4`
- Despliegue: aún no configurado (no hay `vercel.json`, workflows ni `Dockerfile`). Cualquier host estático de Vite sirve (Vercel/Netlify/Cloudflare Pages).

## 2. Stack

- **Frontend:** React 19 + Vite 6 + TypeScript 5.8 + Tailwind CSS 4 (vía `@tailwindcss/vite`, sin `tailwind.config.js`; el tema se define con `@theme { ... }` dentro de `src/index.css`).
- **Render:** Canvas 2D a pantalla completa (`windowSize.width × windowSize.height`), cámara centrada en el coche local, zoom `0.65` en móvil y `1.0` en desktop.
- **Multijugador:** **PeerJS** (WebRTC P2P) con sus defaults (broker + STUN/TURN gratuitos de la librería), mismo enfoque que PlayHubGX. El host abre un peer con id prefijado `microspeed-room-<CODE>` (`<CODE>` = 6 chars de `ABCDEFGHJKLMNPQRSTUVWXYZ23456789`, sin letras ambiguas). En la UI solo se muestra `<CODE>`; el prefijo sirve para namespacing en el broker compartido de PeerJS.
- **Input:** Teclado (flechas + espacio), Gamepad API (D-pad, stick izquierdo, botones A/B, gatillos L2/R2, Start) y joystick virtual en pantalla para móvil.
- **Dependencias runtime destacadas:** `react`, `react-dom`, `peerjs`, `motion`, `lucide-react`. También aparecen `@google/genai`, `express` y `dotenv` — son herencia del template de AI Studio y **no se usan** en el código actual (ver §7).
- **Node:** ≥18, **npm:** ≥9 (no fijado, pero implícito por Vite 6 y React 19).

## 3. Scripts

```bash
npm install
npm run dev       # vite --port=3000 --host=0.0.0.0  → http://localhost:3000
npm run build     # vite build → dist/
npm run preview   # sirve dist/
npm run clean     # rm -rf dist
npm run lint      # tsc --noEmit  (único control estático disponible)
```

No hay tests automatizados ni CI configurados. `npm run lint` hace solo typecheck con TypeScript.

## 4. Estructura relevante

```
.
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
├── metadata.json                # meta de AI Studio
├── README.md                    # scaffold genérico de AI Studio (ver §7)
└── src/
    ├── main.tsx                 # entry point (StrictMode + createRoot)
    ├── index.css                # Tailwind + tema + clases utilitarias (hud-panel, btn-sci-fi, glow-*)
    └── App.tsx                  # TODO el juego vive aquí (~1114 líneas): lobby, red PeerJS,
                                 # físicas, colisiones, render canvas, UI y controles táctiles.
```

## 5. Flujos principales

### 5.1 Menús (`view`)

`App` mantiene un único `view: 'lobby' | 'creating' | 'joining' | 'room_lobby' | 'playing'`.

- **lobby**: input de nombre (`playerName`, autogenerado como `Piloto-NNNN`) y tres botones: `Contrarreloj` (solo), `Crear Sala`, `Unirse a Sala`.
- **creating**: spinner mientras `Peer.on('open')` devuelve el id.
- **joining**: formulario para meter el código `XXXXXX` (6 chars) que da el host. Hay un timeout de **15 s** por si la negociación WebRTC se cuelga.
- **room_lobby**: muestra el id de sala, la lista de pilotos (hasta 7 slots) y — solo para el host — un botón "Iniciar Secuencia" que manda `{ type: 'start_race' }` a todos.
- **playing**: render del canvas + controles.

### 5.2 Red (PeerJS)

- **Host:** `createRoom()` genera un código `CODE` de 6 chars (alfabeto sin ambiguos) y abre un `Peer("microspeed-room-"+CODE, { debug: 2 })`. Acepta conexiones entrantes y mantiene un `connsRef: Map<peerId, DataConnection>`. La UI muestra solo `CODE` al usuario.
- **Cliente:** `joinRoom()` normaliza el código escrito, reconstruye el peer id `microspeed-room-<CODE>` y abre un `Peer(undefined, { debug: 2 })` anónimo que llama `peer.connect(hostPeerId)`. Errores `peer-unavailable` se traducen en "no hay ninguna sala con código X".
- **Handshake:** al abrir una conexión, el cliente envía `{ type: 'hello', name }`. El host registra el nombre en `playerNamesRef` y reemite el lobby completo con `{ type: 'lobby_sync', players, names }` a todo el mundo.
- **Mensajes definidos:**
  - `hello` → cliente → host, lleva el nickname.
  - `lobby_sync` → host → clientes, snapshot de la sala.
  - `start_race` → host → clientes, fuerza `setView('playing')`.
  - `state` → cada cliente broadcastea su posición/ángulo/vuelta/velocidad a ~30 Hz (cada 32 ms). El host actúa de **relay**: reenvía cada `state` recibido al resto de peers (topología hub‑and‑spoke).
  - `restart` → cualquiera puede pedir reinicio cuando la carrera ha terminado; el host lo reenvía al resto.
- El canal de datos es el **no fiable por defecto** de PeerJS (no se fuerza `reliable: true`), pensado para prioridad de latencia en estado de juego.

### 5.3 Bucle de juego (`gameLoop` dentro del `useEffect`)

1. **Input unificado:** teclado + gamepad + `touchKeysRef` del joystick virtual. El joystick móvil es **omnidireccional tipo Asteroids** (apunta y acelera a la vez).
2. **Físicas:** integración por pasos; aceleración `0.14`, velocidad máx `8.5`, fricción global `0.985`, rotación `0.055 rad/frame`. Si `speed < 0.05` se fuerza `vx=vy=0` para evitar deriva.
3. **Colisiones:** el coche es un rectángulo (20×10). Se obtienen las 4 esquinas rotadas y se prueba intersección segmento‑segmento contra `trackOuter` y `trackInner` (muros precalculados a partir del `centerPath` + `TRACK_WIDTH=220`). En colisión, se revierte la posición previa y `vx,vy *= -0.6`.
4. **Carrera:** 3 vueltas (`TOTAL_LAPS=3`). Un checkpoint `halfTrack` (cruzar `x > 3200`) evita contar vueltas por atravesar la línea de meta en dirección opuesta. Estados: `wait_start` (solo; espera a que el jugador se mueva), `racing`, `finished`.
5. **Broadcast** de `state` cada 32 ms.
6. **Render** por capas: fondo, decoraciones ornamentales (500 figuras pseudoaleatorias con seed fija `1337`), pista con patrón hexagonal cyan generado en un canvas offscreen, bordes, línea de meta verde, estelas (triangle strip), coches y HUD (tiempo, vuelta, nombres de rivales, mensajes centrados).
7. **Reset:** tecla `ESPACIO` (o botón `Start` del mando) cuando `mode === "finished"` dispara `resetRace()` local y manda `{ type: 'restart' }` al resto.

### 5.4 Controles

- **Desktop:** `↑ ↓` acelerar/frenar, `← →` girar, `ESPACIO` reiniciar al terminar.
- **Gamepad:** D-pad o stick izquierdo para dirección, `A` o `R2` acelerar, `B` o `L2` frenar, `Start` reiniciar. Hay un `gamepadRestartLock` para evitar reinicios repetidos al mantener pulsado.
- **Móvil / táctil:** joystick virtual izquierdo (componente `VirtualJoystick`) + botón rojo `FRENO` a la derecha. Los botones se procesan con eventos *pointer* y `touch-none` para no mover la página.

### 5.5 Cámara y escala

- Zoom `0.65` si `windowSize.width < 768`, `1.0` en otro caso.
- La cámara centra la vista en `(car.x, car.y)` trasladando `ctx` por `(-camX, -camY)` tras aplicar el `scale(zoomFactor, zoomFactor)`.
- El HUD se dibuja tras `ctx.restore()` en coordenadas de pantalla.

## 6. Convenciones del repo

- **Branches:** no se trabaja sobre `main`. Cada tarea vive en su propia rama creada por Devin (actual: `online`). Se reutiliza la rama mientras se itera sobre la misma tarea/PR y se abre una nueva cuando se empieza otra distinta.
- **PRs:** siempre hacia `main`. Mensajes de commit y títulos en imperativo y en español (siguiendo el estilo ya usado en `ivanmunozmoreno46/PlayHubGX`).
- **Estilo de código:** TypeScript estricto por `tsc --noEmit`, pero con amplio uso de `any` en el estado del juego (`gameStateRef`, mensajes de red). Al añadir código nuevo se prefiere tiparlo bien; no se hace refactor masivo del `any` existente salvo que la tarea lo pida.
- **Todo el juego vive en `src/App.tsx`.** Cuando una feature crezca lo suficiente (IA, persistencia, nuevos circuitos, red más compleja…) es aceptable partirlo en módulos bajo `src/` (p.ej. `src/game/`, `src/net/`, `src/ui/`); mientras no sea necesario, se mantiene el fichero único para no aumentar la complejidad de imports.
- **Sin linter/formatter** (Prettier, ESLint…). Se respeta la indentación existente (2 espacios) y el uso de comillas simples.
- **Assets pesados:** no añadir binarios al repo salvo que sean imprescindibles; preferir generar geometría/patrones procedurales como el patrón hexagonal actual.

## 7. Deuda técnica detectada

1. `package.json` → `name: "react-example"`, `version: "0.0.0"` — scaffold sin personalizar.
2. El `README.md` es el genérico de AI Studio ("Run and deploy your AI Studio app", `GEMINI_API_KEY` en `.env.local`) y **no describe nada de lo que hace realmente el juego**. Habría que reescribirlo.
3. Dependencias no usadas actualmente:
   - `@google/genai` (integración Gemini) — sin imports en el código.
   - `express`, `@types/express`, `tsx` — no hay ningún servidor Node/`server.ts`; vienen del template.
   - `dotenv` — Vite ya carga `.env*` por sí solo.
   - `motion` y `lucide-react` — instaladas pero no importadas en `App.tsx` actualmente.
4. `vite.config.ts` inyecta `process.env.GEMINI_API_KEY` aunque el juego no lo necesita.
5. **No hay `.gitignore`** en el repo. Cualquier `node_modules/`, `dist/`, `.env*` podría acabar commiteado por accidente. Crear uno estándar de Node/Vite es prioritario.
6. **Tipado:** `gs` (`gameStateRef.current`) y los mensajes PeerJS son `any`. Un `type` compartido (`GameMessage = HelloMsg | LobbySyncMsg | StateMsg | RestartMsg | StartRaceMsg`) evitaría bugs al añadir nuevos mensajes.
7. **Arquitectura de red:** el host es *relay* único para los `state`; si el host cae, la partida se rompe (cliente muestra "El anfitrión se ha desconectado" y vuelve al lobby). No hay reconexión ni migración de host.
8. **Autoridad:** cada cliente es autoritativo sobre su propio coche (incluida la detección de colisiones y vueltas). Esto es sencillo pero permite trampas triviales (teletransporte, vueltas instantáneas). Aceptable como prototipo, a documentar si se quiere competitivo.
9. **Colisiones entre coches:** no existen; los rivales son "fantasmas" que se cruzan entre sí.
10. **`finishLine` y checkpoints** están hardcodeados para el circuito único actual (`centerPath`). Añadir más pistas requeriría extraer la detección de vueltas a una función por-pista.
11. **Tamaño de `App.tsx`** (~1100 líneas). Ver §6: no urge, pero es ya el límite cómodo de un solo fichero.
12. **`StrictMode`** en `main.tsx` provoca que los `useEffect` con `view === 'playing'` y la creación de `Peer` puedan ejecutarse dos veces en desarrollo. El código actual reusa `gameStateRef.current` para sobrevivir a un doble mount, pero conviene tenerlo presente al añadir efectos nuevos.
13. **Sin pre-commit hooks** (`.husky/`, `.pre-commit-config.yaml`) y sin CI. Cualquier regresión de types se descubre solo ejecutando `npm run lint` manualmente.

## 8. Documentación auxiliar ya existente

- `README.md` — scaffold genérico de AI Studio (no describe el juego).
- `metadata.json` — nombre y descripción del prototipo para AI Studio.

(Este `PROJECT_NOTES.md` es, por ahora, el único documento vivo del proyecto).

## 9. Reglas de trabajo para Devin

Pensadas para este repo y para cómo trabaja el usuario (ver histórico de PRs en `ivanmunozmoreno46/PlayHubGX`):

1. **Antes de tocar código**: leer `PROJECT_NOTES.md`, `README.md` y `package.json`. Actualizar este fichero al final de cada tarea (§10).
2. **Ramas**: no commitear en `main`. Usar la rama de la tarea actual (hoy `online`). Abrir una nueva solo cuando se inicie una tarea distinta que el usuario pida.
3. **PRs**: siempre hacia `main`. Título y descripción en español, en imperativo. Incluir en la descripción:
   - Qué se ha hecho.
   - Por qué (motivación / problema que resuelve).
   - Cómo probarlo manualmente.
   - Notas para `PROJECT_NOTES.md` si aplica.
4. **Lint obligatorio antes de cada PR**: `npm run lint` (= `tsc --noEmit`) debe pasar. Si TypeScript se queja de `any` preexistentes, no bloquea; si se queja de código nuevo, sí hay que arreglarlo.
5. **Build** (`npm run build`) debe completar sin errores antes del PR si la tarea modifica Vite/TS/CSS/entrypoints.
6. **Sin tests automatizados**: el testing es manual (dev server + dos pestañas del navegador para simular host+cliente). Si una feature es suficientemente grande, detallar en el PR los pasos de prueba.
7. **No introducir dependencias nuevas sin necesidad real**. Preferir implementaciones pequeñas sobre paquetes npm.
8. **No subir secretos** ni `.env.local`. Si una feature los necesita, documentar en el README y en `.env.example`.
9. **No añadir binarios ni assets pesados** al repo salvo que sean imprescindibles para la feature.
10. **Conservar el estilo visual**: paleta actual (`#00f3ff` cyan, `#f27d26` naranja, fondo `#09090b`/`#1a1a1e`), fuentes *Space Grotesk* + *JetBrains Mono*, clases utilitarias `hud-panel`, `btn-sci-fi`, `glow-text-*`.
11. **Idioma del contenido visible al usuario**: español (ya usado en todo el `App.tsx`). Comentarios de código también en español para mantener coherencia con lo existente.
12. **Mobile first cuando aplique**: el juego ya tiene joystick virtual y detección `windowSize.width < 768`; cualquier UI nueva debe considerar ese breakpoint.

## 10. Histórico de cambios (Devin)

| Fecha (UTC) | Rama | PR | Descripción |
|---|---|---|---|
| 2026-04-23 | `online` | — | Creación de la rama `online` a partir de `main` (commit `338f84b`). Sin cambios de código. |
| 2026-04-23 | `online` | #1 | Análisis inicial del proyecto y creación de este `PROJECT_NOTES.md` como documento vivo para las siguientes tareas. Añadido `.gitignore` estándar y `.env.example`. |
| 2026-04-23 | `online` | #1 | **Fix online fuera de LAN**: el `new Peer(...)` usaba solo STUN por defecto, así que cualquier CGNAT/operador móvil/firewall restrictivo rompía la conexión. Se introduce `PEER_OPTIONS` con `iceServers` = `stun.l.google.com` + `global.stun.twilio.com` + TURN público de Metered OpenRelay (`openrelay.metered.ca:80/443` UDP y TCP). Se puede sobrescribir con `VITE_TURN_URL` / `VITE_TURN_USERNAME` / `VITE_TURN_CREDENTIAL` (Twilio/Cloudflare Realtime/Xirsys/coturn propio). Aplica tanto al host (`createRoom`) como al cliente (`joinRoom`). |
