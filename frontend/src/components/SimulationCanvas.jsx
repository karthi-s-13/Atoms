import { Billboard, Line, OrbitControls, Text } from "@react-three/drei";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import {
  directionAxis,
  isVerticalDirection,
  simulationToWorldVector,
  worldPointForDirection,
  worldYawFromSimulationHeading,
  worldYawFromSimulationVector,
} from "../lib/directions";

const LANE_WIDTH = 3.5;
const LANES_PER_DIRECTION = 2;
const SHOULDER = 0.75;
const ROAD_EXTENT = 72;
const INNER_LANE_OFFSET = LANE_WIDTH / 2;
const OUTER_LANE_OFFSET = INNER_LANE_OFFSET + LANE_WIDTH;
const ROAD_HALF_WIDTH = LANE_WIDTH * LANES_PER_DIRECTION;
const ROAD_SURFACE_HALF_WIDTH = ROAD_HALF_WIDTH + SHOULDER;
const ROAD_SURFACE_WIDTH = ROAD_SURFACE_HALF_WIDTH * 2;
const ROAD_SURFACE_LENGTH = (ROAD_EXTENT * 2) + 12;
const ROAD_SURFACE_HALF_LENGTH = ROAD_SURFACE_LENGTH / 2;
const INTERSECTION_SIZE = 14;
const INTERSECTION_HALF_SIZE = INTERSECTION_SIZE / 2;
const GROUND_SURFACE_Y = -0.08;
const ROAD_SURFACE_Y = 0;
const INTERSECTION_SURFACE_Y = ROAD_SURFACE_Y + 0.01;
const INTERSECTION_OUTLINE_Y = INTERSECTION_SURFACE_Y + 0.014;
const MARKING_SURFACE_Y = 0.034;
const STOP_LINE_SURFACE_Y = MARKING_SURFACE_Y + 0.001;
const STOP_LINE_THICKNESS = 0.34;
const DASH_LENGTH = 3.2;
const DASH_GAP = 2.2;
const ROAD_LABEL_DISTANCE = ROAD_EXTENT - 12;
const ROAD_LABEL_HEIGHT = 2.4;
const ROAD_LABEL_PLATE_SIZE = [16, 4.4];
const SIGNAL_SIDE_OFFSET = ROAD_SURFACE_HALF_WIDTH + 3.4;
const SIGNAL_SETBACK = 2.4;
const INTERPOLATION_DELAY_MS = 18;
const VEHICLE_POSITION_DAMPING = 22;
const VEHICLE_ROTATION_DAMPING = 18;

function shortestAngleLerp(start, end, alpha) {
  let delta = end - start;
  while (delta > Math.PI) delta -= Math.PI * 2;
  while (delta < -Math.PI) delta += Math.PI * 2;
  return start + (delta * alpha);
}

function resolveBufferedFrames(frames, targetTime) {
  if (!frames.length) {
    return { previous: null, next: null, alpha: 0 };
  }
  if (frames.length === 1 || targetTime <= frames[0].receivedAt) {
    return { previous: frames[0], next: frames[0], alpha: 0 };
  }

  for (let index = 0; index < frames.length - 1; index += 1) {
    const previous = frames[index];
    const next = frames[index + 1];
    if (previous.receivedAt <= targetTime && targetTime <= next.receivedAt) {
      const duration = Math.max(1, next.receivedAt - previous.receivedAt);
      return { previous, next, alpha: (targetTime - previous.receivedAt) / duration };
    }
  }

  return {
    previous: frames[frames.length - 2] ?? frames[frames.length - 1],
    next: frames[frames.length - 1],
    alpha: 1,
  };
}

