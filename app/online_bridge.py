from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class OnlineBridgeError(RuntimeError):
    status_code: int
    detail: Any

    def __str__(self) -> str:
        return f"epinnox-online returned {self.status_code}: {self.detail}"


async def request_json(
    base_url: str | None,
    cookie: str,
    method: str,
    path: str,
    *,
    json: dict[str, Any] | None = None,
    timeout: float = 20.0,
) -> Any:
    if not base_url:
        raise OnlineBridgeError(503, "EPINNOX_ONLINE_BASE_URL is not configured")
    headers = {"cookie": cookie} if cookie else {}
    async with httpx.AsyncClient(base_url=base_url.rstrip("/"), headers=headers, timeout=timeout) as client:
        response = await client.request(method, path, json=json)
    if response.status_code >= 400:
        try:
            body = response.json()
            detail = body.get("detail", body) if isinstance(body, dict) else body
        except Exception:
            detail = response.text or response.reason_phrase
        raise OnlineBridgeError(response.status_code, detail)
    if not response.content:
        return None
    return response.json()


async def list_accounts(base_url: str | None, cookie: str) -> list[dict[str, Any]]:
    rows = await request_json(base_url, cookie, "GET", "/api/exchange-accounts")
    return rows if isinstance(rows, list) else []


async def activate_account(base_url: str | None, cookie: str, account_id: str) -> dict[str, Any]:
    result = await request_json(base_url, cookie, "POST", f"/api/exchange-accounts/{account_id}/activate")
    return result if isinstance(result, dict) else {"ok": True, "active_account_id": account_id}


async def account_snapshot(base_url: str | None, cookie: str) -> dict[str, Any]:
    result = await request_json(base_url, cookie, "GET", "/api/account/snapshot")
    return result if isinstance(result, dict) else {}


async def paper_state(base_url: str | None, cookie: str) -> dict[str, Any]:
    result = await request_json(base_url, cookie, "GET", "/api/account/paper-state")
    return result if isinstance(result, dict) else {}
