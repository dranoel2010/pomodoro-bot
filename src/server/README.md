# server module

## Purpose
Built-in HTTP + websocket server that serves the selected UI and streams runtime events.

## Key files
- `config.py`: UI server config and path resolution.
- `service.py`: threaded asyncio server implementation.
- `events.py`: event serialization and sticky event cache.
- `static_files.py`: static file resolution and content type helpers.
- `ui_server.py`: standalone launch script.

## Configuration
From `config.toml` (`[ui_server]`):
- `enabled`
- `host`
- `port`
- `ui`
- `index_file`

## Integration notes
- Serves `/`, `/index.html`, `/healthz`, and `/ws`.
- Sticky event replay sends last known state to newly connected clients.
- Runtime calls `publish_state`/`publish` without blocking the main loop.
