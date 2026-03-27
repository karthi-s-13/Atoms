import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import {
  worldYawFromSimulationHeading,
} from "../lib/directions";

// Constants (Reused)
const LANE_WIDTH = 3.5;
const LANES_PER_DIRECTION = 2;
const SHOULDER = 0.75;
const ROAD_EXTENT = 85;
const ROAD_SURFACE_LENGTH = (ROAD_EXTENT * 2) + 20;
const INTERSECTION_SIZE = 14.5;
const INTERSECTION_HALF_SIZE = INTERSECTION_SIZE / 2;
const MAX_VEHICLE_INSTANCES = 64; // Performance Cap for Demo
const ROAD_SURFACE_Y = 0;
const INTERSECTION_SURFACE_Y = ROAD_SURFACE_Y + 0.01;
const GROUND_SURFACE_Y = -0.15;
const MARKING_SURFACE_Y = 0.04;
const STOP_LINE_SURFACE_Y = MARKING_SURFACE_Y + 0.002;

const ASPHALT_COLOR = "#2f2f2f";
const MARKING_COLOR = "#fcfcfc";
const DIVIDER_COLOR = "#facc15";
const EDGE_HIGHLIGHT_COLOR = "#4a4a4a";

const EMISSIVE_RED = "#ff3333";
const EMISSIVE_YELLOW = "#ffcc00";
const EMISSIVE_GREEN = "#00ff88";

const VEHICLE_PALETTE = ["#3b82f6", "#ef4444", "#facc15", "#f8fafc", "#22c55e"];
const INTERPOLATION_DELAY_MS = 60; // Increased for 20Hz backend snapshots
const POSITION_SMOOTHING = 0.15;
const ROTATION_SMOOTHING = 0.10;
const SNAP_THRESHOLD = 0.05;

function shortestAngleLerp(start, end, alpha) {
  let delta = end - start;
  while (delta > Math.PI) delta -= Math.PI * 2;
  while (delta < -Math.PI) delta += Math.PI * 2;
  return start + (delta * alpha);
}

function resolveBufferedFrames(frames, targetTime) {
  if (!frames.length) return { previous: null, next: null, alpha: 0, targetTime };
  if (frames.length === 1 || targetTime <= frames[0].receivedAt) return { previous: frames[0], next: frames[0], alpha: 0, targetTime };

  for (let i = 0; i < frames.length - 1; i++) {
    const prev = frames[i];
    const next = frames[i + 1];
    if (prev.receivedAt <= targetTime && targetTime <= next.receivedAt) {
      const duration = Math.max(1, next.receivedAt - prev.receivedAt);
      return { previous: prev, next, alpha: (targetTime - prev.receivedAt) / duration, targetTime };
    }
  }
  return { 
    previous: frames[frames.length - 2] ?? frames[frames.length - 1], 
    next: frames[frames.length - 1], 
    alpha: (targetTime - (frames[frames.length - 1].receivedAt)) / 50 + 1.0, // Calculated alpha for extrapolation
    targetTime 
  };
}

function sampleResolvedActor(resolvedFrames, actorId) {
  if (!resolvedFrames?.previous || !resolvedFrames?.next) return null;
  const prevActor = resolvedFrames.previous.vehicleMap.get(actorId);
  const nextActor = resolvedFrames.next.vehicleMap.get(actorId);

  if (prevActor && nextActor) {
    const dt = Math.max(0.001, (resolvedFrames.next.receivedAt - resolvedFrames.previous.receivedAt) / 1000);
    const vx = (nextActor.x - prevActor.x) / dt;
    const vy = (nextActor.y - prevActor.y) / dt;

    // INTERPOLATION path
    if (resolvedFrames.alpha <= 1.0) {
      return {
        ...nextActor,
        x: THREE.MathUtils.lerp(prevActor.x, nextActor.x, resolvedFrames.alpha),
        y: THREE.MathUtils.lerp(prevActor.y, nextActor.y, resolvedFrames.alpha),
        vx,
        vy,
        heading: shortestAngleLerp(prevActor.heading, nextActor.heading, resolvedFrames.alpha),
      };
    }
    
    // EXTRAPOLATION path (glide forward based on last velocity if we run out of frames)
    const extraTime = (resolvedFrames.targetTime - resolvedFrames.next.receivedAt) / 1000;
    // Limit extrapolation to 200ms to prevent runaway ghost vehicles
    const glideTime = Math.min(extraTime, 0.2); 
    
    return {
      ...nextActor,
      x: nextActor.x + (vx * glideTime),
      y: nextActor.y + (vy * glideTime),
      vx,
      vy,
      heading: nextActor.heading,
    };
  }
  return nextActor || prevActor || null;
}

