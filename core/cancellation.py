"""İş parçacığına özel, güvenli aşama sınırlarında iptal."""
from contextvars import ContextVar

current_cancel = ContextVar('archive_cancel', default=None)


class Cancelled(Exception):
    pass


def checkpoint():
    event = current_cancel.get()
    if event is not None and event.is_set():
        raise Cancelled('İşlem iptal edildi.')
