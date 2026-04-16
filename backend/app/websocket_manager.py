from __future__ import annotations

from fastapi import WebSocket


class WebSocketManager:
    def __init__(self) -> None:
        self._socket: WebSocket | None = None

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._socket = websocket

    def disconnect(self, websocket: WebSocket) -> None:
        if self._socket is websocket:
            self._socket = None

    async def send_json(self, payload: dict) -> None:
        if self._socket:
            await self._socket.send_json(payload)

    async def send_error(self, code: str, detail: str) -> None:
        await self.send_json(
            {
                "type": "error",
                "payload": {
                    "code": code,
                    "detail": detail,
                },
            }
        )


websocket_manager = WebSocketManager()

