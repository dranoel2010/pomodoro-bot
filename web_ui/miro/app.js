/* MIRO runtime client */

const state = { light: "hell", air: "gut", beh: "idle" };

const stage = document.querySelector(".stage");
const body = document.body;
const faceGroup = document.getElementById("faceGroup");
const eyeL = document.getElementById("eyeL");
const eyeR = document.getElementById("eyeR");
const noseGroup = document.getElementById("noseGroup");
const mouthGroup = document.getElementById("mouthGroup");
const mouthPath = document.getElementById("mouthPath");
const zzzGroup = document.getElementById("zzzGroup");
const particlesEl = document.getElementById("particles");
const starsEl = document.getElementById("stars");

const badgeWs = document.getElementById("badgeWs");
const badgeRuntime = document.getElementById("badgeRuntime");

const pomodoroCard = document.getElementById("pomodoroCard");
const pomodoroIcon = document.getElementById("pomodoroIcon");
const pomodoroPhase = document.getElementById("pomodoroPhase");
const pomodoroSession = document.getElementById("pomodoroSession");
const pomodoroTime = document.getElementById("pomodoroTime");
const pomodoroProgressFill = document.getElementById("pomodoroProgressFill");

const timerBubble = document.getElementById("timerBubble");
const timerTitle = document.getElementById("timerTitle");
const timerTime = document.getElementById("timerTime");

const MOUTHS = {
  idle: "M 112 168 A 33 23 0 0 0 178 168 Z",
  bored: "M 122 172 A 22 9  0 0 0 168 172 Z",
  listen: "M 102 165 A 43 14 0 0 0 188 165 Z",
  think: "M 130 171 A 14 7  0 0 0 162 171 Z",
  respond: "M 106 162 A 39 30 0 0 0 184 162 Z",
  sleep: "M 122 172 A 22 6  0 0 1 168 172 Z",
};

const EYES = {
  idle: { rx: 48, ry: 42 },
  bored: { rx: 48, ry: 28 },
  listen: { rx: 48, ry: 46 },
  think: { rx: 44, ry: 22 },
  respond: { rx: 48, ry: 44 },
  sleep: { rx: 48, ry: 5 },
};

const MOUTH_GRUMPY = "M 118 178 A 27 16 0 0 1 172 178 Z";
const ACTIVE_BEHS = ["listen", "think", "respond"];
const INACTIVE_PHASES = new Set([
  "idle",
  "done",
  "completed",
  "stopped",
  "finished",
  "inactive",
  "aborted",
  "canceled",
  "cancelled",
]);
const RUNTIME_STATE_TO_BEHAVIOR = {
  idle: "idle",
  listening: "listen",
  transcribing: "listen",
  thinking: "think",
  replying: "respond",
  error: "bored",
};

const POMODORO_PHASE_LABELS = {
  focus: "Focus",
  short_break: "Short Break",
  long_break: "Long Break",
  paused: "Paused",
};

const POMODORO_PHASE_ICONS = {
  focus: "🍅",
  short_break: "☕",
  long_break: "🌙",
  paused: "⏸️",
};

const pomodoroState = {
  phase: "idle",
  session: "Pomodoro Session",
  remainingSeconds: 0,
  totalSeconds: 0,
  active: false,
};

const timerState = {
  phase: "idle",
  remainingSeconds: 0,
  active: false,
};

let ws = null;
let reconnectTimer = null;
let reconnectDelayMs = 1000;

let talkRaf = null;
let talkOpen = 0;
const PHONEMES = [0, 0, 0.05, 0.1, 0.05, 0.3, 0.5, 0.7, 0.9, 1.0, 0.6, 0.2];

function setText(el, text) {
  if (el) {
    el.textContent = text;
  }
}

function formatDuration(seconds) {
  const safe = Math.max(0, Number.isFinite(seconds) ? Math.floor(seconds) : 0);
  const mm = Math.floor(safe / 60);
  const ss = safe % 60;
  return `${String(mm).padStart(2, "0")}:${String(ss).padStart(2, "0")}`;
}

function normalizePhase(value) {
  if (typeof value !== "string") {
    return "idle";
  }
  return value.trim().toLowerCase().replace(/\s+/g, "_");
}

