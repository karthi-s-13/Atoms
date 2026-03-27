import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls";

// ─── World constants ──────────────────────────────────────────────────────────
const R   = 50;          // road half-length
const IR  = 8.5;         // intersection radius (half-width)
const LI  = 2.8;         // inner lane offset (widened)
const LO  = 5.0;         // outer lane offset (widened)
const Y   = 0.22;        // vehicle ride height
const SL  = R - IR - 1.5;  // stop-line progress

// ─── Vehicle geometry constants ────────────────────────────────────────────────
const VEH_LEN  = 3.0;    // all vehicles same length
const VEH_W    = 1.6;    // all vehicles same width
const VEH_H    = 1.0;    // all vehicles same height

// ─── Physics constants ────────────────────────────────────────────────────────
const MAX_V    = 50;
const SAFE_GAP = VEH_LEN + 0.8;  // bumper-to-bumper gap = vehicle length + buffer
const SPD_MAX  = 10.0;
const SPD_EMG  = 17.0;
const BRAKE_D  = 20.0;
const MAX_INTR = 3;

// ─── 2-Minute demo timeline ───────────────────────────────────────────────────
const DEMO_LOOP = 122;
const DEMO_TL   = [
  { time:   0, label: "LIGHT TRAFFIC",      traffic: 0.12, emerg: false },
  { time:  20, label: "MODERATE TRAFFIC",   traffic: 0.38, emerg: false },
  { time:  40, label: "HEAVY TRAFFIC",      traffic: 0.65, emerg: false },
  { time:  60, label: "CONGESTION",         traffic: 0.90, emerg: false },
  { time:  80, label: "EMERGENCY PRIORITY", traffic: 0.50, emerg: true  },
  { time: 100, label: "CLEARANCE",          traffic: 0.20, emerg: false },
  { time: 110, label: "BALANCED FLOW",      traffic: 0.36, emerg: false },
];

const PALETTE = ["#e2e8f0","#94a3b8","#f97316","#06b6d4","#8b5cf6","#10b981","#f59e0b","#84cc16","#ec4899","#3b82f6"];

// ─── Path utilities ───────────────────────────────────────────────────────────
function qbez(p0, p1, p2, t) {
  const u = 1 - t;
  return { x: u*u*p0.x + 2*u*t*p1.x + t*t*p2.x, z: u*u*p0.z + 2*u*t*p1.z + t*t*p2.z };
}

function buildPath(segs, nb = 16) {
  const raw = [];
  for (const s of segs) {
    if (s.type === "line") { raw.push(s.p0, s.p1); }
    else { for (let i = 0; i <= nb; i++) raw.push(qbez(s.p0, s.p1, s.p2, i/nb)); }
  }
  const pts = [raw[0]];
  for (let i = 1; i < raw.length; i++) {
    const p = raw[i], q = pts[pts.length-1];
    if (Math.hypot(p.x-q.x, p.z-q.z) > 0.01) pts.push(p);
  }
  const cum = [0];
  for (let i = 1; i < pts.length; i++)
    cum.push(cum[i-1] + Math.hypot(pts[i].x-pts[i-1].x, pts[i].z-pts[i-1].z));
  return { pts, cum, len: cum[cum.length-1] };
}

function samplePath(path, prog) {
  const { pts, cum } = path;
  const d = Math.max(0, Math.min(prog, path.len));
  let lo = 0, hi = cum.length - 2;
  while (lo < hi) { const m = (lo+hi)>>1; if (cum[m+1] <= d) lo=m+1; else hi=m; }
  const t = cum[lo+1] > cum[lo] ? (d-cum[lo])/(cum[lo+1]-cum[lo]) : 0;
  const a = pts[lo], b = pts[lo+1]||a;
  return { x: a.x+(b.x-a.x)*t, z: a.z+(b.z-a.z)*t, heading: Math.atan2(b.x-a.x, b.z-a.z) };
}

