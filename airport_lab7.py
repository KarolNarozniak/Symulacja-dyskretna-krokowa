from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Optional

import matplotlib.pyplot as plt
import simpy

from models import Passenger, Plane
from utils import result_path


@dataclass
class ReliabilityElement:
    name: str
    mean_time_to_failure: float
    repair_mean: float
    repair_std: float
    working: bool = True


class GateReliability:
    def __init__(self, env: simpy.Environment, scanner: ReliabilityElement, door: ReliabilityElement, rng: random.Random):
        self.env = env
        self.scanner = scanner
        self.door = door
        self.rng = rng
        self._service_processes: set[simpy.Process] = set()

        self.state_times: list[float] = []
        self.scanner_states: list[int] = []
        self.door_states: list[int] = []
        self.gate_states: list[int] = []

        self._record_state()

        env.process(self._run_element(scanner))
        env.process(self._run_element(door))

    def _record_state(self) -> None:
        self.state_times.append(self.env.now)
        self.scanner_states.append(1 if self.scanner.working else 0)
        self.door_states.append(1 if self.door.working else 0)
        self.gate_states.append(1 if self.is_operational() else 0)

    def is_operational(self) -> bool:
        return self.scanner.working and self.door.working

    def register_service(self, proc: simpy.Process) -> None:
        self._service_processes.add(proc)

    def unregister_service(self, proc: simpy.Process) -> None:
        self._service_processes.discard(proc)

    def _interrupt_services(self) -> None:
        for proc in list(self._service_processes):
            if not proc.triggered:
                proc.interrupt("gate_failure")

    def _run_element(self, element: ReliabilityElement):
        while True:
            time_to_failure = self.rng.expovariate(1.0 / max(0.0001, element.mean_time_to_failure))
            yield self.env.timeout(time_to_failure)
            if element.working:
                element.working = False
                self._record_state()
                self._interrupt_services()
            repair_time = max(0.0, self.rng.gauss(element.repair_mean, element.repair_std))
            yield self.env.timeout(repair_time)
            if not element.working:
                element.working = True
                self._record_state()


class ServiceGate:
    def __init__(self, env: simpy.Environment, reliability: GateReliability, rng: random.Random, service_rate: float):
        self.env = env
        self.reliability = reliability
        self.rng = rng
        self.service_rate = service_rate

        self.queue: list[Passenger] = []
        self.service_free = True
        self.completed: list[Passenger] = []

        self.queue_times: list[float] = [0.0]
        self.queue_lengths: list[int] = [0]

    def _record_queue(self) -> None:
        self.queue_times.append(self.env.now)
        self.queue_lengths.append(len(self.queue))

    def add_passenger(self, passenger: Passenger) -> None:
        self.queue.append(passenger)
        self._record_queue()
        if self.service_free:
            self.env.process(self._start_service())

    def _wait_until_operational(self):
        while not self.reliability.is_operational():
            yield self.env.timeout(0.1)

    def _start_service(self):
        if not self.queue or not self.service_free:
            return
        self.service_free = False
        passenger = self.queue.pop(0)
        self._record_queue()
        passenger.service_start = self.env.now
        service_time = max(0.01, self.rng.expovariate(self.service_rate))
        remaining = service_time

        proc = self.env.active_process
        if proc is not None:
            self.reliability.register_service(proc)

        try:
            while remaining > 0:
                if not self.reliability.is_operational():
                    yield from self._wait_until_operational()
                start = self.env.now
                try:
                    yield self.env.timeout(remaining)
                    remaining = 0
                except simpy.Interrupt:
                    remaining -= self.env.now - start
        finally:
            if proc is not None:
                self.reliability.unregister_service(proc)

        passenger.service_end = self.env.now
        self.completed.append(passenger)
        self.service_free = True
        if self.queue:
            self.env.process(self._start_service())

    def average_queue_length(self, until: float) -> float:
        if len(self.queue_times) == 1:
            return 0.0
        total = 0.0
        for i in range(1, len(self.queue_times)):
            dt = self.queue_times[i] - self.queue_times[i - 1]
            total += self.queue_lengths[i - 1] * dt
        last_dt = until - self.queue_times[-1]
        if last_dt > 0:
            total += self.queue_lengths[-1] * last_dt
        return total / max(until, 1e-9)


