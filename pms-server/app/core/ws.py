"""Shared WebSocket connection manager — imported by main.py and routers."""
import json
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self._active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self._active:
            self._active.remove(ws)

    async def broadcast(self, data: dict):
        dead: list[WebSocket] = []
        payload = json.dumps(data)
        for ws in self._active:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._active.remove(ws)

    @property
    def connection_count(self) -> int:
        return len(self._active)


# Singleton used by all routers
ws_manager = ConnectionManager()
