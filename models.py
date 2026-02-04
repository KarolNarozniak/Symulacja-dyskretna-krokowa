from dataclasses import dataclass
from typing import Optional


@dataclass
class Plane:
    """Plane tracked through landing and post-landing handling."""
    id: int
    category: int
    arrival_time: float
    landing_start: Optional[float] = None
    landing_end: Optional[float] = None
    unload_end: Optional[float] = None
    departure_time: Optional[float] = None


@dataclass
class Passenger:
    """Passenger waiting for and completing service at the gate."""
    id: int
    arrival_time: float
    service_start: Optional[float] = None
    service_end: Optional[float] = None
