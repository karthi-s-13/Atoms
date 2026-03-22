import { Line, OrbitControls } from "@react-three/drei";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useRef } from "react";
import * as THREE from "three";

function laneHeading(lane) {
  return Math.atan2(lane.end.x - lane.start.x, lane.end.y - lane.start.y);
}

function laneNormal(lane) {
  const dx = lane.end.x - lane.start.x;
  const dz = lane.end.y - lane.start.y;
  const length = Math.hypot(dx, dz) || 1;
  return { x: dz / length, z: -dx / length };
}

function interpolatePoint(start, end, progress) {
  return {
    x: start.x + ((end.x - start.x) * progress),
    y: start.y + ((end.y - start.y) * progress),
  };
}

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

function lightDescriptor(state, lamp) {
  const palette = { RED: "#ef4444", YELLOW: "#facc15", GREEN: "#22c55e" };
  const active = state === lamp;
  return {
    color: active ? palette[lamp] : "#162033",
    emissive: active ? palette[lamp] : "#020617",
    intensity: active ? 2.8 : 0.08,
  };
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

  return (
    <OrbitControls
      ref={controlsRef}
      makeDefault
      enablePan
      enableZoom
      maxPolarAngle={Math.PI / 2.08}
      minDistance={36}
      maxDistance={132}
    />
  );
}

function SignalHead({ lane, state }) {
  const normal = laneNormal(lane);
  const stopPoint = lane.stop_line_position;
  const heading = laneHeading(lane);
  const facing = heading + Math.PI;
  const basePosition = [stopPoint.x + (normal.x * 5), 0, stopPoint.y + (normal.z * 5)];
  const redLight = lightDescriptor(state, "RED");
  const yellowLight = lightDescriptor(state, "YELLOW");
  const greenLight = lightDescriptor(state, "GREEN");

  return (
    <group position={basePosition} rotation={[0, facing, 0]}>
      <mesh position={[0, 3.4, 0]} castShadow receiveShadow>
        <cylinderGeometry args={[0.18, 0.22, 7, 14]} />
        <meshStandardMaterial color="#334155" metalness={0.4} roughness={0.6} />
      </mesh>
      <mesh position={[0.5, 6.3, 0]} castShadow receiveShadow>
        <boxGeometry args={[1.36, 4.3, 1.24]} />
        <meshStandardMaterial color="#0f172a" metalness={0.35} roughness={0.55} />
      </mesh>
      <mesh position={[0.5, 7.36, 0.72]} castShadow>
        <sphereGeometry args={[0.28, 24, 24]} />
        <meshStandardMaterial color={redLight.color} emissive={redLight.emissive} emissiveIntensity={redLight.intensity} />
      </mesh>
      <mesh position={[0.5, 6.3, 0.72]} castShadow>
        <sphereGeometry args={[0.28, 24, 24]} />
        <meshStandardMaterial color={yellowLight.color} emissive={yellowLight.emissive} emissiveIntensity={yellowLight.intensity} />
      </mesh>
      <mesh position={[0.5, 5.24, 0.72]} castShadow>
        <sphereGeometry args={[0.28, 24, 24]} />
        <meshStandardMaterial color={greenLight.color} emissive={greenLight.emissive} emissiveIntensity={greenLight.intensity} />
      </mesh>
    </group>
  );
}

function Crosswalk({ crosswalk, active }) {
  const stripeCount = 8;
  const stripes = [];
  for (let index = 0; index < stripeCount; index += 1) {
    const progress = (index + 0.5) / stripeCount;
    const point = interpolatePoint(crosswalk.start, crosswalk.end, progress);
    const horizontal = Math.abs(crosswalk.start.x - crosswalk.end.x) > Math.abs(crosswalk.start.y - crosswalk.end.y);
    stripes.push(
      <mesh key={`${crosswalk.id}-${index}`} position={[point.x, 0.03, point.y]} rotation={[-Math.PI / 2, 0, horizontal ? 0 : Math.PI / 2]}>
        <planeGeometry args={horizontal ? [2.35, 0.92] : [0.92, 2.35]} />
        <meshStandardMaterial
          color="#f8fafc"
          emissive={active ? "#86efac" : "#000000"}
          emissiveIntensity={active ? 0.42 : 0.0}
          transparent
          opacity={0.96}
        />
      </mesh>,
    );
  }
  return <group>{stripes}</group>;
}

function StopLine({ lane }) {
  const heading = laneHeading(lane);
  const stopPoint = lane.stop_line_position;

  return (
    <mesh position={[stopPoint.x, 0.04, stopPoint.y]} rotation={[-Math.PI / 2, heading, 0]}>
      <planeGeometry args={[7.8, 0.72]} />
      <meshStandardMaterial color="#f8fafc" emissive="#ffffff" emissiveIntensity={0.09} transparent opacity={0.98} />
    </mesh>
  );
}

