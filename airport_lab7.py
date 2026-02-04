from __future__ import annotations

import csv
import math
import os
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import simpy

import utils  # debug: ensure we import the local utils.py
from models import Passenger, Plane
from utils import ensure_results_dir, result_path


# ----------------- CSV logging -----------------


class EventLogger:
    """CSV event logger for later review in Excel."""
    def __init__(self, csv_path: str | Path, enabled: bool = True):
        self.enabled = enabled
        self.path = Path(csv_path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._f = None
        self._w = None

    def open(self) -> None:
        if not self.enabled:
            return
        self._f = open(self.path, "w", newline="", encoding="utf-8")
        self._w = csv.DictWriter(
            self._f,
            fieldnames=[
                "time", "event",
                "plane_id", "plane_cat",
                "passenger_id",
                "queue_len",
                "scanner", "door", "gate",
                "info",
            ],
        )
        self._w.writeheader()

    def close(self) -> None:
        if self._f:
            self._f.close()
            self._f = None
            self._w = None

    def log(
        self,
        time: float,
        event: str,
        plane_id: int | None = None,
        plane_cat: int | None = None,
        passenger_id: int | None = None,
        queue_len: int | None = None,
        scanner: int | None = None,
        door: int | None = None,
        gate: int | None = None,
        info: str = "",
    ) -> None:
        if not self.enabled:
            return
        if self._w is None:
            raise RuntimeError("EventLogger.open() was not called")

        self._w.writerow(
            {
                "time": float(time),
                "event": event,
                "plane_id": "" if plane_id is None else plane_id,
                "plane_cat": "" if plane_cat is None else plane_cat,
                "passenger_id": "" if passenger_id is None else passenger_id,
                "queue_len": "" if queue_len is None else queue_len,
                "scanner": "" if scanner is None else scanner,
                "door": "" if door is None else door,
                "gate": "" if gate is None else gate,
                "info": info,
            }
        )


# ----------------- plot saving -----------------


def _safe_savefig(fig: plt.Figure, out_path: str | Path) -> None:
    p = Path(out_path).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(p)


# ----------------- simulation classes -----------------


@dataclass
class ReliabilityElement:
    name: str
    mean_time_to_failure: float
    repair_mean: float
    repair_std: float
    working: bool = True


class GateReliability:
    """
    Two-element SERIES structure:
      gate_operational == scanner_operational AND door_operational

    Requirements:
    - time-to-failure: exponential
    - repair time: normal (truncated at 0)
    - failure of one element stops the gate (interrupts ongoing service)
    - detailed reliability stats for summary
    """

    def __init__(
        self,
        env: simpy.Environment,
        scanner: ReliabilityElement,
        door: ReliabilityElement,
        rng: random.Random,
        logger: Optional[EventLogger] = None,
    ):
        self.env = env
        self.scanner = scanner
        self.door = door
        self.rng = rng
        self.logger = logger

        # currently running service processes (to interrupt on failure)
        self._service_processes: set[simpy.Process] = set()

        # state history for plots
        self.state_times: list[float] = []
        self.scanner_states: list[int] = []
        self.door_states: list[int] = []
        self.gate_states: list[int] = []

        # --- NEW: detailed reliability stats ---
        self.failure_count: dict[str, int] = {"scanner": 0, "door": 0}
        self.element_downtimes: dict[str, list[float]] = {"scanner": [], "door": []}  # durations
        self.repair_samples: dict[str, list[float]] = {"scanner": [], "door": []}     # sampled repair times
        self._element_down_start: dict[str, Optional[float]] = {"scanner": None, "door": None}

        # gate availability (union of downtimes, not double-counted)
        self.gate_down_time_total: float = 0.0
        self._gate_is_down: bool = False
        self._gate_down_start: Optional[float] = None

        self._record_state()  # initial state
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

    def _log_state(self, event: str, info: str = "") -> None:
        if not self.logger:
            return
        self.logger.log(
            self.env.now,
            event,
            scanner=1 if self.scanner.working else 0,
            door=1 if self.door.working else 0,
            gate=1 if self.is_operational() else 0,
            info=info,
        )

    # --------- NEW: gate downtime union (availability) ----------
    def _on_gate_state_change(self, was_operational: bool, is_operational: bool) -> None:
        if was_operational and (not is_operational):
            # gate transitions UP -> DOWN
            self._gate_is_down = True
            self._gate_down_start = self.env.now
        elif (not was_operational) and is_operational:
            # gate transitions DOWN -> UP
            if self._gate_is_down and self._gate_down_start is not None:
                self.gate_down_time_total += self.env.now - self._gate_down_start
            self._gate_is_down = False
            self._gate_down_start = None

    def _run_element(self, element: ReliabilityElement):
        while True:
            # exponential time to failure
            mtbf = max(0.0001, element.mean_time_to_failure)
            time_to_failure = self.rng.expovariate(1.0 / mtbf)
            yield self.env.timeout(time_to_failure)

            # fail element (if currently working)
            if element.working:
                was_op = self.is_operational()

                element.working = False
                self.failure_count[element.name] += 1
                self._element_down_start[element.name] = self.env.now

                # update gate availability (series structure)
                now_op = self.is_operational()
                self._on_gate_state_change(was_op, now_op)

                self._record_state()
                self._interrupt_services()
                self._log_state("failure", info=f"element={element.name}")

            # repair time ~ Normal(mean, std), truncated at 0
            repair_time = max(0.0, self.rng.gauss(element.repair_mean, element.repair_std))
            self.repair_samples[element.name].append(repair_time)
            yield self.env.timeout(repair_time)

            # repair element (if currently failed)
            if not element.working:
                was_op = self.is_operational()

                element.working = True

                # element downtime duration
                down_start = self._element_down_start.get(element.name)
                if down_start is not None:
                    self.element_downtimes[element.name].append(self.env.now - down_start)
                self._element_down_start[element.name] = None

                # update gate availability
                now_op = self.is_operational()
                self._on_gate_state_change(was_op, now_op)

                self._record_state()
                self._log_state(
                    "repair",
                    info=f"element={element.name}, repair_time={repair_time:.3f}",
                )

    def finalize_availability(self, until: float) -> None:
        """
        If simulation ends while gate is down, close the open downtime interval.
        Call once in summarize().
        """
        if self._gate_is_down and self._gate_down_start is not None:
            self.gate_down_time_total += max(0.0, until - self._gate_down_start)
            self._gate_is_down = False
            self._gate_down_start = None


class ServiceGate:
    def __init__(
        self,
        env: simpy.Environment,
        reliability: GateReliability,
        rng: random.Random,
        service_rate: float,
        logger: Optional[EventLogger] = None,
    ):
        self.env = env
        self.reliability = reliability
        self.rng = rng
        self.service_rate = service_rate
        self.logger = logger

        # FIFO queue
        self.queue: list[Passenger] = []
        self.service_free = True
        self.completed: list[Passenger] = []

        # queue-length over time (piecewise constant)
        self.queue_times: list[float] = [0.0]
        self.queue_lengths: list[int] = [0]

        # --- NEW: max queue length ---
        self.max_queue_len: int = 0

    def _record_queue(self) -> None:
        self.queue_times.append(self.env.now)
        self.queue_lengths.append(len(self.queue))
        if len(self.queue) > self.max_queue_len:
            self.max_queue_len = len(self.queue)

    def _log(self, event: str, passenger_id: Optional[int] = None, info: str = "") -> None:
        if not self.logger:
            return
        self.logger.log(
            self.env.now,
            event,
            passenger_id=passenger_id,
            queue_len=len(self.queue),
            scanner=1 if self.reliability.scanner.working else 0,
            door=1 if self.reliability.door.working else 0,
            gate=1 if self.reliability.is_operational() else 0,
            info=info,
        )

    def add_passenger(self, passenger: Passenger) -> None:
        self.queue.append(passenger)
        self._record_queue()
        self._log("passenger_queue_arrival", passenger_id=passenger.id)
        if self.service_free:
            self.env.process(self._start_service())

    def _wait_until_operational(self):
        # simple polling (keeps code readable)
        while not self.reliability.is_operational():
            try:
                yield self.env.timeout(0.1)
            except simpy.Interrupt:
                # if multiple interrupts happen, we just continue polling
                pass

    def _start_service(self):
        if not self.queue or not self.service_free:
            return

        self.service_free = False
        passenger = self.queue.pop(0)
        self._record_queue()

        passenger.service_start = self.env.now

        # service time ~ Exponential(rate)
        service_time = max(0.01, self.rng.expovariate(self.service_rate))
        remaining = service_time

        self._log("service_start", passenger_id=passenger.id, info=f"service_time_sampled={service_time:.3f}")

        proc = self.env.active_process
        if proc is not None:
            self.reliability.register_service(proc)

        try:
            while remaining > 0:
                # if gate is down, wait
                if not self.reliability.is_operational():
                    yield from self._wait_until_operational()

                # attempt to process remaining time; failure interrupts
                start = self.env.now
                try:
                    yield self.env.timeout(remaining)
                    remaining = 0.0
                except simpy.Interrupt:
                    # gate failure: reduce remaining by time already spent
                    remaining -= (self.env.now - start)
                    remaining = max(0.0, remaining)
                    self._log("service_interrupted", passenger_id=passenger.id, info=f"remaining={remaining:.3f}")
        finally:
            if proc is not None:
                self.reliability.unregister_service(proc)

        passenger.service_end = self.env.now
        self.completed.append(passenger)
        self._log(
            "service_end",
            passenger_id=passenger.id,
            info=f"duration={(passenger.service_end - passenger.service_start):.3f}",
        )

        self.service_free = True
        if self.queue:
            self.env.process(self._start_service())

    def average_queue_length(self, until: float) -> float:
        # time-weighted average (integral of queue length / total time)
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
        verbose: bool = True,
        snapshot_step: float = 1.0,
        stdout_step: float = 1.0,  # stdout snapshot interval
    ) -> None:
        self.env = env
        self.arrival_interval = arrival_interval
        self.landing_duration = landing_duration
        self.checkin_duration = checkin_duration
        self.unloading_duration = unloading_duration
        self.passenger_ranges = passenger_ranges
        self.rng = rng or random.Random()

        self.verbose = verbose
        self.stdout_step = stdout_step

        # --- NEW: global stats ---
        self.total_planes_arrived: int = 0
        self.total_passengers_spawned: int = 0

        ensure_results_dir()  # create output base

        self.events_csv = result_path("events", "csv")
        self.snap_csv = result_path("snapshots", "csv")

        self.logger = EventLogger(self.events_csv, enabled=verbose)
        self.logger.open()

        self.snap_logger = EventLogger(self.snap_csv, enabled=verbose)
        self.snap_logger.open()

        self.logger.log(self.env.now, "sim_start", info=f"cwd={os.getcwd()}, utils={getattr(utils, '__file__', '')}")

        scanner = ReliabilityElement("scanner", *scanner_params)
        door = ReliabilityElement("door", *door_params)
        self.reliability = GateReliability(env, scanner, door, self.rng, logger=self.logger)
        self.service_gate = ServiceGate(env, self.reliability, self.rng, service_rate, logger=self.logger)

        self.queue_air: list[Plane] = []
        self.queue_pad: list[Plane] = []
        self.current_landing: Optional[Plane] = None
        self.runway_busy_until = -1.0
        self.arrival_time = 0.0
        self._next_plane_id = 0
        self._next_passenger_id = 0

        self._schedule_next_arrival(0.0)
        self.env.process(self._arrival_generator())

        if verbose and snapshot_step > 0:
            self.env.process(self._snapshot_proc(step=snapshot_step))

        if verbose and self.stdout_step > 0:
            self.env.process(self._stdout_snapshot_proc(step=self.stdout_step))

    # ------------ stdout snapshots ------------
    def _stdout_snapshot_proc(self, step: float = 1.0):
        while True:
            yield self.env.timeout(step)

            gate = 1 if self.reliability.is_operational() else 0
            scanner = 1 if self.reliability.scanner.working else 0
            door = 1 if self.reliability.door.working else 0

            air_q = len(self.queue_air) + (1 if self.current_landing else 0)
            pad_q = len(self.queue_pad)
            pax_q = len(self.service_gate.queue)
            served = len(self.service_gate.completed)

            landing_info = ""
            if self.current_landing is not None:
                landing_info = f" landing=Plane#{self.current_landing.id}(cat={self.current_landing.category})"

            print(
                f"[t={self.env.now:6.1f}] "
                f"Gate={gate} (scanner={scanner}, door={door}) | "
                f"Planes: air={air_q}, pad={pad_q}{landing_info} | "
                f"PaxQueue={pax_q} | Served={served}"
            )

    # ------------ snapshots to CSV ------------
    def _snapshot_proc(self, step: float = 1.0):
        while True:
            yield self.env.timeout(step)
            self.snap_logger.log(
                self.env.now,
                "snapshot",
                queue_len=len(self.service_gate.queue),
                scanner=1 if self.reliability.scanner.working else 0,
                door=1 if self.reliability.door.working else 0,
                gate=1 if self.reliability.is_operational() else 0,
                info=f"air={len(self.queue_air)} pad={len(self.queue_pad)}",
            )

    def _schedule_next_arrival(self, now: float) -> None:
        raw = self.rng.expovariate(1.0 / max(0.0001, self.arrival_interval))
        delta = max(1, math.ceil(raw))  # integer-ish arrivals (discrete seconds style)
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

    def _arrival(self) -> None:
        self._next_plane_id += 1
        kat = self._losuj_kategorie()
        plane = Plane(id=self._next_plane_id, category=kat, arrival_time=self.env.now)

        self.total_planes_arrived += 1
        self.queue_air.append(plane)

        self.logger.log(
            self.env.now,
            "plane_arrive",
            plane_id=plane.id,
            plane_cat=plane.category,
            queue_len=len(self.service_gate.queue),
            scanner=1 if self.reliability.scanner.working else 0,
            door=1 if self.reliability.door.working else 0,
            gate=1 if self.reliability.is_operational() else 0,
            info=f"air_q={len(self.queue_air)}",
        )

        if self.current_landing is None and not self.queue_pad:
            self._start_landing()

        self._schedule_next_arrival(self.env.now)

    def _start_landing(self) -> None:
        if not self.queue_air or self.queue_pad:
            return
        plane = self.queue_air.pop(0)
        plane.landing_start = self.env.now
        landing_time = self._losuj_czas_ladowania(plane.category)
        self.current_landing = plane
        self.runway_busy_until = self.env.now + landing_time

        self.logger.log(
            self.env.now,
            "landing_start",
            plane_id=plane.id,
            plane_cat=plane.category,
            queue_len=len(self.service_gate.queue),
            scanner=1 if self.reliability.scanner.working else 0,
            door=1 if self.reliability.door.working else 0,
            gate=1 if self.reliability.is_operational() else 0,
            info=f"landing_time={landing_time}",
        )

        self.env.process(self._landing_complete_proc(plane, landing_time))

    def _landing_complete_proc(self, plane: Plane, delay: float):
        yield self.env.timeout(delay)
        self._landing_complete(plane)

    def _landing_complete(self, plane: Plane) -> None:
        plane.landing_end = self.env.now
        self.queue_pad.append(plane)
        self.current_landing = None
        self.runway_busy_until = -1

        self.logger.log(
            self.env.now,
            "landing_end",
            plane_id=plane.id,
            plane_cat=plane.category,
            queue_len=len(self.service_gate.queue),
            scanner=1 if self.reliability.scanner.working else 0,
            door=1 if self.reliability.door.working else 0,
            gate=1 if self.reliability.is_operational() else 0,
            info=f"pad_q={len(self.queue_pad)}",
        )

        self.env.process(self._post_landing_proc(plane))

    def _post_landing_proc(self, plane: Plane):
        # check-in + unloading procedure
        yield self.env.timeout(self.checkin_duration)
        yield self.env.timeout(self.unloading_duration)

        plane.unload_end = self.env.now
        plane.departure_time = self.env.now

        self.logger.log(
            self.env.now,
            "unload_end",
            plane_id=plane.id,
            plane_cat=plane.category,
            queue_len=len(self.service_gate.queue),
            scanner=1 if self.reliability.scanner.working else 0,
            door=1 if self.reliability.door.working else 0,
            gate=1 if self.reliability.is_operational() else 0,
            info="",
        )

        # plane leaves pad, passengers go to gate queue
        self.queue_pad.remove(plane)
        self._spawn_passengers(plane)

        if self.queue_air and self.current_landing is None and not self.queue_pad:
            self._start_landing()

    def _spawn_passengers(self, plane: Plane) -> None:
        a, b = self.passenger_ranges.get(plane.category, (10, 20))
        count = self.rng.randint(a, b)
        self.total_passengers_spawned += count

        self.logger.log(
            self.env.now,
            "passengers_spawned",
            plane_id=plane.id,
            plane_cat=plane.category,
            queue_len=len(self.service_gate.queue),
            scanner=1 if self.reliability.scanner.working else 0,
            door=1 if self.reliability.door.working else 0,
            gate=1 if self.reliability.is_operational() else 0,
            info=f"count={count}",
        )

        for _ in range(count):
            self._next_passenger_id += 1
            passenger = Passenger(id=self._next_passenger_id, arrival_time=self.env.now)
            self.service_gate.add_passenger(passenger)

    def summarize(self, until: float) -> None:
        # close any open downtime interval
        self.reliability.finalize_availability(until)

        # average service duration
        durations = [
            p.service_end - p.service_start
            for p in self.service_gate.completed
            if p.service_start is not None and p.service_end is not None
        ]
        avg_service = (sum(durations) / len(durations)) if durations else 0.0

        # queue stats
        avg_queue = self.service_gate.average_queue_length(until)
        max_queue = self.service_gate.max_queue_len

        # served
        served = len(self.service_gate.completed)

        # reliability stats
        gate_down = self.reliability.gate_down_time_total
        availability = 1.0 - (gate_down / max(until, 1e-9))
        availability = min(max(availability, 0.0), 1.0)

        def _safe_avg(xs: list[float]) -> float:
            return (sum(xs) / len(xs)) if xs else 0.0

        # element-level averages
        sc_fail = self.reliability.failure_count["scanner"]
        dr_fail = self.reliability.failure_count["door"]
        sc_down_avg = _safe_avg(self.reliability.element_downtimes["scanner"])
        dr_down_avg = _safe_avg(self.reliability.element_downtimes["door"])
        sc_rep_avg = _safe_avg(self.reliability.repair_samples["scanner"])
        dr_rep_avg = _safe_avg(self.reliability.repair_samples["door"])

        print("\n--- Podsumowanie (Lab 7) ---")
        print(f"Ile samolotów przyleciało: {self.total_planes_arrived}")
        print(f"Ile pasażerów wysiadło: {self.total_passengers_spawned}")
        print(f"Ile pasażerów obsłużono: {served}")
        print(f"Średni czas obsługi (z awariami): {avg_service:.2f}")
        print(f"Średnia długość kolejki: {avg_queue:.2f}")
        print(f"Maksymalna długość kolejki: {max_queue}")

        print("\n--- Niezawodność (szczegóły) ---")
        print(f"Dostępność bramki (availability): {availability * 100:.2f}%")
        print(f"Łączny czas niedostępności bramki: {gate_down:.2f}")

        print("Skaner:")
        print(f"  liczba awarii: {sc_fail}")
        print(f"  średni czas pojedynczej awarii (downtime): {sc_down_avg:.2f}")
        print(f"  średni wylosowany czas naprawy (Normal, ucięty do 0): {sc_rep_avg:.2f}")

        print("Drzwi:")
        print(f"  liczba awarii: {dr_fail}")
        print(f"  średni czas pojedynczej awarii (downtime): {dr_down_avg:.2f}")
        print(f"  średni wylosowany czas naprawy (Normal, ucięty do 0): {dr_rep_avg:.2f}")

        # --- separate state plots: gate / scanner / door ---
        def plot_state(times, values, title, base_name):
            fig = plt.figure(figsize=(10, 4))
            plt.step(times, values, where="post")
            plt.ylim(-0.05, 1.05)
            plt.yticks([0, 1], ["0 (awaria)", "1 (działa)"])
            plt.grid(True, alpha=0.3)
            plt.xlabel("Czas")
            plt.ylabel("Stan")
            plt.title(title)
            plt.tight_layout()
            out = result_path(base_name, "png")
            _safe_savefig(fig, out)
            plt.close(fig)

        plot_state(self.reliability.state_times, self.reliability.gate_states, "Stan bramki", "stan_bramki")
        plot_state(self.reliability.state_times, self.reliability.scanner_states, "Stan skanera", "stan_skanera")
        plot_state(self.reliability.state_times, self.reliability.door_states, "Stan drzwi", "stan_drzwi")

        # queue plot
        fig_q = plt.figure(figsize=(10, 5))
        plt.step(self.service_gate.queue_times, self.service_gate.queue_lengths, where="post", label="kolejka")
        plt.xlabel("Czas")
        plt.ylabel("Długość kolejki")
        plt.legend()
        plt.tight_layout()
        qfile = result_path("kolejka_pasazerow", "png")
        _safe_savefig(fig_q, qfile)
        plt.close(fig_q)

        # final event + close logs
        self.logger.log(
            self.env.now,
            "sim_end",
            queue_len=len(self.service_gate.queue),
            scanner=1 if self.reliability.scanner.working else 0,
            door=1 if self.reliability.door.working else 0,
            gate=1 if self.reliability.is_operational() else 0,
            info=(
                f"planes={self.total_planes_arrived}, pax_spawned={self.total_passengers_spawned}, "
                f"served={served}, avg_service={avg_service:.3f}, avg_queue={avg_queue:.3f}, "
                f"max_queue={max_queue}, availability={availability:.4f}, gate_down={gate_down:.3f}, "
                f"scanner_fail={sc_fail}, door_fail={dr_fail}"
            ),
        )
        self.logger.close()
        self.snap_logger.close()


