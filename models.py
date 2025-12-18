from dataclasses import dataclass
from typing import Optional


@dataclass
class Samolot:
    """Reprezentacja samolotu. Pola zgodne z oryginalnym zadaniem."""
    id: int
    kategoria: int
    czas_przylotu: int
    czas_rozpoczecia_ladowania: Optional[int] = None
    czas_zakonczenia_ladowania: Optional[int] = None
    czas_odlotu_zaplanowany: Optional[int] = None
    czas_odlotu: Optional[int] = None
