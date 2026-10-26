"""Kart Racer – Mehrspieler-Server.

Liefert index.html aus und verteilt per WebSocket die Zustände aller Spieler
(ihre "presence") an alle anderen im selben Raum. Nur Python-Standardbibliothek.

Start:  python server.py            (Port 8000, oder Umgebungsvariable PORT)
Spielen: http://localhost:8000      eigener Raum: http://localhost:8000/?raum=klasse10b
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import re
import secrets
import struct
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
ROOT = Path(__file__).resolve().parent
PORT = int(os.environ.get("PORT", "8000"))
MAX_FRAME = 16 * 1024      # größte erlaubte Nachricht vom Browser
MAX_PRESENCE = 4096        # größter erlaubter Spielerzustand (JSON-Bytes)
MAX_PER_ROOM = 16          # Zuschauer inklusive; fahren können davon 4
IDLE_TIMEOUT = 60          # Sekunden ohne Nachricht, dann gilt die Verbindung als tot

rooms: dict[str, dict[str, "Client"]] = {}


class Client:
    def __init__(self, writer: asyncio.StreamWriter, room: str):
        self.writer = writer
        self.room = room
        self.peer = secrets.token_hex(6)
        self.presence: dict = {}

    def send_raw(self, opcode: int, data: bytes) -> None:
        if self.writer.is_closing():
            return
        n = len(data)
        if n < 126:
            header = struct.pack("!BB", 0x80 | opcode, n)
        elif n < 65536:
            header = struct.pack("!BBH", 0x80 | opcode, 126, n)
        else:
            header = struct.pack("!BBQ", 0x80 | opcode, 127, n)
        self.writer.write(header + data)
        # langsamer Empfänger staut sich auf -> rauswerfen statt Speicher zu fressen
        if self.writer.transport.get_write_buffer_size() > 1_000_000:
            self.writer.close()

    def send(self, obj) -> None:
        self.send_raw(0x1, json.dumps(obj, separators=(",", ":")).encode())


def broadcast(room: str, obj, exclude: Client | None = None) -> None:
    for c in list(rooms.get(room, {}).values()):
        if c is not exclude:
            c.send(obj)


async def read_frame(reader: asyncio.StreamReader) -> tuple[int, bytes]:
    b0, b1 = await reader.readexactly(2)
    opcode, n = b0 & 0x0F, b1 & 0x7F
    if n == 126:
        (n,) = struct.unpack("!H", await reader.readexactly(2))
    elif n == 127:
        (n,) = struct.unpack("!Q", await reader.readexactly(8))
    if n > MAX_FRAME:
        raise ValueError("Nachricht zu groß")
    mask = await reader.readexactly(4) if b1 & 0x80 else b""
    payload = await reader.readexactly(n)
    if mask:
        payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    return opcode, payload


def apply_patch(client: Client, patch) -> bool:
    if not isinstance(patch, dict):
        return False
    merged = dict(client.presence)
    for key, value in patch.items():
        if not isinstance(key, str) or len(key) > 32:
            return False
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    if len(json.dumps(merged, separators=(",", ":"))) > MAX_PRESENCE:
        return False
    client.presence = merged
    return True


async def websocket(reader, writer, headers: dict, query: dict) -> None:
    key = headers.get("sec-websocket-key", "")
    raw_room = (query.get("raum") or ["lobby"])[0].lower()
    room = re.sub(r"[^a-z0-9-]", "", raw_room)[:32] or "lobby"
    members = rooms.setdefault(room, {})
    if not key or len(members) >= MAX_PER_ROOM:
        writer.write(b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
        return
    accept = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
    writer.write(
        "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
        f"Sec-WebSocket-Accept: {accept}\r\n\r\n".encode()
    )

    client = Client(writer, room)
    client.send({"t": "hello", "you": client.peer, "room": room,
                 "peers": [{"peer": c.peer, "p": c.presence} for c in members.values()]})
    members[client.peer] = client
    print(f"[{room}] +{client.peer} ({len(members)} verbunden)")
    try:
        while True:
            opcode, payload = await asyncio.wait_for(read_frame(reader), IDLE_TIMEOUT)
            if opcode == 0x8:          # Close
                break
            if opcode == 0x9:          # Ping -> Pong
                client.send_raw(0xA, payload)
            elif opcode == 0x1:        # Text
                try:
                    msg = json.loads(payload)
                except ValueError:
                    continue
                if isinstance(msg, dict) and msg.get("t") == "p" and apply_patch(client, msg.get("d")):
                    broadcast(room, {"t": "p", "peer": client.peer, "p": client.presence}, exclude=client)
    except (asyncio.IncompleteReadError, asyncio.TimeoutError, ConnectionError, ValueError):
        pass
    finally:
        members.pop(client.peer, None)
        if not members:
            rooms.pop(room, None)
        broadcast(room, {"t": "left", "peer": client.peer})
        print(f"[{room}] -{client.peer} ({len(members)} verbunden)")


async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        request = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 10)
        lines = request.decode("latin-1").split("\r\n")
        method, target, _ = lines[0].split(" ", 2)
        headers = {}
        for line in lines[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip().lower()] = v.strip()
        url = urlsplit(target)

        if url.path == "/ws" and headers.get("upgrade", "").lower() == "websocket":
            await websocket(reader, writer, headers, parse_qs(url.query))
        elif method in ("GET", "HEAD") and url.path in ("/", "/index.html"):
            body = (ROOT / "index.html").read_bytes()
            writer.write(
                b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
                b"Cache-Control: no-cache\r\nContent-Length: %d\r\nConnection: close\r\n\r\n" % len(body)
                + (body if method == "GET" else b"")
            )
        else:
            writer.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
        await writer.drain()
    except (asyncio.IncompleteReadError, asyncio.TimeoutError, asyncio.LimitOverrunError,
            ConnectionError, ValueError):
        pass
    finally:
        writer.close()


async def main() -> None:
    server = await asyncio.start_server(handle, "0.0.0.0", PORT)
    print(f"Kart Racer läuft auf http://localhost:{PORT}  (Strg+C beendet)")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