function humanizePhase(phase) {
  const key = normalizePhase(phase);
  if (key in POMODORO_PHASE_LABELS) {
    return POMODORO_PHASE_LABELS[key];
  }
  return key
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ") || "Idle";
}

function isActivePhase(phase) {
  return !INACTIVE_PHASES.has(normalizePhase(phase));
}

function setStageMode(mode) {
  if (!stage) {
    return;
  }
  stage.classList.toggle("mode-pomodoro", mode === "pomodoro");
  stage.classList.toggle("mode-timer", mode === "timer");

  if (pomodoroCard) {
    pomodoroCard.setAttribute("aria-hidden", mode !== "pomodoro" ? "true" : "false");
  }
  if (timerBubble) {
    timerBubble.setAttribute("aria-hidden", mode !== "timer" ? "true" : "false");
  }
}

function syncStageMode() {
  if (pomodoroState.active) {
    setStageMode("pomodoro");
    return;
  }
  if (timerState.active) {
    setStageMode("timer");
    return;
  }
  setStageMode("face");
}

function renderPomodoroCard() {
  if (!pomodoroCard) {
    return;
  }

  const phaseKey = normalizePhase(pomodoroState.phase);
  const icon = POMODORO_PHASE_ICONS[phaseKey] || "🍅";
  const phaseLabel = humanizePhase(phaseKey);
  const sessionLabel = pomodoroState.session || "Pomodoro Session";

  setText(pomodoroIcon, icon);
  setText(pomodoroPhase, phaseLabel);
  setText(pomodoroSession, sessionLabel);
  setText(pomodoroTime, formatDuration(pomodoroState.remainingSeconds));

  const progress =
    pomodoroState.totalSeconds > 0
      ? Math.max(0, Math.min(100, (1 - pomodoroState.remainingSeconds / pomodoroState.totalSeconds) * 100))
      : 0;
  if (pomodoroProgressFill) {
    pomodoroProgressFill.style.width = `${progress.toFixed(1)}%`;
  }
}

function renderTimerBubble() {
  if (!timerBubble) {
    return;
  }

  const phaseLabel = humanizePhase(timerState.phase);
  setText(timerTitle, `Timer · ${phaseLabel}`);
  setText(timerTime, formatDuration(timerState.remainingSeconds));
}

function createParticles() {
  particlesEl.innerHTML = "";
  for (let i = 0; i < 22; i += 1) {
    const p = document.createElement("div");
    p.className = "particle";
    const size = 3 + Math.random() * 9;
    const dx = (Math.random() - 0.5) * 60;
    const dur = (2.5 + Math.random() * 5).toFixed(2);
    const del = (Math.random() * 5).toFixed(2);
    p.style.cssText = `
      width:${size}px; height:${size}px;
      left:${5 + Math.random() * 90}%;
      bottom:${Math.random() * 20}%;
      --dx:${dx}px;
      animation: drift ${dur}s linear ${del}s infinite;
    `;
    particlesEl.appendChild(p);
  }
}

function setParticles(active) {
  if (active) {
    createParticles();
  } else {
    particlesEl.innerHTML = "";
  }
}

function lerp(a, b, t) {
  return a + (b - a) * t;
}

function buildMouthPath(open) {
  const baseY = 168;
  const rx = 33 + open * 8;
  const ry = 2 + open * 30;
  const startX = 145 - rx;
  const endX = 145 + rx;
  return `M ${startX} ${baseY} A ${rx} ${ry} 0 0 0 ${endX} ${baseY} Z`;
}

function startTalking() {
  stopTalking();

  let target = 0;
  let holdMs = 0;
  let elapsed = 0;
  let last = performance.now();

  function scheduleNext() {
    holdMs = 60 + Math.random() * 160;
    elapsed = 0;
    const idx = Math.floor(Math.random() * PHONEMES.length);
    target = PHONEMES[idx];
    if (Math.random() < 0.18) {
      target = 0;
    }
  }

  function tick(now) {
    const dt = now - last;
    last = now;
    elapsed += dt;

    const speed = talkOpen < target ? 0.12 : 0.18;
    talkOpen = lerp(talkOpen, target, speed);
    mouthPath.setAttribute("d", buildMouthPath(talkOpen));

    if (elapsed >= holdMs) {
      scheduleNext();
    }

    talkRaf = requestAnimationFrame(tick);
  }

  scheduleNext();
  talkRaf = requestAnimationFrame(tick);
}

