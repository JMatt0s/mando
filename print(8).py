import asyncio
import socket
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
import websockets
from pynput.keyboard import Controller, Key

keyboard = Controller()

# Mapeo de botones del celular a teclas de PES 6 (configuración clásica)
KEY_MAP = {
    "UP": Key.up,
    "DOWN": Key.down,
    "LEFT": Key.left,
    "RIGHT": Key.right,
    "PASS": "s",      # X (Pase corto)
    "THROUGH": "w",   # Triángulo (Pase al hueco)
    "SHOOT": "d",     # Cuadrado (Tiro)
    "CROSS": "a",     # Círculo (Centro / Barrida)
    "SPRINT": "e"     # R1 (Correr)
}

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

# Servidor HTTP para entregar el index.html al celular
def start_http_server():
    server = HTTPServer(("0.0.0.0", 8000), SimpleHTTPRequestHandler)
    server.serve_forever()

# Servidor WebSocket para recibir los botones en tiempo real
async def handle_controller(websocket):
    print("Celular conectado al mando.")
    try:
        async for message in websocket:
            action, button = message.split(":")
            key = KEY_MAP.get(button)
            if key:
                if action == "DOWN":
                    keyboard.press(key)
                elif action == "UP":
                    keyboard.release(key)
    except websockets.exceptions.ConnectionClosed:
        print("Celular desconectado.")

async def main():
    ip = get_local_ip()
    threading.Thread(target=start_http_server, daemon=True).start()
    
    print(f"1. Abre el navegador en tu celular (conectado al mismo Wi-Fi).")
    print(f"2. Entra a: http://{ip}:8000")
    
    async with websockets.serve(handle_controller, "0.0.0.0", 8765):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())