import warnings
from asyncio import ensure_future
from datetime import timedelta, datetime

from exceptions import SessionIsAcquired
from protocol import STATE_OPEN, STATE_CLOSING, STATE_CLOSED
from session import Session

_marker = object()


class SessionManager(dict):
    """A basic session manager."""

    _hb_handle = None  # heartbeat event loop timer
    _hb_task = None  # gc task

    def __init__(self, app, handler, loop,
                 heartbeat=25.0, timeout=timedelta(seconds=5), debug=False):
        self.app = app
        self.handler = handler
        self.factory = Session
        self.acquired = {}
        self.sessions = []
        self.heartbeat = heartbeat
        self.timeout = timeout
        self.loop = loop
        self.debug = debug

    @property
    def started(self):
        return self._hb_handle is not None

    def start(self):
        if not self._hb_handle:
            self._hb_handle = self.loop.call_later(
                self.heartbeat, self._heartbeat)

    def stop(self):
        if self._hb_handle is not None:
            self._hb_handle.cancel()
            self._hb_handle = None
        if self._hb_task is not None:
            self._hb_task.cancel()
            self._hb_task = None

    def _heartbeat(self):
        if self._hb_task is None:
            self._hb_task = ensure_future(
                self._heartbeat_task(), loop=self.loop)

    async def _heartbeat_task(self):
        sessions = self.sessions

        if sessions:
            now = datetime.now()

            idx = 0
            while idx < len(sessions):
                session = sessions[idx]

                session._heartbeat()

                if session.expires < now:
                    # Session is to be GC"d immedietely
                    if session.id in self.acquired:
                        await self.release(session)

                    if session.state == STATE_OPEN:
                        await session._remote_close()

                    if session.state == STATE_CLOSING:
                        await session._remote_closed()

                    del self[session.id]
                    del self.sessions[idx]
                    continue

                idx += 1

        self._hb_task = None
        self._hb_handle = self.loop.call_later(
            self.heartbeat, self._heartbeat)

    def _add(self, session):
        if session.expired:
            raise ValueError("Can not add expired session")

        session.manager = self
        session.registry = self.app

        self[session.id] = session
        self.sessions.append(session)
        return session

    def get(self, id, create=False, default=_marker):
        session = super(SessionManager, self).get(id, None)
        if session is None:
            if create:
                session = self._add(
                    self.factory(
                        id, self.handler,
                        timeout=self.timeout,
                        loop=self.loop, debug=self.debug))
            else:
                if default is not _marker:
                    return default
                raise KeyError(id)

        return session

    async def acquire(self, s):
        sid = s.id

        if sid in self.acquired:
            raise SessionIsAcquired("Another connection still open")
        if sid not in self:
            raise KeyError("Unknown session")

        await s._acquire(self)

        self.acquired[sid] = True
        return s

    def is_acquired(self, session):
        return session.id in self.acquired

    async def release(self, s):
        if s.id in self.acquired:
            s._release()
            del self.acquired[s.id]

    def active_sessions(self):
        for session in self.values():
            if not session.expired:
                yield session

    async def clear(self):
        """Manually expire all sessions in the pool."""
        for session in list(self.values()):
            if session.state != STATE_CLOSED:
                await session._remote_closed()

        self.sessions.clear()
        super(SessionManager, self).clear()

    def broadcast(self, message):
        for session in self.values():
            if not session.expired:
                session.send(message)

    def __del__(self):
        if len(self.sessions):
            warnings.warn(
                "Unclosed sessions! "
                "Please call `await SessionManager.clear()` before del",
                RuntimeWarning
            )
        self.stop()