function sampleResolvedActor(resolvedFrames, actorId) {
  if (!resolvedFrames?.previous || !resolvedFrames?.next) {
    return null;
  }

  const prevMap = resolvedFrames.previous.vehicleMap;
  const nextMap = resolvedFrames.next.vehicleMap;
  const prevActor = prevMap.get(actorId);
  const nextActor = nextMap.get(actorId);

  if (prevActor && nextActor) {
    return {
      ...nextActor,
      x: THREE.MathUtils.lerp(prevActor.x, nextActor.x, resolvedFrames.alpha),
      y: THREE.MathUtils.lerp(prevActor.y, nextActor.y, resolvedFrames.alpha),
      heading: shortestAngleLerp(prevActor.heading, nextActor.heading, resolvedFrames.alpha),
    };
  }

  if (nextActor) {
    return nextActor;
  }

  if (prevActor) {
    return {
      ...prevActor,
      x: prevActor.x,
      y: prevActor.y,
      heading: prevActor.heading ?? 0,
    };
  }

  return null;
}

function FrameInterpolationCoordinator({ sceneBufferRef, resolvedFramesRef }) {
  useFrame(() => {
    resolvedFramesRef.current = resolveBufferedFrames(
      sceneBufferRef.current.frames,
      performance.now() - INTERPOLATION_DELAY_MS,
    );
  });
  return null;
}

function laneDirection(lane) {
  return lane.direction ?? lane.approach;
}

function laneHeading(lane) {
  const start = lane.path?.[0] ?? lane.start;
  const next = lane.path?.[1] ?? lane.end;
  return worldYawFromSimulationVector(next.x - start.x, next.y - start.y);
}

function laneLeftNormal(lane) {
  const start = lane.path?.[0] ?? lane.start;
  const next = lane.path?.[1] ?? lane.end;
  const forward = simulationToWorldVector({ x: next.x - start.x, y: next.y - start.y });
  return { x: -forward.z, z: forward.x };
}

function laneForward(lane) {
  const start = lane.path?.[0] ?? lane.start;
  const next = lane.path?.[1] ?? lane.end;
  return simulationToWorldVector({ x: next.x - start.x, y: next.y - start.y });
}

function lightDescriptor(state, lamp) {
  const palette = { RED: "#ef4444", YELLOW: "#facc15", GREEN: "#22c55e" };
  const active = state === lamp;
  return {
    color: active ? palette[lamp] : "#162033",
    emissive: active ? palette[lamp] : "#020617",
    intensity: active ? 2.8 : 0.08,
  };
}

function signalStateForApproach(signals, approach) {
  return signals?.[approach] ?? "RED";
}

function buildDashCenters(rangeStart, rangeEnd) {
  const centers = [];
  for (
    let center = rangeStart + (DASH_LENGTH / 2);
    center <= (rangeEnd - (DASH_LENGTH / 2)) + 1e-6;
    center += DASH_LENGTH + DASH_GAP
  ) {
    centers.push(center);
  }
  return centers;
}

function stopLaneKey(lane) {
  return `${laneDirection(lane)}:${lane.stop_line_position.x.toFixed(2)}:${lane.stop_line_position.y.toFixed(2)}`;
}

