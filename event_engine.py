from heapq import heappush, heappop
from typing import Callable, Any
from engine import SimulationEngine


class EventEngine(SimulationEngine):
    def __init__(self) -> None:
        self._pq: list = []
        self._now: float = 0.0
        self._seq: int = 0

    def now(self) -> float:
        return self._now

    def schedule(self, time: float, action: Callable[..., Any], *args, **kwargs) -> None:
        if time < self._now:
            time = self._now
        heappush(self._pq, (time, self._seq, action, args, kwargs))
        self._seq += 1

    def run(self, until: float | None = None, max_events: int | None = None) -> None:
        events = 0
        while self._pq:
            time, _seq, action, args, kwargs = heappop(self._pq)
            if until is not None and time > until:
                break
            self._now = time
            action(*args, **kwargs)
            events += 1
            if max_events is not None and events >= max_events:
                break

    def process(self, func: Callable[..., Any]):
        raise NotImplementedError("process() not supported for EventEngine")
