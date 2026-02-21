const container = document.getElementById("jarvis-container");
const mainStatus = document.getElementById("main-status");
const envStatus = document.getElementById("env-status");
const wsIndicator = document.getElementById("ws-indicator");
const transcriptStatus = document.getElementById("last-transcript");
const replyStatus = document.getElementById("last-reply");
const errorStatus = document.getElementById("last-error");

const pomodoroPanel = document.getElementById("pomodoro-panel");
const pomodoroSession = document.getElementById("pomodoro-session");
const pomodoroTimer = document.getElementById("pomodoro-timer");
const pomodoroPhase = document.getElementById("pomodoro-phase");
const timerPanel = document.getElementById("timer-panel");
const timerRemaining = document.getElementById("timer-remaining");
const timerPhase = document.getElementById("timer-phase");

const runtimeStateLabels = {
    idle: "IDLE",
    listening: "LISTENING",
    transcribing: "TRANSCRIBING",
    thinking: "THINKING",
    replying: "REPLYING",
    error: "ERROR",
};

const pomodoroPhaseLabels = {
    idle: "IDLE",
    running: "RUNNING",
    paused: "PAUSED",
    completed: "COMPLETED",
    aborted: "ABORTED",
};

const timerPhaseLabels = {
    idle: "IDLE",
    running: "RUNNING",
    paused: "PAUSED",
    completed: "COMPLETED",
    aborted: "ABORTED",
};

const pomodoroState = {
    phase: "idle",
    session: "",
    durationSeconds: 1500,
    anchorRemainingSeconds: 1500,
    anchorTimestampMs: Date.now(),
};

const timerState = {
    phase: "idle",
    anchorRemainingSeconds: 0,
    anchorTimestampMs: Date.now(),
};

function setState(state) {
    container.classList.remove(
        "state-idle",
        "state-listening",
        "state-transcribing",
        "state-thinking",
        "state-replying",
        "state-error",
    );
    container.classList.add("state-" + state);
    mainStatus.textContent = runtimeStateLabels[state] || state.toUpperCase();
}

function setConnectionStatus(message) {
    if (typeof message === "string" && message.trim()) {
        envStatus.textContent = message.trim();
    }
}

function clearError() {
    errorStatus.textContent = "";
    errorStatus.style.display = "none";
}

function showError(message) {
    const normalized = typeof message === "string" ? message.trim() : "";
    if (!normalized || normalized === "-") {
        clearError();
        return;
    }

    errorStatus.textContent = `ERROR: ${normalized}`;
    errorStatus.style.display = "block";
}

