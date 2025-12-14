import asyncio
import websockets


async def test_client(name: str):
    uri = f"ws://localhost:8000/ws/{name}"
    async with websockets.connect(uri) as websocket:
        message = await websocket.recv()
        print(f"Received {name}: {message}")

        while True:
            message = await websocket.recv()
            print(f"Notification {name}: {message}")


async def main():
    await asyncio.gather(test_client("client1"), test_client("client2"))


asyncio.run(main())
