import { useEffect, useRef, useState } from "react";
import { getApiBaseUrl } from "../lib/backend";

const DIRECTIONS = [
  { key: "north", title: "North" },
  { key: "south", title: "South" },
  { key: "east", title: "East" },
  { key: "west", title: "West" },
];

const DEFAULT_STATS = {
  count: 0,
  uncertainCount: 0,
  emergencyDetected: false,
  emergencyLabels: [],
  ambulanceCueCounts: {},
  accidentDetected: false,
  accidentConfidence: 0,
  accidentMessage: "",
  queueLength: 0,
  densityPercent: 0,
  densityLevel: "low",
  signalPriorityValue: 0,
  signalPriorityReason: "Awaiting analysis.",
  vehicleTypes: {},
  sampledFrames: 0,
  videoSummary: null,
  sourceType: "camera",
  model: "yolov8n + ambulance yolo classifier",
  imageWidth: 1280,
  imageHeight: 720,
  lastUpdated: "waiting",
};

const DEFAULT_DECISION = {
  ready: false,
  recommended_green_direction: null,
  signal_states: { north: "red", south: "red", east: "red", west: "red" },
  cycle_plan: { green_duration_sec: 0, amber_duration_sec: 0, all_red_duration_sec: 0 },
  rationale: "Analyze at least one direction to recommend a safe junction phase plan.",
  controller: { phase_action: "idle", last_green_direction: null, elapsed_green_sec: 0, fairness_cycles: {}, starvation_watch: [] },
  approaches: {},
};

function createApproachState() {
  return DIRECTIONS.reduce((acc, direction) => {
    acc[direction.key] = {
      sourceMode: "camera",
      cameraState: "idle",
      error: "",
      detections: [],
      uncertainDetections: [],
      stats: { ...DEFAULT_STATS },
      selectedFile: null,
      selectedFileUrl: "",
      selectedFileKind: "",
      isAnalyzingUpload: false,
    };
    return acc;
  }, {});
}

function sortEntries(record) {
  return Object.entries(record || {}).sort((a, b) => Number(b[1]) - Number(a[1]));
}

function drawDetections({ overlay, target, items, sourceWidth, sourceHeight }) {
  if (!overlay || !target) return;
  overlay.width = target.clientWidth || 640;
  overlay.height = target.clientHeight || 360;
  const context = overlay.getContext("2d");
  if (!context) return;
  context.clearRect(0, 0, overlay.width, overlay.height);
  context.lineWidth = 2;
  context.font = '600 12px "Segoe UI", sans-serif';
  items.forEach((item) => {
    const scaleX = overlay.width / Math.max(sourceWidth, 1);
    const scaleY = overlay.height / Math.max(sourceHeight, 1);
    const x = item.box.x * scaleX;
    const y = item.box.y * scaleY;
    const width = item.box.width * scaleX;
    const height = item.box.height * scaleY;
    const label = `${item.label} ${(item.confidence * 100).toFixed(0)}%`;
    const palette = item.label === "ambulance"
      ? { stroke: "#22c55e", fill: "rgba(34,197,94,0.16)", badge: "#15803d", text: "#f0fdf4" }
      : { stroke: "#22d3ee", fill: "rgba(8,145,178,0.18)", badge: "#06b6d4", text: "#ecfeff" };
    context.strokeStyle = palette.stroke;
    context.fillStyle = palette.fill;
    context.fillRect(x, y, width, height);
    context.strokeRect(x, y, width, height);
    const textWidth = context.measureText(label).width;
    context.fillStyle = palette.badge;
    context.fillRect(x, Math.max(0, y - 24), textWidth + 16, 22);
    context.fillStyle = palette.text;
    context.fillText(label, x + 8, Math.max(15, y - 8));
  });
}

function clearCanvas(canvas) {
  const context = canvas?.getContext("2d");
  context?.clearRect(0, 0, canvas.width, canvas.height);
}

function badgeClass(signalState) {
  return signalState === "green"
    ? "border-emerald-300/30 bg-emerald-500/10 text-emerald-100"
    : "border-rose-300/20 bg-rose-500/10 text-rose-100";
}

