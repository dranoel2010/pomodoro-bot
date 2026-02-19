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
const pomodoroMotivation = document.getElementById("pomodoro-motivation");

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

const pomodoroState = {
    phase: "idle",
    session: "",
    durationSeconds: 1500,
    anchorRemainingSeconds: 1500,
    anchorTimestampMs: Date.now(),
    motivation: "Start a session to lock in your focus.",
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

function setStatusMessage(message) {
    if (typeof message === "string" && message.trim()) {
        envStatus.textContent = message.trim();
    }
}

function clearError() {
    errorStatus.textContent = "";
    errorStatus.style.display = "none";
}

function showError(message) {
    errorStatus.textContent = `ERROR: ${message}`;
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

function currentPomodoroRemaining() {
    if (pomodoroState.phase !== "running") {
        return pomodoroState.anchorRemainingSeconds;
    }

    const elapsedSeconds = Math.floor((Date.now() - pomodoroState.anchorTimestampMs) / 1000);
    return Math.max(0, pomodoroState.anchorRemainingSeconds - elapsedSeconds);
}

function renderPomodoro() {
    const remainingSeconds = currentPomodoroRemaining();
    const effectivePhase =
        pomodoroState.phase === "running" && remainingSeconds === 0
            ? "completed"
            : pomodoroState.phase;

    pomodoroSession.textContent = (pomodoroState.session || "FOCUS SESSION").toUpperCase();
    pomodoroTimer.textContent = formatDuration(remainingSeconds);
    pomodoroPhase.textContent = pomodoroPhaseLabels[effectivePhase] || effectivePhase.toUpperCase();

    const isActiveSession = isPomodoroFocusPhase(effectivePhase);
    pomodoroPanel.classList.toggle("active", isActiveSession);
    document.body.classList.toggle("pomodoro-focus", isActiveSession);
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
        pomodoroState.anchorTimestampMs = Date.now();
    }

    if (typeof payload.motivation === "string" && payload.motivation.trim()) {
        pomodoroState.motivation = payload.motivation.trim();
        pomodoroMotivation.textContent = pomodoroState.motivation;
    }

    if (!pomodoroMotivation.textContent.trim()) {
        pomodoroMotivation.textContent = "Start a session to lock in your focus.";
    }

    renderPomodoro();
}

function connectWebSocket() {
    const wsProtocol = window.location.protocol === "https:" ? "wss" : "ws";
    const wsUrl = `${wsProtocol}://${window.location.host}/ws`;
    const socket = new WebSocket(wsUrl);

    socket.onopen = () => {
        wsIndicator.textContent = "WS: CONNECTED";
        wsIndicator.style.color = "#00ff00";
        setStatusMessage("Connected to runtime");
        clearError();
    };

    socket.onmessage = (event) => {
        let payload = null;
        try {
            payload = JSON.parse(event.data);
        } catch (_) {
            return;
        }

        if (typeof payload.message === "string") {
            setStatusMessage(payload.message);
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

        if (payload?.type === "error") {
            const message = typeof payload.message === "string" ? payload.message : "Unknown error";
            showError(message);
        }
    };

    socket.onclose = () => {
        wsIndicator.textContent = "WS: RETRYING...";
        wsIndicator.style.color = "#ff4d00";
        setStatusMessage("Connection lost, retrying...");
        setTimeout(connectWebSocket, 2000);
    };

    socket.onerror = () => {
        wsIndicator.textContent = "WS: ERROR";
        wsIndicator.style.color = "#ff4d00";
    };
}

setInterval(() => {
    if (pomodoroState.phase === "running") {
        renderPomodoro();
    }
}, 250);

clearError();
renderPomodoro();
connectWebSocket();
