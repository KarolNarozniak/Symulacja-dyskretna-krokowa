"""
Wrapper dla symulacji lotniska - Zadanie 1.
Uruchamia Airport z Airport2025.py i wypisuje statystyki.
"""
import simpy
import random
from Airport2025 import Airport


def main():
    """Uruchom symulację z parametrami i podsumuj."""
    kroki_symulacji = 200
    arrival_interval = 3.0
    landing_duration = 4.0
    departure_interval = 5
    seed = 0

    env = simpy.Environment()
    airport = Airport(env, arrival_interval, landing_duration, departure_interval, rng=random.Random(seed))
    env.run(until=kroki_symulacji)
    airport.podsumuj()


if __name__ == "__main__":
    main()