// ─── Route builder ────────────────────────────────────────────────────────────
// Builds a path for a given approach + turn + lane offset
function buildRoute(approach, turn, off) {
  // off = lane center offset from road center-line
  // For N/S approaches: offset is along X axis
  // For E/W approaches: offset is along Z axis
  const H = R;
  if (approach === "N") {
    if (turn === "straight") return buildPath([{ type:"line", p0:{x:off,z:-H}, p1:{x:off,z:H} }]);
    if (turn === "right")    return buildPath([
      { type:"line", p0:{x:LO,z:-H},  p1:{x:LO,z:-IR} },
      { type:"bez",  p0:{x:LO,z:-IR}, p1:{x:LO,z:LI},  p2:{x:-IR,z:LI} },
      { type:"line", p0:{x:-IR,z:LI}, p1:{x:-H,z:LI} },
    ]);
    return buildPath([   // left
      { type:"line", p0:{x:LI,z:-H},  p1:{x:LI,z:-IR} },
      { type:"bez",  p0:{x:LI,z:-IR}, p1:{x:LI,z:-LO}, p2:{x:IR,z:-LO} },
      { type:"line", p0:{x:IR,z:-LO}, p1:{x:H,z:-LO} },
    ]);
  }
  if (approach === "S") {
    if (turn === "straight") return buildPath([{ type:"line", p0:{x:-off,z:H}, p1:{x:-off,z:-H} }]);
    if (turn === "right")    return buildPath([
      { type:"line", p0:{x:-LO,z:H},  p1:{x:-LO,z:IR} },
      { type:"bez",  p0:{x:-LO,z:IR}, p1:{x:-LO,z:-LI}, p2:{x:IR,z:-LI} },
      { type:"line", p0:{x:IR,z:-LI}, p1:{x:H,z:-LI} },
    ]);
    return buildPath([
      { type:"line", p0:{x:-LI,z:H},  p1:{x:-LI,z:IR} },
      { type:"bez",  p0:{x:-LI,z:IR}, p1:{x:-LI,z:LO}, p2:{x:-IR,z:LO} },
      { type:"line", p0:{x:-IR,z:LO}, p1:{x:-H,z:LO} },
    ]);
  }
  if (approach === "E") {
    if (turn === "straight") return buildPath([{ type:"line", p0:{x:H,z:off},  p1:{x:-H,z:off} }]);
    if (turn === "right")    return buildPath([
      { type:"line", p0:{x:H,z:LO},   p1:{x:IR,z:LO} },
      { type:"bez",  p0:{x:IR,z:LO},  p1:{x:LI,z:LO}, p2:{x:LI,z:IR} },
      { type:"line", p0:{x:LI,z:IR},  p1:{x:LI,z:H} },
    ]);
    return buildPath([
      { type:"line", p0:{x:H,z:LI},   p1:{x:IR,z:LI} },
      { type:"bez",  p0:{x:IR,z:LI},  p1:{x:-LO,z:LI}, p2:{x:-LO,z:-IR} },
      { type:"line", p0:{x:-LO,z:-IR},p1:{x:-LO,z:-H} },
    ]);
  }
  // W
  if (turn === "straight") return buildPath([{ type:"line", p0:{x:-H,z:-off}, p1:{x:H,z:-off} }]);
  if (turn === "right")    return buildPath([
    { type:"line", p0:{x:-H,z:-LO},  p1:{x:-IR,z:-LO} },
    { type:"bez",  p0:{x:-IR,z:-LO}, p1:{x:-LI,z:-LO}, p2:{x:-LI,z:-IR} },
    { type:"line", p0:{x:-LI,z:-IR}, p1:{x:-LI,z:-H} },
  ]);
  return buildPath([
    { type:"line", p0:{x:-H,z:-LI},  p1:{x:-IR,z:-LI} },
    { type:"bez",  p0:{x:-IR,z:-LI}, p1:{x:LO,z:-LI}, p2:{x:LO,z:IR} },
    { type:"line", p0:{x:LO,z:IR},   p1:{x:LO,z:H} },
  ]);
}

// Pre-compute all routes keyed by approach → lane → turn
// LEFT lane  (inner, LI offset): straight + left
// RIGHT lane (outer, LO offset): straight + right
const ROUTES = {};
for (const a of ["N","S","E","W"]) {
  ROUTES[a] = {
    LEFT:  {
      straight: buildRoute(a, "straight", LI),
      left:     buildRoute(a, "left",     LI),
    },
    RIGHT: {
      straight: buildRoute(a, "straight", LO),
      right:    buildRoute(a, "right",    LO),
    },
  };
}

