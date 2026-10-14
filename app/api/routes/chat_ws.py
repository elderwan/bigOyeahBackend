from collections import defaultdict
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import text

from app.core.security import decode_access_token
from app.db.session import app_session_factory

router = APIRouter()


class ChatConnectionManager:
    def __init__(self) -> None:
        # Map user_id to list of active WebSocket connections
        self.active_connections: dict[int, list[WebSocket]] = defaultdict(list)

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections[user_id].append(websocket)

    def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        if user_id in self.active_connections:
            self.active_connections[user_id] = [
                ws for ws in self.active_connections[user_id] if ws != websocket
            ]
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]

    async def send_to_user(self, user_id: int, message: dict[str, Any]) -> None:
        if user_id in self.active_connections:
            dead_connections = []
            for ws in self.active_connections[user_id]:
                try:
                    await ws.send_json(message)
                except Exception:
                    dead_connections.append(ws)
            for ws in dead_connections:
                self.disconnect(user_id, ws)

    async def broadcast(self, message: dict[str, Any]) -> None:
        for user_id in list(self.active_connections.keys()):
            await self.send_to_user(user_id, message)


chat_manager = ChatConnectionManager()


@router.websocket("/ws/chat")
async def chat_websocket_endpoint(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token")
    if not token:
        # Check subprotocol or close
        await websocket.close(code=1008)
        return

    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        await websocket.close(code=1008)
        return

    user_id = payload.get("sub")
    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        await websocket.close(code=1008)
        return

    await chat_manager.connect(user_id, websocket)
    try:
        # Send initial connected confirmation
        await websocket.send_json({
            "type": "connection_established",
            "user_id": user_id,
            "message": "Connected to FitBooking real-time chat service",
        })

        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "ping")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
            elif msg_type == "message":
                recipient_user_id = data.get("recipient_user_id")
                content = data.get("message_text", "").strip()
                if recipient_user_id and content:
                    out_msg = {
                        "type": "new_message",
                        "sender_user_id": user_id,
                        "recipient_user_id": int(recipient_user_id),
                        "message_text": content,
                    }
                    await chat_manager.send_to_user(int(recipient_user_id), out_msg)
                    # Acknowledge sender
                    await websocket.send_json({"type": "message_sent", "status": "ok"})
    except WebSocketDisconnect:
        chat_manager.disconnect(user_id, websocket)
    except Exception:
        chat_manager.disconnect(user_id, websocket)
