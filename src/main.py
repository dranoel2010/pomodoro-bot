import logging
import signal
import sys
import time
import datetime as dt
import re
from queue import Empty, Queue
from typing import Any, Optional

from app_config import (
    AppConfigurationError,
    load_app_config,
    load_secret_config,
    resolve_config_path,
)
from stt import (
    ConfigurationError,
    FasterWhisperSTT,
    QueueEventPublisher,
    STTConfig,
    STTError,
    UtteranceCapturedEvent,
    WakeWordConfig,
    WakeWordDetectedEvent,
    WakeWordErrorEvent,
    WakeWordService,
)
from tts import (
    CoquiTTSEngine,
    SoundDeviceAudioOutput,
    SpeechService,
    TTSConfig,
    TTSError,
)
from llm import EnvironmentContext, LLMConfig, PomodoroAssistantLLM
from oracle import OracleConfig, OracleContextService
from pomodoro import PomodoroAction, PomodoroSnapshot, PomodoroTick, PomodoroTimer
from server import ServerConfigurationError, UIServer, UIServerConfig


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure logging for the application."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    return logging.getLogger("wake_word_app")


def setup_signal_handlers(service: WakeWordService) -> None:
    """Set up graceful shutdown on SIGTERM and SIGINT."""

    def signal_handler(signum: int, frame) -> None:
        signal_name = signal.Signals(signum).name
        print(f"\n👋 {signal_name} received, stopping...\n")
        service.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)


def wait_for_service_ready(service: WakeWordService, timeout: float = 10.0) -> bool:
    """Wait for service to become ready, with fast-fail on crash.

    Args:
        service: The wake word service
        timeout: Maximum time to wait in seconds

    Returns:
        True if service became ready, False if it failed or timed out
    """
    start_time = time.time()
    poll_interval = 0.1

    while time.time() - start_time < timeout:
        if service.is_ready:
            return True

        # Fast-fail: if service died during startup, don't wait full timeout
        if not service.is_running:
            return False

        time.sleep(poll_interval)

    return service.is_ready


TIMER_TOOL_TO_ACTION: dict[str, PomodoroAction] = {
    "start_timer": "start",
    "pause_timer": "pause",
    "continue_timer": "continue",
    "stop_timer": "abort",
    "reset_timer": "reset",
}

POMODORO_TOOL_TO_ACTION: dict[str, PomodoroAction] = {
    "start_pomodoro_session": "start",
    "pause_pomodoro_session": "pause",
    "continue_pomodoro_session": "continue",
    "stop_pomodoro_session": "abort",
    "reset_pomodoro_session": "reset",
}

CALENDAR_TOOLS: set[str] = {
    "show_upcoming_events",
    "add_calendar_event",
}


def _format_duration(seconds: int) -> str:
    minutes, remainder = divmod(max(0, int(seconds)), 60)
    return f"{minutes:02d}:{remainder:02d}"


def _timer_status_message(snapshot: PomodoroSnapshot) -> str:
    if snapshot.phase == "running":
        return f"Timer laeuft ({_format_duration(snapshot.remaining_seconds)} verbleibend)"
    if snapshot.phase == "paused":
        return f"Timer pausiert ({_format_duration(snapshot.remaining_seconds)} verbleibend)"
    if snapshot.phase == "completed":
        return "Timer abgeschlossen"
    if snapshot.phase == "aborted":
        return "Timer gestoppt"
    return "Bereit"


def _pomodoro_status_message(snapshot: PomodoroSnapshot) -> str:
    if snapshot.phase == "running":
        return (
            f"Pomodoro '{snapshot.session or 'Fokus'}' laeuft "
            f"({_format_duration(snapshot.remaining_seconds)} verbleibend)"
        )
    if snapshot.phase == "paused":
        return (
            f"Pomodoro '{snapshot.session or 'Fokus'}' pausiert "
            f"({_format_duration(snapshot.remaining_seconds)} verbleibend)"
        )
    if snapshot.phase == "completed":
        return f"Pomodoro '{snapshot.session or 'Fokus'}' abgeschlossen"
    if snapshot.phase == "aborted":
        return f"Pomodoro '{snapshot.session or 'Fokus'}' gestoppt"
    return "Bereit"


