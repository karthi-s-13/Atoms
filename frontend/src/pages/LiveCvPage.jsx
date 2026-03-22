import { useEffect, useRef, useState } from "react";

const junctionCards = [
  {
    key: "four-way",
    title: "4 Way Junction Camera",
    status: "Queued",
    copy: "Reserved for a multi-lane intersection feed with separate approach analytics.",
  },
  {
    key: "three-way",
    title: "3 Way Junction Camera",
    status: "Queued",
    copy: "Reserved for T-junction monitoring with directional congestion profiling.",
  },
  {
    key: "two-way",
    title: "2 Way Junction Camera",
    status: "Queued",
    copy: "Reserved for corridor traffic capture and lane-level vehicle counting.",
  },
];

const DEFAULT_STATS = {
  count: 0,
  uncertainCount: 0,
  emergencyCount: 0,
  emergencyDetected: false,
  emergencyLabels: [],
  ambulanceCueCounts: {},
  positionsBreakdown: {},
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

function getApiBaseUrl() {
  if (typeof window === "undefined") {
    return "http://localhost:8000";
  }

  const protocol = window.location.protocol === "https:" ? "https" : "http";
  const host = window.location.hostname || "localhost";
  return `${protocol}://${host}:8000`;
}

function drawDetections({ overlay, target, items, sourceWidth, sourceHeight }) {
  if (!overlay || !target) {
    return;
  }

  const displayWidth = target.clientWidth || 960;
  const displayHeight = target.clientHeight || 540;
  overlay.width = displayWidth;
  overlay.height = displayHeight;

  const context = overlay.getContext("2d");
  if (!context) {
    return;
  }

  context.clearRect(0, 0, overlay.width, overlay.height);
  context.lineWidth = 2;
  context.font = '600 13px "Segoe UI", sans-serif';

  items.forEach((item) => {
    const scaleX = overlay.width / Math.max(sourceWidth, 1);
    const scaleY = overlay.height / Math.max(sourceHeight, 1);
    const x = item.box.x * scaleX;
    const y = item.box.y * scaleY;
    const width = item.box.width * scaleX;
    const height = item.box.height * scaleY;
    const cueSuffix = Array.isArray(item.ambulance_cues) && item.ambulance_cues.length ? ` [${item.ambulance_cues.join(", ")}]` : "";
    const label = `${item.label}${cueSuffix} ${(item.confidence * 100).toFixed(0)}%`;
    const palette =
      item.label === "ambulance"
        ? { stroke: "#22c55e", fill: "rgba(34, 197, 94, 0.16)", badge: "#15803d", text: "#f0fdf4" }
        : { stroke: "#22d3ee", fill: "rgba(8, 145, 178, 0.18)", badge: "#06b6d4", text: "#ecfeff" };

    context.strokeStyle = palette.stroke;
    context.fillStyle = palette.fill;
    context.fillRect(x, y, width, height);
    context.strokeRect(x, y, width, height);

    const textWidth = context.measureText(label).width;
    context.fillStyle = palette.badge;
    context.fillRect(x, Math.max(0, y - 24), textWidth + 18, 24);
    context.fillStyle = palette.text;
    context.fillText(label, x + 9, Math.max(16, y - 8));
  });
}

export default function LiveCvPage() {
  const videoRef = useRef(null);
  const overlayRef = useRef(null);
  const uploadImageRef = useRef(null);
  const uploadOverlayRef = useRef(null);
  const captureCanvasRef = useRef(null);
  const streamRef = useRef(null);
  const detectionTimerRef = useRef(null);
  const detectionLockRef = useRef(false);
  const [sourceMode, setSourceMode] = useState("camera");
  const [cameraState, setCameraState] = useState("idle");
  const [error, setError] = useState("");
  const [detections, setDetections] = useState([]);
  const [uncertainDetections, setUncertainDetections] = useState([]);
  const [stats, setStats] = useState(DEFAULT_STATS);
  const [selectedFile, setSelectedFile] = useState(null);
  const [selectedFileUrl, setSelectedFileUrl] = useState("");
  const [selectedFileKind, setSelectedFileKind] = useState("");
  const [isAnalyzingUpload, setIsAnalyzingUpload] = useState(false);

  useEffect(() => {
    return () => {
      stopCamera();
      if (selectedFileUrl) {
        URL.revokeObjectURL(selectedFileUrl);
      }
    };
  }, [selectedFileUrl]);

  useEffect(() => {
    if (sourceMode === "camera") {
      drawDetections({
        overlay: overlayRef.current,
        target: videoRef.current,
        items: detections,
        sourceWidth: stats.imageWidth,
        sourceHeight: stats.imageHeight,
      });
      return;
    }

    if (selectedFileKind.startsWith("image/")) {
      drawDetections({
        overlay: uploadOverlayRef.current,
        target: uploadImageRef.current,
        items: detections,
        sourceWidth: stats.imageWidth,
        sourceHeight: stats.imageHeight,
      });
    }
  }, [detections, selectedFileKind, sourceMode, stats.imageHeight, stats.imageWidth]);

  const stopCamera = () => {
    if (detectionTimerRef.current) {
      window.clearInterval(detectionTimerRef.current);
      detectionTimerRef.current = null;
    }

    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }

    detectionLockRef.current = false;
    setCameraState("idle");
  };

  const resetAnalysis = (lastUpdated = "waiting") => {
    setDetections([]);
    setUncertainDetections([]);
    setStats({ ...DEFAULT_STATS, lastUpdated });
  };

  const startCamera = async () => {
    if (!navigator.mediaDevices?.getUserMedia) {
      setError("This browser does not support webcam access.");
      setCameraState("error");
      return;
    }

    try {
      setError("");
      setSourceMode("camera");
      resetAnalysis("starting");
      setCameraState("starting");
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: "environment",
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
        audio: false,
      });

      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }

      setCameraState("live");
      detectFrame();
      detectionTimerRef.current = window.setInterval(() => {
        detectFrame();
      }, 1400);
    } catch (cameraError) {
      setCameraState("error");
      setError(cameraError instanceof Error ? cameraError.message : "Could not start the camera.");
    }
  };

  const stopCameraSession = () => {
    stopCamera();
    resetAnalysis("stopped");
    if (overlayRef.current) {
      const context = overlayRef.current.getContext("2d");
      context?.clearRect(0, 0, overlayRef.current.width, overlayRef.current.height);
    }
  };

  const applyDetectionPayload = (payload) => {
    const nextDetections = Array.isArray(payload.detections) ? payload.detections : [];
    const nextUncertainDetections = Array.isArray(payload.uncertain_detections) ? payload.uncertain_detections : [];
    setDetections(nextDetections);
    setUncertainDetections(nextUncertainDetections);
    setStats({
      count: payload.vehicle_count ?? nextDetections.length,
      uncertainCount: payload.uncertain_count ?? nextUncertainDetections.length,
      emergencyCount: payload.emergency_count ?? 0,
      emergencyDetected: Boolean(payload.emergency_detected),
      emergencyLabels: Array.isArray(payload.emergency_labels) ? payload.emergency_labels : [],
      ambulanceCueCounts: payload.ambulance_cue_counts ?? {},
      positionsBreakdown: payload.positions_breakdown ?? {},
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
      sourceType: payload.source_type ?? "camera",
      model: payload.model ?? DEFAULT_STATS.model,
      imageWidth: payload.image?.width ?? DEFAULT_STATS.imageWidth,
      imageHeight: payload.image?.height ?? DEFAULT_STATS.imageHeight,
      lastUpdated: new Date().toLocaleTimeString(),
    });
  };

  const postMediaForAnalysis = async (file, filename) => {
    const formData = new FormData();
    formData.append("media", file, filename);

    const response = await fetch(`${getApiBaseUrl()}/api/live-cv/detect`, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      throw new Error(`Detection failed with status ${response.status}.`);
    }

    const payload = await response.json();
    applyDetectionPayload(payload);
  };

  const detectFrame = async () => {
    const video = videoRef.current;
    const canvas = captureCanvasRef.current;
    if (!video || !canvas || detectionLockRef.current || video.videoWidth === 0 || video.videoHeight === 0) {
      return;
    }

    detectionLockRef.current = true;

    try {
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      const context = canvas.getContext("2d");
      if (!context) {
        throw new Error("Could not access the capture canvas.");
      }

      context.drawImage(video, 0, 0, canvas.width, canvas.height);
      const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.85));
      if (!blob) {
        throw new Error("Could not create a frame snapshot.");
      }

      await postMediaForAnalysis(blob, "frame.jpg");
      setError("");
    } catch (detectionError) {
      setError(detectionError instanceof Error ? detectionError.message : "Vehicle detection failed.");
      setCameraState("error");
      stopCamera();
    } finally {
      detectionLockRef.current = false;
    }
  };

  const handleFileChange = (event) => {
    const file = event.target.files?.[0] ?? null;
    if (selectedFileUrl) {
      URL.revokeObjectURL(selectedFileUrl);
    }

    setSelectedFile(file);
    setSelectedFileKind(file?.type ?? "");
    setSelectedFileUrl(file ? URL.createObjectURL(file) : "");
    setSourceMode("upload");
    setError("");
    resetAnalysis(file ? "ready to analyze" : "waiting");
  };

  const analyzeUpload = async () => {
    if (!selectedFile) {
      setError("Choose an image or video first.");
      return;
    }

    try {
      stopCamera();
      setSourceMode("upload");
      setIsAnalyzingUpload(true);
      setError("");
      await postMediaForAnalysis(selectedFile, selectedFile.name);
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "Upload analysis failed.");
    } finally {
      setIsAnalyzingUpload(false);
    }
  };

  const isLive = cameraState === "live";
  const vehicleTypeEntries = Object.entries(stats.vehicleTypes);
  const ambulanceCueEntries = Object.entries(stats.ambulanceCueCounts);
  const positionEntries = Object.entries(stats.positionsBreakdown);

  return (
    <div className="space-y-6">
      <section className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <div className="glass-panel rounded-[2rem] p-8">
          <p className="text-sm uppercase tracking-[0.3em] text-cyan-300">Live CV</p>
          <h2 className="mt-4 text-4xl font-semibold tracking-tight text-white">Front-view traffic vision for live feeds, uploaded photos, and uploaded videos.</h2>
          <p className="mt-5 max-w-3xl text-base leading-8 text-slate-300">
            The current pipeline now prefers clearly visible front-facing vehicles, explains detections with front-only clues,
            separates uncertain front views, and keeps ambulance identification tied to front emergency markers.
          </p>

          <div className="mt-8 flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => setSourceMode("camera")}
              className={`rounded-full px-5 py-2.5 text-sm font-semibold transition ${
                sourceMode === "camera" ? "bg-cyan-400 text-slate-950" : "border border-white/10 bg-white/5 text-white hover:bg-white/10"
              }`}
            >
              Live Camera
            </button>
            <button
              type="button"
              onClick={() => {
                stopCamera();
                setSourceMode("upload");
              }}
              className={`rounded-full px-5 py-2.5 text-sm font-semibold transition ${
                sourceMode === "upload" ? "bg-cyan-400 text-slate-950" : "border border-white/10 bg-white/5 text-white hover:bg-white/10"
              }`}
            >
              Upload Photo / Video
            </button>
          </div>

          <div className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            <div className="rounded-3xl border border-cyan-400/20 bg-cyan-400/10 p-5">
              <p className="metric-label">Clear Front Vehicles</p>
              <p className="mt-3 text-2xl font-semibold text-white">{stats.count}</p>
            </div>
            <div className="rounded-3xl border border-rose-400/20 bg-rose-500/10 p-5">
              <p className="metric-label">Uncertain Front Views</p>
              <p className="mt-3 text-2xl font-semibold text-white">{stats.uncertainCount}</p>
            </div>
            <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-5">
              <p className="metric-label">Queue Length</p>
              <p className="mt-3 text-2xl font-semibold text-white">{stats.queueLength}</p>
            </div>
            <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-5">
              <p className="metric-label">Density</p>
              <p className="mt-3 text-2xl font-semibold capitalize text-white">
                {stats.densityPercent.toFixed(1)}% <span className="text-base text-slate-400">({stats.densityLevel})</span>
              </p>
            </div>
            <div className="rounded-3xl border border-emerald-400/20 bg-emerald-400/10 p-5">
              <p className="metric-label">Emergency</p>
              <p className="mt-3 text-2xl font-semibold text-white">{stats.emergencyDetected ? "Yes" : "No"}</p>
            </div>
            <div className="rounded-3xl border border-amber-400/20 bg-amber-400/10 p-5">
              <p className="metric-label">Signal Priority</p>
              <p className="mt-3 text-2xl font-semibold text-white">{stats.signalPriorityValue}</p>
            </div>
          </div>

          <div
            className={`mt-6 rounded-3xl border px-5 py-4 text-sm ${
              stats.accidentDetected ? "border-rose-400/30 bg-rose-500/10 text-rose-100" : "border-white/10 bg-white/[0.04] text-slate-300"
            }`}
          >
            <p className="metric-label">{stats.accidentDetected ? "Accident Alert" : "Traffic Priority Guidance"}</p>
            <p className="mt-2 text-base font-semibold text-white">
              {stats.accidentDetected ? stats.accidentMessage || "Possible road accident detected." : stats.signalPriorityReason}
            </p>
            <p className="mt-2 text-sm">
              Accident confidence: <span className="font-medium text-white">{(stats.accidentConfidence * 100).toFixed(0)}%</span>
            </p>
          </div>
        </div>

        <div className="glass-panel rounded-[2rem] p-8">
          <p className="panel-title">Analysis Control</p>
          <div className="mt-5 space-y-4 text-sm leading-7 text-slate-300">
            <p>Status: <span className="font-medium text-white">{sourceMode === "camera" ? cameraState : isAnalyzingUpload ? "analyzing" : "ready"}</span></p>
            <p>Last Detection: <span className="font-medium text-white">{stats.lastUpdated}</span></p>
            <p>Model: <span className="font-medium text-white">{stats.model}</span></p>
            <p>
              Emergency Labels: <span className="font-medium text-white">{stats.emergencyLabels.length ? stats.emergencyLabels.join(", ") : "none"}</span>
            </p>
            <p>
              Ambulance Cues:{" "}
              <span className="font-medium text-white">
                {ambulanceCueEntries.length ? ambulanceCueEntries.map(([label, count]) => `${label} ${count}`).join(", ") : "none"}
              </span>
            </p>
            {stats.sampledFrames ? <p>Sampled Video Frames: <span className="font-medium text-white">{stats.sampledFrames}</span></p> : null}
          </div>

          {sourceMode === "camera" ? (
            <div className="mt-6 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={startCamera}
                disabled={isLive || cameraState === "starting"}
                className="rounded-full bg-cyan-400 px-5 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:bg-cyan-900/40 disabled:text-slate-400"
              >
                Start Camera
              </button>
              <button
                type="button"
                onClick={stopCameraSession}
                disabled={!isLive && cameraState !== "error"}
                className="rounded-full border border-white/10 bg-white/5 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-white/10 disabled:cursor-not-allowed disabled:text-slate-500"
              >
                Stop Camera
              </button>
            </div>
          ) : (
            <div className="mt-6 space-y-4">
              <label className="block rounded-3xl border border-dashed border-white/15 bg-white/[0.03] p-5 text-sm text-slate-300">
                <span className="block text-white">Upload photo or video</span>
                <span className="mt-2 block text-slate-400">Supported by the same backend model route for image and video analysis.</span>
                <input type="file" accept="image/*,video/*" onChange={handleFileChange} className="mt-4 block w-full text-sm text-slate-300" />
              </label>
              <button
                type="button"
                onClick={analyzeUpload}
                disabled={!selectedFile || isAnalyzingUpload}
                className="rounded-full bg-cyan-400 px-5 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:bg-cyan-900/40 disabled:text-slate-400"
              >
                {isAnalyzingUpload ? "Analyzing..." : "Analyze Upload"}
              </button>
            </div>
          )}

          {vehicleTypeEntries.length ? (
            <div className="mt-6">
              <p className="panel-title">Vehicle Types</p>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                {vehicleTypeEntries.map(([label, count]) => (
                  <div key={label} className="rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm text-slate-200">
                    <span className="capitalize">{label.replaceAll("_", " ")}</span>: <span className="font-semibold text-white">{count}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {ambulanceCueEntries.length ? (
            <div className="mt-6">
              <p className="panel-title">Ambulance Cue Labels</p>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                {ambulanceCueEntries.map(([label, count]) => (
                  <div key={label} className="rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm text-slate-200">
                    <span className="capitalize">{label.replaceAll("_", " ")}</span>: <span className="font-semibold text-white">{count}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {positionEntries.length ? (
            <div className="mt-6">
              <p className="panel-title">Vehicle Positions</p>
              <div className="mt-4 grid gap-3 sm:grid-cols-3">
                {positionEntries.map(([label, count]) => (
                  <div key={label} className="rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm text-slate-200">
                    <span className="capitalize">{label}</span>: <span className="font-semibold text-white">{count}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {detections.length ? (
            <div className="mt-6 rounded-3xl border border-white/10 bg-white/[0.04] p-5 text-sm text-slate-300">
              <p className="panel-title">Detected Vehicles</p>
              <div className="mt-4 space-y-3">
                {detections.map((item, index) => (
                  <div key={`${item.label}-${index}-${item.box.x}-${item.box.y}`} className="rounded-2xl border border-white/10 bg-slate-950/30 px-4 py-3">
                    <p className="font-semibold capitalize text-white">
                      {item.vehicle_type || item.label} | {item.position} | {item.confidence_level || "medium"} confidence
                    </p>
                    <p className="mt-1 text-slate-300">{item.clue || "Road vehicle detected."}</p>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {uncertainDetections.length ? (
            <div className="mt-6 rounded-3xl border border-amber-400/20 bg-amber-500/10 p-5 text-sm text-amber-100">
              <p className="panel-title">Uncertain Front Views</p>
              <div className="mt-4 space-y-3">
                {uncertainDetections.map((item, index) => (
                  <div key={`${item.base_vehicle_type || item.label}-${index}-${item.box.x}-${item.box.y}`} className="rounded-2xl border border-amber-300/20 bg-slate-950/30 px-4 py-3">
                    <p className="font-semibold capitalize text-white">
                      {item.base_vehicle_type || item.label} | {item.position} | {item.confidence_level || "low"} confidence
                    </p>
                    <p className="mt-1 text-amber-100">{item.uncertain_reason || "Front view is unclear."}</p>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {stats.videoSummary ? (
            <div className="mt-6 rounded-3xl border border-white/10 bg-white/[0.04] p-5 text-sm text-slate-300">
              <p className="panel-title">Video Summary</p>
              <p className="mt-3">Average vehicles: <span className="font-medium text-white">{stats.videoSummary.average_vehicle_count}</span></p>
              <p className="mt-2">Peak vehicles: <span className="font-medium text-white">{stats.videoSummary.peak_vehicle_count}</span></p>
              <p className="mt-2">Peak queue length: <span className="font-medium text-white">{stats.videoSummary.peak_queue_length}</span></p>
              <p className="mt-2">Peak density: <span className="font-medium text-white">{stats.videoSummary.peak_density_percent.toFixed(1)}%</span></p>
            </div>
          ) : null}

          {error ? <p className="mt-5 rounded-2xl border border-rose-400/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">{error}</p> : null}
        </div>
      </section>

      <section className="grid gap-6 2xl:grid-cols-[1.35fr_0.95fr]">
        <div className="glass-panel rounded-[2rem] p-6">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="panel-title">{sourceMode === "camera" ? "Live Camera" : "Uploaded Media"}</p>
              <h3 className="mt-3 text-2xl font-semibold text-white">
                {sourceMode === "camera" ? "Camera preview with live vehicle boxes" : "Photo or video preview for uploaded traffic analysis"}
              </h3>
            </div>
            <div className="rounded-full border border-cyan-400/20 bg-cyan-400/10 px-4 py-2 text-xs uppercase tracking-[0.24em] text-cyan-200">
              {sourceMode === "camera" ? "Active" : "Upload"}
            </div>
          </div>

          {sourceMode === "camera" ? (
            <div className="relative mt-6 overflow-hidden rounded-[1.75rem] border border-white/10 bg-slate-950">
              <video ref={videoRef} autoPlay muted playsInline className="aspect-video w-full object-cover" />
              <canvas ref={overlayRef} className="pointer-events-none absolute inset-0 h-full w-full" />
              {!isLive ? (
                <div className="absolute inset-0 flex items-center justify-center bg-slate-950/80 px-6 text-center">
                  <div>
                    <p className="text-sm uppercase tracking-[0.3em] text-cyan-300">Preview</p>
                    <p className="mt-4 text-2xl font-semibold text-white">Camera feed will appear here</p>
                    <p className="mt-3 text-sm leading-7 text-slate-400">
                      Start the camera to stream frames into the detector and score only clearly visible front-facing vehicles.
                    </p>
                  </div>
                </div>
              ) : null}
            </div>
          ) : (
            <div className="relative mt-6 overflow-hidden rounded-[1.75rem] border border-white/10 bg-slate-950">
              {selectedFileUrl ? (
                selectedFileKind.startsWith("image/") ? (
                  <>
                    <img ref={uploadImageRef} src={selectedFileUrl} alt="Uploaded traffic scene" className="aspect-video w-full object-contain" />
                    <canvas ref={uploadOverlayRef} className="pointer-events-none absolute inset-0 h-full w-full" />
                  </>
                ) : selectedFileKind.startsWith("video/") ? (
                  <video src={selectedFileUrl} controls className="aspect-video w-full object-contain" />
                ) : null
              ) : (
                <div className="flex aspect-video items-center justify-center px-6 text-center">
                  <div>
                    <p className="text-sm uppercase tracking-[0.3em] text-cyan-300">Upload</p>
                    <p className="mt-4 text-2xl font-semibold text-white">Choose a traffic photo or video</p>
                    <p className="mt-3 text-sm leading-7 text-slate-400">
                      The backend will return clear front-view detections, uncertain front views, ambulance cues, position counts, and type counts.
                    </p>
                  </div>
                </div>
              )}
            </div>
          )}

          <canvas ref={captureCanvasRef} className="hidden" />
        </div>

        <div className="grid gap-4">
          {junctionCards.map((card) => (
            <div key={card.key} className="glass-panel rounded-[2rem] p-6">
              <div className="flex items-center justify-between gap-4">
                <p className="text-lg font-semibold text-white">{card.title}</p>
                <span className="rounded-full border border-amber-400/20 bg-amber-400/10 px-3 py-1 text-xs uppercase tracking-[0.22em] text-amber-200">
                  {card.status}
                </span>
              </div>
              <p className="mt-4 text-sm leading-7 text-slate-300">{card.copy}</p>
            </div>
          ))}

          <div className="glass-panel rounded-[2rem] p-6">
            <p className="panel-title">Front-View Rules</p>
            <div className="mt-5 space-y-3 text-sm leading-7 text-slate-300">
              <p>Only clearly visible front-facing vehicles are counted in the main results.</p>
              <p>Unclear, partial, or non-frontal detections are moved into a separate uncertain section.</p>
              <p>Front-only clues are used for the explanation: headlights, grille, windshield shape, handlebar cues, and front structure.</p>
              <p>Ambulances are highlighted from front emergency cues such as mirrored ambulance text, medical symbols, or emergency lights.</p>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
