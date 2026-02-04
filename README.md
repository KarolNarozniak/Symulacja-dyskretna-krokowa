# Symulacja lotniska (Lab 7) — system kolejkowy i niezawodność

Repozytorium zawiera wersję zadania laboratoryjnego nr 7: symulację zdarzeniową lotniska z obsługą pasażerów oraz niezawodnością automatycznej bramki (skaner + drzwi). Wyniki (obrazy) zapisywane są do katalogu `results/` z unikalnym sufiksem daty-czasu (format YYYYMMDD_HHMMSS).

## Główne pliki
- `airport_lab7.py` — główna symulacja (SimPy) dla laboratorium 7: przyloty, lądowania, odprawa i rozładunek, obsługa pasażerów oraz awaryjność bramki.
- `models.py` — dataclasses: `Plane` i `Passenger`.
- `utils.py` — pomocnik dla zapisu wyników: `result_path()` tworzy katalog `results/` (jeśli brak) i generuje nazwę pliku z timestampem.
- `results/` — katalog wynikowy (z timestampowanymi PNG).

## Założenia zadania (skrót)
- Po lądowaniu realizowana jest odprawa samolotu oraz rozładunek, a następnie pasażerowie trafiają do kolejki FIFO przy automatycznej bramce.
- Liczba pasażerów zależy od kategorii samolotu (losowanie z rozkładu jednostajnego).
- Automatyczna bramka składa się ze skanera i drzwi (struktura szeregowa) — awaria jednego elementu zatrzymuje pracę do czasu naprawy.
- Czas awarii: rozkład wykładniczy; czas naprawy: rozkład normalny.
- Zbierane metryki: średni czas obsługi (z awariami), długość kolejki (w czasie i średnia), przebiegi stanów bramki, skanera i drzwi.

## Jak uruchamiać (szybkie przykłady)
1) Zainstaluj zależności (jeśli nie ma):

```powershell
pip install simpy matplotlib
```

2) Uruchom symulację:

```powershell
python airport_lab7.py
```

## Gdzie są wyniki?
- Wszystkie pliki wynikowe (PNG) trafiają do katalogu `results/` i zawierają w nazwie znacznik czasu, np. `results/kolejka_pasazerow_20251218_161020.png`.

Jeśli chcesz, mogę dostroić parametry rozkładów, czas symulacji lub dodać dodatkowe raporty.
