# web_ui module

## Purpose
Static browser UIs served by `src/server` for runtime state visualization.

## Key files
- `jarvis/`: futuristic HUD-style interface.
- `miro/`: character-style interface with state-driven animations.

## Configuration
Selected by `ui_server.ui` in `config.toml` (`jarvis` or `miro`).

## Integration notes
- Each UI consumes websocket events from `/ws`.
- Static assets are served by `src/server/service.py` from the chosen UI directory.
