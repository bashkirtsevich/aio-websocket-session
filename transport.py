import asyncio
from asyncio import ensure_future

from aiohttp import web

from exceptions import SessionIsClosed

CMD_OPEN = 1
CMD_CLOSE = 2
CMD_CLOSED = 3
CMD_CLOSING = 4
CMD_MESSAGE = 5
CMD_HEARTBEAT = 6


class BasicTransport:
    def __init__(self, loop=None):
        self.loop = loop

    async def _await_cmd(self):
        raise NotImplementedError

    async def _parse_data(self, data):
        raise NotImplementedError

    async def _got_message(self, data):
        raise NotImplementedError

    async def _ping(self):
        raise NotImplementedError

    async def _pong(self):
        raise NotImplementedError

    async def _send(self, data):
        raise NotImplementedError

    async def _receive(self):
        raise NotImplementedError

    async def _disconnect(self):
        raise NotImplementedError

    async def _close(self):
        raise NotImplementedError

    async def _closed(self, exc=None):
        raise NotImplementedError

    async def _sending(self):
        while True:
            try:
                frame, cmd_data = await self._await_cmd()
            except SessionIsClosed:
                break

            if frame == CMD_MESSAGE:
                for data in cmd_data:
                    await self._send(data)

            elif frame == CMD_HEARTBEAT:
                await self._ping()

            elif frame == CMD_CLOSE:
                try:
                    await self._disconnect()
                finally:
                    await self._closed()

    async def _receiving(self):
        while True:
            data = await self._receive()
            cmd, cmd_data = await self._parse_data(data)

            if cmd == CMD_MESSAGE:
                await self._got_message(cmd_data)

            elif cmd == CMD_CLOSE:
                await self._close()

            elif cmd in (CMD_CLOSED, CMD_CLOSING):
                await self._closed()
                break

            elif cmd == CMD_HEARTBEAT:
                await self._pong()

    async def handle_connection(self):
        server = ensure_future(self._sending(), loop=self.loop)
        client = ensure_future(self._receiving(), loop=self.loop)

        try:
            await asyncio.wait(
                (server, client),
                loop=self.loop,
                return_when=asyncio.FIRST_COMPLETED
            )
        except asyncio.CancelledError:
            raise

        except Exception as exc:
            await self._closed(exc)

        finally:
            if not server.done():
                server.cancel()

            if not client.done():
                client.cancel()


class WSBasicTransport(BasicTransport):
    def __init__(self, ws, loop=None):
        super().__init__(loop)
        self.ws = ws

    async def _ping(self):
        await self.ws.ping()

    async def _send(self, data):
        await self.ws.send_str(data)


class WebSocketTransport_HLEB:
    def __init__(self, session, loop):
        self.session = session
        self.loop = loop

    async def server(self, ws):
        while True:
            try:
                frame, data = await self.session._wait()
            except SessionIsClosed:
                break

            if frame == CMD_MESSAGE:
                for text in data:
                    await ws.send_str(text)

            elif frame == CMD_HEARTBEAT:
                await ws.ping()

            elif frame == CMD_CLOSE:
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


class WebSocketServerHLEB(WebSocketTransport_HLEB):
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


class WebSocketClientHLEB(WebSocketTransport_HLEB):
    def __init__(self, session, client_session, url):
        self.client_session = client_session
        self.url = url

        super().__init__(session, self.client_session.loop)

    async def process(self):
        async with self.client_session.ws_connect(self.url) as ws:
            return await super().process(ws)
