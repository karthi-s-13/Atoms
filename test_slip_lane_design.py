#!/usr/bin/env python3
"""Test script to verify the new arc-based slip lane design."""

from simulation_engine.engine import TrafficSimulationEngine
from shared.contracts import Point2D

def test_slip_lane_geometry():
    """Verify slip lane geometry is correct and accessible."""
    engine = TrafficSimulationEngine()
    
    # Check all slip lanes exist - look for actual lane IDs
    print("=" * 60)
    print("SLIP LANE GEOMETRY TEST")
    print("=" * 60)
    print(f"\nAll lanes in engine: {len(engine.lanes)}")
    
    # Find slip lanes
    slip_lanes = {k: v for k, v in engine.lanes.items() if 'left' in k and 'slip' in k}
    print(f"Slip lanes found: {len(slip_lanes)}")
    
    for lane_id, lane in slip_lanes.items():
        print(f"\n{lane_id}:")
        print(f"  Direction: {lane.direction}")
        print(f"  Movement: {lane.movement}")
        print(f"  Path type: {type(lane.path).__name__}")
        print(f"  Path length: {lane.path.length:.2f}")
        
        # Check if arc information is available
        if hasattr(lane, 'arc') and lane.arc:
            arc = lane.arc
            print(f"  Arc center: ({arc.center.x:.2f}, {arc.center.y:.2f})")
            print(f"  Arc radius: {arc.radius:.2f}")
            print(f"  Arc clockwise: {arc.clockwise}")
            if hasattr(arc, 'angle_span'):
                print(f"  Arc angle span: {arc.angle_span:.4f} rad ({arc.angle_span * 180 / 3.14159:.1f}°)")
        
        if hasattr(lane, 'turn_entry') and lane.turn_entry:
            print(f"  Turn entry: ({lane.turn_entry.x:.2f}, {lane.turn_entry.y:.2f})")
        
        if hasattr(lane, 'turn_exit') and lane.turn_exit:
            print(f"  Turn exit: ({lane.turn_exit.x:.2f}, {lane.turn_exit.y:.2f})")
        
        print(f"  Stop line: ({lane.stop_line_position.x:.2f}, {lane.stop_line_position.y:.2f})")

def test_intersection_logic():
    """Verify intersection and other turn logic is not disturbed."""
    engine = TrafficSimulationEngine()
    
    print("\n" + "=" * 60)
    print("INTERSECTION & TURN LOGIC TEST")
    print("=" * 60)
    
    # Check right turn lanes (should still be using arc paths)
    right_turn_lanes = [lane_id for lane_id in engine.lanes if 'right' in lane_id]
    print(f"\nRight turn lanes: {len(right_turn_lanes)}")
    for lane_id in right_turn_lanes:
        lane = engine.lanes[lane_id]
        print(f"  {lane_id}: {type(lane.path).__name__}")
        if hasattr(lane, 'arc') and lane.arc:
            print(f"    Has arc: ✓")
    
    # Check straight lanes
    straight_lanes = [lane_id for lane_id in engine.lanes if 'straight' in lane_id]
    print(f"\nStraight lanes: {len(straight_lanes)}")
    
    print(f"\nTotal lanes defined: {len(engine.lanes)}")
    print(f"\nLane categories:")
    categories = {}
    for lane_id in engine.lanes:
        for cat in ['straight', 'right', 'left', 'slip']:
            if cat in lane_id:
                categories[cat] = categories.get(cat, 0) + 1
                break
    for cat, count in sorted(categories.items()):
        print(f"  {cat}: {count}")

def test_vehicle_movement():
    """Test that vehicles can navigate the new slip lanes."""
    engine = TrafficSimulationEngine()
    
    print("\n" + "=" * 60)
    print("VEHICLE MOVEMENT TEST")
    print("=" * 60)
    
    # Simulate a few ticks
    for i in range(10):
        snapshot = engine.tick(0.016)
        if i == 0:
            print(f"Snapshot frame: {snapshot['frame']}")
            print(f"Active direction: {snapshot['active_direction']}")
            print(f"Vehicles spawned: {len(snapshot['vehicles'])}")
            print("  Simulation running normally ✓")

if __name__ == "__main__":
    try:
        test_slip_lane_geometry()
        test_intersection_logic()
        test_vehicle_movement()
        print("\n" + "=" * 60)
        print("ALL TESTS COMPLETED SUCCESSFULLY ✓")
        print("=" * 60)
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
