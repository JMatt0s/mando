"""
Mando PES 6 v2 - Servidor en Python
-----------------------------------
Sirve la página del mando (HTTP) y recibe los botones por WebSocket para
simular el teclado en el PC.

Instalación:
    pip install -U websockets pynput pydirectinput

(pydirectinput es opcional pero RECOMENDADO en Windows: PES 6 usa DirectInput
y muchas veces ignora las teclas enviadas por pynput.)

Uso:
    1. Ejecuta este archivo en el PC donde corre PES 6 (mejor como administrador).
    2. Abre en el celular la dirección completa que se imprime (incluye el token).
    3. Pon el celular en horizontal.
"""

import asyncio
import secrets
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import websockets

HTTP_PORT = 8000
WS_PORT = 8765
TOKEN = secrets.token_urlsafe(8)  # solo quien tenga la URL impresa puede conectarse

# ---------------------------------------------------------------
# Mapa botón -> tecla. Ajústalo a tu configuración de PES 6.
# Nombres de tecla estilo pydirectinput: "up", "down", "left", "right",
# letras ("a"), "enter", "esc", "space", "shift", "ctrl"...
# ---------------------------------------------------------------
KEYMAP = {
    "UP": "up",
    "DOWN": "down",
    "LEFT": "left",
    "RIGHT": "right",
    "CORRER": "d",                 # R1
    "CAMBIAR_CURSOR": "w",         # L1
    "ESTRATEGIA": "q",             # L2
    "CONTROLES_ESPACIALES": "e",   # R2
    "PASE_ADELANTADO": "a",        # △
    "PASE_CORTO": "z",             # ✕
    "DISPARO": "x",                # □
    "PASE_LARGO": "s",             # ○
    "START": "enter",
    "SELECT": "esc",
}

# ---------------------------------------------------------------
# Backend de teclado: pydirectinput si existe, si no pynput
# ---------------------------------------------------------------
try:
    import pydirectinput

    pydirectinput.PAUSE = 0
    pydirectinput.FAILSAFE = False

    def key_down(name):
        pydirectinput.keyDown(name)

    def key_up(name):
        pydirectinput.keyUp(name)

    BACKEND = "pydirectinput"
except ImportError:
    from pynput.keyboard import Controller, Key

    _kb = Controller()
    _SPECIAL = {
        "up": Key.up, "down": Key.down, "left": Key.left, "right": Key.right,
        "enter": Key.enter, "esc": Key.esc, "space": Key.space,
        "shift": Key.shift, "ctrl": Key.ctrl, "tab": Key.tab,
    }

    def _k(name):
        return _SPECIAL.get(name, name)

    def key_down(name):
        _kb.press(_k(name))

    def key_up(name):
        _kb.release(_k(name))

    BACKEND = "pynput"

HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
<title>Mando PES 6</title>
<style>
  * { box-sizing: border-box; user-select: none; -webkit-user-select: none;
      touch-action: none; -webkit-tap-highlight-color: transparent; }
  html, body { height: 100%; }
  body { margin: 0; background: #ac8080; color: white; font-family: sans-serif;
         display: flex; justify-content: space-between; align-items: center;
         height: 100dvh; padding: 16px; overflow: hidden; }
  .zone { position: relative; width: 42vw; height: 80%; }
  .center { width: 12vw; display: flex; flex-direction: column; gap: 14px;
            align-items: center; justify-content: center; }
  .btn { position: absolute; background: #2c2c2c; border: 2px solid #555; color: white;
         border-radius: 50%; width: 72px; height: 72px; font-size: 20px; font-weight: bold;
         display: flex; justify-content: center; align-items: center; }
  .btn.pressed { background: #00a8ff; border-color: #fff; }
  .sh { border-radius: 12px; width: 80px; height: 42px; font-size: 16px; top: 0; }
  .small { position: static; border-radius: 12px; width: 76px; height: 36px; font-size: 13px; }

  /* Gatillos */
  #CAMBIAR_CURSOR { left: 5%; }
  #ESTRATEGIA { left: calc(5% + 90px); }
  #CORRER { right: 5%; }
  #CONTROLES_ESPACIALES { right: calc(5% + 90px); }
  /* Botones de acción */
  #PASE_ADELANTADO { top: 22%;    left: calc(50% - 36px); color: #4cd137; }
  #PASE_CORTO      { bottom: 6%;  left: calc(50% - 36px); color: #00a8ff; }
  #DISPARO         { top: 46%;    left: 4%;  color: #e84118; transform: translateY(-50%); }
  #PASE_LARGO      { top: 46%;    right: 4%; color: #fbc531; transform: translateY(-50%); }

  /* Palanca */
  #stick { position: absolute; width: 170px; height: 170px; left: calc(50% - 85px);
           top: calc(50% - 60px); border-radius: 50%; background: rgba(0,0,0,0.35);
           border: 2px solid #777; }
  #knob { position: absolute; width: 64px; height: 64px; left: 50%; top: 50%;
          margin-left: -32px; margin-top: -32px; border-radius: 50%;
          background: #3d3d3d; border: 2px solid #aaa; }
  #status { position: fixed; top: 4px; left: 50%; transform: translateX(-50%);
            font-size: 12px; padding: 2px 10px; border-radius: 10px; background: #b33; }
  #status.ok { background: #2a7; }
</style>
</head>
<body>
  <div id="status">desconectado</div>

  <div class="zone">
    <div class="btn sh" id="CAMBIAR_CURSOR">L1</div>
    <div class="btn sh" id="ESTRATEGIA">L2</div>
    <div id="stick"><div id="knob"></div></div>
  </div>

  <div class="center">
    <div class="btn small" id="SELECT">SELECT</div>
    <div class="btn small" id="START">START</div>
  </div>

  <div class="zone">
    <div class="btn sh" id="CORRER">R1</div>
    <div class="btn sh" id="CONTROLES_ESPACIALES">R2</div>
    <div class="btn" id="PASE_ADELANTADO">△</div>
    <div class="btn" id="PASE_CORTO">✕</div>
    <div class="btn" id="DISPARO">□</div>
    <div class="btn" id="PASE_LARGO">○</div>
  </div>

<script>
  const TOKEN = "__TOKEN__";
  const WS_URL = `ws://${location.hostname}:__WS_PORT__`;
  const statusEl = document.getElementById('status');
  let ws = null;
  const held = new Set();   // lo que está presionado ahora mismo

  function send(msg) {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(msg);
  }

  function connect() {
    ws = new WebSocket(WS_URL);
    ws.onopen = () => {
      ws.send('AUTH:' + TOKEN);
      statusEl.textContent = 'conectado';
      statusEl.classList.add('ok');
      held.forEach(n => ws.send('DOWN:' + n));   // restablece lo que siga presionado
    };
    ws.onclose = () => {
      statusEl.textContent = 'desconectado';
      statusEl.classList.remove('ok');
      setTimeout(connect, 1000);                 // reconexión automática
    };
    ws.onerror = () => ws.close();
  }
  connect();

  function setState(name, on) {
    if (on === held.has(name)) return;
    on ? held.add(name) : held.delete(name);
    send((on ? 'DOWN:' : 'UP:') + name);
  }

  // ---------- Botones (funciona con dedo y con mouse) ----------
  document.querySelectorAll('.btn').forEach(btn => {
    const down = e => {
      e.preventDefault();
      btn.setPointerCapture(e.pointerId);
      btn.classList.add('pressed');
      setState(btn.id, true);
    };
    const up = e => {
      e.preventDefault();
      btn.classList.remove('pressed');
      setState(btn.id, false);
    };
    btn.addEventListener('pointerdown', down);
    btn.addEventListener('pointerup', up);
    btn.addEventListener('pointercancel', up);
    btn.addEventListener('lostpointercapture', up);
  });

  // ---------- Palanca (8 direcciones por ángulo) ----------
  const stick = document.getElementById('stick');
  const knob = document.getElementById('knob');
  const maxR = 52;    // recorrido máximo del botón de la palanca (px)
  const dead = 16;    // zona muerta (px)
  let stickPointer = null;

  function applyStick(x, y) {
    const r = stick.getBoundingClientRect();
    const dx = x - (r.left + r.width / 2);
    const dy = y - (r.top + r.height / 2);
    const dist = Math.hypot(dx, dy);
    const k = dist > maxR ? maxR / dist : 1;
    const nx = dx * k, ny = dy * k;
    knob.style.transform = `translate(${nx}px, ${ny}px)`;

    const active = dist > dead;
    const ang = Math.atan2(dy, dx) * 180 / Math.PI;   // 0=der, 90=abajo, -90=arriba
    setState('RIGHT', active && Math.abs(ang) < 67.5);
    setState('LEFT',  active && Math.abs(ang) > 112.5);
    setState('DOWN',  active && ang > 22.5 && ang < 157.5);
    setState('UP',    active && ang < -22.5 && ang > -157.5);
  }

  function resetStick() {
    knob.style.transform = 'translate(0px, 0px)';
    ['UP', 'DOWN', 'LEFT', 'RIGHT'].forEach(d => setState(d, false));
    stickPointer = null;
  }

  stick.addEventListener('pointerdown', e => {
    e.preventDefault();
    if (stickPointer !== null) return;
    stickPointer = e.pointerId;
    stick.setPointerCapture(e.pointerId);
    applyStick(e.clientX, e.clientY);
  });
  stick.addEventListener('pointermove', e => {
    if (e.pointerId === stickPointer) applyStick(e.clientX, e.clientY);
  });
  const endStick = e => { if (e.pointerId === stickPointer) resetStick(); };
  stick.addEventListener('pointerup', endStick);
  stick.addEventListener('pointercancel', endStick);
  stick.addEventListener('lostpointercapture', endStick);

  // Si la pantalla se apaga o cambias de app, suelta todo
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      resetStick();
      [...held].forEach(n => setState(n, false));
      document.querySelectorAll('.pressed').forEach(b => b.classList.remove('pressed'));
    }
  });