// ─── Vehicle ──────────────────────────────────────────────────────────────────
let _VID = 0;
class Veh {
  constructor(approach, isEmerg = false) {
    this.id       = ++_VID;
    this.approach = approach;
    this.isEmerg  = isEmerg;

    // Assign lane: 50/50 LEFT (inner) vs RIGHT (outer)
    this.lane = Math.random() < 0.5 ? "LEFT" : "RIGHT";

    // Constrain turn by lane: LEFT→straight/left, RIGHT→straight/right
    if (this.lane === "LEFT") {
      this.turn = Math.random() < 0.65 ? "straight" : "left";
    } else {
      this.turn = Math.random() < 0.65 ? "straight" : "right";
    }

    this.path    = ROUTES[approach][this.lane][this.turn];
    this.progress= 0;
    this.pos     = samplePath(this.path, 0);
    this.baseSpd = isEmerg ? SPD_EMG : SPD_MAX * (0.80 + Math.random()*0.20);
    this.curSpd  = 0;
    this.waited  = 0;
    this.inInter = false;
    // Standardized size
    this.length  = isEmerg ? VEH_LEN * 1.4 : VEH_LEN;
    this.width   = isEmerg ? VEH_W   * 1.1 : VEH_W;
    this.color   = isEmerg ? "#ffffff" : PALETTE[Math.floor(Math.random()*PALETTE.length)];
  }
}

// ─── Single-Direction Adaptive Signal Controller ──────────────────────────────
const YELLOW_DUR  = 2.5;
const ALLRED_DUR  = 1.5;
const DIRS_LIST   = ["N","S","E","W"];
const DIR_FULL    = { N:"NORTH", S:"SOUTH", E:"EAST", W:"WEST" };

function makeCtrl() {
  return {
    activeDir:  "N",
    nextDir:    null,
    state:      "GREEN",   // GREEN | YELLOW | ALL_RED
    timer:      0,
    greenDur:   8,
    starvation: { N:0, S:0, E:0, W:0 },
  };
}

function scoreDir(dir, vehicles, starvation) {
  let q = 0, wSum = 0, emg = 0, arrivals = 0;
  for (const v of vehicles) {
    if (v.approach !== dir) continue;
    arrivals++;
    if (v.progress < SL + 3 && v.curSpd < 0.8) { q++; wSum += v.waited; }
    if (v.isEmerg) emg++;
  }
  const avgW = q > 0 ? wSum / q : 0;
  return q*1.0 + avgW*1.5 + Math.min(arrivals/5,1)*1.2 + emg*4.0 + starvation[dir]*0.4;
}

function adaptGreen(dir, vehicles) {
  let q = 0;
  for (const v of vehicles) if (v.approach === dir && v.progress < SL) q++;
  return Math.min(25, Math.max(6, 6 + q * 1.5));
}

function tickCtrl(ctrl, dt, vehicles, forceDir) {
  ctrl.timer += dt;

  // starvation — dirs not active accumulate
  for (const d of DIRS_LIST) { if (d !== ctrl.activeDir) ctrl.starvation[d] += dt; }

  if (ctrl.state === "GREEN") {
    // Emergency override
    if (forceDir && ctrl.activeDir !== forceDir) {
      ctrl.nextDir = forceDir;
      ctrl.state   = "YELLOW"; ctrl.timer = 0;
      return;
    }
    // Check green expiry
    if (ctrl.timer >= ctrl.greenDur) {
      // Pick best next direction
      let best = -Infinity, bestDir = null;
      for (const d of DIRS_LIST) {
        if (d === ctrl.activeDir) continue;
        const s = scoreDir(d, vehicles, ctrl.starvation);
        if (s > best) { best = s; bestDir = d; }
      }
      ctrl.nextDir = bestDir || DIRS_LIST[(DIRS_LIST.indexOf(ctrl.activeDir)+1)%4];
      ctrl.state   = "YELLOW"; ctrl.timer = 0;
    }
  }
  else if (ctrl.state === "YELLOW") {
    if (ctrl.timer >= YELLOW_DUR) { ctrl.state = "ALL_RED"; ctrl.timer = 0; }
  }
  else if (ctrl.state === "ALL_RED") {
    if (ctrl.timer >= ALLRED_DUR) {
      ctrl.activeDir = ctrl.nextDir;
      ctrl.starvation[ctrl.activeDir] = 0;
      ctrl.state     = "GREEN"; ctrl.timer = 0;
      ctrl.greenDur  = adaptGreen(ctrl.activeDir, vehicles);
    }
  }
}

