"""
Wrapper dla symulacji lotniska - Zadanie 1.
Uruchamia Airport z Airport2025.py i wypisuje statystyki.
"""
import simpy
from Airport2025 import Airport


def main():
    """Uruchom symulację z parametrami i podsumuj."""
    czas_symulacji = 200
    arrival_interval = 3.0
    landing_duration = 3.0
    departure_interval = 4

    env = simpy.Environment()
    airport = Airport(env, arrival_interval, landing_duration, departure_interval)
    env.run(until=czas_symulacji)
    airport.podsumuj()


if __name__ == "__main__":
    main()

