from __future__ import annotations

import math
import unittest
from pathlib import Path

from realtime_server.traffic_platform import MapStreamHub, TrafficPlatformService


PROJECT_ROOT = Path(__file__).resolve().parent.parent
JUNCTION_REGISTRY_PATH = PROJECT_ROOT / "realtime_server" / "junction_registry.json"


class FakeWebSocket:
    def __init__(self) -> None:
        self.accepted = False
        self.messages: list[dict[str, object]] = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, payload: dict[str, object]) -> None:
        self.messages.append(payload)


class StaticSnapshotPlatform:
    def __init__(self, snapshots: list[dict[str, object]]) -> None:
        self.snapshots = snapshots
        self.calls = 0

    def build_snapshot(self, emergency_override=None) -> dict[str, object]:
        index = min(self.calls, len(self.snapshots) - 1)
        self.calls += 1
        return self.snapshots[index]


class TrafficPlatformStabilityTests(unittest.TestCase):
    def test_demo_presets_expose_four_junction_corridors(self) -> None:
        service = TrafficPlatformService(JUNCTION_REGISTRY_PATH)

        config = service.get_demo_config()
        starting_points = config["starting_points"]  # type: ignore[index]

        self.assertEqual(len(starting_points), 4)
        for start_point in starting_points:
            route_nodes = start_point["emergency_route_nodes"]
            self.assertEqual(len(route_nodes), 4)
            self.assertEqual(route_nodes[0], start_point["activation_junction_id"])
            self.assertEqual(len(start_point["pre_detection_junctions"]), 2)

    def test_start_emergency_demo_uses_selected_preset_route(self) -> None:
        service = TrafficPlatformService(JUNCTION_REGISTRY_PATH)

        emergency_state = service.start_emergency_demo("S3")

        self.assertEqual(emergency_state["activation_junction_id"], "J3")
        self.assertEqual(emergency_state["planned_route_nodes"], ["J3", "J2", "J4", "J5"])
        self.assertEqual(emergency_state["pre_detection_junctions"], ["J3", "J2"])
        self.assertEqual(emergency_state["hospital"]["id"], "H2")

    def test_unhealthy_camera_fallback_keeps_metrics_finite(self) -> None:
        service = TrafficPlatformService(JUNCTION_REGISTRY_PATH)
        for health in service.camera_health.values():
            health["last_seen_at"] = 0.0

        snapshot: dict[str, object] | None = None
        for _ in range(25):
            snapshot = service.build_snapshot()

        self.assertIsNotNone(snapshot)
        junctions = snapshot["junctions"]  # type: ignore[index]
        coordination = snapshot["coordination"]["coordination"]  # type: ignore[index]

        for junction in junctions:
            for metric in (
                "vehicle_count",
                "queue_length",
                "flow_count",
                "average_speed_kmph",
                "predicted_load",
                "coordination_priority",
            ):
                self.assertTrue(math.isfinite(float(junction[metric])), msg=f"{junction['junction_id']} {metric} should stay finite")
            self.assertLessEqual(float(junction["vehicle_count"]), 180.0)
            self.assertLessEqual(float(junction["queue_length"]), 120.0)
            self.assertLessEqual(float(junction["flow_count"]), 80.0)
            self.assertLessEqual(float(junction["average_speed_kmph"]), 90.0)
            self.assertLessEqual(float(junction["predicted_load"]), 180.0)

        for junction_id, control in coordination.items():
            self.assertTrue(math.isfinite(float(control["priority_score"])), msg=f"{junction_id} priority score should stay finite")


class MapStreamHubTests(unittest.IsolatedAsyncioTestCase):
    async def test_connect_does_not_reset_existing_delta_baseline(self) -> None:
        previous_snapshot = {
            "junctions": [{"junction_id": "J1", "vehicle_count": 8}],
            "coordination": {"updated_at": 1},
            "global_status": {"system_health": "stable"},
        }
        current_snapshot = {
            "junctions": [{"junction_id": "J1", "vehicle_count": 9}],
            "coordination": {"updated_at": 2},
            "global_status": {"system_health": "stable"},
        }
        platform = StaticSnapshotPlatform([current_snapshot])
        hub = MapStreamHub(platform, lambda: {})
        hub.last_snapshot = previous_snapshot
        websocket = FakeWebSocket()

        await hub.connect(websocket)

        self.assertTrue(websocket.accepted)
        self.assertEqual(hub.last_snapshot, previous_snapshot)
        self.assertEqual(len(websocket.messages), 1)
        self.assertEqual(websocket.messages[0]["type"], "snapshot")
        self.assertEqual(websocket.messages[0]["snapshot"], current_snapshot)


if __name__ == "__main__":
    unittest.main()