function getSignals(ctrl) {
  const s = {};
  for (const d of DIRS_LIST) {
    const full = DIR_FULL[d];
    if (ctrl.state === "ALL_RED") { s[full] = "RED"; }
    else if (ctrl.state === "YELLOW" && d === ctrl.activeDir) { s[full] = "YELLOW"; }
    else if (ctrl.state === "GREEN"  && d === ctrl.activeDir) { s[full] = "GREEN"; }
    else { s[full] = "RED"; }
  }
  return s;
}

function canMove(approach, ctrl) {
  return ctrl.state === "GREEN" && ctrl.activeDir === approach;
}

// ─── Component ────────────────────────────────────────────────────────────────
export default function DemoCanvas({ className = "", onStatsUpdate, onSignalChange }) {
  const containerRef = useRef(null);
  const onSignalChangeRef = useRef(onSignalChange);
  const lastSignalKeyRef = useRef("");
  
  useEffect(() => {
    onSignalChangeRef.current = onSignalChange;
  }, [onSignalChange]);

  useEffect(() => {
    const el = containerRef.current; if (!el) return;

    // ── Scene ──
    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#070d18");
    scene.fog = new THREE.Fog("#070d18", 48, 160);

    const W = el.clientWidth || 800, H = el.clientHeight || 600;
    const camera = new THREE.PerspectiveCamera(50, W/H, 0.1, 400);
    camera.position.set(20, 26, 20); camera.lookAt(0,0,0);

    const renderer = new THREE.WebGLRenderer({ antialias:true, powerPreference:"high-performance" });
    renderer.setSize(W, H); renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    el.appendChild(renderer.domElement);

    const orbit = new OrbitControls(camera, renderer.domElement);
    orbit.enablePan=false; orbit.maxPolarAngle=Math.PI/2.12;
    orbit.minDistance=12; orbit.maxDistance=110;

    // ── Lights ──
    scene.add(new THREE.AmbientLight(0xffffff, 0.9));
    const sun = new THREE.DirectionalLight("#ffffff", 0.7);
    sun.position.set(30, 60, 30); scene.add(sun);
    const fill = new THREE.PointLight("#4f46e5", 0.3);
    fill.position.set(-16, 12, -16); scene.add(fill);

    // ── Road ──
    const pg = new THREE.PlaneGeometry(1,1);
    const addPlane = (mat,sx,sz,y=0,px=0,pz=0) => {
      const m=new THREE.Mesh(pg,mat); m.rotation.x=-Math.PI/2;
      m.scale.set(sx,sz,1); m.position.set(px,y,pz); scene.add(m);
    };
    const matRoad  = new THREE.MeshStandardMaterial({ color:"#2f2f2f", roughness:0.85 });
    const matInter = new THREE.MeshStandardMaterial({ color:"#1f1f1f", roughness:0.7  });
    const matDiv   = new THREE.MeshBasicMaterial({ color:"#fbbf24" });
    const matDash  = new THREE.MeshBasicMaterial({ color:"#e2e8f0", transparent:true, opacity:0.65 });
    const matStop  = new THREE.MeshBasicMaterial({ color:"#ffffff", transparent:true, opacity:0.9  });

    const laneW = (LO+LI*0.6)*2+1;
    addPlane(matRoad,  R*2, laneW);
    addPlane(matRoad,  laneW, R*2);
    addPlane(matInter, laneW, laneW, 0.005);
    addPlane(matDiv,   R*2, 0.18, 0.01);
    addPlane(matDiv,   0.18, R*2, 0.01);

    const mid = (LI+LO)/2;
    for (let z=-R; z<R; z+=7) {
      for (const x of [mid,-mid]) { const m=new THREE.Mesh(pg,matDash); m.rotation.x=-Math.PI/2; m.scale.set(0.15,3,1); m.position.set(x,0.015,z+1.5); scene.add(m); }
    }
    for (let x=-R; x<R; x+=7) {
      for (const z of [mid,-mid]) { const m=new THREE.Mesh(pg,matDash); m.rotation.x=-Math.PI/2; m.scale.set(3,0.15,1); m.position.set(x+1.5,0.015,z); scene.add(m); }
    }

    const SLO = IR + 1.5; // stop-line offset from center
    addPlane(matStop, laneW, 0.28, 0.02,  0, -SLO);
    addPlane(matStop, laneW, 0.28, 0.02,  0,  SLO);
    addPlane(matStop, 0.28, laneW, 0.02,  SLO,  0);
    addPlane(matStop, 0.28, laneW, 0.02, -SLO,  0);

    // ── Traffic lights ──
    const sigMats = {};
    const DIRS = ["NORTH","SOUTH","EAST","WEST"];
    const mkL = col => new THREE.MeshStandardMaterial({ color:"#080808", emissive:col, emissiveIntensity:0 });
    const cornerPos = {
      NORTH:[ LO+0.9, 0, -(SLO+1.2)], SOUTH:[-(LO+0.9), 0, SLO+1.2],
      EAST: [ SLO+1.2, 0,-(LO+0.9)],  WEST: [-(SLO+1.2), 0, LO+0.9],
    };
    DIRS.forEach(dir => {
      const g=new THREE.Group(); g.position.set(...cornerPos[dir]); scene.add(g);
      const pole=new THREE.Mesh(new THREE.CylinderGeometry(0.1,0.13,7,8), new THREE.MeshStandardMaterial({color:"#334155",metalness:0.6}));
      pole.position.y=3.5; g.add(pole);
      const box=new THREE.Mesh(new THREE.BoxGeometry(0.85,2.5,0.62), new THREE.MeshStandardMaterial({color:"#1e293b"}));
      box.position.set(0,6.5,0.32); g.add(box);
      const rM=mkL("#ff0a00"), yM=mkL("#ffaa00"), gM=mkL("#00dd44");
      [[0.75,rM],[0,yM],[-0.75,gM]].forEach(([dy,mat])=>{
        const l=new THREE.Mesh(new THREE.CircleGeometry(0.24,12),mat); l.position.set(0,6.5+dy,0.63); g.add(l);
      });
      sigMats[dir]={r:rM,y:yM,g:gM};
    });

    const applySignals = (signals) => {
      DIRS.forEach(d => {
        const st=signals[d]||"RED", m=sigMats[d];
        m.r.emissiveIntensity = st==="RED"    ? 3 : 0.05;
        m.y.emissiveIntensity = st==="YELLOW" ? 3 : 0.05;
        m.g.emissiveIntensity = st==="GREEN"  ? 3 : 0.05;
        m.r.color.set(st==="RED"    ?"#ff0a00":"#180000");
        m.y.color.set(st==="YELLOW" ?"#ffaa00":"#181000");
        m.g.color.set(st==="GREEN"  ?"#00dd44":"#001808");
      });
    };

    // ── Instanced meshes ──
    const vGeo = new THREE.BoxGeometry(1,1,1);
    const vMat = new THREE.MeshStandardMaterial({ metalness:0.1, roughness:0.35, emissive:"#fff", emissiveIntensity:0.1 });
    const vMesh = new THREE.InstancedMesh(vGeo, vMat, MAX_V); vMesh.count=0; scene.add(vMesh);
    const sMesh = new THREE.InstancedMesh(new THREE.PlaneGeometry(1,1), new THREE.MeshBasicMaterial({color:"#000",transparent:true,opacity:0.18}), MAX_V);
    sMesh.count=0; scene.add(sMesh);

    // ── Sim state ──
    let vehicles=[], ctrl=makeCtrl(), signals={};
    let demoTime=0, spawnTimer=0, curScn=DEMO_TL[0], spawnedEmerg=false;
    let throughput=0, tputTimer=0, lastTput=0, statsTimer=0;
    let lastT=performance.now(), animId;
    const dummy=new THREE.Object3D();

    // ── Loop ──
    const animate = () => {
      animId = requestAnimationFrame(animate);
      const now = performance.now();
      const dt  = Math.min((now-lastT)/1000, 0.033); lastT=now;

      // Demo timeline
      demoTime += dt;
      if (demoTime > DEMO_LOOP) { demoTime=0; vehicles=[]; spawnedEmerg=false; ctrl=makeCtrl(); throughput=0; }
      let scn=DEMO_TL[0];
      for (let i=DEMO_TL.length-1; i>=0; i--) { if (demoTime>=DEMO_TL[i].time){scn=DEMO_TL[i];break;} }
      if (curScn.label!==scn.label) { curScn=scn; spawnedEmerg=false; }

      // Signal tick
      const forceDir = curScn.emerg ? "N" : null;
      tickCtrl(ctrl, dt, vehicles, forceDir);
      signals = getSignals(ctrl);
      applySignals(signals);

      // Report signal change to parent
      const sigKey = `${ctrl.activeDir}_${ctrl.state}`;
      if (sigKey !== lastSignalKeyRef.current) {
        lastSignalKeyRef.current = sigKey;
        if (onSignalChangeRef.current) {
          onSignalChangeRef.current({
            activeDirection: DIR_FULL[ctrl.activeDir],
            state: ctrl.state,
            command: ctrl.state === "GREEN" ? `${DIR_FULL[ctrl.activeDir]}_GREEN` : 
                     ctrl.state === "YELLOW" ? `${DIR_FULL[ctrl.activeDir]}_YELLOW` : "ALL_RED"
          });
        }
      }

      if (curScn.emerg && !spawnedEmerg) {
        const v = new Veh("N", true);
        v.lane = "RIGHT"; v.turn = "straight";
        v.path = ROUTES.N.RIGHT.straight;
        v.pos  = samplePath(v.path, 0);
        vehicles.push(v); spawnedEmerg = true;
      }

      // Density spawn
      spawnTimer -= dt;
      const target = Math.round(curScn.traffic * MAX_V);
      if (spawnTimer <= 0 && vehicles.length < target) {
        const app = ["N","S","E","W"][Math.floor(Math.random()*4)];
        const inApp = vehicles.filter(v=>v.approach===app);
        if (!inApp.some(v=>v.progress < SAFE_GAP*2.5+5)) vehicles.push(new Veh(app));
        spawnTimer = 0.5 + Math.random()*(1.1*(1-curScn.traffic*0.65));
      }

      // ── Physics ──
      // ── Physics ──
      // Group by LANE KEY: approach + lane ("LEFT"|"RIGHT")
      // Vehicles in the same approach + lane form one physical queue
      const byLane = {};
      for (const v of vehicles) {
        const k = `${v.approach}_${v.lane}`;
        if (!byLane[k]) byLane[k] = [];
        byLane[k].push(v);
      }

      // Intersection occupancy
      const iS=SL, iE=SL+SLO*2.4;
      let inInter=0;
      for (const v of vehicles) { v.inInter=v.progress>iS&&v.progress<iE; if(v.inInter) inInter++; }

      for (const key of Object.keys(byLane)) {
        const grp = byLane[key];
        grp.sort((a,b)=>a.progress-b.progress);

        const app   = grp[0].approach;
        const green = canMove(app, ctrl);

        for (let i=0; i<grp.length; i++) {
          const v = grp[i];
          const leader = i+1 < grp.length ? grp[i+1] : null;

          // committed → never stop in intersection
          const committed = v.inInter || v.progress > iE;
          let tSpd = v.baseSpd;

          if (!committed && !v.isEmerg) {
            if (!green) {
              // Brake smoothly toward stop line
              const d = SL - v.progress;
              if (d > 0 && d <= BRAKE_D) tSpd = v.baseSpd * Math.pow(d/BRAKE_D, 1.6);
              if (d <= 0.3) tSpd = 0;
            } else {
              // Green but intersection at capacity
              if (v.progress >= SL-1.5 && inInter >= MAX_INTR) tSpd = 0;
            }
          }

          // Leader following
          if (leader) {
            const gap = leader.progress - v.progress - v.length;
            if (gap < SAFE_GAP) tSpd = Math.min(tSpd, leader.curSpd*0.4);
            else if (gap < SAFE_GAP*2.5) tSpd = Math.min(tSpd, leader.curSpd*(gap/(SAFE_GAP*2.5)));
          }

          tSpd = Math.max(0, tSpd);
          v.curSpd += ((tSpd<v.curSpd?0.22:0.10)) * (tSpd-v.curSpd);
          v.curSpd  = Math.max(0, Math.min(v.curSpd, v.baseSpd));
          v.waited  = v.curSpd<0.4 ? v.waited+dt : Math.max(0,v.waited-dt*0.5);

          let np = v.progress + v.curSpd * dt;
          // Pre-advance clamp: never pass leader
          if (leader) np = Math.min(np, leader.progress - v.length - SAFE_GAP);
          v.progress = Math.max(v.progress, np);

          // Hard post-update enforcement: guarantee no overlap
          if (leader && leader.progress - v.progress - v.length < SAFE_GAP) {
            v.progress = leader.progress - v.length - SAFE_GAP;
            v.curSpd   = Math.min(v.curSpd, leader.curSpd);
          }

          v.pos = samplePath(v.path, v.progress);
        }
      }

      // Throughput & despawn
      tputTimer+=dt;
      if (tputTimer>=1) { lastTput=throughput; throughput=0; tputTimer=0; }
      vehicles=vehicles.filter(v=>{ if(v.progress>=v.path.len){throughput++;return false;} return true; });

      // Stats
      statsTimer+=dt;
      if (statsTimer>=0.12 && onStatsUpdate) {
        statsTimer=0;
        const wSum=vehicles.reduce((s,v)=>s+v.waited,0);
        const dir=DIR_FULL[ctrl.activeDir]||"NORTH";
        onStatsUpdate({
          phase:            curScn.label,
          demoTime,
          signals,
          vehicles:         vehicles.length,
          avgWait:          vehicles.length>0?wSum/vehicles.length:0,
          throughput:       lastTput,
          queuePressure:    vehicles.length/MAX_V,
          emergencyVehicles:vehicles.filter(v=>v.isEmerg).length,
          activeDirection:  dir,
          signalPhase:      `${dir} GREEN • ${ctrl.state}`,
          signalState:      ctrl.state,
        });
      }

      // ── Render ──
      const toR=vehicles.slice(0,MAX_V);
      vMesh.count=toR.length; sMesh.count=toR.length;
      for (let i=0; i<toR.length; i++) {
        const v=toR[i];
        dummy.position.set(v.pos.x, Y + VEH_H * 0.5 + 0.02, v.pos.z);
        dummy.rotation.set(0, v.pos.heading, 0);
        dummy.scale.set(v.width, VEH_H, v.length);
        dummy.updateMatrix(); vMesh.setMatrixAt(i, dummy.matrix);
        let col=v.color;
        if (v.isEmerg) col=now%200<100?"#ff2222":"#2222ff";
        vMesh.setColorAt(i,new THREE.Color(col));

        dummy.position.set(v.pos.x, 0.007, v.pos.z);
        dummy.rotation.set(-Math.PI/2, 0, v.pos.heading);
        dummy.scale.set(v.width * 1.1, v.length * 1.05, 1);
        dummy.updateMatrix(); sMesh.setMatrixAt(i, dummy.matrix);
      }
      vMesh.instanceMatrix.needsUpdate=true;
      if(vMesh.instanceColor) vMesh.instanceColor.needsUpdate=true;
      sMesh.instanceMatrix.needsUpdate=true;
      orbit.update(); renderer.render(scene,camera);
    };

    animate();

    const onResize=()=>{ const w=el.clientWidth,h=el.clientHeight; renderer.setSize(w,h); camera.aspect=w/h; camera.updateProjectionMatrix(); };
    window.addEventListener("resize",onResize);
    return ()=>{ cancelAnimationFrame(animId); window.removeEventListener("resize",onResize); orbit.dispose(); renderer.dispose(); if(el.contains(renderer.domElement)) el.removeChild(renderer.domElement); };
  }, []);

  return <div ref={containerRef} className={`w-full h-full bg-[#070d18] ${className}`} />;
}
