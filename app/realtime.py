from __future__ import annotations

from collections import defaultdict

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self.connections: dict[int, set[WebSocket]] = defaultdict(set)

    async def connect(self, user_id: int, websocket: WebSocket, subprotocol: str | None = None) -> None:
        await websocket.accept(subprotocol=subprotocol)
        self.connections[user_id].add(websocket)

    def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        self.connections[user_id].discard(websocket)
        if not self.connections[user_id]:
            self.connections.pop(user_id, None)

    async def send_to_user(self, user_id: int, payload: dict) -> None:
        dead: list[WebSocket] = []
        for websocket in self.connections.get(user_id, set()):
            try:
                await websocket.send_json(payload)
            except RuntimeError:
                dead.append(websocket)
        for websocket in dead:
            self.disconnect(user_id, websocket)

    async def broadcast(self, payload: dict) -> None:
        for user_id in list(self.connections):
            await self.send_to_user(user_id, payload)


manager = ConnectionManager()
