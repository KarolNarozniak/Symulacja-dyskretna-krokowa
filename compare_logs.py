import csv
import random
import simpy
from airport_step import AirportStep
from event_engine import EventEngine
from airport_event import AirportEvent
from Airport2025 import Airport as AirportProcess
from utils import result_path
from pregen import generate_prefed


def write_csv(filename, records):
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['id', 'czas_przylotu', 'czas_rozpoczecia_ladowania', 'czas_zakonczenia_ladowania', 'czas_odlotu'])
        for r in records:
            writer.writerow([r.id, r.czas_przylotu, r.czas_rozpoczecia_ladowania, r.czas_zakonczenia_ladowania, r.czas_odlotu])


def run_and_dump(seed=0, sim_time=100):
    rng = random.Random(seed)
    # generate shared prefed streams so all three implementations get identical input sequences
    streams = generate_prefed(seed, sim_time, arrival_interval=3.0, landing_duration=3.0)

    # step
    step = AirportStep(arrival_interval=3.0, landing_duration=3.0, departure_interval=4, rng=random.Random(rng.randint(0,2**31-1)), streams=streams)
    step.run(sim_time)
    write_csv(result_path('log_step', 'csv'), step.completed)

    # event
    eng = EventEngine()
    event = AirportEvent(eng, arrival_interval=3.0, landing_duration=3.0, departure_interval=4, rng=random.Random(rng.randint(0,2**31-1)), streams=streams)
    eng.run(until=sim_time)
    write_csv(result_path('log_event', 'csv'), event.completed)

    # process
    env = simpy.Environment()
    proc = AirportProcess(env, arrival_interval=3.0, landing_duration=3.0, departure_interval=4, rng=random.Random(rng.randint(0,2**31-1)), streams=streams)
    env.run(until=sim_time)
    write_csv(result_path('log_process', 'csv'), proc.completed)

    # logs written


if __name__ == '__main__':
    run_and_dump(seed=0, sim_time=100)
