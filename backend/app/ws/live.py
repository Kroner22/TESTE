from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..log_config import get_logger
from ..middleware.rate_limit import get_rate_limiter
from ..monitoring.metrics import ws_connections_total, ws_connections_active, ws_messages_total

router = APIRouter(tags=["ws"])
logger = get_logger(__name__)


@dataclass
class ConnectionManager:
    max_clients: int = 10000
    max_backpressure: int = 128

    _connections: dict[str, WebSocket] = field(default_factory=dict)
    _channels: dict[str, set[str]] = field(default_factory=dict)

    @property
    def active_count(self) -> int:
        return len(self._connections)

    async def connect(self, client_id: str, ws: WebSocket) -> bool:
        if len(self._connections) >= self.max_clients:
            logger.warning("max_connections_reached", client_id=client_id)
            return False
        self._connections[client_id] = ws
        ws_connections_total.inc()
        ws_connections_active.set(self.active_count)
        logger.info("ws_connected", client_id=client_id, active=self.active_count)
        return True

    async def disconnect(self, client_id: str) -> None:
        self._connections.pop(client_id, None)
        for channel, members in self._channels.items():
            members.discard(client_id)
        ws_connections_active.set(self.active_count)
        logger.info("ws_disconnected", client_id=client_id, active=self.active_count)

    async def subscribe(self, client_id: str, channel: str) -> None:
        if channel not in self._channels:
            self._channels[channel] = set()
        self._channels[channel].add(client_id)

    async def unsubscribe(self, client_id: str, channel: str) -> None:
        if channel in self._channels:
            self._channels[channel].discard(client_id)

    async def broadcast(self, channel: str, message: dict) -> int:
        subscribers = self._channels.get(channel, set())
        if not subscribers:
            return 0

        payload = json.dumps(message, default=str)
        sent = 0

        for client_id in list(subscribers):
            ws = self._connections.get(client_id)
            if ws is None:
                continue
            try:
                await ws.send_text(payload)
                sent += 1
                ws_messages_total.labels(direction="out", channel=channel).inc()
            except Exception:
                logger.warning("ws_broadcast_failed", client_id=client_id, channel=channel)
                await self.disconnect(client_id)

        return sent

    async def send_to(self, client_id: str, message: dict) -> bool:
        ws = self._connections.get(client_id)
        if ws is None:
            return False
        try:
            await ws.send_json(message)
            return True
        except Exception:
            logger.warning("ws_send_failed", client_id=client_id)
            await self.disconnect(client_id)
            return False


manager = ConnectionManager()


@router.websocket("/ws/live")
async def websocket_live(ws: WebSocket):
    await ws.accept()
    client_id = f"client_{id(ws)}_{int(time.time())}"

    ok = await manager.connect(client_id, ws)
    if not ok:
        await ws.send_json({"type": "error", "detail": "server_full"})
        await ws.close()
        return

    await manager.subscribe(client_id, "live")

    try:
        while True:
            data = await ws.receive_text()

            limiter = get_rate_limiter()
            allowed, remaining, _ = limiter.check(
                client_id, "ws", max_requests=20, window=1,
            )
            if not allowed:
                await ws.send_json({
                    "type": "rate_limit",
                    "detail": "message_rate_exceeded",
                })
                continue

            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "detail": "invalid_json"})
                continue

            ws_messages_total.labels(direction="in", channel="live").inc()
            msg_type = msg.get("type", "")

            if msg_type == "ping":
                await ws.send_json({"type": "pong", "timestamp": time.time()})
            elif msg_type == "subscribe":
                channel = msg.get("channel")
                if channel:
                    await manager.subscribe(client_id, channel)
                    await ws.send_json({"type": "subscribed", "channel": channel})
            elif msg_type == "unsubscribe":
                channel = msg.get("channel")
                if channel:
                    await manager.unsubscribe(client_id, channel)
                    await ws.send_json({"type": "unsubscribed", "channel": channel})
            else:
                await ws.send_json({"type": "unknown", "original_type": msg_type})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("ws_error", client_id=client_id, error=str(e))
    finally:
        await manager.disconnect(client_id)


@router.post("/api/v1/ws/broadcast")
async def broadcast_message(channel: str, message: dict):
    """Admin endpoint to broadcast a message to all subscribers of a channel."""
    sent = await manager.broadcast(channel, message)
    return {"channel": channel, "subscribers_reached": sent}


@router.get("/api/v1/ws/status")
async def ws_status():
    """WebSocket server status."""
    return {
        "active_connections": manager.active_count,
        "max_clients": manager.max_clients,
        "channels": {ch: len(members) for ch, members in manager._channels.items()},
    }