function stopTalking() {
  if (talkRaf) {
    cancelAnimationFrame(talkRaf);
    talkRaf = null;
  }
  talkOpen = 0;
}

for (let i = 0; i < 28; i += 1) {
  const s = document.createElement("div");
  s.className = "star";
  const sz = 1.5 + Math.random() * 2.5;
  s.style.cssText = `
    width:${sz}px; height:${sz}px;
    left:${Math.random() * 100}%;
    top:${Math.random() * 65}%;
    animation-duration:${1.5 + Math.random() * 3}s;
    animation-delay:${Math.random() * 3}s;
  `;
  starsEl.appendChild(s);
}

function swapClass(el, prefix, val) {
  [...el.classList]
    .filter((c) => c.startsWith(prefix))
    .forEach((c) => el.classList.remove(c));
  el.classList.add(prefix + val);
}

function syncTired() {
  const isDark = state.light === "dunkel";
  const isActive = ACTIVE_BEHS.includes(state.beh);
  if (isDark && !isActive) {
    body.classList.add("tired");
  } else {
    body.classList.remove("tired");
  }
}

function setLight(mode) {
  state.light = mode;
  if (mode === "dunkel") {
    body.classList.add("dark");
  } else {
    body.classList.remove("dark");
  }

  const scaleY = (EYES[state.beh]?.ry ?? 42) / 42;
  eyeL.style.transform = `scaleY(${scaleY})`;
  eyeR.style.transform = `scaleY(${scaleY})`;
  syncTired();
}

function setAir(quality) {
  state.air = quality;
  const bad = quality === "schlecht";
  if (bad) {
    body.classList.add("bad-air");
  } else {
    body.classList.remove("bad-air");
  }
  setParticles(bad);

  if (bad && !mouthGroup.classList.contains("talking")) {
    mouthPath.setAttribute("d", MOUTH_GRUMPY);
  } else if (!bad) {
    mouthPath.setAttribute("d", MOUTHS[state.beh] || MOUTHS.idle);
  }
}

function setBeh(beh) {
  state.beh = beh;

  swapClass(faceGroup, "s-", beh);
  swapClass(eyeL, "s-", beh);
  swapClass(eyeR, "s-", beh);

  const shape = EYES[beh] || EYES.idle;
  const scaleY = shape.ry / 42;
  eyeL.style.transform = `scaleY(${scaleY})`;
  eyeR.style.transform = `scaleY(${scaleY})`;

  swapClass(noseGroup, "s-", beh);

  if (zzzGroup) {
    zzzGroup.style.display = beh === "sleep" ? "block" : "none";
  }

  if (state.air === "schlecht" && beh !== "respond") {
    mouthPath.setAttribute("d", MOUTH_GRUMPY);
  } else {
    mouthPath.setAttribute("d", MOUTHS[beh] || MOUTHS.idle);
  }

  if (beh === "respond") {
    mouthGroup.classList.add("talking");
    startTalking();
  } else {
    mouthGroup.classList.remove("talking");
    stopTalking();
  }

  syncTired();
}

function inferAirQualityLabel(payload) {
  const air = payload?.air_quality;
  if (!air || typeof air !== "object") {
    return null;
  }

  const aqiCandidate =
    air.aqi ?? air.iaq ?? air.air_quality_index ?? air.index ?? null;
  const aqi = Number(aqiCandidate);
  if (Number.isFinite(aqi)) {
    return aqi >= 3 ? "schlecht" : "gut";
  }

  const textual = String(air.status ?? air.label ?? "").toLowerCase();
  if (!textual) {
    return null;
  }
  if (
    textual.includes("bad") ||
    textual.includes("poor") ||
    textual.includes("schlecht")
  ) {
    return "schlecht";
  }
  return "gut";
}

