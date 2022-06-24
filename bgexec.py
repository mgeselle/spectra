import queue
import threading
from typing import Any, Callable

FINISHED = 'finished'
ERROR = 'error'
INFO = 'info'


class Event:
    def __init__(self, evt_type: (ERROR, FINISHED, INFO), client_data: Any = None):
        self.evt_type = evt_type
        self.client_data = client_data


class BgExec(threading.Thread):
    def __init__(self, run_func: Callable[[], Any], status_queue: queue.Queue):
        super().__init__()
        self._run_func = run_func
        self._status_queue = status_queue

    def run(self) -> None:
        try:
            result = self._run_func()
            self._status_queue.put(Event(FINISHED, result))
        except Exception as err:
            self._status_queue.put(Event(ERROR, err))
