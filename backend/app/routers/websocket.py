from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.core.logging import logger

router = APIRouter()

# Store active connections
active_connections: list[WebSocket] = []


@router.websocket("/ws/incidents")
async def websocket_incidents(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    logger.info("ws_client_connected", total=len(active_connections))
    try:
        while True:
            await websocket.receive_text()  # keep alive
    except WebSocketDisconnect:
        active_connections.remove(websocket)
        logger.info("ws_client_disconnected", total=len(active_connections))


async def broadcast(message: dict) -> None:
    for connection in active_connections.copy():
        try:
            await connection.send_json(message)
        except Exception:
            active_connections.remove(connection)