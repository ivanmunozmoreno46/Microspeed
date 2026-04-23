# Microspeed TURN credentials server

Tiny FastAPI service that mints fresh Cloudflare Realtime TURN credentials for
the Microspeed frontend on demand, so credentials never need to be baked into
the static build.

## Endpoints

- `GET /healthz` — liveness probe.
- `GET /ice-servers` — returns `{ "iceServers": [...] }` in WebRTC
  `RTCIceServer[]` shape, ready to be passed to `new RTCPeerConnection` or
  `new Peer(id, { config: { iceServers } })`.

## Environment variables

- `TURN_TOKEN_ID` (required) — Cloudflare Realtime TURN Token ID.
- `TURN_API_TOKEN` (required) — Cloudflare Realtime TURN API Token.
- `TURN_TTL_SECONDS` (optional, default `7200`) — credential lifetime in
  seconds. Must be ≤ 172800 (48h, Cloudflare max).

## Local run

```bash
cd server
python -m venv .venv && source .venv/bin/activate
pip install -e .
TURN_TOKEN_ID=... TURN_API_TOKEN=... \
    uvicorn app.main:app --host 0.0.0.0 --port 8000
curl http://localhost:8000/ice-servers
```

## Deployment

Deployed to Fly.io via Devin's `deploy backend` tool (auto-generates Dockerfile
and `fly.toml`). Secrets are stored in Fly.io's secret manager, never committed
to git.
