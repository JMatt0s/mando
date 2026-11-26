
import asyncio
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import websockets
from pynput.keyboard import Controller, Key

HTTP_PORT = 8000
WS_PORT = 8765

# ---------------------------------------------------------------
# Mapa botón -> tecla del teclado. Ajústalo a tu configuración de PES 6.
# ---------------------------------------------------------------
KEYMAP = {
    "UP": Key.up,
    "DOWN": Key.down,
    "LEFT": Key.left,
    "RIGHT": Key.right,
    "CORRER": "d",             # R1
    "CAMBIAR_CURSOR": "w",     # L1
    "ESTRATEGIA": "q",         # L2
    "CONTROLES_ESPACIALES": "e",  # R2
    "PASE_ADELANTADO": "a",    # △
    "PASE_CORTO": "z",         # ✕
    "DISPARO": "x",            # □
    "PASE_LARGO": "s",         # ○
}

HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Mando PES 6</title>
<style>
  * { box-sizing: border-box; user-select: none; -webkit-user-select: none; touch-action: none; }
  body { margin: 0; background: #ac8080; color: white; font-family: sans-serif;
         display: flex; justify-content: space-between; align-items: center;
         height: 100vh; padding: 20px; overflow: hidden; }
  .zone { position: relative; width: 42vw; height: 80vh; }
  .btn { position: absolute; background: #2c2c2c; border: 2px solid #555; color: white;
         border-radius: 50%; width: 72px; height: 72px; font-size: 20px; font-weight: bold;
         display: flex; justify-content: center; align-items: center; }
  .btn.pressed { background: #00a8ff; border-color: #fff; }
  /* Cruceta */
  #UP    { top: 15%;    left: calc(50% - 36px); }
  #DOWN  { bottom: 5%;  left: calc(50% - 36px); }
  #LEFT  { top: 42%;    left: 5%; }
  #RIGHT { top: 42%;    right: 5%; }
  /* Gatillos */
  .sh { border-radius: 12px; width: 80px; height: 42px; font-size: 16px; top: 0; }
  #CAMBIAR_CURSOR { left: 5%; }
  #CORRER { right: 5%; }
  #ESTRATEGIA { left: calc(5% + 90px); }
  #CONTROLES_ESPACIALES { right: calc(5% + 90px); }
  /* Botones PS */
  #PASE_ADELANTADO { top: 15%;   left: calc(50% - 36px); color: #4cd137; }
  #PASE_CORTO      { bottom: 5%; left: calc(50% - 36px); color: #00a8ff; }
  #DISPARO         { top: 42%;   left: 5%;  color: #e84118; }
  #PASE_LARGO      { top: 42%;   right: 5%; color: #fbc531; }
</style>
</head>
<body>
  <div class="zone">
    <div class="btn sh" id="CAMBIAR_CURSOR">L1</div>
    <div class="btn sh" id="ESTRATEGIA">L2</div>
    <div class="btn" id="UP">▲</div>
    <div class="btn" id="DOWN">▼</div>
    <div class="btn" id="LEFT">◀</div>
    <div class="btn" id="RIGHT">▶</div>
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
  const ws = new WebSocket(`ws://${window.location.hostname}:__WS_PORT__`);
  document.querySelectorAll('.btn').forEach(btn => {
    const send = (state, e) => {
      e.preventDefault();
      btn.classList.toggle('pressed', state === 'DOWN');
      if (ws.readyState === WebSocket.OPEN) ws.send(`${state}:${btn.id}`);
    };
    btn.addEventListener('touchstart', e => send('DOWN', e));
    btn.addEventListener('touchend', e => send('UP', e));
    btn.addEventListener('touchcancel', e => send('UP', e));
  });
</script>
</body>
</html>
""".replace("__WS_PORT__", str(WS_PORT))


class PageHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        data = HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def start_http():
    HTTPServer(("0.0.0.0", HTTP_PORT), PageHandler).serve_forever()


keyboard = Controller()


async def handler(websocket):
    pressed = set()
    try:
        async for message in websocket:
            try:
                state, btn = message.split(":", 1)
            except ValueError:
                continue
            key = KEYMAP.get(btn)
            if key is None:
                continue
            if state == "DOWN" and btn not in pressed:
                keyboard.press(key)
                pressed.add(btn)
            elif state == "UP" and btn in pressed:
                keyboard.release(key)
                pressed.discard(btn)
    finally:
        # Si el celular se desconecta, suelta todas las teclas
        for btn in pressed:
            keyboard.release(KEYMAP[btn])


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
    print(f"Abre en el celular: http://{local_ip()}:{HTTP_PORT}")
    async with websockets.serve(handler, "0.0.0.0", WS_PORT):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
