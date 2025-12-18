import random
import matplotlib.pyplot as plt
from utils import result_path
from airport_step import AirportStep
from airport_event import AirportEvent
import simpy
from Airport2025 import Airport as AirportProcess
from pregen import generate_prefed


def resample_event_series(times, values, until):
    """Resample event-driven step series to integer times 0..until."""
    out = [0] * (until + 1)
    if not times:
        return out
    idx = 0
    last_val = 0
    for t in range(until + 1):
        while idx < len(times) and times[idx] <= t:
            last_val = values[idx]
            idx += 1
        out[t] = last_val
    return out


def run_all(sim_time=100, seed=0):
    master = random.Random(seed)
    seeds = [master.randint(0, 2**31 - 1) for _ in range(3)]

    # Step engine
    # generate a shared prefed stream
    streams = generate_prefed(seed, sim_time, arrival_interval=3.0, landing_duration=3.0)
    step = AirportStep(arrival_interval=3.0, landing_duration=3.0, departure_interval=4, rng=random.Random(master.randint(0, 2**31-1)), streams=streams)
    step.run(sim_time)
    step_air = step.hist_kolejki_powietrze
    step_ground = step.hist_kolejki_plyta

    # Event engine (SimPy)
    env = simpy.Environment()
    event = AirportEvent(env, arrival_interval=3.0, landing_duration=3.0, departure_interval=4, rng=random.Random(master.randint(0, 2**31-1)), streams=streams)
    env.run(until=sim_time)
    evt_air = resample_event_series(event.hist_times, event.hist_kolejki_powietrze, sim_time)
    evt_ground = resample_event_series(event.hist_times, event.hist_kolejki_plyta, sim_time)

    # Process (simpy) engine
    env = simpy.Environment()
    proc = AirportProcess(env, arrival_interval=3.0, landing_duration=3.0, departure_interval=4, rng=random.Random(master.randint(0, 2**31-1)), streams=streams)
    env.run(until=sim_time)
    proc_air = proc.hist_kolejki_powietrze
    proc_ground = proc.hist_kolejki_plyta

    # Align lengths
    def align(arr):
        if len(arr) > sim_time + 1:
            return arr[: sim_time + 1]
        return arr + [arr[-1]] * (sim_time + 1 - len(arr)) if arr else [0] * (sim_time + 1)

    step_air = align(step_air)
    step_ground = align(step_ground)
    proc_air = align(proc_air)
    proc_ground = align(proc_ground)

    # Plot time-series comparison
    t = list(range(sim_time + 1))
    plt.figure(figsize=(10, 5))
    plt.plot(t, step_air, label='krok - powietrze')
    plt.plot(t, evt_air, label='zdarzenia - powietrze')
    plt.plot(t, proc_air, label='proces - powietrze')
    plt.xlabel('Czas')
    plt.ylabel('Liczba w kolejce (powietrze)')
    plt.legend()
    plt.tight_layout()
    plt.savefig(result_path('compare_powietrze', 'png'))

    plt.figure(figsize=(10, 5))
    plt.plot(t, step_ground, label='krok - plyta')
    plt.plot(t, evt_ground, label='zdarzenia - plyta')
    plt.plot(t, proc_ground, label='proces - plyta')
    plt.xlabel('Czas')
    plt.ylabel('Liczba na płycie')
    plt.legend()
    plt.tight_layout()
    plt.savefig(result_path('compare_plyta', 'png'))

    # Average waiting times
    def avg(lst):
        return sum(lst) / len(lst) if lst else 0

    stats = {
        'krok': (avg(step.czasy_oczekiwania_powietrze), avg(step.czasy_oczekiwania_plyta)),
        'zdarzenia': (avg(event.czasy_oczekiwania_powietrze), avg(event.czasy_oczekiwania_plyta)),
        'proces': (avg(proc.czasy_oczekiwania_powietrze), avg(proc.czasy_oczekiwania_plyta)),
    }

    # Bar chart
    labels = ['powietrze', 'plyta']
    x = [0, 1]
    width = 0.2
    plt.figure(figsize=(8, 5))
    plt.bar([xi - width for xi in x], [stats['krok'][0], stats['krok'][1]], width=width, label='krok')
    plt.bar(x, [stats['zdarzenia'][0], stats['zdarzenia'][1]], width=width, label='zdarzenia')
    plt.bar([xi + width for xi in x], [stats['proces'][0], stats['proces'][1]], width=width, label='proces')
    plt.xticks(x, labels)
    plt.ylabel('Sredni czas oczekiwania')
    plt.legend()
    plt.tight_layout()
    plt.savefig(result_path('compare_waiting_times', 'png'))


if __name__ == '__main__':
    run_all(sim_time=100, seed=0)
