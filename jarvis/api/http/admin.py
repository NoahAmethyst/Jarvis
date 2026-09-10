"""Token-protected model administration, shared by all service replicas."""

import os
import secrets
import hashlib
import json
import asyncio
from threading import BoundedSemaphore
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from jarvis.llm import _base_llm, runtime
from jarvis.llm.errors import LLMError

router = APIRouter()
bearer = HTTPBearer(auto_error=False)
STATIC = Path(__file__).with_name("static")
catalog_slots = BoundedSemaphore(2)
CATALOG_DEADLINE = 15


def authorize(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    expected = os.getenv("JARVIS_ADMIN_TOKEN", "")
    if not expected or not runtime.enabled():
        raise HTTPException(503, "Model administration is disabled")
    if credentials is None or not secrets.compare_digest(
        credentials.credentials.encode(), expected.encode()
    ):
        raise HTTPException(401, "Invalid administrator token", headers={"WWW-Authenticate": "Bearer"})


@router.get("/admin/models", include_in_schema=False)
def page():
    return FileResponse(STATIC / "models.html", headers={
        "Cache-Control": "no-store",
        "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
        "Referrer-Policy": "no-referrer",
    })


@router.get("/admin/assets/{name}", include_in_schema=False)
def asset(name: str):
    if name not in {"models.js", "models.css", "reload.svg"}:
        raise HTTPException(404)
    return FileResponse(STATIC / name)


class ModelUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=0)
    config_version: str = Field(min_length=64, max_length=64)
    models: dict[str, str] = Field(max_length=50)


def config_version():
    data = _base_llm().settings.model_dump_json()
    return hashlib.sha256(data.encode()).hexdigest()


def snapshot(revision, models):
    base = _base_llm().settings
    effective = runtime.apply_overrides(base, models)
    return {
        "revision": revision,
        "config_version": config_version(),
        "providers": {name: {"adapter": p.adapter, "tools": p.capabilities.tools,
                             "thinking": p.capabilities.thinking}
                      for name, p in base.providers.items()},
        "profiles": {name: {"model": p.model, "default_model": base.profiles[name].model,
                            "tools": p.tools, "thinking": p.thinking.mode}
                     for name, p in effective.profiles.items()},
    }


@router.get("/admin/api/models", dependencies=[Depends(authorize)])
def get_models():
    try:
        return snapshot(*runtime.read_overrides())
    except LLMError:
        raise HTTPException(503, "Model configuration unavailable") from None


@router.put("/admin/api/models", dependencies=[Depends(authorize)])
def update_models(body: ModelUpdate):
    try:
        base = _base_llm().settings
        if body.config_version != config_version():
            raise HTTPException(409, "Base configuration changed; reload before saving")
        if body.models and set(body.models) != set(base.profiles):
            raise HTTPException(400, "Supply all profiles or an empty mapping to restore defaults")
        effective = runtime.apply_overrides(base, body.models)
        for profile in effective.profiles.values():
            provider = base.providers[profile.model.split("/", 1)[0]]
            if not os.getenv(provider.api_key_env, ""):
                raise HTTPException(400, "Selected provider credential is missing")
        result = snapshot(body.revision + 1, body.models)
        runtime.save_overrides(body.revision, body.models)
        return result
    except runtime.RevisionConflict:
        raise HTTPException(409, "Configuration changed; reload before saving") from None
    except LLMError as error:
        from jarvis.llm.errors import LLMUnavailableError
        code = 503 if isinstance(error, LLMUnavailableError) else 400
        raise HTTPException(code, str(error)) from None


@router.get("/admin/api/providers/{name}/models", dependencies=[Depends(authorize)])
async def provider_models(name: str):
    provider = _base_llm().settings.providers.get(name)
    if provider is None:
        raise HTTPException(404, "Unknown provider")
    if provider.adapter == "anthropic":
        raise HTTPException(400, "Enter this provider's model ID manually")
    key = os.getenv(provider.api_key_env, "")
    url = (os.getenv(provider.base_url_env, "") if provider.base_url_env else "") or provider.base_url
    if not key or not url:
        raise HTTPException(503, "Provider is not configured")
    if not catalog_slots.acquire(blocking=False):
        raise HTTPException(429, "Model discovery is busy; try again later")
    try:
        async with asyncio.timeout(CATALOG_DEADLINE):
            async with httpx.AsyncClient(timeout=httpx.Timeout(10, connect=3), follow_redirects=False) as client:
                async with client.stream("GET", url.rstrip("/") + "/models",
                                         headers={"Authorization": f"Bearer {key}"}) as response:
                    if response.status_code != 200:
                        raise ValueError("provider error")
                    data = bytearray()
                    async for chunk in response.aiter_bytes(8192):
                        data.extend(chunk)
                        if len(data) > 262144:
                            raise ValueError("catalog too large")
                    catalog = json.loads(data)["data"]
                    ids = sorted({item["id"] for item in catalog if isinstance(item.get("id"), str)})
                    return {"models": ids}
    except (httpx.HTTPError, TimeoutError, ValueError, KeyError, TypeError, AttributeError):
        raise HTTPException(502, "Model list unavailable; enter a model ID manually") from None
    finally:
        catalog_slots.release()