def run_simulation(sim_time: int = 500, seed: int = 0, stable_demo: bool = False) -> AirportLab7:
    rng = random.Random(seed)
    env = simpy.Environment()

    if not stable_demo:
        # overloaded
        arrival_interval = 6.0
        passenger_ranges = {1: (40, 60), 2: (60, 80), 3: (80, 120)}
        service_rate = 2.0
    else:
        # stable
        arrival_interval = 10.0
        passenger_ranges = {1: (20, 30), 2: (30, 45), 3: (45, 60)}
        service_rate = 8.0

    airport = AirportLab7(
        env=env,
        arrival_interval=arrival_interval,
        landing_duration=3.0,
        checkin_duration=4.0,
        unloading_duration=3.0,
        passenger_ranges=passenger_ranges,
        service_rate=service_rate,
        scanner_params=(80.0, 6.0, 1.0),   # MTBF, repair_mean, repair_std
        door_params=(100.0, 8.0, 1.5),     # MTBF, repair_mean, repair_std
        rng=rng,
        verbose=True,
        snapshot_step=1.0,  
        stdout_step=1.0,    
    )

    env.run(until=sim_time)
    airport.summarize(sim_time)
    return airport


if __name__ == "__main__":
    run_simulation(sim_time=500, seed=6900, stable_demo=True)
