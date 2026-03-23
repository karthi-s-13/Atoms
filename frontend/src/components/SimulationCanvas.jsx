import { Line, OrbitControls } from "@react-three/drei";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";

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
const CROSSWALK_INNER_OFFSET = INTERSECTION_HALF_SIZE + 0.4;
const STOP_OFFSET = INTERSECTION_HALF_SIZE + 3;
const CROSSWALK_OUTER_OFFSET = STOP_OFFSET - 0.9;
const CROSSWALK_DEPTH = CROSSWALK_OUTER_OFFSET - CROSSWALK_INNER_OFFSET;
const STRIPE_WIDTH = 0.6;
const STRIPE_GAP = 0.55;
const DASH_LENGTH = 3.2;
const DASH_GAP = 2.2;
const TURN_ARC_SAMPLES = 40;

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

function sampleActor(frames, actorId, kind, now) {
  const { previous, next, alpha } = resolveBufferedFrames(frames, now - 70);
  if (!previous || !next) {
    return null;
  }

  const prevMap = kind === "vehicle" ? previous.vehicleMap : previous.pedestrianMap;
  const nextMap = kind === "vehicle" ? next.vehicleMap : next.pedestrianMap;
  const prevActor = prevMap.get(actorId);
  const nextActor = nextMap.get(actorId);

  if (prevActor && nextActor) {
    return {
      ...nextActor,
      x: THREE.MathUtils.lerp(prevActor.x, nextActor.x, alpha),
      y: THREE.MathUtils.lerp(prevActor.y, nextActor.y, alpha),
      heading: kind === "vehicle" ? shortestAngleLerp(prevActor.heading, nextActor.heading, alpha) : 0,
    };
  }

  if (nextActor) {
    return nextActor;
  }

  if (prevActor) {
    const driftSeconds = Math.min(0.1, Math.max(0, (now - previous.receivedAt) / 1000));
    return {
      ...prevActor,
      x: prevActor.x + ((prevActor.velocity_x ?? 0) * driftSeconds),
      y: prevActor.y + ((prevActor.velocity_y ?? 0) * driftSeconds),
      heading: prevActor.heading ?? 0,
    };
  }

  return null;
}

function laneHeading(lane) {
  const start = lane.path?.[0] ?? lane.start;
  const next = lane.path?.[1] ?? lane.end;
  return Math.atan2(next.x - start.x, next.y - start.y);
}

function laneLeftNormal(lane) {
  const start = lane.path?.[0] ?? lane.start;
  const next = lane.path?.[1] ?? lane.end;
  const dx = next.x - start.x;
  const dz = next.y - start.y;
  const length = Math.hypot(dx, dz) || 1;
  return { x: -dz / length, z: dx / length };
}