function RoadNetwork({ lanes, crosswalks, signals, pedestrianPhaseActive }) {
  return (
    <group>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.06, 0]} receiveShadow>
        <planeGeometry args={[190, 190]} />
        <meshStandardMaterial color="#05101f" />
      </mesh>

      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[2, 0, 0]} receiveShadow>
        <planeGeometry args={[20, 156]} />
        <meshStandardMaterial color="#13233a" roughness={0.95} />
      </mesh>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, 2]} receiveShadow>
        <planeGeometry args={[156, 20]} />
        <meshStandardMaterial color="#13233a" roughness={0.95} />
      </mesh>

      {lanes.map((lane) => (
        <Line
          key={lane.id}
          points={[
            [lane.start.x, 0.02, lane.start.y],
            [lane.end.x, 0.02, lane.end.y],
          ]}
          color="#67e8f9"
          lineWidth={1.0}
          dashed
          dashScale={9}
          dashSize={2}
          gapSize={1.2}
          opacity={0.42}
          transparent
        />
      ))}

      {crosswalks.map((crosswalk) => (
        <Crosswalk key={crosswalk.id} crosswalk={crosswalk} active={pedestrianPhaseActive} />
      ))}

      {lanes.map((lane) => (
        <StopLine key={`stop-${lane.id}`} lane={lane} />
      ))}

      {lanes.map((lane) => (
        <SignalHead key={`signal-${lane.id}`} lane={lane} state={signals[lane.approach] ?? "RED"} />
      ))}
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
    groupRef.current.position.set(sampled.x, 0.92, sampled.y);
    groupRef.current.rotation.y = sampled.heading ?? 0;
  });

  if (!initial) {
    return null;
  }

  const size =
    initial.kind === "firetruck"
      ? [2.45, 1.45, 5.8]
      : initial.kind === "ambulance"
        ? [2.25, 1.35, 5.0]
        : initial.kind === "police"
          ? [2.1, 1.2, 4.55]
          : [2.0, 1.15, 4.3];

  return (
    <group ref={groupRef} position={[initial.x, 0.92, initial.y]} rotation={[0, initial.heading ?? 0, 0]}>
      <mesh castShadow receiveShadow>
        <boxGeometry args={size} />
        <meshStandardMaterial color={initial.color} metalness={0.16} roughness={0.4} />
      </mesh>
      <mesh position={[0, 0.48, 0.06]} castShadow>
        <boxGeometry args={[size[0] * 0.72, size[1] * 0.34, size[2] * 0.45]} />
        <meshStandardMaterial color={initial.kind === "car" ? "#0f172a" : "#cbd5e1"} metalness={0.24} roughness={0.3} />
      </mesh>
      {initial.has_siren ? (
        <>
          <mesh position={[-0.42, 0.82, -0.18]}>
            <boxGeometry args={[0.34, 0.12, 0.5]} />
            <meshStandardMaterial color="#ef4444" emissive="#ef4444" emissiveIntensity={1.8} />
          </mesh>
          <mesh position={[0.42, 0.82, -0.18]}>
            <boxGeometry args={[0.34, 0.12, 0.5]} />
            <meshStandardMaterial color="#60a5fa" emissive="#60a5fa" emissiveIntensity={1.8} />
          </mesh>
        </>
      ) : null}
    </group>
  );
}

function PedestrianActor({ id, sceneBufferRef, initial }) {
  const meshRef = useRef();

  useFrame(() => {
    const sampled = sampleActor(sceneBufferRef.current.frames, id, "pedestrian", performance.now());
    if (!sampled || !meshRef.current) {
      return;
    }
    meshRef.current.position.set(sampled.x, 0.42, sampled.y);
  });

  if (!initial) {
    return null;
  }

  return (
    <mesh ref={meshRef} position={[initial.x, 0.42, initial.y]} castShadow>
      <boxGeometry args={[0.84, 0.84, 0.84]} />
      <meshStandardMaterial color={initial.state === "WAITING" ? "#fb923c" : "#f8fafc"} roughness={0.5} />
    </mesh>
  );
}

export default function SimulationCanvas({ sceneSnapshot, sceneBufferRef, cameraStateRef }) {
  return (
    <div className="glass-panel h-[680px] overflow-hidden rounded-[2rem]">
      <Canvas shadows camera={{ position: cameraStateRef.current.position, fov: 42 }}>
        <color attach="background" args={["#06111f"]} />
        <fog attach="fog" args={["#06111f", 88, 190]} />
        <ambientLight intensity={0.72} />
        <directionalLight
          castShadow
          position={[42, 72, 34]}
          intensity={1.45}
          shadow-mapSize-width={2048}
          shadow-mapSize-height={2048}
        />
        <pointLight position={[0, 22, 0]} intensity={0.78} color="#22d3ee" />

        <RoadNetwork
          lanes={sceneSnapshot.lanes}
          crosswalks={sceneSnapshot.crosswalks}
          signals={sceneSnapshot.signals}
          pedestrianPhaseActive={sceneSnapshot.pedestrian_phase_active}
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