function uniquePhysicalLanes(lanes) {
  const seen = new Set();
  return lanes.filter((lane) => {
    const key = stopLaneKey(lane);
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function buildApproachMarkingDescriptor(lanes) {
  const physicalLanes = uniquePhysicalLanes(lanes);
  const representativeLane = physicalLanes.find((lane) => lane.movement === "STRAIGHT") ?? physicalLanes[0];
  const direction = laneDirection(representativeLane);
  const leftNormal = laneLeftNormal(representativeLane);
  const forward = laneForward(representativeLane);
  const stopPoint = physicalLanes.reduce(
    (accumulator, lane) => ({
      x: accumulator.x + lane.stop_line_position.x,
      y: accumulator.y + lane.stop_line_position.y,
    }),
    { x: 0, y: 0 },
  );
  stopPoint.x /= physicalLanes.length;
  stopPoint.y /= physicalLanes.length;
  const vertical = isVerticalDirection(direction);

  return {
    direction,
    facing: laneHeading(representativeLane) + Math.PI,
    forward,
    leftNormal,
    roadsideNormal: vertical
      ? { x: Math.sign(stopPoint.x || leftNormal.x || 1), z: 0 }
      : { x: 0, z: Math.sign(-stopPoint.y || leftNormal.z || 1) },
    physicalLanes,
    stopPoint,
    laneSpan: physicalLanes.length * LANE_WIDTH,
    vertical,
  };
}

function buildRoadLabelDescriptors(lanes, directionAxes) {
  const lanesByDirection = lanes.reduce((groups, lane) => {
    const direction = laneDirection(lane);
    if (!direction) {
      return groups;
    }
    groups[direction] = groups[direction] ?? [];
    groups[direction].push(lane);
    return groups;
  }, {});

  return Object.keys(lanesByDirection)
    .map((direction) => {
      const axis = directionAxis(direction, directionAxes);
      if (!axis) {
        return null;
      }
      return {
        direction,
        axis,
        position: worldPointForDirection(direction, ROAD_LABEL_DISTANCE, ROAD_LABEL_HEIGHT, directionAxes),
      };
    })
    .filter(Boolean);
}

function dividerSegments() {
  const sideLength = ROAD_SURFACE_HALF_LENGTH - INTERSECTION_HALF_SIZE;
  const sideCenter = (ROAD_SURFACE_HALF_LENGTH + INTERSECTION_HALF_SIZE) / 2;
  const dashCenters = buildDashCenters(INTERSECTION_HALF_SIZE, ROAD_SURFACE_HALF_LENGTH);
  const segments = [
    { id: "yellow-v-top-a", position: [-0.22, 0.032, sideCenter], size: [0.14, sideLength], color: "#facc15" },
    { id: "yellow-v-top-b", position: [0.22, 0.032, sideCenter], size: [0.14, sideLength], color: "#facc15" },
    { id: "yellow-v-bottom-a", position: [-0.22, 0.032, -sideCenter], size: [0.14, sideLength], color: "#facc15" },
    { id: "yellow-v-bottom-b", position: [0.22, 0.032, -sideCenter], size: [0.14, sideLength], color: "#facc15" },
    { id: "yellow-h-right-a", position: [sideCenter, 0.032, -0.22], size: [sideLength, 0.14], color: "#facc15" },
    { id: "yellow-h-right-b", position: [sideCenter, 0.032, 0.22], size: [sideLength, 0.14], color: "#facc15" },
    { id: "yellow-h-left-a", position: [-sideCenter, 0.032, -0.22], size: [sideLength, 0.14], color: "#facc15" },
    { id: "yellow-h-left-b", position: [-sideCenter, 0.032, 0.22], size: [sideLength, 0.14], color: "#facc15" },
  ];

  dashCenters.forEach((center, index) => {
    segments.push(
      { id: `dash-v-west-${index}`, position: [-LANE_WIDTH, 0.031, center], size: [0.12, DASH_LENGTH], color: "#e2e8f0" },
      { id: `dash-v-east-${index}`, position: [LANE_WIDTH, 0.031, center], size: [0.12, DASH_LENGTH], color: "#e2e8f0" },
      { id: `dash-v-west-b-${index}`, position: [-LANE_WIDTH, 0.031, -center], size: [0.12, DASH_LENGTH], color: "#e2e8f0" },
      { id: `dash-v-east-b-${index}`, position: [LANE_WIDTH, 0.031, -center], size: [0.12, DASH_LENGTH], color: "#e2e8f0" },
      { id: `dash-h-north-${index}`, position: [center, 0.031, LANE_WIDTH], size: [DASH_LENGTH, 0.12], color: "#e2e8f0" },
      { id: `dash-h-south-${index}`, position: [center, 0.031, -LANE_WIDTH], size: [DASH_LENGTH, 0.12], color: "#e2e8f0" },
      { id: `dash-h-north-b-${index}`, position: [-center, 0.031, LANE_WIDTH], size: [DASH_LENGTH, 0.12], color: "#e2e8f0" },
      { id: `dash-h-south-b-${index}`, position: [-center, 0.031, -LANE_WIDTH], size: [DASH_LENGTH, 0.12], color: "#e2e8f0" },
    );
  });

  return segments;
}

function roadSurfaceSegments() {
  const armLength = ROAD_SURFACE_HALF_LENGTH - INTERSECTION_HALF_SIZE;
  const armCenter = (ROAD_SURFACE_HALF_LENGTH + INTERSECTION_HALF_SIZE) / 2;
  return [
    { id: "road-north", position: [0, ROAD_SURFACE_Y, armCenter], size: [ROAD_SURFACE_WIDTH, armLength] },
    { id: "road-south", position: [0, ROAD_SURFACE_Y, -armCenter], size: [ROAD_SURFACE_WIDTH, armLength] },
    { id: "road-east", position: [armCenter, ROAD_SURFACE_Y, 0], size: [armLength, ROAD_SURFACE_WIDTH] },
    { id: "road-west", position: [-armCenter, ROAD_SURFACE_Y, 0], size: [armLength, ROAD_SURFACE_WIDTH] },
  ];
}

function PersistentOrbitController({ cameraStateRef }) {
  const controlsRef = useRef();
  const { camera } = useThree();

  useEffect(() => {
    camera.position.fromArray(cameraStateRef.current.position);
    if (controlsRef.current) {
      controlsRef.current.target.fromArray(cameraStateRef.current.target);
      controlsRef.current.update();
    }
  }, [camera, cameraStateRef]);

  useFrame(() => {
    if (!controlsRef.current) {
      return;
    }
    cameraStateRef.current.position = camera.position.toArray();
    cameraStateRef.current.target = controlsRef.current.target.toArray();
  });

  return <OrbitControls ref={controlsRef} makeDefault enablePan enableZoom maxPolarAngle={Math.PI / 2.08} minDistance={36} maxDistance={126} />;
}

function SurfaceStripe({ segment }) {
  return (
    <mesh position={segment.position} rotation={[-Math.PI / 2, 0, 0]}>
      <planeGeometry args={segment.size} />
      <meshStandardMaterial color={segment.color} emissive={segment.color} emissiveIntensity={segment.color === "#facc15" ? 0.14 : 0.08} />
    </mesh>
  );
}

function buildSignalDescriptor(lanes, signals) {
  const descriptor = buildApproachMarkingDescriptor(lanes);

  return {
    id: descriptor.direction,
    state: signalStateForApproach(signals, descriptor.direction),
    position: [
      descriptor.stopPoint.x + (descriptor.roadsideNormal.x * SIGNAL_SIDE_OFFSET) - (descriptor.forward.x * SIGNAL_SETBACK),
      0,
      -descriptor.stopPoint.y + (descriptor.roadsideNormal.z * SIGNAL_SIDE_OFFSET) - (descriptor.forward.z * SIGNAL_SETBACK),
    ],
    facing: descriptor.facing,
  };
}

function SignalHead({ signal }) {
  const { facing, position, state } = signal;
  const redLight = lightDescriptor(state, "RED");
  const yellowLight = lightDescriptor(state, "YELLOW");
  const greenLight = lightDescriptor(state, "GREEN");

  return (
    <group position={position} rotation={[0, facing, 0]}>
      <mesh position={[0, 0.14, 0]}>
        <cylinderGeometry args={[0.34, 0.44, 0.28, 12]} />
        <meshStandardMaterial color="#64748b" roughness={0.92} />
      </mesh>
      <mesh position={[0, 3.4, 0]}>
        <cylinderGeometry args={[0.1, 0.12, 6.8, 12]} />
        <meshStandardMaterial color="#475569" roughness={0.62} />
      </mesh>
      <mesh position={[0, 6.84, 0]}>
        <sphereGeometry args={[0.11, 10, 10]} />
        <meshStandardMaterial color="#94a3b8" roughness={0.58} />
      </mesh>
      <mesh position={[0, 5.24, -0.02]}>
        <boxGeometry args={[1.24, 3.08, 0.16]} />
        <meshStandardMaterial color="#334155" roughness={0.72} />
      </mesh>
      <mesh position={[0, 5.24, 0.2]}>
        <boxGeometry args={[0.96, 2.7, 0.62]} />
        <meshStandardMaterial color="#0f172a" roughness={0.56} />
      </mesh>
      <mesh position={[0, 5.24, 0.44]}>
        <boxGeometry args={[1.04, 2.86, 0.04]} />
        <meshStandardMaterial color="#020617" roughness={0.82} transparent opacity={0.78} />
      </mesh>
      <mesh position={[0, 5.24, 0.02]}>
        <boxGeometry args={[0.12, 2.86, 0.12]} />
        <meshStandardMaterial color="#1e293b" roughness={0.64} />
      </mesh>
      <mesh position={[0, 6.1, 0.36]}>
        <boxGeometry args={[0.5, 0.3, 0.26]} />
        <meshStandardMaterial color="#020617" roughness={0.82} />
      </mesh>
      <mesh position={[0, 5.24, 0.36]}>
        <boxGeometry args={[0.5, 0.3, 0.26]} />
        <meshStandardMaterial color="#020617" roughness={0.82} />
      </mesh>
      <mesh position={[0, 4.38, 0.36]}>
        <boxGeometry args={[0.5, 0.3, 0.26]} />
        <meshStandardMaterial color="#020617" roughness={0.82} />
      </mesh>
      <mesh position={[0, 6.1, 0.48]}>
        <sphereGeometry args={[0.2, 12, 12]} />
        <meshStandardMaterial color={redLight.color} emissive={redLight.emissive} emissiveIntensity={redLight.intensity} />
      </mesh>
      <mesh position={[0, 5.24, 0.48]}>
        <sphereGeometry args={[0.2, 12, 12]} />
        <meshStandardMaterial color={yellowLight.color} emissive={yellowLight.emissive} emissiveIntensity={yellowLight.intensity} />
      </mesh>
      <mesh position={[0, 4.38, 0.48]}>
        <sphereGeometry args={[0.2, 12, 12]} />
        <meshStandardMaterial color={greenLight.color} emissive={greenLight.emissive} emissiveIntensity={greenLight.intensity} />
      </mesh>
      <mesh position={[0.38, 1.36, -0.02]}>
        <boxGeometry args={[0.34, 0.68, 0.26]} />
        <meshStandardMaterial color="#1e293b" roughness={0.72} />
      </mesh>
    </group>
  );
}

function StopLine({ lanes }) {
  const descriptor = buildApproachMarkingDescriptor(lanes);

  return (
    <mesh position={[descriptor.stopPoint.x, STOP_LINE_SURFACE_Y, -descriptor.stopPoint.y]} rotation={[-Math.PI / 2, 0, 0]}>
      <planeGeometry args={descriptor.vertical ? [descriptor.laneSpan, STOP_LINE_THICKNESS] : [STOP_LINE_THICKNESS, descriptor.laneSpan]} />
      <meshStandardMaterial color="#f8fafc" emissive="#ffffff" emissiveIntensity={0.12} />
    </mesh>
  );
}

function RoadDirectionLabel({ label }) {
  return (
    <Billboard position={label.position} follow lockX lockZ>
      <group>
        <mesh position={[0, 0, -0.04]}>
          <planeGeometry args={ROAD_LABEL_PLATE_SIZE} />
          <meshStandardMaterial color="#08131f" emissive="#0f766e" emissiveIntensity={0.18} transparent opacity={0.9} />
        </mesh>
        <Text
          anchorX="center"
          anchorY="middle"
          fontSize={1.48}
          color="#f8fafc"
          outlineWidth={0.08}
          outlineColor="#020617"
          letterSpacing={0.08}
          maxWidth={ROAD_LABEL_PLATE_SIZE[0] - 2}
        >
          {label.direction}
        </Text>
      </group>
    </Billboard>
  );
}

function RoadNetwork({ lanes, signals, directionAxes }) {
  const stripes = useMemo(() => dividerSegments(), []);
  const roadSurfaces = useMemo(() => roadSurfaceSegments(), []);
  const roadLabels = useMemo(() => buildRoadLabelDescriptors(lanes, directionAxes), [lanes, directionAxes]);
  const lanesByApproach = lanes.reduce((groups, lane) => {
    const direction = laneDirection(lane);
    groups[direction] = groups[direction] ?? [];
    groups[direction].push(lane);
    return groups;
  }, {});
  const stopLineGroups = Object.values(lanesByApproach);
  const signalDescriptors = Object.values(
    Object.entries(lanesByApproach).reduce((descriptors, [approach, groupedLanes]) => {
      descriptors[approach] = buildSignalDescriptor(groupedLanes, signals);
      return descriptors;
    }, {}),
  );
  const intersectionOutline = [
    [-INTERSECTION_HALF_SIZE, INTERSECTION_OUTLINE_Y, -INTERSECTION_HALF_SIZE],
    [-INTERSECTION_HALF_SIZE, INTERSECTION_OUTLINE_Y, INTERSECTION_HALF_SIZE],
    [INTERSECTION_HALF_SIZE, INTERSECTION_OUTLINE_Y, INTERSECTION_HALF_SIZE],
    [INTERSECTION_HALF_SIZE, INTERSECTION_OUTLINE_Y, -INTERSECTION_HALF_SIZE],
    [-INTERSECTION_HALF_SIZE, INTERSECTION_OUTLINE_Y, -INTERSECTION_HALF_SIZE],
  ];

  return (
    <group>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, GROUND_SURFACE_Y, 0]}>
        <planeGeometry args={[210, 210]} />
        <meshBasicMaterial color="#0b1725" />
      </mesh>

      {roadSurfaces.map((segment) => (
        <mesh key={segment.id} rotation={[-Math.PI / 2, 0, 0]} position={segment.position}>
          <planeGeometry args={segment.size} />
          <meshBasicMaterial color="#1f2937" />
        </mesh>
      ))}

      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, INTERSECTION_SURFACE_Y, 0]}>
        <planeGeometry args={[INTERSECTION_SIZE, INTERSECTION_SIZE]} />
        <meshBasicMaterial color="#2a3545" />
      </mesh>
      <Line points={intersectionOutline} color="#f8fafc" transparent opacity={0.35} lineWidth={1.2} />

      {stripes.map((segment) => (
        <SurfaceStripe key={segment.id} segment={segment} />
      ))}
      {stopLineGroups.map((group) => (
        <StopLine key={`stop-${laneDirection(group[0])}`} lanes={group} />
      ))}

      {signalDescriptors.map((signal) => (
        <SignalHead key={`signal-${signal.id}`} signal={signal} />
      ))}

      {roadLabels.map((label) => (
        <RoadDirectionLabel key={`road-label-${label.direction}`} label={label} />
      ))}
    </group>
  );
}