</script>
</body>
</html>
""".replace("__WS_PORT__", str(WS_PORT)).replace("__TOKEN__", TOKEN)


class PageHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        if query.get("t", [""])[0] != TOKEN:
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b"Acceso denegado. Usa la URL completa que imprime el programa.")
            return
        data = HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def start_http():
    ThreadingHTTPServer(("0.0.0.0", HTTP_PORT), PageHandler).serve_forever()


async def handler(websocket):
    pressed = set()
    try:
        # El primer mensaje debe ser la autenticación
        first = await asyncio.wait_for(websocket.recv(), timeout=5)
        if not isinstance(first, str) or first != f"AUTH:{TOKEN}":
            await websocket.close(code=1008, reason="no autorizado")
            return

        async for message in websocket:
            if not isinstance(message, str):
                continue
            state, sep, btn = message.partition(":")
            key = KEYMAP.get(btn)
            if not sep or key is None:
                continue
            if state == "DOWN" and btn not in pressed:
                key_down(key)
                pressed.add(btn)
            elif state == "UP" and btn in pressed:
                key_up(key)
                pressed.discard(btn)
    except (asyncio.TimeoutError, websockets.ConnectionClosed):
        pass
    finally:
        # Si el celular se desconecta, suelta todas las teclas
        for btn in pressed:
            key_up(KEYMAP[btn])


def local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


async def main():
    threading.Thread(target=start_http, daemon=True).start()
    print(f"Teclado: {BACKEND}")
    print(f"Abre en el celular: http://{local_ip()}:{HTTP_PORT}/?t={TOKEN}")
    async with websockets.serve(handler, "0.0.0.0", WS_PORT, compression=None):
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass