import collections

ENCODING = 'utf-8'

STATE_NEW = 0
STATE_OPEN = 1
STATE_CLOSING = 2
STATE_CLOSED = 3

# Handler messages
# ---------------------

MSG_OPEN = 1
MSG_MESSAGE = 2
MSG_CLOSE = 3
MSG_CLOSED = 4


class SockjsMessage(collections.namedtuple('SockjsMessage', ['type', 'data'])):
    @property
    def tp(self):
        return self.type


OpenMessage = SockjsMessage(MSG_OPEN, None)
CloseMessage = SockjsMessage(MSG_CLOSE, None)
ClosedMessage = SockjsMessage(MSG_CLOSED, None)