function applyEnvironmentHints(payload) {
  if (typeof payload.light_level_lux === "number") {
    setLight(payload.light_level_lux > 40 ? "hell" : "dunkel");
  }

  const airLabel = inferAirQualityLabel(payload);
  if (airLabel) {
    setAir(airLabel);
  }
}

function setWsStatus(status, text) {
  if (!badgeWs) {
    return;
  }

  badgeWs.className = `badge ws-${status}`;
  badgeWs.textContent = text;
}

function setRuntimeState(stateName) {
  setText(badgeRuntime, `State: ${stateName}`);

  const nextBehavior = RUNTIME_STATE_TO_BEHAVIOR[stateName];
  if (nextBehavior) {
    setBeh(nextBehavior);
  }
}

function updatePomodoro(payload) {
  const previousPhase = pomodoroState.phase;

  if (typeof payload.phase === "string") {
    pomodoroState.phase = normalizePhase(payload.phase);
  }
  if (typeof payload.session === "string" && payload.session.trim()) {
    pomodoroState.session = payload.session.trim();
  }
  if (typeof payload.remaining_seconds === "number") {
    pomodoroState.remainingSeconds = Math.max(0, Math.floor(payload.remaining_seconds));
  }

  pomodoroState.active = isActivePhase(pomodoroState.phase);
  if (pomodoroState.active) {
    timerState.active = false;

    if (
      !pomodoroState.totalSeconds ||
      pomodoroState.phase !== previousPhase ||
      pomodoroState.remainingSeconds > pomodoroState.totalSeconds
    ) {
      pomodoroState.totalSeconds = pomodoroState.remainingSeconds;
    }
  } else {
    pomodoroState.totalSeconds = 0;
  }

  renderPomodoroCard();
  syncStageMode();
}

function updateTimer(payload) {
  if (typeof payload.phase === "string") {
    timerState.phase = normalizePhase(payload.phase);
  }
  if (typeof payload.remaining_seconds === "number") {
    timerState.remainingSeconds = Math.max(0, Math.floor(payload.remaining_seconds));
  }

  timerState.active = isActivePhase(timerState.phase);
  if (timerState.active) {
    pomodoroState.active = false;
  }

  renderTimerBubble();
  syncStageMode();
}

function handleEvent(payload) {
  if (!payload || typeof payload !== "object") {
    return;
  }

  if (payload.type === "hello" || payload.type === "state_update") {
    if (typeof payload.state === "string") {
      setRuntimeState(payload.state);
    }
    applyEnvironmentHints(payload);
    return;
  }

  if (payload.type === "pomodoro") {
    updatePomodoro(payload);
    return;
  }

  if (payload.type === "timer") {
    updateTimer(payload);
    return;
  }

  if (payload.type === "error") {
    setRuntimeState("error");
  }
}

function scheduleReconnect() {
  if (reconnectTimer) {
    return;
  }

  setWsStatus(
    "connecting",
    `WS: reconnecting in ${Math.round(reconnectDelayMs / 1000)}s`,
  );
  reconnectTimer = window.setTimeout(() => {
    reconnectTimer = null;
    connectWebSocket();
  }, reconnectDelayMs);

  reconnectDelayMs = Math.min(reconnectDelayMs * 2, 10000);
}

function connectWebSocket() {
  const wsProtocol = window.location.protocol === "https:" ? "wss" : "ws";
  const wsUrl = `${wsProtocol}://${window.location.host}/ws`;

  setWsStatus("connecting", "WS: connecting");

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    reconnectDelayMs = 1000;
    setWsStatus("connected", "WS: connected");
  };

  ws.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data);
      handleEvent(payload);
    } catch (_error) {
      // Ignore malformed payloads from experiments.
    }
  };

  ws.onerror = () => {
    setWsStatus("disconnected", "WS: error");
  };

  ws.onclose = () => {
    setWsStatus("disconnected", "WS: disconnected");
    scheduleReconnect();
  };
}

function init() {
  setLight("hell");
  setAir("gut");
  setBeh("idle");
  renderPomodoroCard();
  renderTimerBubble();
  syncStageMode();
  connectWebSocket();
}

init();