function formatDuration(seconds) {
    const safeSeconds = Math.max(0, Number.isFinite(seconds) ? Math.floor(seconds) : 0);
    const minutes = Math.floor(safeSeconds / 60);
    const remainder = safeSeconds % 60;
    return `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
}

function isPomodoroFocusPhase(phase) {
    return phase === "running" || phase === "paused";
}

function isTimerFocusPhase(phase) {
    return phase === "running" || phase === "paused";
}

function parseEventTimestampMs(payload) {
    if (typeof payload?.timestamp === "string") {
        const parsed = Date.parse(payload.timestamp);
        if (Number.isFinite(parsed)) {
            return parsed;
        }
    }
    return Date.now();
}

function currentPomodoroRemaining() {
    if (pomodoroState.phase !== "running") {
        return pomodoroState.anchorRemainingSeconds;
    }

    const elapsedSeconds = Math.floor((Date.now() - pomodoroState.anchorTimestampMs) / 1000);
    return Math.max(0, pomodoroState.anchorRemainingSeconds - elapsedSeconds);
}

function currentTimerRemaining() {
    if (timerState.phase !== "running") {
        return timerState.anchorRemainingSeconds;
    }

    const elapsedSeconds = Math.floor((Date.now() - timerState.anchorTimestampMs) / 1000);
    return Math.max(0, timerState.anchorRemainingSeconds - elapsedSeconds);
}

function effectivePomodoroPhase() {
    const remainingSeconds = currentPomodoroRemaining();
    if (pomodoroState.phase === "running" && remainingSeconds === 0) {
        return "completed";
    }
    return pomodoroState.phase;
}

function effectiveTimerPhase() {
    const remainingSeconds = currentTimerRemaining();
    if (timerState.phase === "running" && remainingSeconds === 0) {
        return "completed";
    }
    return timerState.phase;
}

function renderSessionLayout() {
    const pomodoroActive = isPomodoroFocusPhase(effectivePomodoroPhase());
    const timerActive = !pomodoroActive && isTimerFocusPhase(effectiveTimerPhase());

    pomodoroPanel.classList.toggle("active", pomodoroActive);
    timerPanel.classList.toggle("active", timerActive);
    document.body.classList.toggle("pomodoro-focus", pomodoroActive);
}

function renderTimer() {
    const remainingSeconds = currentTimerRemaining();
    const phase = effectiveTimerPhase();

    timerRemaining.textContent = formatDuration(remainingSeconds);
    timerPhase.textContent = timerPhaseLabels[phase] || phase.toUpperCase();
    renderSessionLayout();
}

function renderPomodoro() {
    const remainingSeconds = currentPomodoroRemaining();
    const phase = effectivePomodoroPhase();

    pomodoroSession.textContent = (pomodoroState.session || "FOCUS SESSION").toUpperCase();
    pomodoroTimer.textContent = formatDuration(remainingSeconds);
    pomodoroPhase.textContent = pomodoroPhaseLabels[phase] || phase.toUpperCase();
    renderSessionLayout();
}

function applyPomodoroUpdate(payload) {
    if (typeof payload.phase === "string" && payload.phase.trim()) {
        pomodoroState.phase = payload.phase.trim();
    }

    if (typeof payload.session === "string") {
        pomodoroState.session = payload.session.trim();
    }

    if (
        typeof payload.duration_seconds === "number" &&
        Number.isFinite(payload.duration_seconds) &&
        payload.duration_seconds > 0
    ) {
        pomodoroState.durationSeconds = Math.floor(payload.duration_seconds);
    }

    if (
        typeof payload.remaining_seconds === "number" &&
        Number.isFinite(payload.remaining_seconds) &&
        payload.remaining_seconds >= 0
    ) {
        pomodoroState.anchorRemainingSeconds = Math.floor(payload.remaining_seconds);
        pomodoroState.anchorTimestampMs = parseEventTimestampMs(payload);
    }

    renderPomodoro();
}

function applyTimerUpdate(payload) {
    if (typeof payload.phase === "string" && payload.phase.trim()) {
        timerState.phase = payload.phase.trim();
    }

    if (
        typeof payload.remaining_seconds === "number" &&
        Number.isFinite(payload.remaining_seconds) &&
        payload.remaining_seconds >= 0
    ) {
        timerState.anchorRemainingSeconds = Math.floor(payload.remaining_seconds);
        timerState.anchorTimestampMs = parseEventTimestampMs(payload);
    }

    renderTimer();
}

function connectWebSocket() {
    const wsProtocol = window.location.protocol === "https:" ? "wss" : "ws";
    const wsUrl = `${wsProtocol}://${window.location.host}/ws`;
    setConnectionStatus("CONNECTION: CONNECTING...");
    const socket = new WebSocket(wsUrl);

    socket.onopen = () => {
        wsIndicator.textContent = "WS: CONNECTED";
        wsIndicator.style.color = "#00ff00";
        setConnectionStatus("CONNECTION: CONNECTED");
        clearError();
    };

    socket.onmessage = (event) => {
        let payload = null;
        try {
            payload = JSON.parse(event.data);
        } catch (_) {
            return;
        }

        const nextState = payload?.state;
        if (["idle", "listening", "transcribing", "thinking", "replying", "error"].includes(nextState)) {
            setState(nextState);
        }
        if (nextState && nextState !== "error") {
            clearError();
        }

        if (payload?.type === "transcript" && typeof payload.text === "string") {
            transcriptStatus.textContent = `TRANSCRIPT: ${payload.text}`;
        }

        if (payload?.type === "assistant_reply" && typeof payload.text === "string") {
            replyStatus.textContent = `REPLY: ${payload.text}`;
        }

        if (payload?.type === "pomodoro") {
            applyPomodoroUpdate(payload);
        }

        if (payload?.type === "timer") {
            applyTimerUpdate(payload);
        }

        if (payload?.type === "error") {
            const message = typeof payload.message === "string" ? payload.message : "Unknown error";
            showError(message);
        }
    };

    socket.onclose = () => {
        wsIndicator.textContent = "WS: RETRYING...";
        wsIndicator.style.color = "#ff4d00";
        setConnectionStatus("CONNECTION: RETRYING...");
        setTimeout(connectWebSocket, 2000);
    };

    socket.onerror = () => {
        wsIndicator.textContent = "WS: ERROR";
        wsIndicator.style.color = "#ff4d00";
        setConnectionStatus("CONNECTION: ERROR");
    };
}

setInterval(() => {
    if (pomodoroState.phase === "running") {
        renderPomodoro();
    }
    if (timerState.phase === "running") {
        renderTimer();
    }
}, 250);

clearError();
renderPomodoro();
renderTimer();
connectWebSocket();
