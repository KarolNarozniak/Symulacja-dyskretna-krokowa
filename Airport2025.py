import simpy
from typing import Generator, Optional
import random
import math
import statistics
from dataclasses import dataclass
import matplotlib.pyplot as plt
from utils import result_path
from models import Samolot

SIM_TIME: int = 100
ARRIVAL_INTERVAL: float = 3.0
LANDING_DURATION: float = 3.0
DEPARTURE_INTERVAL: int = 4


class Airport:
    def __init__(
        self,
        env: simpy.Environment,
        arrival_interval: float,
        landing_duration: float,
        departure_interval: int,
        rng: Optional[random.Random] = None,
        streams=None,
    ) -> None:
        self.env: simpy.Environment = env
        self.in_the_air: int = 0
        self.on_the_ground: int = 0
        self.runway_free: bool = True
        self.arrival_interval: float = arrival_interval
        self.landing_duration: float = landing_duration
        self.departure_interval: int = departure_interval

        # Struktury obiektowe
        self.kolejka_w_powietrzu: list[Samolot] = []
        self.kolejka_na_plycie: list[Samolot] = []
        self.aktualny_ladujacy: Optional[Samolot] = None
        self.pas_zajety_do: int = -1
        self._next_id: int = 0

        # RNG (przekazywalne dla deterministyczności)
        self.rng: random.Random = rng or random.Random()
        self.streams = streams

        # Statystyki
        self.hist_kolejki_powietrze: list[int] = []
        self.hist_kolejki_plyta: list[int] = []
        self.czasy_oczekiwania_powietrze: list[int] = []
        self.czasy_oczekiwania_plyta: list[int] = []

        # completed samolots for logging/analysis
        self.completed: list[Samolot] = []

        # Planowanie pierwszego przylotu
        self.arrival_time: int = 0
        self._zaplanuj_nastepny_przylot()

        # Start procesu
        self.action = env.process(self.run())

    def _zaplanuj_nastepny_przylot(self) -> None:
        """Losuje interwał wykładniczy i ustawia arrival_time."""
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
        self.arrival_time = self.env.now + delta

    def _losuj_kategorie(self, sam_id: Optional[int] = None) -> int:
        """Losuje kategorię: 1, 2 lub 3 równomiernie. If streams provided, return pre-generated category for sam_id."""
        if self.streams is not None and sam_id is not None:
            return self.streams.category_for(sam_id)
        return self.rng.choice([1, 2, 3])

    def _losuj_czas_ladowania(self, kategoria: int, sam_id: Optional[int] = None) -> int:
        """Czas lądowania: 1 stała, 2 randint(2,5), 3 normal ucięty w 1. If streams provided and sam_id set, return pre-generated."""
        if self.streams is not None and sam_id is not None:
            return self.streams.landing_for(sam_id)
        if kategoria == 1:
            return max(1, int(self.landing_duration))
        if kategoria == 2:
            return self.rng.randint(2, 5)
        val = self.rng.gauss(self.landing_duration, 1.5)
        return max(1, math.ceil(val))

    def _rozpocznij_ladowanie(self) -> None:
        """Rozpoczyna lądowanie pierwszego z kolejki w powietrzu (FIFO)."""
        # Nie zaczynamy lądowania jeśli nie ma samolotów w powietrzu
        # lub jeśli na płycie już jest samolot (tylko 1 samolot na płycie jednocześnie)
        if not self.kolejka_w_powietrzu:
            return
        if self.kolejka_na_plycie:
            # płyta zajęta — nie można rozpocząć nowego lądowania
            return
        sam = self.kolejka_w_powietrzu.pop(0)
        sam.czas_rozpoczecia_ladowania = self.env.now
        czas_l = self._losuj_czas_ladowania(sam.kategoria, sam.id)
        self.aktualny_ladujacy = sam
        self.pas_zajety_do = self.env.now + czas_l
        self.runway_free = False

    def arrival(self) -> None:
        """Tworzy Samolot przy przylocie i wstawia do kolejki w powietrzu."""
        if self.env.now == self.arrival_time:
            self._next_id += 1
            kat = self._losuj_kategorie()
            sam = Samolot(id=self._next_id, kategoria=kat, czas_przylotu=self.env.now)
            self.kolejka_w_powietrzu.append(sam)
            self.in_the_air += 1

            if self.runway_free and self.kolejka_w_powietrzu:
                self._rozpocznij_ladowanie()

            self._zaplanuj_nastepny_przylot()

    def landing(self) -> None:
        """Obsługa zakończenia lądowania: przenosi na płytę, planuje odlot."""
        if self.aktualny_ladujacy is not None and self.env.now == self.pas_zajety_do:
            sam = self.aktualny_ladujacy
            sam.czas_zakonczenia_ladowania = self.env.now
            self.in_the_air = max(0, self.in_the_air - 1)
            self.on_the_ground += 1
            sam.czas_odlotu_zaplanowany = self.env.now + self.departure_interval
            self.kolejka_na_plycie.append(sam)

            if sam.czas_rozpoczecia_ladowania is not None:
                self.czasy_oczekiwania_powietrze.append(sam.czas_rozpoczecia_ladowania - sam.czas_przylotu)

            self.aktualny_ladujacy = None
            self.pas_zajety_do = -1

            if self.kolejka_w_powietrzu:
                self._rozpocznij_ladowanie()
            else:
                self.runway_free = True

    def departure(self) -> None:
        """Obsługa odlotów: usuwa z płyty (FIFO), zapisuje czas oczekiwania."""
        if self.kolejka_na_plycie and self.kolejka_na_plycie[0].czas_odlotu_zaplanowany == self.env.now:
            sam = self.kolejka_na_plycie.pop(0)
            sam.czas_odlotu = self.env.now
            self.on_the_ground = max(0, self.on_the_ground - 1)
            if sam.czas_zakonczenia_ladowania is not None:
                self.czasy_oczekiwania_plyta.append(sam.czas_odlotu - sam.czas_zakonczenia_ladowania)

            # record completed
            self.completed.append(sam)

            # Po odlocie — jesli teraz płyta jest wolna i mamy samoloty w powietrzu,
            # mozemy rozpocząć kolejne lądowanie.
            if not self.kolejka_na_plycie and self.kolejka_w_powietrzu and self.aktualny_ladujacy is None:
                self._rozpocznij_ladowanie()

    def _collect_stats(self) -> None:
        """
        Zbiera liczebności kolejek.
        Dopisuje do historii aktualną liczbę samolotów „w powietrzu” powiększoną o 1, 
        jeśli istnieje samolot aktualnie lądujący
        """
        count = len(self.kolejka_w_powietrzu)
        if self.aktualny_ladujacy:
            count += 1
        self.hist_kolejki_powietrze.append(count)
        self.hist_kolejki_plyta.append(len(self.kolejka_na_plycie))

    def run(self) -> Generator:
        while True:
            self.arrival()
            self.landing()
            self.departure()
            self._collect_stats()
            yield self.env.timeout(1)

    def podsumuj(self) -> None:
        """Liczy statystyki i rysuje wykresy."""
        avg_pow = statistics.mean(self.czasy_oczekiwania_powietrze) if self.czasy_oczekiwania_powietrze else 0
        avg_plyta = statistics.mean(self.czasy_oczekiwania_plyta) if self.czasy_oczekiwania_plyta else 0
        print("\n--- Podsumowanie ---")
        print(f"Liczba wyladowanych: {len(self.czasy_oczekiwania_powietrze)}")
        print(f"Sredni czas w powietrzu: {avg_pow:.2f}")
        print(f"Sredni czas na plycie: {avg_plyta:.2f}")

        t = list(range(len(self.hist_kolejki_powietrze)))
        plt.figure(figsize=(10, 5))
        plt.plot(t, self.hist_kolejki_powietrze, label="powietrze")
        plt.plot(t, self.hist_kolejki_plyta, label="plyta")
        plt.xlabel("Czas")
        plt.ylabel("Liczba")
        plt.legend()
        plt.tight_layout()
        plt.savefig(result_path("kolejki_w_czasie", "png"))

        plt.figure(figsize=(10, 5))
        if self.czasy_oczekiwania_powietrze:
            plt.hist(self.czasy_oczekiwania_powietrze, bins=15, alpha=0.6, label="powietrze")
        if self.czasy_oczekiwania_plyta:
            plt.hist(self.czasy_oczekiwania_plyta, bins=15, alpha=0.6, label="plyta")
        plt.xlabel("Czas oczekiwania")
        plt.ylabel("Liczba")
        plt.legend()
        plt.tight_layout()
        plt.savefig(result_path("hist_czasy_oczekiwania", "png"))


if __name__ == "__main__":
    env = simpy.Environment()
    airport = Airport(env, ARRIVAL_INTERVAL, LANDING_DURATION, DEPARTURE_INTERVAL, rng=random.Random(0))
    env.run(until=SIM_TIME)
    airport.podsumuj()
