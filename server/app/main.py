"""Tiny FastAPI service that mints fresh Cloudflare Realtime TURN credentials.

Microspeed's frontend is a static build, so any TURN credentials baked into
the JS leak to whoever downloads the page. Cloudflare solves this by issuing
*ephemeral* credentials with a max TTL of 48h, but then the frontend would
need a redeploy every 48h. Instead, this service keeps the long-lived
Cloudflare API token on the server side and hands out fresh short-lived TURN
credentials on demand through `GET /ice-servers`. The frontend calls it
once at startup before creating the Peer.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware


def _load_local_config() -> dict:
    """Load TURN credentials from a local JSON file if present.

    This is the fallback for deployments where proper secret management
    isn't available (e.g. Fly.io without flyctl access). The file is
    gitignored; it's baked into the container image at build time.
    """
    candidates = [
        Path("/app/turn_config.json"),
        Path(__file__).resolve().parent.parent / "turn_config.json",
    ]
    for candidate in candidates:
        try:
            if candidate.is_file():
                return json.loads(candidate.read_text())
        except Exception:
            continue
    return {}


_local = _load_local_config()
TURN_TOKEN_ID = (os.environ.get("TURN_TOKEN_ID") or _local.get("token_id") or "").strip()
TURN_API_TOKEN = (os.environ.get("TURN_API_TOKEN") or _local.get("api_token") or "").strip()
TTL_SECONDS = int(os.environ.get("TURN_TTL_SECONDS", str(60 * 60 * 2)))  # 2h

CLOUDFLARE_ENDPOINT = (
    "https://rtc.live.cloudflare.com/v1/turn/keys/"
    f"{TURN_TOKEN_ID}/credentials/generate"
)

app = FastAPI(title="Microspeed TURN credentials")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # static site with no credentials -> wildcard OK
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/healthz")
async def healthz() -> dict[str, bool]:
    return {"ok": True}


@app.get("/ice-servers")
async def ice_servers() -> dict[str, list[dict]]:
    if not TURN_TOKEN_ID or not TURN_API_TOKEN:
        raise HTTPException(status_code=500, detail="TURN credentials not configured.")

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            CLOUDFLARE_ENDPOINT,
            headers={"Authorization": f"Bearer {TURN_API_TOKEN}"},
            json={"ttl": TTL_SECONDS},
        )

    if resp.status_code not in (200, 201):
        raise HTTPException(
            status_code=502,
            detail=f"Cloudflare TURN API returned {resp.status_code}: {resp.text}",
        )

    data = resp.json()
    cf_entry = data.get("iceServers") or {}
    urls = cf_entry.get("urls") or []
    username = cf_entry.get("username") or ""
    credential = cf_entry.get("credential") or ""

    # Split Cloudflare's single entry into STUN-only (no auth) + TURN (authed)
    # so every RTCIceServer entry has credentials only where it needs them.
    stun_urls = [u for u in urls if u.startswith("stun:")]
    turn_urls = [u for u in urls if u.startswith(("turn:", "turns:"))]

    entries: list[dict] = []
    if stun_urls:
        entries.append({"urls": stun_urls})
    if turn_urls:
        entries.append(
            {
                "urls": turn_urls,
                "username": username,
                "credential": credential,
            }
        )

    return {"iceServers": entries}