function laneForward(lane) {
  const start = lane.path?.[0] ?? lane.start;
  const next = lane.path?.[1] ?? lane.end;
  const dx = next.x - start.x;
  const dz = next.y - start.y;
  const length = Math.hypot(dx, dz) || 1;
  return { x: dx / length, z: dz / length };
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

function isCrosswalkActive(crosswalk, activeCrosswalkIds) {
  return activeCrosswalkIds.has(crosswalk.id);
}

function pedestrianFacing(pedestrian) {
  const velocityX = pedestrian.velocity_x ?? 0;
  const velocityY = pedestrian.velocity_y ?? 0;
  if (Math.hypot(velocityX, velocityY) > 0.04) {
    return Math.atan2(velocityX, velocityY);
  }
  if (pedestrian.crossing === "EW") {
    return pedestrian.x <= 0 ? Math.PI / 2 : -Math.PI / 2;
  }
  return pedestrian.y <= 0 ? 0 : Math.PI;
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

function pushUniqueLanePoint(points, point) {
  const previous = points[points.length - 1];
  if (!previous) {
    points.push(point);
    return;
  }
  if (Math.hypot(previous[0] - point[0], previous[2] - point[2]) > 1e-4) {
    points.push(point);
  }
}

function laneDebugPoints(lane) {
  const points = [];
  const appendPoint2D = (point) => {
    if (!point) {
      return;
    }
    pushUniqueLanePoint(points, [point.x, 0.08, point.y]);
  };

  appendPoint2D(lane.start);

  if (lane.arc && lane.turn_entry && lane.turn_exit) {
    appendPoint2D(lane.turn_entry);
    const curve = new THREE.EllipseCurve(
      lane.arc.center.x,
      lane.arc.center.y,
      lane.arc.radius,
      lane.arc.radius,
      lane.arc.start_angle,
      lane.arc.end_angle,
      lane.arc.clockwise,
      0,
    );
    curve.getPoints(TURN_ARC_SAMPLES).forEach((point) => {
      pushUniqueLanePoint(points, [point.x, 0.08, point.y]);
    });
    appendPoint2D(lane.turn_exit);
    appendPoint2D(lane.end);
    return points;
  }

  (lane.path ?? []).forEach(appendPoint2D);
  appendPoint2D(lane.end);
  return points;
}

function stopLaneKey(lane) {
  return `${lane.approach}:${lane.stop_line_position.x.toFixed(2)}:${lane.stop_line_position.y.toFixed(2)}`;
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
  const physicalLanes = uniquePhysicalLanes(lanes);
  const representativeLane = physicalLanes.find((lane) => lane.movement === "STRAIGHT") ?? physicalLanes[0];
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

  return {
    id: representativeLane.approach,
    state: signalStateForApproach(signals, representativeLane.approach),
    position: [
      stopPoint.x + (leftNormal.x * 4.2) - (forward.x * 1.6),
      0,
      stopPoint.y + (leftNormal.z * 4.2) - (forward.z * 1.6),
    ],
    facing: laneHeading(representativeLane) + Math.PI,
  };
}

function SignalHead({ signal }) {
  const { facing, position, state } = signal;
  const redLight = lightDescriptor(state, "RED");
  const yellowLight = lightDescriptor(state, "YELLOW");
  const greenLight = lightDescriptor(state, "GREEN");

  return (
    <group position={position} rotation={[0, facing, 0]}>
      <mesh position={[0, 3.2, 0]} castShadow>
        <cylinderGeometry args={[0.16, 0.2, 6.4, 14]} />
        <meshStandardMaterial color="#334155" metalness={0.35} roughness={0.6} />
      </mesh>
      <mesh position={[0.44, 5.9, 0]} castShadow>
        <boxGeometry args={[1.18, 3.1, 1.04]} />
        <meshStandardMaterial color="#0f172a" metalness={0.3} roughness={0.58} />
      </mesh>
      <mesh position={[0.44, 6.52, 0.6]} castShadow>
        <sphereGeometry args={[0.24, 18, 18]} />
        <meshStandardMaterial color={redLight.color} emissive={redLight.emissive} emissiveIntensity={redLight.intensity} />
      </mesh>
      <mesh position={[0.44, 5.6, 0.6]} castShadow>
        <sphereGeometry args={[0.24, 18, 18]} />
        <meshStandardMaterial color={yellowLight.color} emissive={yellowLight.emissive} emissiveIntensity={yellowLight.intensity} />
      </mesh>
      <mesh position={[0.44, 4.68, 0.6]} castShadow>
        <sphereGeometry args={[0.24, 18, 18]} />
        <meshStandardMaterial color={greenLight.color} emissive={greenLight.emissive} emissiveIntensity={greenLight.intensity} />
      </mesh>
    </group>
  );
}

function Crosswalk({ crosswalk, active }) {
  const horizontal = Math.abs(crosswalk.end.x - crosswalk.start.x) > Math.abs(crosswalk.end.y - crosswalk.start.y);
  const stripeSpan = horizontal
    ? Math.abs(crosswalk.end.x - crosswalk.start.x)
    : Math.abs(crosswalk.end.y - crosswalk.start.y);
  const center = {
    x: (crosswalk.start.x + crosswalk.end.x) / 2,
    y: (crosswalk.start.y + crosswalk.end.y) / 2,
  };
  const stripePitch = STRIPE_WIDTH + STRIPE_GAP;
  const stripeCount = Math.max(1, Math.floor((CROSSWALK_DEPTH + STRIPE_GAP) / stripePitch));
  const usedDepth = (stripeCount * STRIPE_WIDTH) + ((stripeCount - 1) * STRIPE_GAP);
  const firstStripeOffset = -((usedDepth - STRIPE_WIDTH) / 2);

  return (
    <group>
      <mesh position={[center.x, 0.024, center.y]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={horizontal ? [stripeSpan, CROSSWALK_DEPTH] : [CROSSWALK_DEPTH, stripeSpan]} />
        <meshStandardMaterial color="#273243" roughness={0.96} metalness={0.04} />
      </mesh>
      {Array.from({ length: stripeCount }, (_, index) => {
        const offset = firstStripeOffset + (index * stripePitch);
        const position = horizontal
          ? [center.x, 0.031, center.y + offset]
          : [center.x + offset, 0.031, center.y];
        return (
          <mesh key={`${crosswalk.id}-${index}`} position={position} rotation={[-Math.PI / 2, 0, 0]}>
            <planeGeometry args={horizontal ? [stripeSpan, STRIPE_WIDTH] : [STRIPE_WIDTH, stripeSpan]} />
            <meshStandardMaterial color="#f8fafc" emissive={active ? "#86efac" : "#e2e8f0"} emissiveIntensity={active ? 0.48 : 0.08} />
          </mesh>
        );
      })}
    </group>
  );
}

function StopLine({ lanes }) {
  const physicalLanes = uniquePhysicalLanes(lanes);
  const stopPoint = physicalLanes.reduce(
    (accumulator, lane) => ({
      x: accumulator.x + lane.stop_line_position.x,
      y: accumulator.y + lane.stop_line_position.y,
    }),
    { x: 0, y: 0 },
  );
  stopPoint.x /= physicalLanes.length;
  stopPoint.y /= physicalLanes.length;
  const vertical = physicalLanes[0].approach === "NORTH" || physicalLanes[0].approach === "SOUTH";

  return (
    <mesh position={[stopPoint.x, 0.032, stopPoint.y]} rotation={[-Math.PI / 2, 0, 0]}>
      <planeGeometry args={vertical ? [physicalLanes.length * LANE_WIDTH, 0.44] : [0.44, physicalLanes.length * LANE_WIDTH]} />
      <meshStandardMaterial color="#f8fafc" emissive="#ffffff" emissiveIntensity={0.12} />
    </mesh>
  );
}

function PathDebugLine({ lane }) {
  const points = useMemo(() => laneDebugPoints(lane), [lane]);
  const color = lane.movement === "RIGHT" ? "#f59e0b" : "#7dd3fc";
  return <Line points={points} color={color} transparent opacity={0.28} lineWidth={1.4} />;
}

function RoadNetwork({ lanes, crosswalks, pedestrians, signals }) {
  const stripes = useMemo(() => dividerSegments(), []);
  const activeCrosswalkIds = useMemo(
    () => new Set(pedestrians.filter((pedestrian) => pedestrian.state === "CROSSING").map((pedestrian) => pedestrian.crosswalk_id)),
    [pedestrians],
  );
  const lanesByApproach = lanes.reduce((groups, lane) => {
    groups[lane.approach] = groups[lane.approach] ?? [];
    groups[lane.approach].push(lane);
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
    [-INTERSECTION_HALF_SIZE, 0.05, -INTERSECTION_HALF_SIZE],
    [-INTERSECTION_HALF_SIZE, 0.05, INTERSECTION_HALF_SIZE],
    [INTERSECTION_HALF_SIZE, 0.05, INTERSECTION_HALF_SIZE],
    [INTERSECTION_HALF_SIZE, 0.05, -INTERSECTION_HALF_SIZE],
    [-INTERSECTION_HALF_SIZE, 0.05, -INTERSECTION_HALF_SIZE],
  ];

  return (
    <group>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.08, 0]} receiveShadow>
        <planeGeometry args={[210, 210]} />
        <meshStandardMaterial color="#0b1725" />
      </mesh>

      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.004, 0]} receiveShadow>
        <planeGeometry args={[ROAD_SURFACE_WIDTH, ROAD_SURFACE_LENGTH]} />
        <meshStandardMaterial color="#1f2937" roughness={0.96} metalness={0.05} />
      </mesh>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.004, 0]} receiveShadow>
        <planeGeometry args={[ROAD_SURFACE_LENGTH, ROAD_SURFACE_WIDTH]} />
        <meshStandardMaterial color="#1f2937" roughness={0.96} metalness={0.05} />
      </mesh>

      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.008, 0]} receiveShadow>
        <planeGeometry args={[INTERSECTION_SIZE, INTERSECTION_SIZE]} />
        <meshStandardMaterial color="#2a3545" roughness={0.88} metalness={0.05} />
      </mesh>
      <Line points={intersectionOutline} color="#f8fafc" transparent opacity={0.35} lineWidth={1.2} />

      {stripes.map((segment) => (
        <SurfaceStripe key={segment.id} segment={segment} />
      ))}

      {lanes.map((lane) => (
        <PathDebugLine key={`path-${lane.id}`} lane={lane} />
      ))}

      {crosswalks.map((crosswalk) => (
        <Crosswalk
          key={crosswalk.id}
          crosswalk={crosswalk}
          active={isCrosswalkActive(crosswalk, activeCrosswalkIds)}
        />
      ))}

      {stopLineGroups.map((group) => (
        <StopLine key={`stop-${group[0].approach}`} lanes={group} />
      ))}

      {signalDescriptors.map((signal) => (
        <SignalHead key={`signal-${signal.id}`} signal={signal} />
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
    </group>
  );
}

function VehicleActor({ id, sceneBufferRef, initial }) {
  const groupRef = useRef();

  useFrame(() => {
    const sampled = sampleActor(sceneBufferRef.current.frames, id, "vehicle", performance.now());
    if (!sampled || !groupRef.current) {
      return;
    }
    groupRef.current.position.set(sampled.x, 0.9, sampled.y);
    groupRef.current.rotation.y = sampled.heading ?? 0;
  });

  if (!initial) {
    return null;
  }

  const appearance = vehicleAppearance(initial);

  return (
    <group ref={groupRef} position={[initial.x, 0.9, initial.y]} rotation={[0, initial.heading ?? 0, 0]}>
      <mesh position={[0, -0.86, 0]} rotation={[-Math.PI / 2, 0, 0]} scale={appearance.shadowScale}>
        <circleGeometry args={[1, 24]} />
        <meshBasicMaterial color="#020617" transparent opacity={0.24} />
      </mesh>
      <VehicleShell vehicle={initial} appearance={appearance} />
    </group>
  );
}

function PedestrianActor({ id, sceneBufferRef, initial }) {
  const rootRef = useRef();
  const bodyRef = useRef();
  const leftLegRef = useRef();
  const rightLegRef = useRef();
  const phaseOffsetRef = useRef((Number(id.replace(/\D/g, "")) || 1) * 0.5);

  useFrame((renderState) => {
    const sampled = sampleActor(sceneBufferRef.current.frames, id, "pedestrian", performance.now());
    if (!sampled || !rootRef.current) {
      return;
    }

    const elapsed = renderState.clock.getElapsedTime() + phaseOffsetRef.current;
    const crossing = sampled.state !== "WAITING";
    const swing = crossing ? Math.sin(elapsed * 8) * 0.4 : 0;
    const bob = crossing ? Math.sin(elapsed * 8) * 0.04 : 0;

    rootRef.current.position.set(sampled.x, 0, sampled.y);
    rootRef.current.rotation.y = pedestrianFacing(sampled);

    if (bodyRef.current) {
      bodyRef.current.position.y = 0.02 + bob;
    }
    if (leftLegRef.current) {
      leftLegRef.current.rotation.x = -swing;
    }
    if (rightLegRef.current) {
      rightLegRef.current.rotation.x = swing;
    }
  });

  if (!initial) {
    return null;
  }

  return (
    <group ref={rootRef} position={[initial.x, 0, initial.y]} rotation={[0, pedestrianFacing(initial), 0]} scale={[initial.body_scale ?? 1, initial.body_scale ?? 1, initial.body_scale ?? 1]}>
      <mesh position={[0, 0.01, 0]} rotation={[-Math.PI / 2, 0, 0]} scale={[0.35, 0.5, 1]}>
        <circleGeometry args={[1, 18]} />
        <meshBasicMaterial color="#020617" transparent opacity={0.2} />
      </mesh>
      <group ref={bodyRef} position={[0, 0.02, 0]}>
        <group ref={leftLegRef} position={[-0.1, 0.32, 0]}>
          <mesh castShadow>
            <cylinderGeometry args={[0.06, 0.07, 0.5, 10]} />
            <meshStandardMaterial color={initial.pants_color ?? "#334155"} roughness={0.72} />
          </mesh>
        </group>
        <group ref={rightLegRef} position={[0.1, 0.32, 0]}>
          <mesh castShadow>
            <cylinderGeometry args={[0.06, 0.07, 0.5, 10]} />
            <meshStandardMaterial color={initial.pants_color ?? "#334155"} roughness={0.72} />
          </mesh>
        </group>
        <mesh position={[0, 0.86, 0]} castShadow>
          <capsuleGeometry args={[0.18, 0.48, 6, 10]} />
          <meshStandardMaterial color={initial.shirt_color ?? "#fb923c"} roughness={0.42} metalness={0.06} />
        </mesh>
        <mesh position={[0, 1.44, 0]} castShadow>
          <sphereGeometry args={[0.18, 16, 16]} />
          <meshStandardMaterial color="#f8d5b8" roughness={0.82} />
        </mesh>
      </group>
    </group>
  );
}

export default function SimulationCanvas({ sceneSnapshot, sceneBufferRef, cameraStateRef }) {
  return (
    <div className="glass-panel h-[680px] overflow-hidden rounded-[2rem]">
      <Canvas shadows camera={{ position: cameraStateRef.current.position, fov: 42 }}>
        <color attach="background" args={["#08131f"]} />
        <fog attach="fog" args={["#08131f", 86, 190]} />
        <ambientLight intensity={0.72} />
        <directionalLight
          castShadow
          position={[42, 74, 34]}
          intensity={1.42}
          shadow-bias={-0.0005}
          shadow-normalBias={0.02}
          shadow-mapSize-width={1024}
          shadow-mapSize-height={1024}
        />

        <RoadNetwork
          lanes={sceneSnapshot.lanes}
          crosswalks={sceneSnapshot.crosswalks}
          pedestrians={sceneSnapshot.pedestrians}
          signals={sceneSnapshot.signals}
        />

        {sceneSnapshot.vehicles.map((vehicle) => (
          <VehicleActor key={vehicle.id} id={vehicle.id} sceneBufferRef={sceneBufferRef} initial={vehicle} />
        ))}

        {sceneSnapshot.pedestrians.map((pedestrian) => (
          <PedestrianActor key={pedestrian.id} id={pedestrian.id} sceneBufferRef={sceneBufferRef} initial={pedestrian} />
        ))}

        <PersistentOrbitController cameraStateRef={cameraStateRef} />
      </Canvas>
    </div>
  );
}