function vehicleAppearance(vehicle) {
  const width = vehicle.width ?? 2;
  const length = vehicle.length ?? 4.5;
  return {
    footprint: [width, 1.02, length],
    cabinColor: "#0f172a",
    detailColor: "#cbd5e1",
    shadowScale: [width * 0.55, length * 0.4, 1],
  };
}

function emergencyLightPalette(vehicle) {
  if (!vehicle.has_siren) {
    return [];
  }
  if (vehicle.kind === "ambulance") {
    return [
      { color: "#ef4444", phase: 0 },
      { color: "#2563eb", phase: Math.PI },
    ];
  }
  if (vehicle.kind === "firetruck") {
    return [{ color: "#fca5a5", phase: 0 }];
  }
  if (vehicle.kind === "police") {
    return [
      { color: "#60a5fa", phase: 0 },
      { color: "#dbeafe", phase: Math.PI },
    ];
  }
  return [];
}

function EmergencyLightBar({ vehicle, appearance }) {
  const lightRefs = useRef([]);
  const lights = emergencyLightPalette(vehicle);

  useFrame((renderState) => {
    if (!lights.length) {
      return;
    }
    const phaseTime = renderState.clock.getElapsedTime() * 9;
    lightRefs.current.forEach((material, index) => {
      if (!material) {
        return;
      }
      const pulse = Math.sin(phaseTime + lights[index].phase);
      material.emissiveIntensity = pulse > 0 ? 2.4 : 0.22;
      material.opacity = pulse > 0 ? 0.98 : 0.58;
    });
  });

  if (!lights.length) {
    return null;
  }

  const slotOffsets = lights.length === 1 ? [0] : [-0.18, 0.18];
  return (
    <group position={[0, appearance.footprint[1] * 0.8, 0]}>
      {lights.map((light, index) => (
        <mesh key={`${vehicle.kind}-${light.color}`} position={[slotOffsets[index] ?? 0, 0, -0.04]}>
          <boxGeometry args={[0.22, 0.08, 0.38]} />
          <meshStandardMaterial
            ref={(material) => {
              lightRefs.current[index] = material;
            }}
            color={light.color}
            emissive={light.color}
            emissiveIntensity={0.3}
            transparent
            opacity={0.7}
          />
        </mesh>
      ))}
    </group>
  );
}

