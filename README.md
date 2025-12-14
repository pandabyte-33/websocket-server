# WebSocket Server

WebSocket server for sending real-time notifications with graceful shutdown

## Setup

### Prerequisites

- Python 3.13.5
- Redis server (or use Docker Compose)

###  Get started

Start all services with Docker Compose
```
docker-compose up
```

Install dependencies

```
pip install -r requirements.txt
```

###  Run

```
uvicorn main:app --workers 4
```

### Test clients

```
python tests/test_clients.py
```

## Graceful Shutdown Logic

The server implements a graceful shutdown mechanism.

### How It Works

1. **Shutdown Initiation:**
   - When a shutdown signal (SIGTERM, SIGINT) is received, the server enters `SHUTDOWN_REQUESTED` state
   - The server immediately stops accepting new WebSocket connections

2. **Connection Draining:**
   - The server periodically sends ping messages to all active connections to check if they are still alive

3. **Timeout and Force Close:**
   - By default, the server waits for all connections to close naturally
   - If connections remain after the timeout period, the server forces closure

4. **Completion:**
   - Once all connections are closed or timeout is reached, the server completes shutdown

