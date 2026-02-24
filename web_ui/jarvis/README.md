# web_ui.jarvis module

## Purpose
JARVIS-themed status dashboard for runtime, pomodoro, and timer events.

## Key files
- `index.html`: HUD markup and status panels.
- `styles.css`: visual theme and animations.
- `app.js`: websocket client and UI state reducer.

## Configuration
No direct module configuration.
Selected through `ui_server.ui = "jarvis"`.

## Integration notes
- Consumes `state_update`, `pomodoro`, `timer`, `transcript`, `assistant_reply`, and `error` events.
- Maintains local timer anchors to render countdown movement between websocket updates.
