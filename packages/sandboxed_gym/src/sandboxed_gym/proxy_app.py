# Copyright (c) 2026, NVIDIA CORPORATION.  All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Local FastAPI proxy: /health and /rollouts/run → Gym host."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from sandboxed_gym.orchestrator import SandboxedGymSession


LOGGER = logging.getLogger(__name__)

AUTH_HEADER = "X-Sandboxed-Gym-Token"


def build_proxy_app(session: SandboxedGymSession) -> FastAPI:
    """Proxy Gym host endpoints; optionally require ``rollout_auth_token``."""
    app = FastAPI(title="sandboxed-gym-orchestrator", version="0.1.0")
    expected = session.cfg.rollout_auth_token

    def _check_auth(token: str | None) -> None:
        if expected is None:
            return
        if not token or token != expected:
            raise HTTPException(status_code=401, detail="unauthorized")

    @app.get("/health")
    def health(
        x_sandboxed_gym_token: str | None = Header(default=None, alias=AUTH_HEADER),
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        bearer = None
        if authorization and authorization.lower().startswith("bearer "):
            bearer = authorization[7:].strip()
        _check_auth(x_sandboxed_gym_token or bearer)
        request = urllib.request.Request(
            session.host.health_url,
            method="GET",
            headers=dict(session.host.headers),
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            raise HTTPException(status_code=exc.code, detail=exc.read().decode()) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        try:
            return json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            return {"status": "unknown", "raw": body.decode("utf-8", errors="replace")}

    @app.post("/rollouts/run")
    async def rollouts_run(
        request: Request,
        x_sandboxed_gym_token: str | None = Header(default=None, alias=AUTH_HEADER),
        authorization: str | None = Header(default=None),
    ) -> Response:
        bearer = None
        if authorization and authorization.lower().startswith("bearer "):
            bearer = authorization[7:].strip()
        _check_auth(x_sandboxed_gym_token or bearer)

        payload = await request.body()
        max_req = session.cfg.sandbox.max_request_bytes
        if len(payload) > max_req:
            raise HTTPException(status_code=413, detail="request too large")

        upstream = urllib.request.Request(
            session.host.rollout_url,
            data=payload,
            method="POST",
            headers={
                "Content-Type": request.headers.get("content-type", "application/json"),
                **session.host.headers,
            },
        )
        try:
            with urllib.request.urlopen(
                upstream, timeout=session.cfg.sandbox.rollout_timeout_s
            ) as response:
                body = response.read()
                status = response.status
                content_type = response.headers.get("Content-Type", "application/json")
        except urllib.error.HTTPError as exc:
            return Response(
                content=exc.read(),
                status_code=exc.code,
                media_type="application/json",
            )
        except Exception as exc:
            LOGGER.exception("upstream rollout failed")
            return JSONResponse(status_code=502, content={"error": str(exc)})

        if len(body) > session.cfg.sandbox.max_response_bytes:
            raise HTTPException(status_code=502, detail="upstream response too large")
        return Response(content=body, status_code=status, media_type=content_type)

    @app.get("/session")
    def session_info(
        x_sandboxed_gym_token: str | None = Header(default=None, alias=AUTH_HEADER),
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        bearer = None
        if authorization and authorization.lower().startswith("bearer "):
            bearer = authorization[7:].strip()
        _check_auth(x_sandboxed_gym_token or bearer)
        desc = session.descriptor(mode="orchestrator", orchestrator_url=session.orchestrator_url)
        data = desc.model_dump(mode="json")
        # Do not echo broker token on the public session endpoint unless authenticated
        # with the rollout token (already checked when expected is set).
        return data

    return app
