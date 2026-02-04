# Symulacja lotniska (Lab 7) — system kolejkowy i niezawodność

Repozytorium zawiera wersję zadania laboratoryjnego nr 7: **symulację zdarzeniową** lotniska z obsługą pasażerów oraz niezawodnością automatycznej bramki (**skaner + drzwi** w strukturze szeregowej).  
Wyniki (obrazy) oraz pliki CSV zapisywane są do katalogu wynikowego generowanego przez `utils.result_path()`.

## Główne pliki
- `airport_lab7.py` — główna symulacja (SimPy): przyloty, lądowania, odprawa i rozładunek, obsługa pasażerów oraz awaryjność bramki.
- `models.py` — dataclasses: `Plane` i `Passenger`.
- `utils.py` — pomocnik dla zapisu wyników: `ensure_results_dir()` i `result_path()`.

## Założenia zadania (skrót)
- Po lądowaniu realizowana jest odprawa samolotu oraz rozładunek, a następnie pasażerowie trafiają do kolejki FIFO przy automatycznej bramce.
- Liczba pasażerów zależy od kategorii samolotu (losowanie z rozkładu jednostajnego na przedziale `(a,b)`).
- Automatyczna bramka składa się ze skanera i drzwi (**struktura szeregowa**) — awaria jednego elementu zatrzymuje pracę do czasu naprawy.
- Czas do awarii: rozkład wykładniczy; czas naprawy: rozkład normalny (ucięty do 0).
- Zbierane metryki: średni czas obsługi (z awariami), długość kolejki (w czasie i średnia), przebiegi stanów bramki, skanera i drzwi.

## Odpowiedzi na pytania prowadzącego (15)

### 1️⃣ Gdzie w tym programie jest zaimplementowana symulacja zdarzeniowa?
Symulacja jest zdarzeniowa, bo **czas w modelu przesuwa się tylko w momentach zdarzeń** sterowanych przez SimPy:
- uruchamiam procesy przez `env.process(...)` (np. `AirportLab7._arrival_generator()`, `AirportLab7._landing_complete_proc()`, `AirportLab7._post_landing_proc()`, `GateReliability._run_element()`),
- a przejścia czasu realizuję przez `yield env.timeout(...)`.
Nie ma żadnej pętli typu „for t in range(sim_time)” ani ręcznego kroku czasowego — wszystko dzieje się jako sekwencja zdarzeń i timeoutów.

### 2️⃣ Jakie są główne zdarzenia w symulacji i gdzie są generowane?
Główne zdarzenia (w sensie modelu) i miejsca w kodzie:
- **Przylot samolotu**: `AirportLab7._arrival()` (wywoływane z procesu `AirportLab7._arrival_generator()`).
- **Start lądowania / koniec lądowania**: `AirportLab7._start_landing()` oraz `AirportLab7._landing_complete_proc()` → `AirportLab7._landing_complete()`.
- **Odprawa + rozładunek**: `AirportLab7._post_landing_proc()` (dwa `yield env.timeout(...)`).
- **Wygenerowanie pasażerów**: `AirportLab7._spawn_passengers()`.
- **Przyjście pasażera do kolejki**: `ServiceGate.add_passenger()`.
- **Start/koniec obsługi**: `ServiceGate._start_service()` (logi `service_start`, `service_end`).
- **Awaria/naprawa skanera lub drzwi**: `GateReliability._run_element()` (logi `failure`, `repair`).
- **Snapshoty stanu**: `AirportLab7._snapshot_proc()`.

### 3️⃣ Jak obsługiwana jest kolejka pasażerów i dlaczego jest FIFO?
Kolejka jest zwykłą listą:
- dodanie na koniec: `self.queue.append(passenger)` w `ServiceGate.add_passenger()`,
- pobranie „z przodu” (pierwszy przyszedł, pierwszy obsłużony): `passenger = self.queue.pop(0)` w `ServiceGate._start_service()`.
To jest FIFO, bo zawsze usuwam element o najniższym indeksie (najwcześniejszy przybyły).

