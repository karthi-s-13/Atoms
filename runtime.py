"""Simulation runtime wrapper that integrates the traffic engine with hardware signaling."""

from hardware import SignalController
from simulation_engine.network import TrafficNetwork

class SimulationRuntime:
    """ AUTHORITATIVE RUNTIME: Wraps the simulation engine and mirrors state to physical hardware. """
    
    def __init__(self, port="COM7"):
        self.engine = TrafficNetwork()
        self.hw = SignalController(port=port)
    
    def frame_update(self):
        """
        Executes one simulation step and mirrors the resulting state to physical LEDs via Serial.
        """
        # Advance the simulation
        snapshot = self.engine.tick()
        
        # Mirror the simulation state to the Arduino Hardware
        # active_direction: e.g. "NORTH", "SOUTH"
        # phase_state: e.g. "GREEN", "YELLOW", "RED"
        # pedestrian_active: True if pedestrian phase is on
        self.hw.update(
            active_direction=snapshot.get("active_direction"),
            phase_state=self.engine.engine.phase_state, # Accessing the property on the inner engine
            pedestrian_active=snapshot.get("pedestrian_phase_active", False)
        )
        
        return snapshot

    def reset(self):
        self.engine.reset()
        # Ensure hardware resets to ALL_RED on sim reset
        self.hw.update(active_direction=None, phase_state="RED", pedestrian_active=False)

    def close(self):
        self.hw.close()
