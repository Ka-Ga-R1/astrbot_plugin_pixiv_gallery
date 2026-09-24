"""Minimal, credential-free client for Lolicon API v2 candidate discovery."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


class LoliconAPIError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class LoliconCandidate:
    uid: int
    pid: int


def _positive_id(value: Any) -> int | None:
    if type(value) is int and value > 0:
        return value
    if isinstance(value, str) and value.isascii() and value.isdigit():
        parsed = int(value)
        return parsed if parsed > 0 else None
    return None


class LoliconClient:
    API_URL = "https://api.lolicon.app/setu/v2"

    def __init__(
        self,
        *,
        timeout: float = 20,
        proxy: str = "",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.timeout = timeout
        self.proxy = proxy
        self.transport = transport

    async def find_random(self, tags: list[str]) -> LoliconCandidate | None:
        normalized = [tag.strip() for tag in tags if isinstance(tag, str) and tag.strip()][:2]
        if not normalized:
            return None
        params = [("r18", "0"), ("num", "1")]
        params.extend(("tag", tag) for tag in normalized)
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                proxy=self.proxy or None,
                transport=self.transport,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                response = await client.get(
                    self.API_URL, params=params, headers={"Accept": "application/json"}
                )
        except (httpx.HTTPError, OSError):
            raise LoliconAPIError("Lolicon network request failed") from None
        except Exception:
            raise LoliconAPIError("Lolicon request failed") from None
        if not 200 <= response.status_code < 300:
            raise LoliconAPIError(
                "Lolicon returned an unsuccessful HTTP status", status_code=response.status_code
            )
        try:
            payload = response.json()
        except (ValueError, UnicodeDecodeError):
            raise LoliconAPIError("Lolicon returned invalid JSON") from None
        if not isinstance(payload, dict):
            raise LoliconAPIError("Lolicon returned an invalid response")
        if payload.get("error"):
            raise LoliconAPIError("Lolicon reported an API error")
        data = payload.get("data")
        if not isinstance(data, list):
            raise LoliconAPIError("Lolicon returned invalid candidate data")
        if not data:
            return None
        record = data[0]
        if not isinstance(record, dict):
            raise LoliconAPIError("Lolicon returned an invalid candidate")
        uid = _positive_id(record.get("uid"))
        pid = _positive_id(record.get("pid"))
        if uid is None or pid is None:
            raise LoliconAPIError("Lolicon candidate did not include valid Pixiv IDs")
        # Deliberately discard Lolicon image URLs; image delivery must use Pixiv originals.
        return LoliconCandidate(uid=uid, pid=pid)