### 4️⃣ Co dokładnie oznacza „jedna bramka” w Twoim modelu?
„Jedna bramka” oznacza **jeden obiekt** `ServiceGate` (jedno stanowisko obsługi) z:
- jedną kolejką `ServiceGate.queue`,
- jednym serwerem logicznym (flaga `ServiceGate.service_free`),
- jedną niezawodnością `GateReliability` (wspólne stany skanera i drzwi).
Nie używam `simpy.Resource`, ale realizuję ograniczenie „jedna obsługa naraz” przez `service_free` i uruchamianie pojedynczego procesu `_start_service()`.

### 5️⃣ Jak jest zaimplementowana struktura szeregowa bramki (drzwi + skaner)?
Struktura szeregowa (AND) jest w `GateReliability.is_operational()`:
```python
return self.scanner.working and self.door.working
```
To znaczy: jeśli **dowolny element ma awarię**, to cała bramka jest nieoperacyjna.  
Dodatkowo w `GateReliability._run_element()` po awarii:
- ustawiam `element.working = False`,
- przeliczam stan bramki,
- i przerywam obsługę pasażera przez `self._interrupt_services()`.

### 6️⃣ Jakie rozkłady losowe stosujesz i do czego?
W kodzie są następujące rozkłady:
- **Czas do awarii elementów bramki (skaner, drzwi)**: wykładniczy  
  `time_to_failure = rng.expovariate(1.0 / MTBF)` w `GateReliability._run_element()`.
- **Czas naprawy elementów**: normalny (ucięty do 0)  
  `repair_time = max(0.0, rng.gauss(mean, std))` w `GateReliability._run_element()`.
- **Czas obsługi pasażera**: wykładniczy  
  `service_time = rng.expovariate(service_rate)` w `ServiceGate._start_service()`.
- **Liczba pasażerów w samolocie** (zależnie od kategorii): jednostajny całkowity  
  `count = rng.randint(a, b)` w `AirportLab7._spawn_passengers()`.
- **Czas do kolejnego przylotu samolotu**: wykładniczy  
  `raw = rng.expovariate(1.0 / arrival_interval)` w `AirportLab7._schedule_next_arrival()`.
- **Wybór kategorii samolotu**: losowanie z dyskretnego zbioru  
  `rng.choice([1,2,3])` w `AirportLab7._losuj_kategorie()`.

### 7️⃣ Dlaczego do czasu awarii użyto rozkładu wykładniczego?
Wykładniczy ma własność **braku pamięci** (memoryless), czyli prawdopodobieństwo awarii w następnym krótkim okresie nie zależy od tego, jak długo element już działał.  
To jest standardowy model w prostych analizach niezawodności (proces Poissona dla awarii). Normalny mógłby generować wartości ujemne i nie ma własności braku pamięci.

### 8️⃣ Jak obsługujesz sytuację, gdy awaria nastąpi w trakcie obsługi pasażera?
Obsługa pasażera jest **przerywana i wznawiana**:
- proces obsługi rejestruję w `GateReliability.register_service(proc)`,
- gdy element pada, `GateReliability._interrupt_services()` wywołuje `proc.interrupt("gate_failure")`,
- w `ServiceGate._start_service()` mam pętlę z `try/except simpy.Interrupt`, gdzie odejmuję wykonany czas i zapamiętuję `remaining`.
Po naprawie (`GateReliability.is_operational()` wraca na True) obsługa jest kontynuowana aż `remaining` spadnie do 0.

### 9️⃣ Skąd wiesz, że pasażer nie zostanie „zgubiony” podczas awarii?
Pasażer jest zawsze w jednym z dwóch miejsc:
- albo w kolejce `ServiceGate.queue`,
- albo aktualnie obsługiwany w lokalnej zmiennej `passenger` w procesie `_start_service()`.
Awaria nie usuwa pasażera z systemu — tylko przerywa timeout obsługi, a pasażer „czeka” w tym samym procesie aż bramka znów będzie działać. Dopiero po zakończeniu obsługi dopisuję go do `self.completed`.