function VehicleShell({ vehicle, appearance }) {
  return (
    <group>
      <mesh castShadow>
        <boxGeometry args={appearance.footprint} />
        <meshStandardMaterial color={vehicle.color} metalness={0.18} roughness={0.4} />
      </mesh>
      <mesh position={[0, 0.44, 0.05]} castShadow>
        <boxGeometry args={[appearance.footprint[0] * 0.72, appearance.footprint[1] * 0.34, appearance.footprint[2] * 0.46]} />
        <meshStandardMaterial color={appearance.cabinColor} metalness={0.24} roughness={0.28} />
      </mesh>
      <mesh position={[0, 0.12, appearance.footprint[2] * 0.36]}>
        <boxGeometry args={[appearance.footprint[0] * 0.78, 0.08, appearance.footprint[2] * 0.16]} />
        <meshStandardMaterial color={appearance.detailColor} roughness={0.36} />
      </mesh>
      <EmergencyLightBar vehicle={vehicle} appearance={appearance} />
    </group>
  );
}

function VehicleActor({ id, resolvedFramesRef, initial }) {
  const groupRef = useRef();

  useFrame((_, delta) => {
    const sampled = sampleResolvedActor(resolvedFramesRef.current, id);
    if (!sampled || !groupRef.current) {
      return;
    }
    const group = groupRef.current;
    const targetX = sampled.x;
    const targetZ = -sampled.y;
    const positionAlpha = 1 - Math.exp(-VEHICLE_POSITION_DAMPING * delta);
    const rotationAlpha = 1 - Math.exp(-VEHICLE_ROTATION_DAMPING * delta);
    const offsetX = targetX - group.position.x;
    const offsetZ = targetZ - group.position.z;

    if ((offsetX * offsetX) + (offsetZ * offsetZ) > 49) {
      group.position.set(targetX, 0.9, targetZ);
    } else {
      group.position.x = THREE.MathUtils.lerp(group.position.x, targetX, positionAlpha);
      group.position.z = THREE.MathUtils.lerp(group.position.z, targetZ, positionAlpha);
      group.position.y = 0.9;
    }

    const targetHeading = worldYawFromSimulationHeading(sampled.heading ?? 0);
    group.rotation.y = shortestAngleLerp(group.rotation.y, targetHeading, rotationAlpha);
  });

  if (!initial) {
    return null;
  }

  const appearance = vehicleAppearance(initial);
  const initialHeading = worldYawFromSimulationHeading(initial.heading ?? 0);

  return (
    <group ref={groupRef} position={[initial.x, 0.9, -initial.y]} rotation={[0, initialHeading, 0]}>
      <mesh position={[0, -0.86, 0]} rotation={[-Math.PI / 2, 0, 0]} scale={appearance.shadowScale}>
        <circleGeometry args={[1, 24]} />
        <meshBasicMaterial color="#020617" transparent opacity={0.24} />
      </mesh>
      <VehicleShell vehicle={initial} appearance={appearance} />
    </group>
  );
}

