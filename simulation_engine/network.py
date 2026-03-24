"""Compatibility wrapper that delegates to the simplified single intersection engine."""

from __future__ import annotations

from typing import Dict

from simulation_engine.engine import FRAME_DT, TrafficSimulationEngine


class TrafficNetwork:
    """Preserve the old runtime interface while serving one simplified intersection."""

    def __init__(self) -> None:
        self.engine = TrafficSimulationEngine()

    @property
    def time(self) -> float:
        return self.engine.time

    @property
    def config(self):
        return self.engine.config

    def update_config(self, values: Dict[str, object]):
        return self.engine.update_config(values)

    def reset(self, config: Dict[str, object] | None = None) -> None:
        self.engine.reset(config)

    def tick(self, dt: float = FRAME_DT) -> Dict[str, object]:
        return self.engine.tick(dt)

    def snapshot(self):
        return self.engine.snapshot()

    def get_state(self) -> Dict[str, object]:
        return self.engine.get_state()
