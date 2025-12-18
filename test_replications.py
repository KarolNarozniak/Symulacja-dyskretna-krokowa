import random
import statistics
from airport_step import AirportStep
from airport_event import AirportEvent
import simpy
from Airport2025 import Airport as AirportProcess
from pregen import generate_prefed


def run_once(seed, sim_time=100):
    rng = random.Random(seed)
    # generate shared prefed streams so all three sims use identical arrivals/categories/landing times
    streams = generate_prefed(seed, sim_time, arrival_interval=3.0, landing_duration=3.0)

    step = AirportStep(arrival_interval=3.0, landing_duration=3.0, departure_interval=4,
                       rng=random.Random(rng.randint(0, 2**31-1)), streams=streams)
    step.run(sim_time)
    step_vals = (statistics.mean(step.czasy_oczekiwania_powietrze) if step.czasy_oczekiwania_powietrze else 0,
                 statistics.mean(step.czasy_oczekiwania_plyta) if step.czasy_oczekiwania_plyta else 0)

    env = simpy.Environment()
    event = AirportEvent(env, arrival_interval=3.0, landing_duration=3.0, departure_interval=4,
                         rng=random.Random(rng.randint(0, 2**31-1)), streams=streams)
    env.run(until=sim_time)
    event_vals = (statistics.mean(event.czasy_oczekiwania_powietrze) if event.czasy_oczekiwania_powietrze else 0,
                  statistics.mean(event.czasy_oczekiwania_plyta) if event.czasy_oczekiwania_plyta else 0)

    env = simpy.Environment()
    proc = AirportProcess(env, arrival_interval=3.0, landing_duration=3.0, departure_interval=4,
                         rng=random.Random(rng.randint(0, 2**31-1)), streams=streams)
    env.run(until=sim_time)
    proc_vals = (statistics.mean(proc.czasy_oczekiwania_powietrze) if proc.czasy_oczekiwania_powietrze else 0,
                 statistics.mean(proc.czasy_oczekiwania_plyta) if proc.czasy_oczekiwania_plyta else 0)

    return step_vals, event_vals, proc_vals


def run_replicates(n=100, sim_time=100, base_seed=0):
    step_air = []
    step_ground = []
    evt_air = []
    evt_ground = []
    proc_air = []
    proc_ground = []

    for i in range(n):
        s_seed = base_seed + i
        s, e, p = run_once(s_seed, sim_time=sim_time)
        step_air.append(s[0]); step_ground.append(s[1])
        evt_air.append(e[0]); evt_ground.append(e[1])
        proc_air.append(p[0]); proc_ground.append(p[1])

    def summarize(arr):
        return (statistics.mean(arr), statistics.pstdev(arr))

    print('Replikacje:', n)
    print('Krok powietrze mean,std:', summarize(step_air))
    print('Zdarzenia powietrze mean,std:', summarize(evt_air))
    print('Proces powietrze mean,std:', summarize(proc_air))
    print('---')
    print('Krok plyta mean,std:', summarize(step_ground))
    print('Zdarzenia plyta mean,std:', summarize(evt_ground))
    print('Proces plyta mean,std:', summarize(proc_ground))


if __name__ == '__main__':
    run_replicates(n=100, sim_time=100, base_seed=0)