def main() -> int:
    """Run the wake word detection service."""
    logger = setup_logging(level=logging.INFO)

    # Load typed app configuration and secrets.
    try:
        config_path = resolve_config_path()
        app_config = load_app_config(str(config_path))
        secret_config = load_secret_config()
        logger.info("Loaded runtime config: %s", config_path)
    except AppConfigurationError as error:
        logger.error(f"App configuration error: {error}")
        return 1

    # Load configurations
    try:
        config = WakeWordConfig.from_settings(
            pico_voice_access_key=secret_config.pico_voice_access_key,
            settings=app_config.wake_word,
        )
        stt_config = STTConfig.from_settings(app_config.stt)
    except ConfigurationError as error:
        logger.error(f"Configuration error: {error}")
        return 1

    # Create STT service
    stt_logger = logging.getLogger("stt")
    try:
        stt = FasterWhisperSTT(
            model_size=stt_config.model_size,
            device=stt_config.device,
            compute_type=stt_config.compute_type,
            language=stt_config.language,
            beam_size=stt_config.beam_size,
            vad_filter=stt_config.vad_filter,
            logger=stt_logger,
        )
    except STTError as error:
        logger.error(f"STT initialization error: {error}")
        return 1

    # Optional TTS service
    speech_service: Optional[SpeechService] = None
    if app_config.tts.enabled:
        try:
            tts_config = TTSConfig.from_settings(app_config.tts)
            tts_engine = CoquiTTSEngine(
                config=tts_config,
                logger=logging.getLogger("tts.engine"),
            )
            tts_output = SoundDeviceAudioOutput(
                output_device_index=tts_config.output_device_index,
                logger=logging.getLogger("tts.output"),
            )
            speech_service = SpeechService(
                engine=tts_engine,
                output=tts_output,
                logger=logging.getLogger("tts"),
            )
            logger.info("TTS enabled")
        except (ConfigurationError, TTSError) as error:
            logger.error(f"TTS initialization error: {error}")
            return 1

    # Optional LLM service
    assistant_llm: Optional[PomodoroAssistantLLM] = None
    llm_requested = app_config.llm.enabled
    if llm_requested:
        try:
            llm_config = LLMConfig.from_sources(
                model_dir=app_config.llm.model_path,
                hf_filename=app_config.llm.hf_filename,
                hf_repo_id=app_config.llm.hf_repo_id or None,
                hf_revision=app_config.llm.hf_revision or None,
                hf_token=secret_config.hf_token,
                system_prompt_path=app_config.llm.system_prompt or None,
                n_threads=app_config.llm.n_threads,
                n_ctx=app_config.llm.n_ctx,
                n_batch=app_config.llm.n_batch,
                temperature=app_config.llm.temperature,
                top_p=app_config.llm.top_p,
                repeat_penalty=app_config.llm.repeat_penalty,
                verbose=app_config.llm.verbose,
                logger=logging.getLogger("llm.config"),
            )
            assistant_llm = PomodoroAssistantLLM(llm_config)
            logger.info("LLM enabled (model: %s)", llm_config.model_path)
        except Exception as error:
            logger.error(f"LLM initialization error: {error}")
            return 1
    elif speech_service:
        logger.warning(
            "TTS is enabled but LLM is disabled; no spoken reply will be generated."
        )

    # Optional oracle context providers (sensors/calendar) for LLM environment block
    oracle_service: Optional[OracleContextService] = None
    if assistant_llm:
        try:
            oracle_config = OracleConfig.from_settings(
                app_config.oracle,
                calendar_id=secret_config.oracle_google_calendar_id,
                calendar_service_account_file=secret_config.oracle_google_service_account_file,
            )
            oracle_service = OracleContextService(
                config=oracle_config,
                logger=logging.getLogger("oracle")
            )
        except Exception as error:
            logger.warning("Oracle context disabled due to init error: %s", error)

    def build_llm_environment_context() -> EnvironmentContext:
        payload = {
            "now_local": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "light_level_lux": None,
            "air_quality": None,
            "upcoming_events": None,
        }
        if oracle_service is not None:
            try:
                payload.update(oracle_service.build_environment_payload())
            except Exception as error:
                logger.warning("Failed to collect oracle context: %s", error)

        return EnvironmentContext(
            now_local=payload["now_local"],
            light_level_lux=payload.get("light_level_lux"),
            air_quality=payload.get("air_quality"),
            upcoming_events=payload.get("upcoming_events"),
        )

    # Optional UI server for static page + websocket updates
    ui_server: Optional[UIServer] = None
    ui_server_config: Optional[UIServerConfig] = None
    try:
        ui_server_config = UIServerConfig.from_settings(app_config.ui_server)
    except ServerConfigurationError as error:
        logger.error(f"UI server configuration error: {error}")
        logger.warning("Continuing without UI server.")

    if ui_server_config and ui_server_config.enabled:
        try:
            ui_server = UIServer(
                config=ui_server_config,
                logger=logging.getLogger("ui_server"),
            )
            logger.info("Starting UI server...")
            ui_server.start(timeout_seconds=5.0)
            logger.info(
                "UI server ready at http://%s:%d",
                ui_server.host,
                ui_server.port,
            )
            ui_server.publish_state("idle", message="UI server connected")
        except Exception as error:
            logger.error(f"UI server startup failed: {error}")
            logger.warning("Continuing without UI server.")

    def publish_ui(event_type: str, **payload) -> None:
        if ui_server:
            ui_server.publish(event_type, **payload)

    def publish_ui_state(
        state: str,
        *,
        message: Optional[str] = None,
        **payload,
    ) -> None:
        if ui_server:
            ui_server.publish_state(state, message=message, **payload)

    pomodoro_timer = PomodoroTimer(logger=logging.getLogger("pomodoro"))
    countdown_timer = PomodoroTimer(
        duration_seconds=10 * 60,
        logger=logging.getLogger("timer"),
    )

    def _default_pomodoro_text(action: str, snapshot: PomodoroSnapshot) -> str:
        topic = snapshot.session or "Fokus"
        if action == "start":
            return f"Ich starte jetzt deine Pomodoro Sitzung fuer {topic}."
        if action == "continue":
            return f"Ich setze die Pomodoro Sitzung fuer {topic} fort."
        if action == "pause":
            return f"Ich pausiere die Pomodoro Sitzung fuer {topic}."
        if action == "abort":
            return f"Ich stoppe die Pomodoro Sitzung fuer {topic}."
        if action == "completed":
            return f"Pomodoro abgeschlossen. Gute Arbeit bei {topic}."
        return f"Pomodoro aktualisiert: {topic}."

    def _pomodoro_rejection_text(action: str, reason: str) -> str:
        if reason == "not_running" and action == "pause":
            return "Die Pomodoro Sitzung laeuft gerade nicht."
        if reason == "not_paused" and action == "continue":
            return "Die Pomodoro Sitzung ist nicht pausiert."
        if reason == "not_active" and action == "abort":
            return "Es gibt keine aktive Pomodoro Sitzung."
        return "Die Pomodoro Aktion ist im aktuellen Zustand nicht moeglich."

    def _default_timer_text(action: str, snapshot: PomodoroSnapshot) -> str:
        if action == "start":
            return f"Ich starte den Timer mit {_format_duration(snapshot.duration_seconds)}."
        if action == "continue":
            return "Ich setze den Timer fort."
        if action == "pause":
            return "Ich pausiere den Timer."
        if action == "abort":
            return "Ich stoppe den Timer."
        if action == "reset":
            return "Ich setze den Timer zurueck."
        if action == "completed":
            return "Der Timer ist abgelaufen."
        return "Timer aktualisiert."

    def _timer_rejection_text(action: str, reason: str) -> str:
        if reason == "not_running" and action == "pause":
            return "Der Timer laeuft gerade nicht."
        if reason == "not_paused" and action == "continue":
            return "Der Timer ist nicht pausiert."
        if reason == "not_active" and action == "abort":
            return "Es gibt keinen aktiven Timer."
        return "Die Timer Aktion ist im aktuellen Zustand nicht moeglich."

    def publish_pomodoro_update(
        snapshot: PomodoroSnapshot,
        *,
        action: str,
        accepted: Optional[bool] = None,
        reason: str = "",
        tool_name: Optional[str] = None,
        motivation: Optional[str] = None,
    ) -> None:
        payload: dict[str, Any] = {
            "action": action,
            "phase": snapshot.phase,
            "session": snapshot.session,
            "duration_seconds": snapshot.duration_seconds,
            "remaining_seconds": snapshot.remaining_seconds,
        }
        if accepted is not None:
            payload["accepted"] = accepted
        if reason:
            payload["reason"] = reason
        if tool_name:
            payload["tool_name"] = tool_name
        if motivation:
            payload["motivation"] = motivation
        publish_ui("pomodoro", **payload)

    def publish_timer_update(
        snapshot: PomodoroSnapshot,
        *,
        action: str,
        accepted: Optional[bool] = None,
        reason: str = "",
        tool_name: Optional[str] = None,
        message: Optional[str] = None,
    ) -> None:
        payload: dict[str, Any] = {
            "action": action,
            "phase": snapshot.phase,
            "duration_seconds": snapshot.duration_seconds,
            "remaining_seconds": snapshot.remaining_seconds,
        }
        if accepted is not None:
            payload["accepted"] = accepted
        if reason:
            payload["reason"] = reason
        if tool_name:
            payload["tool_name"] = tool_name
        if message:
            payload["message"] = message
        publish_ui("timer", **payload)

    def _parse_duration_seconds(value: Any, *, default_seconds: int) -> int:
        if isinstance(value, (int, float)) and int(value) > 0:
            return int(value) * 60
        if isinstance(value, str):
            raw = value.strip().lower()
            if raw.isdigit():
                return max(1, int(raw)) * 60
            match = re.search(
                r"(\d{1,4})\s*(s|sek|sekunde|sekunden|m|min|minute|minuten|h|stunde|stunden)",
                raw,
            )
            if match:
                amount = int(match.group(1))
                unit = match.group(2)
                if unit in {"s", "sek", "sekunde", "sekunden"}:
                    return max(1, amount)
                if unit in {"h", "stunde", "stunden"}:
                    return max(1, amount) * 3600
                return max(1, amount) * 60
        return default_seconds

    def _active_runtime_message() -> str:
        pomodoro_snapshot = pomodoro_timer.snapshot()
        if pomodoro_snapshot.phase in {"running", "paused"}:
            return _pomodoro_status_message(pomodoro_snapshot)
        timer_snapshot = countdown_timer.snapshot()
        if timer_snapshot.phase in {"running", "paused"}:
            return _timer_status_message(timer_snapshot)
        return "Listening for wake word"

    def _parse_calendar_datetime(value: Any) -> Optional[dt.datetime]:
        if not isinstance(value, str):
            return None
        raw = value.strip()
        if not raw:
            return None

        raw = raw.replace(" ", "T")
        try:
            parsed = dt.datetime.fromisoformat(raw)
        except ValueError:
            de_match = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})T(\d{1,2}):(\d{2})$", raw)
            if not de_match:
                return None
            day, month, year, hour, minute = de_match.groups()
            parsed = dt.datetime(
                year=int(year),
                month=int(month),
                day=int(day),
                hour=int(hour),
                minute=int(minute),
            )

        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=dt.datetime.now().astimezone().tzinfo)
        return parsed

    def _calendar_window_end(time_range: str) -> dt.datetime:
        now = dt.datetime.now().astimezone()
        lowered = time_range.lower()
        if "uebermorgen" in lowered:
            target = now + dt.timedelta(days=2)
            return target.replace(hour=23, minute=59, second=59, microsecond=0)
        if "morgen" in lowered:
            target = now + dt.timedelta(days=1)
            return target.replace(hour=23, minute=59, second=59, microsecond=0)
        if "naechste woche" in lowered:
            return now + dt.timedelta(days=7)
        days_match = re.search(r"naechste\s+(\d+)\s+tage", lowered)
        if days_match:
            return now + dt.timedelta(days=max(1, int(days_match.group(1))))
        if "heute" in lowered:
            return now.replace(hour=23, minute=59, second=59, microsecond=0)
        return now + dt.timedelta(days=3)

    def _handle_calendar_tool_call(tool_name: str, arguments: dict[str, Any]) -> str:
        if oracle_service is None:
            return "Kalenderfunktion ist derzeit nicht verfuegbar."

        try:
            if tool_name == "show_upcoming_events":
                time_range = str(arguments.get("time_range", "heute")).strip() or "heute"
                now = dt.datetime.now().astimezone()
                window_end = _calendar_window_end(time_range)
                events = oracle_service.list_upcoming_events(
                    max_results=app_config.oracle.google_calendar_max_results * 2,
                    time_min=now,
                )

                filtered: list[dict[str, Any]] = []
                for event in events:
                    start_raw = event.get("start")
                    if not isinstance(start_raw, str):
                        continue
                    parsed_start = _parse_calendar_datetime(start_raw)
                    if parsed_start is None:
                        continue
                    if parsed_start <= window_end:
                        filtered.append(event)

                if not filtered:
                    return f"Es gibt keine anstehenden Termine fuer {time_range}."

                top = filtered[: app_config.oracle.google_calendar_max_results]
                parts = []
                for item in top:
                    summary = str(item.get("summary") or "Ohne Titel")
                    start_time = str(item.get("start") or "ohne Zeit")
                    parts.append(f"{summary} um {start_time}")
                return "Anstehende Termine: " + "; ".join(parts) + "."

            if tool_name == "add_calendar_event":
                title = str(arguments.get("title", "")).strip()
                start_time = _parse_calendar_datetime(arguments.get("start_time"))
                end_time = _parse_calendar_datetime(arguments.get("end_time"))
                duration_seconds = _parse_duration_seconds(
                    arguments.get("duration"),
                    default_seconds=30 * 60,
                )
                if start_time is None:
                    return "Ich konnte den Termin nicht anlegen, weil die Startzeit fehlt oder ungueltig ist."
                if not title:
                    return "Ich konnte den Termin nicht anlegen, weil der Titel fehlt."
                if end_time is None:
                    end_time = start_time + dt.timedelta(seconds=duration_seconds)
                if end_time <= start_time:
                    end_time = start_time + dt.timedelta(seconds=duration_seconds)

                event_id = oracle_service.add_event(
                    title=title,
                    start=start_time,
                    end=end_time,
                )
                return f"Termin angelegt: {title}. Ereignis-ID: {event_id}."
        except Exception as error:
            logger.error("Kalenderaktion fehlgeschlagen (%s): %s", tool_name, error)
            return f"Kalenderaktion fehlgeschlagen: {error}"

        return "Kalenderaktion verarbeitet."

    def handle_pomodoro_tool_call(
        tool_name: str,
        arguments: dict[str, Any],
        assistant_text: str,
    ) -> str:
        action = POMODORO_TOOL_TO_ACTION[tool_name]
        focus_topic_raw = arguments.get("focus_topic")
        focus_topic = (
            str(focus_topic_raw).strip()
            if isinstance(focus_topic_raw, str) and focus_topic_raw.strip()
            else None
        )
        result = pomodoro_timer.apply(action, session=focus_topic)
        if result.accepted:
            response_text = assistant_text.strip() or _default_pomodoro_text(
                action,
                result.snapshot,
            )
        else:
            response_text = _pomodoro_rejection_text(action, result.reason)
        publish_pomodoro_update(
            result.snapshot,
            action=action,
            accepted=result.accepted,
            reason=result.reason,
            tool_name=tool_name,
            motivation=response_text,
        )
        return response_text

    def handle_timer_tool_call(
        tool_name: str,
        arguments: dict[str, Any],
        assistant_text: str,
    ) -> str:
        action = TIMER_TOOL_TO_ACTION[tool_name]
        if action == "start":
            duration_seconds = _parse_duration_seconds(
                arguments.get("duration"),
                default_seconds=10 * 60,
            )
            result = countdown_timer.apply(
                action,
                session="Timer",
                duration_seconds=duration_seconds,
            )
        else:
            result = countdown_timer.apply(action, session="Timer")

        if result.accepted:
            response_text = assistant_text.strip() or _default_timer_text(
                action,
                result.snapshot,
            )
        else:
            response_text = _timer_rejection_text(action, result.reason)
        publish_timer_update(
            result.snapshot,
            action=action,
            accepted=result.accepted,
            reason=result.reason,
            tool_name=tool_name,
            message=response_text,
        )
        return response_text

    def handle_tool_call(tool_call: dict[str, Any], assistant_text: str) -> str:
        raw_name = tool_call.get("name")
        if not isinstance(raw_name, str):
            return assistant_text
        raw_arguments = tool_call.get("arguments")
        arguments = raw_arguments if isinstance(raw_arguments, dict) else {}

        if raw_name in POMODORO_TOOL_TO_ACTION:
            return handle_pomodoro_tool_call(raw_name, arguments, assistant_text)
        if raw_name in TIMER_TOOL_TO_ACTION:
            return handle_timer_tool_call(raw_name, arguments, assistant_text)
        if raw_name in CALENDAR_TOOLS:
            return _handle_calendar_tool_call(raw_name, arguments)

        logger.warning("Unsupported tool call: %s", raw_name)
        return assistant_text

    def handle_pomodoro_tick(tick: PomodoroTick) -> None:
        if tick.completed:
            completion_message = _default_pomodoro_text("completed", tick.snapshot)
            publish_pomodoro_update(
                tick.snapshot,
                action="completed",
                accepted=True,
                reason="completed",
                motivation=completion_message,
            )
            publish_ui("assistant_reply", state="replying", text=completion_message)
            if speech_service:
                try:
                    speech_service.speak(completion_message)
                except TTSError as error:
                    logger.error("TTS completion playback failed: %s", error)
            return

        publish_pomodoro_update(
            tick.snapshot,
            action="tick",
            accepted=True,
            reason="tick",
        )

    def handle_timer_tick(tick: PomodoroTick) -> None:
        if tick.completed:
            completion_message = _default_timer_text("completed", tick.snapshot)
            publish_timer_update(
                tick.snapshot,
                action="completed",
                accepted=True,
                reason="completed",
                message=completion_message,
            )
            publish_ui("assistant_reply", state="replying", text=completion_message)
            if speech_service:
                try:
                    speech_service.speak(completion_message)
                except TTSError as error:
                    logger.error("TTS timer completion playback failed: %s", error)
            return

        publish_timer_update(
            tick.snapshot,
            action="tick",
            accepted=True,
            reason="tick",
        )

    def publish_idle_state() -> None:
        publish_ui_state("idle", message=_active_runtime_message())

    publish_pomodoro_update(
        pomodoro_timer.snapshot(),
        action="sync",
        accepted=True,
        reason="startup",
    )
    publish_timer_update(
        countdown_timer.snapshot(),
        action="sync",
        accepted=True,
        reason="startup",
    )

    # Create wake word service
    event_queue: Queue = Queue()
    publisher = QueueEventPublisher(event_queue)
    service: Optional[WakeWordService] = None
    wake_word_logger = logging.getLogger("wake_word")

    try:
        service = WakeWordService(
            config=config,
            publisher=publisher,
            logger=wake_word_logger,
        )

        setup_signal_handlers(service)

        logger.info("Starting wake word service...")
        service.start()

        # Wait for service to be ready (with fast-fail on crash)
        logger.debug("Initializing wake word detection...")
        if not wait_for_service_ready(service, timeout=10.0):
            # Check if service crashed vs. timed out
            if not service.is_running:
                logger.error("Service crashed during initialization.")
            else:
                logger.error("Service initialization timed out.")

            return 1

        logger.info("Ready! Listening for wake word ...")
        publish_idle_state()

        # Main event loop
        while True:
            pomodoro_tick = pomodoro_timer.poll()
            if pomodoro_tick is not None:
                handle_pomodoro_tick(pomodoro_tick)

            timer_tick = countdown_timer.poll()
            if timer_tick is not None:
                handle_timer_tick(timer_tick)

            try:
                event = event_queue.get(timeout=0.25)
            except Empty:
                if not service.is_running:
                    logger.error("Service stopped unexpectedly")
                    publish_ui(
                        "error",
                        state="error",
                        message="Wake word service stopped unexpectedly",
                    )
                    return 1
                continue

            if isinstance(event, WakeWordDetectedEvent):
                print(f"[{event.occurred_at.isoformat()}] 🎤 WakeWordDetectedEvent\n")
                publish_ui_state("listening", message="Wake word detected")

            elif isinstance(event, UtteranceCapturedEvent):
                utterance = event.utterance
                print(
                    f"[{utterance.created_at.isoformat()}] ✓ UtteranceCapturedEvent: "
                    f"{utterance.duration_seconds:.2f}s, {len(utterance.audio_bytes):,} bytes\n"
                )
                publish_ui_state(
                    "transcribing",
                    message="Transcribing utterance",
                    duration_seconds=round(utterance.duration_seconds, 2),
                    audio_bytes=len(utterance.audio_bytes),
                )

                # Transcribe the utterance
                print("  ⏳ Transcribing...\n", end="", flush=True)
                try:
                    result = stt.transcribe(utterance)
                    if result.text:
                        confidence_str = (
                            f" (confidence: {result.confidence:.0%})"
                            if result.confidence
                            else ""
                        )
                        print(f'\r  💬 "{result.text}"{confidence_str}\n')
                        publish_ui(
                            "transcript",
                            state="transcribing",
                            text=result.text,
                            language=result.language,
                            confidence=result.confidence,
                        )

                        if assistant_llm:
                            publish_ui_state("thinking", message="Generating reply")
                            try:
                                env_context = build_llm_environment_context()
                                llm_response = assistant_llm.run(
                                    result.text,
                                    env=env_context,
                                )
                                assistant_text = llm_response["assistant_text"].strip()
                                tool_call = llm_response.get("tool_call")
                                if isinstance(tool_call, dict):
                                    assistant_text = handle_tool_call(
                                        tool_call,
                                        assistant_text,
                                    ).strip()

                                if assistant_text:
                                    print(f'  🤖 "{assistant_text}"\n')
                                    publish_ui(
                                        "assistant_reply",
                                        state="replying",
                                        text=assistant_text,
                                    )
                                if speech_service and assistant_text:
                                    speech_service.speak(assistant_text)
                                publish_idle_state()
                            except TTSError as error:
                                logger.error(f"TTS playback failed: {error}")
                                publish_ui(
                                    "error",
                                    state="error",
                                    message=f"TTS playback failed: {error}",
                                )
                                publish_idle_state()
                            except Exception as error:
                                logger.error(f"LLM processing failed: {error}")
                                publish_ui(
                                    "error",
                                    state="error",
                                    message=f"LLM processing failed: {error}",
                                )
                                publish_idle_state()
                        else:
                            publish_idle_state()
                    else:
                        print("\r  ⚠️  No speech detected\n")
                        publish_ui_state("idle", message="No speech detected")
                except STTError as error:
                    logger.error(f"Transcription failed: {error}")
                    publish_ui(
                        "error",
                        state="error",
                        message=f"Transcription failed: {error}",
                    )
                    publish_idle_state()

            elif isinstance(event, WakeWordErrorEvent):
                logger.error(
                    f"WakeWordErrorEvent: {event.message}", exc_info=event.exception
                )
                publish_ui(
                    "error",
                    state="error",
                    message=f"WakeWordErrorEvent: {event.message}",
                )
                return 1

    except KeyboardInterrupt:
        print("\n👋 Shutting down...\n")
        return 0

    except Exception as error:
        logger.error(f"Unexpected error: {error}", exc_info=True)
        return 1

    finally:
        if service:
            logger.info("Stopping service...")
            try:
                service.stop(timeout_seconds=5.0)
            except Exception as error:
                logger.error(f"Error stopping service: {error}", exc_info=True)
        if ui_server:
            logger.info("Stopping UI server...")
            try:
                ui_server.stop(timeout_seconds=5.0)
            except Exception as error:
                logger.error(f"Error stopping UI server: {error}", exc_info=True)


if __name__ == "__main__":
    sys.exit(main())
