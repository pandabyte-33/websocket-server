from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, status
from starlette.status import WS_1001_GOING_AWAY

from src import manager
from src.logging import logger


router = APIRouter(tags=["websocket"])

@router.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    if not manager.is_accepting_connections():
        await websocket.close(code=WS_1001_GOING_AWAY, reason='Server is shutting down')
        return

    client_ip = websocket.client.host if websocket.client else 'unknown'

    conn_id = await manager.connect(websocket, client_id, client_ip)
    await websocket.send_json({
        "type": "connection",
        "message": "Connected to server",
        "client_id": client_id,
        "timestamp": datetime.now().isoformat()
    })

    try:
        while True:
            data = await websocket.receive_text()
            logger.debug(f"Received from {client_id}: {data}")
    except WebSocketDisconnect:
        logger.info(f'Client {client_id} disconnected normally')
    except Exception as e:
        logger.error(f'Error with client {client_id}: {e}')
    finally:
        await manager.disconnect(conn_id)


@router.post("/notify")
async def send_message(message: str):
    """Send a message to all connected clients"""
    if not manager.is_accepting_connections():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='Server is shutting down')

    message = {
        "message": message,
        "timestamp": datetime.now().isoformat()
    }
    await manager.broadcast(message)
    total_connections = await manager.backend.get_connection_count()

    return {
        "status": "sent",
        "recipients": total_connections,
        "message": message
    }


@router.get("/status")
async def get_status():
    """Get connection status"""
    stat = await manager.get_status()
    return {
        "status": stat,
        "timestamp": datetime.now().isoformat()
    }





