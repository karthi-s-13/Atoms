# Realtime Server

FastAPI + WebSocket bridge for the traffic digital twin.

Responsibilities:

- own the authoritative simulation clock
- tick the engine at `0.016` seconds
- broadcast snapshots to connected clients
- accept runtime control messages
- expose `/health` and `/ws`

Run:

```powershell
.\.venv\Scripts\python.exe -m pip install -r realtime_server\requirements.txt
.\.venv\Scripts\python.exe -m uvicorn realtime_server.main:app --reload --host 0.0.0.0 --port 8000
```
