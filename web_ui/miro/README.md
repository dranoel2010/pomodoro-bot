# web_ui.miro module

## Purpose
MIRO character UI variant with expressive runtime-state animations.

## Key files
- `index.html`: face/stage layout with pomodoro and timer overlays.
- `styles.css`: theme, animation, and responsive layout rules.
- `app.js`: websocket client, state mapping, and animation control.

## Configuration
No direct module configuration.
Selected through `ui_server.ui = "miro"`.

## Integration notes
- Reacts to runtime state and timer events to switch character behavior.
- Supports pomodoro and timer overlays with local countdown rendering.
