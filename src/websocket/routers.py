from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.status import WS_1001_GOING_AWAY

from src import manager
from src.logging import logger
from .schemas import ManagerState


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


@router.post("/shutdown")
async def initiate_shutdown():
    """Manually initiate a graceful shutdown"""
    if manager.state != ManagerState.RUNNING:
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"error": "Shutdown already in progress"})

    manager.request_shutdown()
    await manager.backend.publish_shutdown_signal()
    total_connections = await manager.backend.get_connection_count()

    return {
        "status": "shutdown_initiated",
        "active_connections": total_connections,
        "shutdown_timeout": manager.shutdown_timeout
    }


@router.get("/status")
async def get_full_status():
    """Get connection full status"""
    full_status = await manager.get_full_status()
    return {
        "status": full_status,
        "timestamp": datetime.now().isoformat()
    }





