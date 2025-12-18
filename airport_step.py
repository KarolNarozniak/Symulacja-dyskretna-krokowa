import math
import statistics
import matplotlib.pyplot as plt
from utils import result_path
from typing import Optional
import random
from models import Samolot


class AirportStep:
    def __init__(
        self,
        arrival_interval: float,
        landing_duration: float,
        departure_interval: int,
        rng: Optional[random.Random] = None,
        streams=None,
    ) -> None:
        self.arrival_interval = arrival_interval
        self.landing_duration = landing_duration
        self.departure_interval = departure_interval

        self.kolejka_w_powietrzu: list[Samolot] = []
        self.kolejka_na_plycie: list[Samolot] = []
        self.aktualny_ladujacy: Optional[Samolot] = None
        self.pas_zajety_do: int = -1

        self.in_the_air = 0
        self.on_the_ground = 0
        self._next_id = 0
        self.rng = rng or random.Random()
        self.streams = streams

        # statystyki
        self.hist_kolejki_powietrze: list[int] = []
        self.hist_kolejki_plyta: list[int] = []
        self.czasy_oczekiwania_powietrze: list[int] = []
        self.czasy_oczekiwania_plyta: list[int] = []
        # completed samolots for logging/analysis
        self.completed: list[Samolot] = []

        # pierwsze przyloty
        self.arrival_time = 0
        self._zaplanuj_nastepny_przylot(0)

    def _zaplanuj_nastepny_przylot(self, now: int) -> None:
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
        self.arrival_time = now + delta

    def _losuj_kategorie(self, sam_id: Optional[int] = None) -> int:
        if self.streams is not None and sam_id is not None:
            return self.streams.category_for(sam_id)
        return self.rng.choice([1, 2, 3])

    def _losuj_czas_ladowania(self, kategoria: int, sam_id: Optional[int] = None) -> int:
        if self.streams is not None and sam_id is not None:
            return self.streams.landing_for(sam_id)
        if kategoria == 1:
            return max(1, int(self.landing_duration))
        if kategoria == 2:
            return self.rng.randint(2, 5)
        val = self.rng.gauss(self.landing_duration, 1.5)
        return max(1, math.ceil(val))

    def _rozpocznij_ladowanie(self, now: int) -> None:
        if not self.kolejka_w_powietrzu:
            return
        if self.kolejka_na_plycie:
            return
        sam = self.kolejka_w_powietrzu.pop(0)
        sam.czas_rozpoczecia_ladowania = now
        czas_l = self._losuj_czas_ladowania(sam.kategoria, sam.id)
        self.aktualny_ladujacy = sam
        self.pas_zajety_do = now + czas_l

    def arrival(self, now: int) -> None:
        if now == self.arrival_time:
            self._next_id += 1
            kat = self._losuj_kategorie(self._next_id)
            sam = Samolot(id=self._next_id, kategoria=kat, czas_przylotu=now)
            self.kolejka_w_powietrzu.append(sam)
            self.in_the_air += 1
            if self.aktualny_ladujacy is None and not self.kolejka_na_plycie:
                self._rozpocznij_ladowanie(now)
            self._zaplanuj_nastepny_przylot(now)

    def landing(self, now: int) -> None:
        if self.aktualny_ladujacy is not None and now == self.pas_zajety_do:
            sam = self.aktualny_ladujacy
            sam.czas_zakonczenia_ladowania = now
            self.in_the_air = max(0, self.in_the_air - 1)
            self.on_the_ground += 1
            sam.czas_odlotu_zaplanowany = now + self.departure_interval
            self.kolejka_na_plycie.append(sam)
            if sam.czas_rozpoczecia_ladowania is not None:
                self.czasy_oczekiwania_powietrze.append(sam.czas_rozpoczecia_ladowania - sam.czas_przylotu)
            self.aktualny_ladujacy = None
            self.pas_zajety_do = -1
            if self.kolejka_w_powietrzu:
                self._rozpocznij_ladowanie(now)

    def departure(self, now: int) -> None:
        if self.kolejka_na_plycie and self.kolejka_na_plycie[0].czas_odlotu_zaplanowany == now:
            sam = self.kolejka_na_plycie.pop(0)
            sam.czas_odlotu = now
            self.on_the_ground = max(0, self.on_the_ground - 1)
            if sam.czas_zakonczenia_ladowania is not None:
                self.czasy_oczekiwania_plyta.append(sam.czas_odlotu - sam.czas_zakonczenia_ladowania)
            # record completed
            self.completed.append(sam)
            if not self.kolejka_na_plycie and self.kolejka_w_powietrzu and self.aktualny_ladujacy is None:
                self._rozpocznij_ladowanie(now)

    def _collect_stats(self) -> None:
        count = len(self.kolejka_w_powietrzu)
        if self.aktualny_ladujacy:
            count += 1
        self.hist_kolejki_powietrze.append(count)
        self.hist_kolejki_plyta.append(len(self.kolejka_na_plycie))

    def run(self, until: int) -> None:
        for t in range(until + 1):
            self.arrival(t)
            self.landing(t)
            self.departure(t)
            self._collect_stats()

    def podsumuj(self) -> None:
        avg_pow = statistics.mean(self.czasy_oczekiwania_powietrze) if self.czasy_oczekiwania_powietrze else 0
        avg_plyta = statistics.mean(self.czasy_oczekiwania_plyta) if self.czasy_oczekiwania_plyta else 0
        print("\n--- Podsumowanie (krok) ---")
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
        plt.savefig(result_path("kolejki_krok", "png"))

        plt.figure(figsize=(10, 5))
        if self.czasy_oczekiwania_powietrze:
            plt.hist(self.czasy_oczekiwania_powietrze, bins=15, alpha=0.6, label="powietrze")
        if self.czasy_oczekiwania_plyta:
            plt.hist(self.czasy_oczekiwania_plyta, bins=15, alpha=0.6, label="plyta")
        plt.xlabel("Czas oczekiwania")
        plt.ylabel("Liczba")
        plt.legend()
        plt.tight_layout()
        plt.savefig(result_path("hist_czasy_oczekiwania_krok", "png"))


if __name__ == '__main__':
    ap = AirportStep(arrival_interval=3.0, landing_duration=3.0, departure_interval=4, rng=random.Random(0))
    ap.run(100)
    ap.podsumuj()
