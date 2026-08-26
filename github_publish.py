from __future__ import annotations

import base64
import json
import logging
from datetime import UTC, datetime

import httpx

from config import (
    GITHUB_API,
    GITHUB_BRANCH,
    GITHUB_ENABLED,
    GITHUB_REPO,
    GITHUB_SITE_PATH,
    github_headers,
)

logger = logging.getLogger(__name__)


class GithubPublisher:
    def __init__(self, enabled: bool = GITHUB_ENABLED) -> None:
        self.enabled = enabled
        self._client: httpx.AsyncClient | None = None

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=f"{GITHUB_API}/repos/{GITHUB_REPO}/contents/",
                headers=github_headers(),
                timeout=httpx.Timeout(30.0, connect=10.0),
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    async def _get_sha(self, path: str) -> str | None:
        client = await self._http()
        resp = await client.get(path, params={"ref": GITHUB_BRANCH})
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json().get("sha")

    async def put_file(self, path: str, content: bytes, message: str) -> None:
        if not self.enabled:
            return
        client = await self._http()
        payload = {
            "message": message,
            "content": base64.b64encode(content).decode(),
            "branch": GITHUB_BRANCH,
        }
        sha = await self._get_sha(path)
        if sha:
            payload["sha"] = sha
        resp = await client.put(path, json=payload)
        resp.raise_for_status()

    async def publish_day(self, day: str, pages: list[bytes], pdf_hash: str, link: str) -> None:
        if not self.enabled:
            return
        base = f"{GITHUB_SITE_PATH}/{day}"
        for index, page in enumerate(pages, start=1):
            await self.put_file(f"{base}/page-{index}.png", page, f"update {day} page {index}")
        manifest = {
            "day": day,
            "hash": pdf_hash,
            "pages": len(pages),
            "link": link,
            "ext": "png",
            "updated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        await self.put_file(
            f"{base}/manifest.json",
            json.dumps(manifest, ensure_ascii=True, indent=2).encode(),
            f"update {day} manifest",
        )
        logger.info("github: опубликован %s (%s стр.)", day, len(pages))