### 🔟 Jak liczysz średnią długość kolejki i dlaczego tak?
Liczenie jest **średnią po czasie** (time-weighted average), a nie średnią z próbek:
- zapisuję zmianę kolejki w momentach zdarzeń (`queue_times`, `queue_lengths`),
- w `ServiceGate.average_queue_length()` liczę pole pod wykresem schodkowym:  
  sumuję `queue_len * dt` dla kolejnych przedziałów czasu,
- dzielę przez całkowity czas `until`.
To jest poprawne w symulacji zdarzeniowej, bo kolejka jest funkcją schodkową.

### 1️⃣1️⃣ Dlaczego kolejka ma skoki, a nie rośnie płynnie?
Bo pasażerowie pojawiają się **pakietami** po zakończeniu rozładunku samolotu:
- `AirportLab7._post_landing_proc()` kończy rozładunek,
- potem `AirportLab7._spawn_passengers()` dodaje naraz `count` pasażerów do kolejki.
To daje nagłe wzrosty, a spadki wynikają z kolejnych zakończeń obsługi.

### 1️⃣2️⃣ Skąd wiesz, że symulacja jest stabilna, a nie przeciążona?
Praktycznie sprawdzam to na podstawie wyników:
- czy średnia i maksymalna długość kolejki nie rosną „w nieskończoność” w czasie,
- czy liczba obsłużonych rośnie w tempie podobnym do napływu.
Teoretycznie: stabilność zależy od relacji „średni napływ pasażerów” vs „przepustowość bramki”.  
W kodzie można to stroić przez `arrival_interval`, zakresy pasażerów i `service_rate` (tryb `stable_demo=True` ma mniejszy napływ i większą przepustowość).

### 1️⃣3️⃣ Jak sprawdziłbyś poprawność FIFO bez patrzenia na kod?
Walidacja wynikami (bez czytania implementacji):
1. W logach CSV (`events_*.csv`) patrzę na kolejność zdarzeń `service_start` i porównuję `passenger_id`.  
2. W trakcie tworzenia pasażerów ID rośnie monotonicznie, więc przy FIFO powinienem widzieć, że starty obsługi idą w kolejności rosnącej (z pominięciem sytuacji, gdy kolejka jest pusta).
3. Dodatkowo mogę policzyć statystykę: czy kiedykolwiek obsłużyłem ID większe, gdy w kolejce był jeszcze mniejszy (to da się wykryć z eventów).

### 1️⃣4️⃣ Jakie dane zapisujesz do CSV i po co aż dwa pliki?
Są dwa typy danych:
- `events_*.csv` (EventLogger): log zdarzeń „kto/co/kiedy” — np. `plane_arrive`, `landing_start`, `failure`, `repair`, `service_start`, `service_end`. To służy do audytu przebiegu symulacji i weryfikacji logiki.
- `snapshots_*.csv`: okresowe migawki stanu co `snapshot_step` — stan bramki/skanera/drzwi + długość kolejki + info o kolejkach samolotów. To jest wygodne do wykresów i analizy czasu bez odtwarzania wszystkiego z eventów.

### 1️⃣5️⃣ Co by się stało, gdyby zwiększyć intensywność przylotów samolotów?
Zwiększenie intensywności przylotów (czyli mniejsze `arrival_interval`) podnosi średni napływ pasażerów.  
Jeśli napływ przekroczy przepustowość bramki (uwzględniając przestoje przez awarie), to:
- kolejka zacznie rosnąć, średnia długość kolejki i maksima będą większe,
- czasy oczekiwania i średni czas „bycia w systemie” wzrosną,
- system stanie się przeciążony (brak stanu stacjonarnego w praktyce dla długiego horyzontu).

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
- Wykresy PNG: `stan_bramki_*.png`, `stan_skanera_*.png`, `stan_drzwi_*.png`, `kolejka_pasazerow_*.png`
- Logi: `events_*.csv` oraz `snapshots_*.csv`
