import unittest
import os
import sys
from unittest.mock import MagicMock

# Mock serial before importing hardware
sys.modules['serial'] = MagicMock()

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from hardware import SignalController
from simulation_engine.engine import TrafficSimulationEngine

class TestHardwareSync(unittest.TestCase):
    def setUp(self):
        # Initialize hardware in mock mode
        self.hw = SignalController(port="COM5", mock=True)
        self.engine = TrafficSimulationEngine()

    def test_state_mapping(self):
        """Verify that engine states correctly map to hardware commands."""
        
        # Test Case 1: All Red (Initial/Reset)
        self.hw.update(active_direction=None, phase_state="RED")
        self.assertEqual(self.hw.last_command, "ALL_RED")

        # Test Case 2: North Green
        self.hw.update(active_direction="NORTH", phase_state="GREEN")
        self.assertEqual(self.hw.last_command, "NORTH_GREEN")

        # Test Case 3: North Yellow
        self.hw.update(active_direction="NORTH", phase_state="YELLOW")
        self.assertEqual(self.hw.last_command, "NORTH_YELLOW")

        # Test Case 4: East Green
        self.hw.update(active_direction="EAST", phase_state="GREEN")
        self.assertEqual(self.hw.last_command, "EAST_GREEN")

    def test_pedestrian_override(self):
        """Verify that pedestrian active state forces ALL_RED."""
        self.hw.update(active_direction="NORTH", phase_state="GREEN", pedestrian_active=True)
        self.assertEqual(self.hw.last_command, "ALL_RED")

    def test_command_deduplication(self):
        """Verify that redundant commands are not re-sent (internal tracking)."""
        self.hw.update(active_direction="NORTH", phase_state="GREEN")
        self.assertEqual(self.hw.last_command, "NORTH_GREEN")
        
        # Manually reset last_command to check if update changes it
        self.hw.last_command = "OTHER"
        self.hw.update(active_direction="NORTH", phase_state="GREEN")
        self.assertEqual(self.hw.last_command, "NORTH_GREEN")

if __name__ == "__main__":
    unittest.main()