export default function InstancedSimulationCanvas({ sceneSnapshot, sceneBufferRef, cameraStateRef, className = "" }) {
  const containerRef = useRef(null);
  const snapshotRef = useRef(sceneSnapshot);
  
  // Update ref when prop changes
  useEffect(() => {
    snapshotRef.current = sceneSnapshot;
  }, [sceneSnapshot]);

  useEffect(() => {
    if (!containerRef.current) return;

    // 1. Scene Setup
    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#0a121d");
    scene.fog = new THREE.Fog("#0a121d", 100, 220);

    // 2. Camera Setup
    const width = containerRef.current.clientWidth || 800;
    const height = containerRef.current.clientHeight || 600;
    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);
    camera.position.set(20, 25, 20);
    camera.lookAt(0, 0, 0);

    // 3. Renderer Setup
    const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    containerRef.current.appendChild(renderer.domElement);

    // 4. Controls
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enablePan = false;
    controls.maxPolarAngle = Math.PI / 2.3;
    controls.minDistance = 20;
    controls.maxDistance = 120;

    // 5. Lighting
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.8);
    scene.add(ambientLight);

    const dirLight = new THREE.DirectionalLight(0xffffff, 0.6);
    dirLight.position.set(50, 80, 40);
    dirLight.castShadow = false; // Disable heavy shadows as requested
    scene.add(dirLight);

    const pointLight = new THREE.PointLight("#3b82f6", 0.3);
    pointLight.position.set(-20, 10, -20);
    scene.add(pointLight);

    // 6. VALIDATION CUBE (Rotating)
    const cubeGeom = new THREE.BoxGeometry(2, 2, 2);
    const cubeMat = new THREE.MeshStandardMaterial({ color: "#00ff88", emissive: "#00ff88", emissiveIntensity: 0.5 });
    const validationCube = new THREE.Mesh(cubeGeom, cubeMat);
    validationCube.position.set(0, 10, 0);
    scene.add(validationCube);

    // ... (Road geometry remains same)

    // 9. VEHICLES (InstancedMesh)
    const vehicleMesh = new THREE.InstancedMesh(
      new THREE.BoxGeometry(1, 1, 1), 
      new THREE.MeshStandardMaterial({ 
        metalness: 0.1, 
        roughness: 0.4,
        emissiveIntensity: 0.3 // Base emissive for visibility
      }), 
      MAX_VEHICLE_INSTANCES
    );
    scene.add(vehicleMesh);

    const shadowMesh = new THREE.InstancedMesh(
      new THREE.PlaneGeometry(1, 1), 
      new THREE.MeshBasicMaterial({ color: "#000", transparent: true, opacity: 0.3 }), 
      MAX_VEHICLE_INSTANCES
    );
    scene.add(shadowMesh);

    // 10. ADVANCED MOTION STATE
    const vehicleStates = new Map();
    const freeIndices = Array.from({ length: MAX_VEHICLE_INSTANCES }, (_, i) => i).reverse();
    const idToPoolIndex = new Map();
    
    // Smooth Speed Multiplier
    let actualSpeedMultiplier = 1.0;

    const getPoolIndex = (id) => {
      if (idToPoolIndex.has(id)) return idToPoolIndex.get(id);
      if (freeIndices.length === 0) return null;
      const idx = freeIndices.pop();
      idToPoolIndex.set(id, idx);
      return idx;
    };

    const releasePoolIndex = (id) => {
      if (idToPoolIndex.has(id)) {
        freeIndices.push(idToPoolIndex.get(id));
        idToPoolIndex.delete(id);
      }
    };

    // 11. Animation Loop
    let animationId;
    const dummy = new THREE.Object3D();
    let lastTime = performance.now();

    const animate = () => {
      animationId = requestAnimationFrame(animate);
      
      const now = performance.now();
      let delta = Math.min(0.033, (now - lastTime) / 1000); // Clamp delta as requested
      lastTime = now;

      // Smooth Speed Transition
      const targetSpeed = snapshotRef.current.config?.sim_speed || 1.0;
      actualSpeedMultiplier += (targetSpeed - actualSpeedMultiplier) * 0.1;
      
      // Pulse for Emergency Lights
      const emergencyIntensity = (Math.sin(now * 0.01) * 0.5) + 0.5;

      // Rotate Validation Cube
      validationCube.rotation.y += delta * 0.5 * actualSpeedMultiplier;

      const currentSnapshot = snapshotRef.current;
      const frames = sceneBufferRef.current.frames;
      const resolved = resolveBufferedFrames(frames, now - INTERPOLATION_DELAY_MS);

      // --- 1. Update Signals --- (Signal logic same)

      // --- 2. Advanced Vehicle Synchronization & Spacing ---
      const activeVehicles = currentSnapshot.vehicles || [];
      const activeIds = new Set(activeVehicles.map(v => v.id));

      // Cleanup stale states
      for (const id of vehicleStates.keys()) {
        if (!activeIds.has(id)) {
          releasePoolIndex(id);
          vehicleStates.delete(id);
        }
      }

      // Update/Create internal states
      activeVehicles.forEach(v => {
        const sampled = sampleResolvedActor(resolved, v.id);
        if (!sampled) return;

        let state = vehicleStates.get(v.id);
        if (!state) {
          const idx = getPoolIndex(v.id);
          if (idx === null) return;
          state = {
            id: v.id,
            index: idx,
            pos: new THREE.Vector3(sampled.x, 0.2, -sampled.y), // Elevated to y: 0.2
            targetPos: new THREE.Vector3(sampled.x, 0.2, -sampled.y),
            vel: new THREE.Vector3(sampled.vx || 0, 0, -(sampled.vy || 0)),
            targetVel: new THREE.Vector3(sampled.vx || 0, 0, -(sampled.vy || 0)),
            heading: worldYawFromSimulationHeading(sampled.heading ?? 0),
            laneId: v.lane_id,
            length: v.length || 4.4,
            width: v.width || 1.9,
            hasSiren: v.has_siren,
            color: v.color || VEHICLE_PALETTE[Math.abs(v.id.split('').reduce((a, b) => a + b.charCodeAt(0), 0)) % VEHICLE_PALETTE.length]
          };
          vehicleStates.set(v.id, state);
        } else {
          state.targetPos.set(sampled.x, 0.2, -sampled.y);
          state.targetVel.set(sampled.vx || 0, 0, -(sampled.vy || 0));
          state.rawHeading = worldYawFromSimulationHeading(sampled.heading ?? 0);
          state.laneId = v.lane_id;
        }
      });

      // --- 3. Leader-Following Gap Preservation ---
      // Group by Lane to enforce spacing
      const laneGroups = {};
      vehicleStates.forEach(s => {
        if (!laneGroups[s.laneId]) laneGroups[s.laneId] = [];
        laneGroups[s.laneId].push(s);
      });

      Object.values(laneGroups).forEach(laneVehicles => {
        // Sort by approximate distance from center (using X or Z depending on lane orientation)
        // This is a simplification; ideally we'd use distance-along-path from backend
        laneVehicles.sort((a, b) => b.pos.lengthSq() - a.pos.lengthSq());

        for (let i = 1; i < laneVehicles.length; i++) {
          const leader = laneVehicles[i-1];
          const follower = laneVehicles[i];
          const dist = follower.pos.distanceTo(leader.pos);
          const minSafe = (leader.length + follower.length) / 2 + 1.2; // 1.2m buffer

          if (dist < minSafe) {
            // Adjust follower velocity to match leader and prevent overlap
            follower.targetVel.copy(leader.vel).multiplyScalar(0.8);
            // Push back slightly if merged
            const overlap = minSafe - dist;
            const pushDir = follower.pos.clone().sub(leader.pos).normalize().multiplyScalar(overlap * 0.1);
            follower.pos.add(pushDir);
          }
        }
      });

      // --- 4. Physics Update & Mesh Transform ---
      vehicleMesh.count = vehicleStates.size;
      shadowMesh.count = vehicleStates.size;

      let drawIdx = 0;
      vehicleStates.forEach(s => {
        // Smooth Velocity & Position (incorporate actualSpeedMultiplier)
        s.vel.lerp(s.targetVel, 0.2); 
        
        // Glide toward target with position damping
        const toTarget = s.targetPos.clone().sub(s.pos);
        if (toTarget.length() < SNAP_THRESHOLD) {
          s.pos.copy(s.targetPos);
        } else {
          // Combination of velocity glide and position correction (multiplied by speed factor)
          s.pos.add(s.vel.clone().multiplyScalar(delta * actualSpeedMultiplier));
          s.pos.lerp(s.targetPos, POSITION_SMOOTHING * actualSpeedMultiplier);
        }

        s.heading = shortestAngleLerp(s.heading, s.rawHeading, ROTATION_SMOOTHING);

        // Update Meshes
        dummy.position.copy(s.pos);
        dummy.rotation.set(0, s.heading, 0);
        dummy.scale.set(s.width, 1.2, s.length);
        dummy.updateMatrix();
        vehicleMesh.setMatrixAt(drawIdx, dummy.matrix);

        let vColor = s.color;
        if (s.hasSiren) {
          vColor = "#ffffff"; // Bright white for emergency
          const pulseColor = (s.id.includes("police")) ? sirenBlue : sirenRed;
          vColor = (now % 400 < 200) ? "#ffffff" : pulseColor;
          
          // Apply pulsing emissive intensity
          const emissiveInt = (Math.sin(now * 0.01) * 0.5 + 0.5) * 2.0;
          // In an InstancedMesh, we can't easily change per-instance material properties like emissiveIntensity
          // without a custom shader, but we can modulate the COLOR to simulate it.
        }
        vehicleMesh.setColorAt(drawIdx, new THREE.Color(vColor));

        // Shadow Mesh (slightly closer to road)
        dummy.position.set(s.pos.x, 0.01, s.pos.z);
        dummy.rotation.set(-Math.PI/2, 0, 0);
        dummy.scale.set(s.width * 1.15, s.length * 1.15, 1);
        dummy.updateMatrix();
        shadowMesh.setMatrixAt(drawIdx, dummy.matrix);

        drawIdx++;
      });

      vehicleMesh.instanceMatrix.needsUpdate = true;
      if (vehicleMesh.instanceColor) vehicleMesh.instanceColor.needsUpdate = true;
      shadowMesh.instanceMatrix.needsUpdate = true;

      controls.update();
      renderer.render(scene, camera);
    };

    animate();

    // 11. Resize Handler
    const handleResize = () => {
      if (!containerRef.current) return;
      const w = containerRef.current.clientWidth;
      const h = containerRef.current.clientHeight;
      renderer.setSize(w, h);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };
    window.addEventListener("resize", handleResize);

    // 12. Cleanup
    return () => {
      cancelAnimationFrame(animationId);
      window.removeEventListener("resize", handleResize);
      renderer.dispose();
      controls.dispose();
      if (containerRef.current) {
        containerRef.current.removeChild(renderer.domElement);
      }
      // Properly dispose materials and geometries
      scene.traverse(obj => {
        if (obj.isMesh) {
          obj.geometry.dispose();
          if (Array.isArray(obj.material)) obj.material.forEach(m => m.dispose());
          else obj.material.dispose();
        }
      });
    };
  }, []); // Run once on mount

  return (
    <div 
      ref={containerRef}
      className={`glass-panel relative overflow-hidden rounded-[2.5rem] border border-white/5 bg-slate-900/40 shadow-2xl ${className || "h-[680px]"}`}
    />
  );
}
