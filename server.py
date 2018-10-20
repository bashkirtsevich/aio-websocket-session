import asyncio
import datetime
import uuid

import aiohttp.web

from protocol import MSG_OPEN, MSG_MESSAGE, MSG_CLOSED
from session_manager import SessionManager
from transport import WebSocketServerHLEB


async def chat_msg_handler(msg, session):
    if msg.type == MSG_OPEN:
        session.manager.broadcast("Someone joined.")
    elif msg.type == MSG_MESSAGE:
        session.manager.broadcast(msg.data)
    elif msg.type == MSG_CLOSED:
        session.manager.broadcast("Someone left.")


async def websocket(manager, request):
    session = manager.get(str(uuid.uuid4()), True)

    transport = WebSocketServerHLEB(manager, session, request)
    try:
        return await transport.process()
    except asyncio.CancelledError:
        raise
    except aiohttp.web.HTTPException as exc:
        return exc


async def send_currenttime(manager):
    while True:
        manager.broadcast("Payload: " + str(datetime.datetime.now()))
        await asyncio.sleep(1)


if __name__ == '__main__':
    app = aiohttp.web.Application()

    manager = SessionManager(app, chat_msg_handler, app.loop)

    app.router.add_get("/ws", lambda request: websocket(manager, request))

    asyncio.ensure_future(send_currenttime(manager), loop=app.loop)
    aiohttp.web.run_app(app)