/* Legacy compass removed in favor of world-anchored road labels.
function DirectionCompass({ directionAxes }) {
  const axes = directionAxes ?? WORLD_DIRECTION_AXES;
  const northLabel = axes.NORTH?.z === -1 ? "N" : "N?";
  const southLabel = axes.SOUTH?.z === 1 ? "S" : "S?";
  const eastLabel = axes.EAST?.x === 1 ? "E" : "E?";
  const westLabel = axes.WEST?.x === -1 ? "W" : "W?";

  return (
    <div className="pointer-events-none absolute right-4 top-4 z-10 rounded-3xl border border-white/10 bg-slate-950/75 px-4 py-3 text-[11px] text-slate-200 shadow-2xl backdrop-blur">
      <p className="text-[10px] uppercase tracking-[0.28em] text-cyan-300">World Compass</p>
      <div className="relative mt-3 h-20 w-20 rounded-full border border-white/10 bg-white/[0.03]">
        <span className="absolute left-1/2 top-2 -translate-x-1/2 text-sm font-semibold text-white">{northLabel} ↑</span>
        <span className="absolute right-2 top-1/2 -translate-y-1/2 text-sm font-semibold text-white">{eastLabel} →</span>
        <span className="absolute bottom-2 left-1/2 -translate-x-1/2 text-sm font-semibold text-white">{southLabel} ↓</span>
        <span className="absolute left-2 top-1/2 -translate-y-1/2 text-sm font-semibold text-white">{westLabel} ←</span>
        <div className="absolute left-1/2 top-1/2 h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-cyan-300" />
      </div>
      <p className="mt-3 text-[10px] text-slate-400">N=-Z, S=+Z, E=+X, W=-X</p>
    </div>
  );
}
*/

