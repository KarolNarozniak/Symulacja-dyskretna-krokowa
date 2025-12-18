from typing import Optional
import math
import statistics
import matplotlib.pyplot as plt
from utils import result_path
from models import Samolot
from event_engine import EventEngine
import random


class AirportEvent:
    def __init__(
        self,
        engine: EventEngine,
        arrival_interval: float,
        landing_duration: float,
        departure_interval: int,
        rng: Optional[random.Random] = None,
        streams=None,
    ) -> None:
        self.engine = engine
        self.in_the_air = 0
        self.on_the_ground = 0
        self.arrival_interval = arrival_interval
        self.landing_duration = landing_duration
        self.departure_interval = departure_interval

        self.kolejka_w_powietrzu: list[Samolot] = []
        self.kolejka_na_plycie: list[Samolot] = []
        self.aktualny_ladujacy: Optional[Samolot] = None

        self._next_id = 0
        self.rng = rng or random.Random()
        self.streams = streams

        # statystyki (zapis przy zmianie stanu)
        self.hist_times: list[float] = []
        self.hist_kolejki_powietrze: list[int] = []
        self.hist_kolejki_plyta: list[int] = []
        self.czasy_oczekiwania_powietrze: list[int] = []
        self.czasy_oczekiwania_plyta: list[int] = []

        # completed samolots for logging/analysis
        self.completed: list[Samolot] = []

        # zaplanuj pierwszy przylot
        self._zaplanuj_nastepny_przylot()

    def _zaplanuj_nastepny_przylot(self) -> None:
        if self.streams is not None:
            idx = getattr(self, '_stream_idx', 0)
            if idx >= len(self.streams.deltas):
                delta = self.streams.deltas[-1]
            else:
                delta = self.streams.deltas[idx]
            self._stream_idx = idx + 1
        else:
            raw = self.rng.expovariate(1.0 / max(0.0001, self.arrival_interval))
            delta = max(1, math.ceil(raw))
        t = self.engine.now() + delta
        self.engine.schedule(t, self._arrival)

    def _losuj_kategorie(self) -> int:
        # when using prefed streams, categories are indexed by aircraft id
        return self.rng.choice([1, 2, 3])

    def _losuj_czas_ladowania(self, kategoria: int, sam_id: int | None = None) -> int:
        if self.streams is not None and sam_id is not None:
            return self.streams.landing_for(sam_id)
        if kategoria == 1:
            return max(1, int(self.landing_duration))
        if kategoria == 2:
            return self.rng.randint(2, 5)
        val = self.rng.gauss(self.landing_duration, 1.5)
        return max(1, math.ceil(val))

    def _collect_stats(self) -> None:
        t = self.engine.now()
        count_air = len(self.kolejka_w_powietrzu) + (1 if self.aktualny_ladujacy else 0)
        count_ground = len(self.kolejka_na_plycie)
        self.hist_times.append(t)
        self.hist_kolejki_powietrze.append(count_air)
        self.hist_kolejki_plyta.append(count_ground)

    def _arrival(self) -> None:
        self._next_id += 1
        if self.streams is not None:
            kat = self.streams.category_for(self._next_id)
        else:
            kat = self._losuj_kategorie()
        sam = Samolot(id=self._next_id, kategoria=kat, czas_przylotu=self.engine.now())
        self.kolejka_w_powietrzu.append(sam)
        self.in_the_air += 1
        # rozpocznij ladowanie jesli mozna
        if self.aktualny_ladujacy is None and not self.kolejka_na_plycie:
            self._rozpocznij_ladowanie()
        self._collect_stats()
        self._zaplanuj_nastepny_przylot()

    def _rozpocznij_ladowanie(self) -> None:
        if not self.kolejka_w_powietrzu:
            return
        sam = self.kolejka_w_powietrzu.pop(0)
        sam.czas_rozpoczecia_ladowania = self.engine.now()
        czas_l = self._losuj_czas_ladowania(sam.kategoria, sam.id)
        self.aktualny_ladujacy = sam
        t_koniec = self.engine.now() + czas_l
        self.engine.schedule(t_koniec, self._landing_complete, sam)
        self._collect_stats()

    def _landing_complete(self, sam: Samolot) -> None:
        sam.czas_zakonczenia_ladowania = self.engine.now()
        self.in_the_air = max(0, self.in_the_air - 1)
        self.on_the_ground += 1
        sam.czas_odlotu_zaplanowany = self.engine.now() + self.departure_interval
        self.kolejka_na_plycie.append(sam)
        if sam.czas_rozpoczecia_ladowania is not None:
            self.czasy_oczekiwania_powietrze.append(sam.czas_rozpoczecia_ladowania - sam.czas_przylotu)
        self.aktualny_ladujacy = None
        # zaplanuj odlot dla tego samolotu
        self.engine.schedule(sam.czas_odlotu_zaplanowany, self._departure, sam)
        # jesli płyta jest wolna i sa samoloty w powietrzu — rozpocznij nastepne ladowanie
        if not self.kolejka_na_plycie and self.kolejka_w_powietrzu:
            self._rozpocznij_ladowanie()
        self._collect_stats()

    def _departure(self, sam: Samolot) -> None:
        # usuń samolot z kolejki na płycie (jeśli nadal tam jest)
        try:
            self.kolejka_na_plycie.remove(sam)
        except ValueError:
            return
        sam.czas_odlotu = self.engine.now()
        self.on_the_ground = max(0, self.on_the_ground - 1)
        if sam.czas_zakonczenia_ladowania is not None:
            self.czasy_oczekiwania_plyta.append(sam.czas_odlotu - sam.czas_zakonczenia_ladowania)
        # record completed
        self.completed.append(sam)
        # po odlocie — jesli płyta wolna i sa samoloty w powietrzu, rozpocznij ladowanie
        if not self.kolejka_na_plycie and self.kolejka_w_powietrzu and self.aktualny_ladujacy is None:
            self._rozpocznij_ladowanie()
        self._collect_stats()

    def podsumuj(self) -> None:
        avg_pow = statistics.mean(self.czasy_oczekiwania_powietrze) if self.czasy_oczekiwania_powietrze else 0
        avg_plyta = statistics.mean(self.czasy_oczekiwania_plyta) if self.czasy_oczekiwania_plyta else 0

        if self.hist_times:
            plt.figure(figsize=(10, 5))
            plt.step(self.hist_times, self.hist_kolejki_powietrze, where='post', label='powietrze')
            plt.step(self.hist_times, self.hist_kolejki_plyta, where='post', label='plyta')
            plt.xlabel('Czas')
            plt.ylabel('Liczba')
            plt.legend()
            plt.tight_layout()
            plt.savefig(result_path('kolejki_event', 'png'))

        plt.figure(figsize=(10, 5))
        if self.czasy_oczekiwania_powietrze:
            plt.hist(self.czasy_oczekiwania_powietrze, bins=15, alpha=0.6, label='powietrze')
        if self.czasy_oczekiwania_plyta:
            plt.hist(self.czasy_oczekiwania_plyta, bins=15, alpha=0.6, label='plyta')
        plt.xlabel('Czas oczekiwania')
        plt.ylabel('Liczba')
        plt.legend()
        plt.tight_layout()
        plt.savefig(result_path('hist_czasy_oczekiwania_event', 'png'))


if __name__ == '__main__':
    eng = EventEngine()
    ap = AirportEvent(eng, arrival_interval=3.0, landing_duration=3.0, departure_interval=4, rng=random.Random(0))
    eng.run(until=100)
    ap.podsumuj()
