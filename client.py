import asyncio

import aiohttp


async def main():
    session = aiohttp.ClientSession()

    async with session.ws_connect("http://localhost:8080/ws") as ws:
        async for msg in ws:
            print("Message received from server:", msg.data)

            if msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                break


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())

# import asyncio
#
# import aiohttp.web
#
# from protocol import MSG_OPEN, MSG_MESSAGE, MSG_CLOSED
# from session import Session
# from transport import WebSocketClient
#
#
# async def chat_msg_handler(msg, session):
#     if msg.type == MSG_OPEN:
#         session.send("Connected")
#     elif msg.type == MSG_MESSAGE:
#         session.send("some data " + msg.data)
#     elif msg.type == MSG_CLOSED:
#         session.send("Disconnected")
#
#
# async def main(client_session):
#     session = Session("qwe", chat_msg_handler, None)
#
#     transport = WebSocketClient(session, client_session, "http://localhost:8080/ws")
#     try:
#         session.send("Connected")
#         return await transport.process()
#     except asyncio.CancelledError:
#         raise
#     except aiohttp.web.HTTPException as exc:
#         return exc
#
#
# if __name__ == "__main__":
#     loop = asyncio.get_event_loop()
#     loop.run_until_complete(main(aiohttp.ClientSession()))
