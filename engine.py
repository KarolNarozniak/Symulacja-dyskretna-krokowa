from abc import ABC, abstractmethod
from typing import Any, Callable


class SimulationEngine(ABC):
    """Abstrakcja silnika symulacji.

    Implementacje: krokowy, zdarzeniowy, procesowy (np. simpy).
    """

    @abstractmethod
    def now(self) -> float:
        raise NotImplementedError()

    @abstractmethod
    def schedule(self, time: float, action: Callable[..., Any], *args, **kwargs) -> None:
        raise NotImplementedError()

    @abstractmethod
    def run(self, until: float | None = None, max_events: int | None = None) -> None:
        raise NotImplementedError()

    def process(self, func: Callable[..., Any]):
        """Opcjonalna metoda dla silników opartych na procesach (np. simpy)."""
        raise NotImplementedError()
