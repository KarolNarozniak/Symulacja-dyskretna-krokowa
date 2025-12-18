# Symulacja lotniska — krokowa / zdarzeniowa / procesowa

To repozytorium zawiera implementację trzech wariantów prostego symulatora lotniska: krokową (dyskretne kroki czasu), zdarzeniową (event-driven) i procesową (SimPy). Pliki wynikowe (obrazy i logi) zapisywane są do katalogu `results/` z unikalnym sufiksem daty-czasu (format YYYYMMDD_HHMMSS).

## Główne pliki
- `Airport_zad1.py` — prosty wrapper uruchamiający wersję procesową (`Airport2025.Airport`) z przykładowymi parametrami.
- `Airport2025.py` — wersja procesowa (SimPy). Klasa `Airport` zarządza kolejkami, lądowaniami i odlotami; przyjmuje `rng: random.Random` dla deterministyczności.
- `airport_step.py` — implementacja krokowa; w pętli czasowej (co jednostkę czasu) wywołuje `arrival`, `landing`, `departure` i zbiera statystyki.
- `event_engine.py` — prosty silnik zdarzeń (priority queue) implementujący planowanie zdarzeń.
- `airport_event.py` — model lotniska korzystający z `event_engine` (wersja zdarzeniowa).
- `models.py` — `Samolot` dataclass z polami czasów (przylot, start lądowania, koniec lądowania, odlot).
- `compare.py` — uruchamia krokową, zdarzeniową i procesową wersję z tymi samymi ziar-nami i generuje wykresy porównawcze (zapis w `results/`).
- `test_replications.py` — uruchamia N replikacji (dla różnych ziaren) i wypisuje średnie/odchylenia czasów oczekiwania.
- `compare_logs.py` — generuje CSV z listą wszystkich samolotów i ich czasami dla każdej implementacji (zapis w `results/`).
- `utils.py` — pomocnik dla zapisu wyników: `result_path()` tworzy katalog `results/` (jeśli brak) i generuje nazwę pliku z timestampem.
- `results/` — katalog wynikowy (z timestampowanymi PNG/CSV).

## Co zmieniłem względem pierwotnych plików
- Ujednolicono użycie generatora losowego: wszystkie moduły przyjmują `random.Random` (argument `rng`) — ułatwia to odtwarzalność eksperymentów.
- Dodano implementację zdarzeniową (`event_engine.py` + `airport_event.py`) oraz wersję krokową (`airport_step.py`).
- Usunięto nadmiarowe debugujące `print`y i zmodyfikowano zapisy plików tak, by trafiały do `results/` z unikalnym sufiksem daty-czasu (funkcja w `utils.py`).
- Dodano skrypty pomocnicze: `compare.py`, `test_replications.py`, `compare_logs.py` do porównań i zbierania wyników.

## Jak uruchamiać (szybkie przykłady)
1) Aktywuj venv (Windows PowerShell):

```powershell
.\venv\Scripts\Activate
```

2) Zainstaluj zależności (jeśli nie ma):

```powershell
pip install simpy matplotlib
```

3) Pojedynczy przebieg (procesowy):

```powershell
python Airport_zad1.py
```

4) Porównanie wszystkich trzech wersji (zapis plików do `results/`):

```powershell
python compare.py
```

5) Replikacje (np. 100 replik):

```powershell
python test_replications.py
```

6) Eksport szczegółowych logów per-samolot (CSV):

```powershell
python compare_logs.py
```

## Gdzie są wyniki?
- Wszystkie pliki wynikowe (PNG/CSV) trafiają do katalogu `results/` i zawierają w nazwie znacznik czasu, np. `results/compare_powietrze_20251218_161020.png`.

## Kilka uwag technicznych i ograniczeń
- Determinizm: podanie ziarna RNG pozwala powtarzać eksperymenty, ale aby trzy implementacje generowały dokładnie tę samą sekwencję zdarzeń (bit-po-bicie), trzeba by pre-generować i podawać tę samą sekwencję interwałów/obsług itp. Obecnie porównania są statystyczne (te same rozkłady i RNG), nie gwarantują identycznych trajektorii.
- Testy: projekt nie zawiera jeszcze automatycznych testów jednostkowych; mogę dodać prosty test porównawczy.

## Co mogę zrobić dalej (opcjonalnie)
- Dodać `requirements.txt` i prosty `run_all.ps1`.
- Dodać jednostkowe testy porównujące kluczowe metryki.
- Przygotować raport PDF/HTML z wykresami wyników.

Jeśli chcesz, dostosuję README dalej (np. dodać przykład wyników i zrzuty wykresów). Plik znajduje się teraz tutaj: [README.md](README.md)