class AirportLab7:
    def __init__(
        self,
        env: simpy.Environment,
        arrival_interval: float,
        landing_duration: float,
        checkin_duration: float,
        unloading_duration: float,
        passenger_ranges: dict[int, tuple[int, int]],
        service_rate: float,
        scanner_params: tuple[float, float, float],
        door_params: tuple[float, float, float],
        rng: Optional[random.Random] = None,
    ) -> None:
        self.env = env
        self.arrival_interval = arrival_interval
        self.landing_duration = landing_duration
        self.checkin_duration = checkin_duration
        self.unloading_duration = unloading_duration
        self.passenger_ranges = passenger_ranges
        self.rng = rng or random.Random()

        scanner = ReliabilityElement("scanner", *scanner_params)
        door = ReliabilityElement("door", *door_params)
        self.reliability = GateReliability(env, scanner, door, self.rng)
        self.service_gate = ServiceGate(env, self.reliability, self.rng, service_rate)

        self.queue_air: list[Plane] = []
        self.queue_pad: list[Plane] = []
        self.current_landing: Optional[Plane] = None
        self.runway_busy_until = -1.0
        self.arrival_time = 0.0
        self._next_plane_id = 0
        self._next_passenger_id = 0

        self.plane_history_times: list[float] = []
        self.plane_air_counts: list[int] = []
        self.plane_pad_counts: list[int] = []

        self._schedule_next_arrival(0.0)
        self.env.process(self._arrival_generator())

    def _schedule_next_arrival(self, now: float) -> None:
        raw = self.rng.expovariate(1.0 / max(0.0001, self.arrival_interval))
        delta = max(1, math.ceil(raw))
        self.arrival_time = now + delta

    def _arrival_generator(self):
        while True:
            delta = self.arrival_time - self.env.now
            if delta > 0:
                yield self.env.timeout(delta)
            self._arrival()

    def _losuj_kategorie(self) -> int:
        return self.rng.choice([1, 2, 3])

    def _losuj_czas_ladowania(self, kategoria: int) -> int:
        if kategoria == 1:
            return max(1, int(self.landing_duration))
        if kategoria == 2:
            return self.rng.randint(2, 5)
        val = self.rng.gauss(self.landing_duration, 1.5)
        return max(1, math.ceil(val))

    def _collect_plane_stats(self) -> None:
        count_air = len(self.queue_air) + (1 if self.current_landing else 0)
        count_pad = len(self.queue_pad)
        self.plane_history_times.append(self.env.now)
        self.plane_air_counts.append(count_air)
        self.plane_pad_counts.append(count_pad)

    def _arrival(self) -> None:
        self._next_plane_id += 1
        kat = self._losuj_kategorie()
        plane = Plane(id=self._next_plane_id, category=kat, arrival_time=self.env.now)
        self.queue_air.append(plane)
        if self.current_landing is None and not self.queue_pad:
            self._start_landing()
        self._collect_plane_stats()
        self._schedule_next_arrival(self.env.now)

    def _start_landing(self) -> None:
        if not self.queue_air or self.queue_pad:
            return
        plane = self.queue_air.pop(0)
        plane.landing_start = self.env.now
        landing_time = self._losuj_czas_ladowania(plane.category)
        self.current_landing = plane
        self.runway_busy_until = self.env.now + landing_time
        self.env.process(self._landing_complete_proc(plane, landing_time))

    def _landing_complete_proc(self, plane: Plane, delay: float):
        yield self.env.timeout(delay)
        self._landing_complete(plane)

    def _landing_complete(self, plane: Plane) -> None:
        plane.landing_end = self.env.now
        self.queue_pad.append(plane)
        self.current_landing = None
        self.runway_busy_until = -1
        self.env.process(self._post_landing_proc(plane))
        if self.queue_air and not self.queue_pad:
            self._start_landing()
        self._collect_plane_stats()

    def _post_landing_proc(self, plane: Plane):
        yield self.env.timeout(self.checkin_duration)
        yield self.env.timeout(self.unloading_duration)
        plane.unload_end = self.env.now
        plane.departure_time = self.env.now
        self.queue_pad.remove(plane)
        self._spawn_passengers(plane)
        if self.queue_air and self.current_landing is None and not self.queue_pad:
            self._start_landing()
        self._collect_plane_stats()

    def _spawn_passengers(self, plane: Plane) -> None:
        a, b = self.passenger_ranges.get(plane.category, (10, 20))
        count = self.rng.randint(a, b)
        for _ in range(count):
            self._next_passenger_id += 1
            passenger = Passenger(id=self._next_passenger_id, arrival_time=self.env.now)
            self.service_gate.add_passenger(passenger)

    def summarize(self, until: float) -> None:
        durations = [
            p.service_end - p.service_start
            for p in self.service_gate.completed
            if p.service_start is not None and p.service_end is not None
        ]
        avg_service = sum(durations) / len(durations) if durations else 0.0
        avg_queue = self.service_gate.average_queue_length(until)

        print("\n--- Podsumowanie (Lab 7) ---")
        print(f"Liczba obsłużonych pasażerów: {len(durations)}")
        print(f"Średni czas obsługi (z awariami): {avg_service:.2f}")
        print(f"Średnia długość kolejki: {avg_queue:.2f}")

        plt.figure(figsize=(10, 5))
        plt.step(self.reliability.state_times, self.reliability.gate_states, where="post", label="bramka")
        plt.step(self.reliability.state_times, self.reliability.scanner_states, where="post", label="skaner")
        plt.step(self.reliability.state_times, self.reliability.door_states, where="post", label="drzwi")
        plt.xlabel("Czas")
        plt.ylabel("Stan (1=działa, 0=awaria)")
        plt.legend()
        plt.tight_layout()
        plt.savefig(result_path("stany_bramki", "png"))

        plt.figure(figsize=(10, 5))
        plt.step(self.service_gate.queue_times, self.service_gate.queue_lengths, where="post", label="kolejka")
        plt.xlabel("Czas")
        plt.ylabel("Długość kolejki")
        plt.legend()
        plt.tight_layout()
        plt.savefig(result_path("kolejka_pasazerow", "png"))


def run_simulation(sim_time: int = 500, seed: int = 0) -> AirportLab7:
    rng = random.Random(seed)
    env = simpy.Environment()
    airport = AirportLab7(
        env=env,
        arrival_interval=6.0,
        landing_duration=3.0,
        checkin_duration=4.0,
        unloading_duration=3.0,
        passenger_ranges={1: (40, 60), 2: (60, 80), 3: (80, 120)},
        service_rate=2.0,
        scanner_params=(80.0, 6.0, 1.0),
        door_params=(100.0, 8.0, 1.5),
        rng=rng,
    )
    env.run(until=sim_time)
    airport.summarize(sim_time)
    return airport


if __name__ == "__main__":
    run_simulation(sim_time=500, seed=0)
