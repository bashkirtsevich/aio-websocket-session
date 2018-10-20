import asyncio
from asyncio import ensure_future

from aiohttp import web

from exceptions import SessionIsClosed
from protocol import FRAME_CLOSE, FRAME_MESSAGE, FRAME_HEARTBEAT


class WebSocketTransport:
    def __init__(self, session, loop):
        self.session = session
        self.loop = loop

    async def server(self, ws):
        while True:
            try:
                frame, data = await self.session._wait()
            except SessionIsClosed:
                break

            if frame == FRAME_MESSAGE:
                for text in data:
                    await ws.send_str(text)

            elif frame == FRAME_HEARTBEAT:
                await ws.ping()

            elif frame == FRAME_CLOSE:
                try:
                    await ws.close(message="Go away!")
                finally:
                    await self.session._remote_closed()

    async def client(self, ws):
        while True:
            msg = await ws.receive()

            if msg.type == web.WSMsgType.text:
                if not msg.data:
                    continue

                await self.session._remote_message(msg.data)

            elif msg.type == web.WSMsgType.close:
                await self.session._remote_close()

            elif msg.type in (web.WSMsgType.closed, web.WSMsgType.closing):
                await self.session._remote_closed()
                break

            elif msg.type == web.WSMsgType.PONG:
                self.session._tick()

    async def process(self, ws):
        server = ensure_future(self.server(ws), loop=self.loop)
        client = ensure_future(self.client(ws), loop=self.loop)

        try:
            await asyncio.wait((server, client), loop=self.loop, return_when=asyncio.FIRST_COMPLETED)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self.session._remote_close(exc)
        finally:
            if not server.done():
                server.cancel()

            if not client.done():
                client.cancel()


class WebSocketServer(WebSocketTransport):
    def __init__(self, manager, session, request):
        self.manager = manager
        self.request = request

        super().__init__(session, request.app.loop)

    async def process(self):
        ws = web.WebSocketResponse(autoping=False)
        await ws.prepare(self.request)

        try:
            await self.manager.acquire(self.session)

            await super().process(ws)
        except Exception:  # should use specific exception
            await ws.close(message="Go away!")

        finally:
            await self.manager.release(self.session)

        return ws


class WebSocketClient(WebSocketTransport):
    def __init__(self, session, client_session, url):
        self.client_session = client_session
        self.url = url

        super().__init__(session, self.client_session.loop)

    async def process(self):
        async with self.client_session.ws_connect(self.url) as ws:
            return await super().process(ws)