export default function SimulationCanvas({ sceneSnapshot, sceneBufferRef, cameraStateRef, className = "" }) {
  const resolvedFramesRef = useRef({
    previous: null,
    next: null,
    alpha: 0,
  });

  return (
    <div className={`glass-panel relative overflow-hidden rounded-[2rem] ${className || "h-[680px]"}`}>
      <Canvas
        camera={{ position: cameraStateRef.current.position, fov: 42 }}
        dpr={[1, 1.2]}
        gl={{ antialias: false, powerPreference: "high-performance" }}
        frameloop="always"
      >
        <color attach="background" args={["#08131f"]} />
        <fog attach="fog" args={["#08131f", 86, 190]} />
        <ambientLight intensity={0.72} />
        <directionalLight
          position={[42, 74, 34]}
          intensity={1.42}
        />

        <RoadNetwork
          lanes={sceneSnapshot.lanes}
          signals={sceneSnapshot.signals}
          directionAxes={sceneSnapshot.direction_axes}
        />

        <FrameInterpolationCoordinator sceneBufferRef={sceneBufferRef} resolvedFramesRef={resolvedFramesRef} />

        {sceneSnapshot.vehicles.map((vehicle) => (
          <VehicleActor key={vehicle.id} id={vehicle.id} resolvedFramesRef={resolvedFramesRef} initial={vehicle} />
        ))}

        <PersistentOrbitController cameraStateRef={cameraStateRef} />
      </Canvas>
    </div>
  );
}