export default function LiveCvPage() {
  const [layoutMode, setLayoutMode] = useState("single");
  const [approaches, setApproaches] = useState(() => createApproachState());
  const [decision, setDecision] = useState(DEFAULT_DECISION);
  const [decisionStatus, setDecisionStatus] = useState("Awaiting direction analysis.");
  const [decisionError, setDecisionError] = useState("");

  const approachesRef = useRef(approaches);
  const videoRefs = useRef({});
  const overlayRefs = useRef({});
  const imageRefs = useRef({});
  const uploadOverlayRefs = useRef({});
  const captureRefs = useRef({});
  const streamRefs = useRef({});
  const timerRefs = useRef({});
  const lockRefs = useRef({});
  const requestIdRef = useRef(0);

  useEffect(() => {
    approachesRef.current = approaches;
  }, [approaches]);

  useEffect(() => {
    return () => {
      DIRECTIONS.forEach(({ key }) => {
        if (timerRefs.current[key]) window.clearInterval(timerRefs.current[key]);
        if (streamRefs.current[key]) streamRefs.current[key].getTracks().forEach((track) => track.stop());
      });
      Object.values(approachesRef.current).forEach((approach) => {
        if (approach.selectedFileUrl) URL.revokeObjectURL(approach.selectedFileUrl);
      });
    };
  }, []);

  useEffect(() => {
    if (layoutMode === "single") {
      DIRECTIONS.slice(1).forEach(({ key }) => {
        releaseCamera(key);
        clearCanvas(overlayRefs.current[key]);
      });
      setApproaches((previous) => {
        const next = { ...previous };
        DIRECTIONS.slice(1).forEach(({ key }) => {
          if (previous[key].sourceMode === "camera") {
            next[key] = {
              ...previous[key],
              cameraState: "idle",
              error: "",
            };
          }
        });
        return next;
      });
    }
    void refreshDecision(approachesRef.current);
  }, [layoutMode]);

  useEffect(() => {
    DIRECTIONS.forEach(({ key }) => {
      const approach = approaches[key];
      if (approach.sourceMode === "camera") {
        drawDetections({
          overlay: overlayRefs.current[key],
          target: videoRefs.current[key],
          items: approach.detections,
          sourceWidth: approach.stats.imageWidth,
          sourceHeight: approach.stats.imageHeight,
        });
        clearCanvas(uploadOverlayRefs.current[key]);
      } else if (approach.selectedFileKind.startsWith("image/")) {
        drawDetections({
          overlay: uploadOverlayRefs.current[key],
          target: imageRefs.current[key],
          items: approach.detections,
          sourceWidth: approach.stats.imageWidth,
          sourceHeight: approach.stats.imageHeight,
        });
      } else {
        clearCanvas(uploadOverlayRefs.current[key]);
      }
    });
  }, [approaches]);

  const releaseCamera = (key) => {
    if (timerRefs.current[key]) {
      window.clearInterval(timerRefs.current[key]);
      timerRefs.current[key] = null;
    }
    if (streamRefs.current[key]) {
      streamRefs.current[key].getTracks().forEach((track) => track.stop());
      streamRefs.current[key] = null;
    }
    lockRefs.current[key] = false;
  };

  const refreshDecision = async (nextApproaches) => {
    const relevantDirections = layoutMode === "single" ? [DIRECTIONS[0]] : DIRECTIONS;
    const payload = {
      approaches: relevantDirections.reduce((acc, { key }) => {
        const stats = nextApproaches[key].stats;
        acc[key] = {
          vehicle_count: stats.count,
          uncertain_count: stats.uncertainCount,
          queue_length: stats.queueLength,
          density_percent: stats.densityPercent,
          density_level: stats.densityLevel,
          signal_priority_value: stats.signalPriorityValue,
          emergency_detected: stats.emergencyDetected,
          accident_detected: stats.accidentDetected,
        };
        return acc;
      }, {}),
    };
    const hasData = Object.values(payload.approaches).some(
      (item) =>
        item.vehicle_count > 0 ||
        item.uncertain_count > 0 ||
        item.queue_length > 0 ||
        item.density_percent > 0 ||
        item.signal_priority_value > 0 ||
        item.emergency_detected ||
        item.accident_detected,
    );
    if (!hasData) {
      setDecision(DEFAULT_DECISION);
      setDecisionStatus("Awaiting direction analysis.");
      setDecisionError("");
      return;
    }
    const requestId = ++requestIdRef.current;
    setDecisionStatus("Recomputing signal recommendation...");
    try {
      const response = await fetch(`${getApiBaseUrl()}/api/live-cv/junction/priority`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) throw new Error(`Junction decision failed with status ${response.status}.`);
      const result = await response.json();
      if (requestId !== requestIdRef.current) return;
      setDecision(result);
      setDecisionStatus(result.ready ? `Updated ${new Date().toLocaleTimeString()}` : "Awaiting direction analysis.");
      setDecisionError("");
    } catch (error) {
      if (requestId !== requestIdRef.current) return;
      setDecisionError(error instanceof Error ? error.message : "Could not compute junction priority.");
      setDecisionStatus("Signal recommendation unavailable.");
    }
  };

  const patchApproach = (key, updater) => {
    setApproaches((previous) => {
      const next = updater(previous);
      void refreshDecision(next);
      return next;
    });
  };

  const applyPayload = (key, payload) => {
    patchApproach(key, (previous) => ({
      ...previous,
      [key]: {
        ...previous[key],
        error: "",
        detections: Array.isArray(payload.detections) ? payload.detections : [],
        uncertainDetections: Array.isArray(payload.uncertain_detections) ? payload.uncertain_detections : [],
        stats: {
          count: payload.vehicle_count ?? 0,
          uncertainCount: payload.uncertain_count ?? 0,
          emergencyDetected: Boolean(payload.emergency_detected),
          emergencyLabels: Array.isArray(payload.emergency_labels) ? payload.emergency_labels : [],
          ambulanceCueCounts: payload.ambulance_cue_counts ?? {},
          accidentDetected: Boolean(payload.accident_detected),
          accidentConfidence: payload.accident_confidence ?? 0,
          accidentMessage: payload.accident_message ?? "",
          queueLength: payload.queue_length ?? 0,
          densityPercent: payload.density_percent ?? 0,
          densityLevel: payload.density_level ?? "low",
          signalPriorityValue: payload.signal_priority_value ?? 0,
          signalPriorityReason: payload.signal_priority_reason ?? "Awaiting analysis.",
          vehicleTypes: payload.vehicle_types ?? {},
          sampledFrames: payload.sampled_frames ?? 0,
          videoSummary: payload.video_summary ?? null,
          sourceType: payload.source_type ?? previous[key].sourceMode,
          model: payload.model ?? DEFAULT_STATS.model,
          imageWidth: payload.image?.width ?? DEFAULT_STATS.imageWidth,
          imageHeight: payload.image?.height ?? DEFAULT_STATS.imageHeight,
          lastUpdated: new Date().toLocaleTimeString(),
        },
      },
    }));
  };

  const postMedia = async (key, file, filename) => {
    const formData = new FormData();
    formData.append("media", file, filename);
    const response = await fetch(`${getApiBaseUrl()}/api/live-cv/detect`, { method: "POST", body: formData });
    if (!response.ok) throw new Error(`Detection failed with status ${response.status}.`);
    applyPayload(key, await response.json());
  };

  const detectFrame = async (key) => {
    const video = videoRefs.current[key];
    const canvas = captureRefs.current[key];
    if (!video || !canvas || lockRefs.current[key] || video.videoWidth === 0 || video.videoHeight === 0) return;
    lockRefs.current[key] = true;
    try {
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      const context = canvas.getContext("2d");
      if (!context) throw new Error("Could not access the capture canvas.");
      context.drawImage(video, 0, 0, canvas.width, canvas.height);
      const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.85));
      if (!blob) throw new Error("Could not create a frame snapshot.");
      await postMedia(key, blob, `${key}-frame.jpg`);
    } catch (error) {
      releaseCamera(key);
      patchApproach(key, (previous) => ({ ...previous, [key]: { ...previous[key], cameraState: "error", error: error instanceof Error ? error.message : "Vehicle detection failed." } }));
    } finally {
      lockRefs.current[key] = false;
    }
  };

  const startCamera = async (key) => {
    if (!navigator.mediaDevices?.getUserMedia) {
      patchApproach(key, (previous) => ({ ...previous, [key]: { ...previous[key], cameraState: "error", error: "This browser does not support webcam access." } }));
      return;
    }
    releaseCamera(key);
    patchApproach(key, (previous) => ({ ...previous, [key]: { ...previous[key], sourceMode: "camera", cameraState: "starting", error: "", detections: [], uncertainDetections: [], stats: { ...DEFAULT_STATS, lastUpdated: "starting" } } }));
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment", width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false });
      streamRefs.current[key] = stream;
      if (videoRefs.current[key]) {
        videoRefs.current[key].srcObject = stream;
        await videoRefs.current[key].play();
      }
      setApproaches((previous) => ({ ...previous, [key]: { ...previous[key], sourceMode: "camera", cameraState: "live", error: "" } }));
      void detectFrame(key);
      timerRefs.current[key] = window.setInterval(() => void detectFrame(key), 1600);
    } catch (error) {
      releaseCamera(key);
      patchApproach(key, (previous) => ({ ...previous, [key]: { ...previous[key], cameraState: "error", error: error instanceof Error ? error.message : "Could not start the camera." } }));
    }
  };

  const stopCamera = (key) => {
    releaseCamera(key);
    clearCanvas(overlayRefs.current[key]);
    patchApproach(key, (previous) => ({ ...previous, [key]: { ...previous[key], cameraState: "idle", error: "", detections: [], uncertainDetections: [], stats: { ...DEFAULT_STATS, lastUpdated: "stopped" } } }));
  };

  const changeSourceMode = (key, mode) => {
    if (mode === "upload") {
      releaseCamera(key);
      clearCanvas(overlayRefs.current[key]);
    }
    setApproaches((previous) => ({ ...previous, [key]: { ...previous[key], sourceMode: mode, cameraState: mode === "upload" ? "idle" : previous[key].cameraState, error: "" } }));
  };

  const handleFileChange = (key, event) => {
    const file = event.target.files?.[0] ?? null;
    releaseCamera(key);
    clearCanvas(overlayRefs.current[key]);
    patchApproach(key, (previous) => {
      if (previous[key].selectedFileUrl) URL.revokeObjectURL(previous[key].selectedFileUrl);
      return {
        ...previous,
        [key]: {
          ...previous[key],
          sourceMode: "upload",
          cameraState: "idle",
          error: "",
          selectedFile: file,
          selectedFileKind: file?.type ?? "",
          selectedFileUrl: file ? URL.createObjectURL(file) : "",
          detections: [],
          uncertainDetections: [],
          stats: { ...DEFAULT_STATS, lastUpdated: file ? "ready to analyze" : "waiting" },
        },
      };
    });
  };

  const analyzeUpload = async (key) => {
    const approach = approaches[key];
    if (!approach.selectedFile) {
      patchApproach(key, (previous) => ({ ...previous, [key]: { ...previous[key], error: "Choose an image or video first." } }));
      return;
    }
    setApproaches((previous) => ({ ...previous, [key]: { ...previous[key], sourceMode: "upload", isAnalyzingUpload: true, error: "" } }));
    try {
      await postMedia(key, approach.selectedFile, approach.selectedFile.name);
    } catch (error) {
      patchApproach(key, (previous) => ({ ...previous, [key]: { ...previous[key], error: error instanceof Error ? error.message : "Upload analysis failed." } }));
    } finally {
      setApproaches((previous) => ({ ...previous, [key]: { ...previous[key], isAnalyzingUpload: false } }));
    }
  };

  const activeDirections = layoutMode === "single" ? [DIRECTIONS[0]] : DIRECTIONS;
  const totalVehicles = activeDirections.reduce((sum, { key }) => sum + approaches[key].stats.count, 0);
  const greenDirection = decision.recommended_green_direction ? DIRECTIONS.find((direction) => direction.key === decision.recommended_green_direction)?.title : "Awaiting data";
  const activeDirectionLabel = layoutMode === "single" ? "Single Camera" : greenDirection;
  const analyzedCount = activeDirections.filter(({ key }) => approaches[key].stats.signalPriorityValue || approaches[key].stats.count || approaches[key].stats.uncertainCount).length;

  return (
    <div className="space-y-6">
      <section className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <div className="glass-panel rounded-[2rem] p-8">
          <p className="text-sm uppercase tracking-[0.3em] text-cyan-300">{layoutMode === "single" ? "Single Camera Live CV" : "4-Way Junction Live CV"}</p>
          <h2 className="mt-4 text-4xl font-semibold tracking-tight text-white">{layoutMode === "single" ? "Single camera traffic analysis for one live feed or one uploaded CCTV source." : "North, South, East, and West traffic feeds with one recommended green approach."}</h2>
          <p className="mt-5 max-w-3xl text-base leading-8 text-slate-300">{layoutMode === "single" ? "Use one camera or uploaded image/video when you want the original one-feed workflow. Switch to 4-way mode when you want per-direction signal planning for a real junction." : "Each direction can run from a live browser camera or uploaded CCTV image/video. The model scores traffic demand per approach, then the junction controller recommends one green approach while the other three stay red."}</p>
          <div className="mt-8 flex flex-wrap gap-3">
            <button type="button" onClick={() => setLayoutMode("single")} className={`rounded-full px-5 py-2.5 text-sm font-semibold transition ${layoutMode === "single" ? "bg-cyan-400 text-slate-950" : "border border-white/10 bg-white/5 text-white hover:bg-white/10"}`}>Single Camera</button>
            <button type="button" onClick={() => setLayoutMode("junction")} className={`rounded-full px-5 py-2.5 text-sm font-semibold transition ${layoutMode === "junction" ? "bg-cyan-400 text-slate-950" : "border border-white/10 bg-white/5 text-white hover:bg-white/10"}`}>4-Way Junction</button>
          </div>
          <div className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-3xl border border-cyan-400/20 bg-cyan-400/10 p-5"><p className="metric-label">{layoutMode === "single" ? "Analyzed Feeds" : "Analyzed Legs"}</p><p className="mt-3 text-2xl font-semibold text-white">{analyzedCount}/{activeDirections.length}</p></div>
            <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-5"><p className="metric-label">Total Vehicles</p><p className="mt-3 text-2xl font-semibold text-white">{totalVehicles}</p></div>
            <div className="rounded-3xl border border-emerald-400/20 bg-emerald-400/10 p-5"><p className="metric-label">{layoutMode === "single" ? "Active Feed" : "Green Now"}</p><p className="mt-3 text-2xl font-semibold text-white">{activeDirectionLabel}</p></div>
            <div className="rounded-3xl border border-amber-400/20 bg-amber-400/10 p-5"><p className="metric-label">{layoutMode === "single" ? "Priority Value" : "Cycle Plan"}</p><p className="mt-3 text-lg font-semibold text-white">{layoutMode === "single" ? activeDirections[0] && approaches[activeDirections[0].key].stats.signalPriorityValue : `${decision.cycle_plan.green_duration_sec}s / ${decision.cycle_plan.amber_duration_sec}s / ${decision.cycle_plan.all_red_duration_sec}s`}</p></div>
          </div>
          <div className="mt-6 rounded-3xl border border-white/10 bg-white/[0.04] px-5 py-4 text-sm text-slate-300">
            <p className="metric-label">{layoutMode === "single" ? "Single Feed Guidance" : "Signal Recommendation"}</p>
            <p className="mt-2 text-base font-semibold text-white">{layoutMode === "single" ? approaches[activeDirections[0].key].stats.signalPriorityReason : decision.rationale}</p>
            <p className="mt-2">Status: <span className="font-medium text-white">{decisionStatus}</span></p>
          </div>
        </div>

        <div className="glass-panel rounded-[2rem] p-8">
          <p className="panel-title">{layoutMode === "single" ? "Single Feed Control" : "Junction Controller"}</p>
          <div className="mt-5 grid gap-3 sm:grid-cols-2">
            {activeDirections.map(({ key, title }) => (
              <div key={key} className={`rounded-2xl border px-4 py-3 ${badgeClass(decision.signal_states[key] || "red")}`}>
                <div className="flex items-center justify-between gap-3">
                  <p className="font-semibold text-white">{layoutMode === "single" ? "Camera 1" : title}</p>
                  <span className="rounded-full border border-white/10 px-3 py-1 text-[11px] uppercase tracking-[0.22em] text-white">{layoutMode === "single" ? "active" : decision.signal_states[key] || "red"}</span>
                </div>
                <p className="mt-3 text-sm">{layoutMode === "single" ? "Priority value" : "Effective priority"}: <span className="font-semibold text-white">{layoutMode === "single" ? approaches[key].stats.signalPriorityValue : decision.approaches?.[key]?.effective_priority ?? 0}</span></p>
                {layoutMode === "junction" ? <p className="mt-2 text-sm">Fairness cycles: <span className="font-semibold text-white">{decision.controller?.fairness_cycles?.[key] ?? 0}</span></p> : null}
              </div>
            ))}
          </div>
          {layoutMode === "junction" ? (
            <div className="mt-5 rounded-3xl border border-white/10 bg-white/[0.04] px-5 py-4 text-sm text-slate-300">
              <p>Phase action: <span className="font-medium uppercase text-white">{String(decision.controller?.phase_action || "idle").replaceAll("_", " ")}</span></p>
              <p className="mt-2">Elapsed green: <span className="font-medium text-white">{decision.controller?.elapsed_green_sec ?? 0}s</span></p>
              <p className="mt-2">Starvation watch: <span className="font-medium text-white">{decision.controller?.starvation_watch?.length ? decision.controller.starvation_watch.join(", ") : "none"}</span></p>
            </div>
          ) : null}
          <p className="mt-5 text-sm leading-7 text-slate-300">{layoutMode === "single" ? "This is the original one-camera workflow. Use it for one roadside feed, one upload, or one operator test camera." : "Real-world note: in production, connect one fixed CCTV or RTSP stream per direction. Browser camera mode is for testing when four roadside feeds are not yet wired in."}</p>
          {decisionError ? <p className="mt-5 rounded-2xl border border-rose-400/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">{decisionError}</p> : null}
        </div>
      </section>

      <section className="grid gap-6 lg:grid-cols-2">
        {activeDirections.map(({ key, title }) => {
          const approach = approaches[key];
          const types = sortEntries(approach.stats.vehicleTypes).slice(0, 3);
          const signalState = decision.signal_states[key] || "red";
          return (
            <article key={key} className="glass-panel rounded-[2rem] p-6">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div><p className="text-sm uppercase tracking-[0.28em] text-cyan-300">{layoutMode === "single" ? "Single Camera" : `${title} Approach`}</p><h3 className="mt-3 text-2xl font-semibold text-white">{layoutMode === "single" ? "One camera live feed or upload analysis" : `${title} camera lane analysis`}</h3></div>
                <div className={`rounded-full border px-4 py-2 text-xs uppercase tracking-[0.24em] ${badgeClass(signalState)}`}>{layoutMode === "single" ? "active feed" : `${signalState} signal`}</div>
              </div>

              <div className="mt-6 flex flex-wrap gap-3">
                <button type="button" onClick={() => changeSourceMode(key, "camera")} className={`rounded-full px-4 py-2 text-sm font-semibold transition ${approach.sourceMode === "camera" ? "bg-cyan-400 text-slate-950" : "border border-white/10 bg-white/5 text-white hover:bg-white/10"}`}>Live Camera</button>
                <button type="button" onClick={() => changeSourceMode(key, "upload")} className={`rounded-full px-4 py-2 text-sm font-semibold transition ${approach.sourceMode === "upload" ? "bg-cyan-400 text-slate-950" : "border border-white/10 bg-white/5 text-white hover:bg-white/10"}`}>Upload Image / Video</button>
              </div>

              <div className="relative mt-6 overflow-hidden rounded-[1.75rem] border border-white/10 bg-slate-950">
                {approach.sourceMode === "camera" ? (
                  <>
                    <video ref={(node) => { videoRefs.current[key] = node; }} autoPlay muted playsInline className="aspect-video w-full object-cover" />
                    <canvas ref={(node) => { overlayRefs.current[key] = node; }} className="pointer-events-none absolute inset-0 h-full w-full" />
                    {approach.cameraState !== "live" ? <div className="absolute inset-0 flex items-center justify-center bg-slate-950/80 px-6 text-center"><div><p className="text-sm uppercase tracking-[0.3em] text-cyan-300">{layoutMode === "single" ? "Camera Feed" : `${title} Feed`}</p><p className="mt-4 text-xl font-semibold text-white">Camera preview will appear here</p></div></div> : null}
                  </>
                ) : approach.selectedFileUrl ? (
                  approach.selectedFileKind.startsWith("image/") ? (
                    <>
                      <img ref={(node) => { imageRefs.current[key] = node; }} src={approach.selectedFileUrl} alt={`${title} upload`} className="aspect-video w-full object-contain" />
                      <canvas ref={(node) => { uploadOverlayRefs.current[key] = node; }} className="pointer-events-none absolute inset-0 h-full w-full" />
                    </>
                  ) : <video src={approach.selectedFileUrl} controls className="aspect-video w-full object-contain" />
                ) : (
                  <div className="flex aspect-video items-center justify-center px-6 text-center"><div><p className="text-sm uppercase tracking-[0.3em] text-cyan-300">{layoutMode === "single" ? "Camera Upload" : `${title} Upload`}</p><p className="mt-4 text-xl font-semibold text-white">Choose CCTV image or video</p></div></div>
                )}
              </div>

              <canvas ref={(node) => { captureRefs.current[key] = node; }} className="hidden" />

              {approach.sourceMode === "camera" ? (
                <div className="mt-6 flex flex-wrap gap-3">
                  <button type="button" onClick={() => startCamera(key)} disabled={approach.cameraState === "live" || approach.cameraState === "starting"} className="rounded-full bg-cyan-400 px-5 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:bg-cyan-900/40 disabled:text-slate-400">Start Camera</button>
                  <button type="button" onClick={() => stopCamera(key)} disabled={approach.cameraState !== "live" && approach.cameraState !== "error"} className="rounded-full border border-white/10 bg-white/5 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-white/10 disabled:cursor-not-allowed disabled:text-slate-500">Stop Camera</button>
                </div>
              ) : (
                <div className="mt-6 space-y-4">
                  <label className="block rounded-3xl border border-dashed border-white/15 bg-white/[0.03] p-5 text-sm text-slate-300">
                    <span className="block text-white">Upload CCTV image or video</span>
                    <input type="file" accept="image/*,video/*" onChange={(event) => handleFileChange(key, event)} className="mt-4 block w-full text-sm text-slate-300" />
                  </label>
                  <button type="button" onClick={() => analyzeUpload(key)} disabled={!approach.selectedFile || approach.isAnalyzingUpload} className="rounded-full bg-cyan-400 px-5 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:bg-cyan-900/40 disabled:text-slate-400">{approach.isAnalyzingUpload ? "Analyzing..." : layoutMode === "single" ? "Analyze Camera" : `Analyze ${title}`}</button>
                </div>
              )}

              <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <div className="rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3"><p className="metric-label">Vehicles</p><p className="mt-2 text-xl font-semibold text-white">{approach.stats.count}</p></div>
                <div className="rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3"><p className="metric-label">Priority</p><p className="mt-2 text-xl font-semibold text-white">{approach.stats.signalPriorityValue}</p></div>
                <div className="rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3"><p className="metric-label">Queue</p><p className="mt-2 text-xl font-semibold text-white">{approach.stats.queueLength}</p></div>
                <div className="rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3"><p className="metric-label">Density</p><p className="mt-2 text-xl font-semibold text-white">{approach.stats.densityPercent.toFixed(1)}%</p></div>
              </div>

              <div className={`mt-6 rounded-3xl border px-5 py-4 text-sm ${approach.stats.accidentDetected ? "border-rose-400/30 bg-rose-500/10 text-rose-100" : "border-white/10 bg-white/[0.04] text-slate-300"}`}>
                <p className="metric-label">{approach.stats.accidentDetected ? "Accident Alert" : "Approach Guidance"}</p>
                <p className="mt-2 text-base font-semibold text-white">{approach.stats.accidentDetected ? approach.stats.accidentMessage || "Possible road accident detected." : approach.stats.signalPriorityReason}</p>
                <p className="mt-2">Last update: <span className="font-medium text-white">{approach.stats.lastUpdated}</span></p>
              </div>

              <div className="mt-6 grid gap-4 xl:grid-cols-[1fr_0.95fr]">
                <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-5 text-sm text-slate-300">
                  <p className="panel-title">Detected Vehicles</p>
                  {approach.detections.length ? approach.detections.slice(0, 4).map((item, index) => (
                    <div key={`${key}-${item.label}-${index}-${item.box.x}`} className="mt-3 rounded-2xl border border-white/10 bg-slate-950/30 px-4 py-3">
                      <p className="font-semibold capitalize text-white">{item.vehicle_type || item.label} | {item.position} | {item.confidence_level || "medium"}</p>
                      <p className="mt-1 text-slate-300">{item.clue || "Road vehicle detected."}</p>
                    </div>
                  )) : <p className="mt-4 text-slate-400">No clear front-facing vehicles have been scored yet.</p>}
                </div>

                <div className="space-y-4">
                  <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-5 text-sm text-slate-300">
                    <p className="panel-title">Type Summary</p>
                    {types.length ? types.map(([label, count]) => (
                      <div key={`${key}-${label}`} className="mt-3 rounded-2xl border border-white/10 bg-slate-950/30 px-4 py-3">
                        <span className="capitalize text-white">{label.replaceAll("_", " ")}</span><span className="ml-2 font-semibold text-cyan-200">{count}</span>
                      </div>
                    )) : <p className="mt-4 text-slate-400">Vehicle type counts will appear here after analysis.</p>}
                  </div>
                  <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-5 text-sm text-slate-300">
                    <p className="panel-title">Emergency Summary</p>
                    <p className="mt-3">Emergency labels: <span className="font-medium text-white">{approach.stats.emergencyLabels.length ? approach.stats.emergencyLabels.join(", ") : "none"}</span></p>
                    <p className="mt-2">Ambulance cues: <span className="font-medium text-white">{sortEntries(approach.stats.ambulanceCueCounts).length ? sortEntries(approach.stats.ambulanceCueCounts).map(([label, count]) => `${label} ${count}`).join(", ") : "none"}</span></p>
                    <p className="mt-2">Uncertain views: <span className="font-medium text-white">{approach.stats.uncertainCount}</span></p>
                    {approach.stats.videoSummary ? <p className="mt-2">Peak vehicles: <span className="font-medium text-white">{approach.stats.videoSummary.peak_vehicle_count}</span></p> : null}
                  </div>
                </div>
              </div>

              {approach.error ? <p className="mt-5 rounded-2xl border border-rose-400/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">{approach.error}</p> : null}
            </article>
          );
        })}
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <div className="glass-panel rounded-[2rem] p-6">
          <p className="panel-title">{layoutMode === "single" ? "Single Camera Notes" : "Real-World Approach"}</p>
          <div className="mt-5 space-y-3 text-sm leading-7 text-slate-300">
            <p>{layoutMode === "single" ? "Mount one fixed camera with a stable view of the stop line and upstream queue." : "Mount one fixed camera per approach with a stable view of the stop line and the upstream queue."}</p>
            <p>{layoutMode === "single" ? "Use this mode when you only want one roadside feed, one uploaded test video, or one operator camera." : "Keep one approach green at a time, then insert amber and all-red clearance before the next phase starts."}</p>
            <p>Use emergency detections to override normal demand, and send accident detections to operators for confirmation and incident handling.</p>
            <p>Use uploaded footage to tune the model before the live roadside feeds are integrated.</p>
          </div>
        </div>
        <div className="glass-panel rounded-[2rem] p-6">
          <p className="panel-title">{layoutMode === "single" ? "Camera Summary" : "Operator Summary"}</p>
          <div className="mt-5 space-y-4 text-sm leading-7 text-slate-300">
            {activeDirections.map(({ key, title }) => <p key={`summary-${key}`}>{layoutMode === "single" ? "Camera 1" : title}: <span className="font-medium text-white">{approaches[key].stats.count} vehicles | priority {approaches[key].stats.signalPriorityValue}</span></p>)}
            <p>{layoutMode === "single" ? "Current active feed" : "Recommended active leg"}: <span className="font-medium text-white">{activeDirectionLabel}</span></p>
            <p>{layoutMode === "single" ? "Switch to 4-way mode any time to compare all four directions together." : "Other legs stay red until the green phase and clearance times finish."}</p>
          </div>
        </div>
      </section>
    </div>
  );
}
