import math
from pregen import generate_prefed
import random
import simpy
from airport_step import AirportStep
from airport_event import AirportEvent
from Airport2025 import Airport as AirportProcess
import simpy


def normalize(x):
    # convert floats that are whole numbers to int for clearer comparison
    if x is None:
        return None
    try:
        if isinstance(x, float) and abs(x - round(x)) < 1e-9:
            return int(round(x))
    except Exception:
        pass
    return x


def record_dict(sam):
    return {
        'id': sam.id,
        'czas_przylotu': normalize(sam.czas_przylotu),
        'czas_rozpoczecia_ladowania': normalize(sam.czas_rozpoczecia_ladowania),
        'czas_zakonczenia_ladowania': normalize(sam.czas_zakonczenia_ladowania),
        'czas_odlotu': normalize(sam.czas_odlotu),
    }


def run_and_compare(seed=0, sim_time=100):
    streams = generate_prefed(seed, sim_time, arrival_interval=3.0, landing_duration=3.0)

    rng = random.Random(seed)

    # step
    step = AirportStep(arrival_interval=3.0, landing_duration=3.0, departure_interval=4,
                       rng=random.Random(rng.randint(0, 2**31-1)), streams=streams)
    step.run(sim_time)
    step_map = {s.id: record_dict(s) for s in step.completed}

    # event (SimPy)
    env = simpy.Environment()
    event = AirportEvent(env, arrival_interval=3.0, landing_duration=3.0, departure_interval=4,
                         rng=random.Random(rng.randint(0, 2**31-1)), streams=streams)
    env.run(until=sim_time)
    event_map = {s.id: record_dict(s) for s in event.completed}

    # process
    env = simpy.Environment()
    proc = AirportProcess(env, arrival_interval=3.0, landing_duration=3.0, departure_interval=4,
                         rng=random.Random(rng.randint(0, 2**31-1)), streams=streams)
    env.run(until=sim_time)
    proc_map = {s.id: record_dict(s) for s in proc.completed}

    # union of ids
    ids = sorted(set(list(step_map.keys()) + list(event_map.keys()) + list(proc_map.keys())))

    total_diffs = 0
    for sid in ids:
        s = step_map.get(sid)
        e = event_map.get(sid)
        p = proc_map.get(sid)
        # if any missing, report
        if s is None or e is None or p is None:
            print(f"ID {sid}: missing in one of the outputs -> step:{'yes' if s else 'no'} event:{'yes' if e else 'no'} proc:{'yes' if p else 'no'}")
            total_diffs += 1
            continue
        # compare fields
        for key in ['czas_przylotu', 'czas_rozpoczecia_ladowania', 'czas_zakonczenia_ladowania', 'czas_odlotu']:
            sv, ev, pv = s[key], e[key], p[key]
            if sv != ev or sv != pv:
                print(f"ID {sid} field '{key}': step={sv}, event={ev}, proc={pv}")
                total_diffs += 1

    if total_diffs == 0:
        print("All records identical (after normalization).")
    else:
        print(f"Found {total_diffs} differences (fields/IDs).")


if __name__ == '__main__':
    run_and_compare(seed=0, sim_time=100)
