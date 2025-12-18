import math
import random
from typing import List


class PrefedStreams:
    """Pre-generated sequences of interarrival deltas (ints), categories and landing times per aircraft id.

    Usage: create with generate_prefed(seed, sim_time, arrival_interval, landing_duration, max_extra=50)
    Then: call next_delta() when scheduling next arrival, and use category_for(id)/landing_for(id).
    """

    def __init__(self, deltas: List[int], categories: List[int], landings: List[int]):
        self.deltas = deltas
        self.categories = categories
        self.landings = landings
        self._delta_idx = 0

    def next_delta(self) -> int:
        # kept for compatibility but does not advance global cursor for shared use
        return self.deltas[0] if self.deltas else 1

    def category_for(self, sam_id: int) -> int:
        idx = sam_id - 1
        if idx < 0 or idx >= len(self.categories):
            return self.categories[-1]
        return self.categories[idx]

    def landing_for(self, sam_id: int) -> int:
        idx = sam_id - 1
        if idx < 0 or idx >= len(self.landings):
            return self.landings[-1]
        return self.landings[idx]


def generate_prefed(seed: int, sim_time: int, arrival_interval: float, landing_duration: float, max_extra: int = 50) -> PrefedStreams:
    rng = random.Random(seed)
    deltas: List[int] = []
    categories: List[int] = []
    landings: List[int] = []

    # generate interarrival deltas until cumulative time exceeds sim_time + max_extra
    t = 0
    while t <= sim_time + max_extra:
        raw = rng.expovariate(1.0 / max(0.0001, arrival_interval))
        delta = max(1, math.ceil(raw))
        deltas.append(delta)
        t += delta

    # generate categories and landing durations for each potential arrival
    for _ in range(len(deltas)):
        kat = rng.choice([1, 2, 3])
        categories.append(kat)
        if kat == 1:
            land = max(1, int(landing_duration))
        elif kat == 2:
            land = rng.randint(2, 5)
        else:
            val = rng.gauss(landing_duration, 1.5)
            land = max(1, math.ceil(val))
        landings.append(land)

    return PrefedStreams(deltas, categories, landings)
