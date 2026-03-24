#!/usr/bin/env python3
"""Test merge conflict detection in slip lanes."""

from simulation_engine.engine import TrafficSimulationEngine

def test_merge_conflict():
    print("Testing merge conflict detection...")
    try:
        engine = TrafficSimulationEngine()
        print("✓ Engine initialized successfully")
        
        # Get snapshot to verify slip lanes exist
        snapshot = engine.snapshot()
        slip_lanes = [l for l in snapshot.lanes if "slip" in l.id]
        print(f"✓ Found {len(slip_lanes)} slip lanes")
        
        # List them
        for lane in slip_lanes:
            print(f"  - {lane.id} ({lane.movement})")
        
        # Run a few simulation ticks
        for i in range(10):
            engine.tick(0.016)
        print(f"✓ Ran 10 simulation ticks successfully")
        
        # Check final state
        final_snapshot = engine.snapshot()
        print(f"✓ Vehicles active: {len(final_snapshot.vehicles)}")
        
        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_merge_conflict()
    exit(0 if success else 1)
