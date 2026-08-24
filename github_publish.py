from __future__ import annotations

import base64
import json
import logging
from datetime import datetime
from io import BytesIO

import httpx

from config import GITHUB_API, GITHUB_BRANCH, GITHUB_ENABLED, GITHUB_HEADERS, GITHUB_REPO, GITHUB_SITE_PATH

logger = logging.getLogger(__name__)


async def gh_get_sha(path: str) -> str | None:
    if not GITHUB_ENABLED:
        return None
    url = f"{GITHUB_API}/repos/{GITHUB_REPO}/contents/{path}"
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(url, headers=GITHUB_HEADERS, params={"ref": GITHUB_BRANCH})
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json().get("sha")


async def gh_put_file(path: str, content: bytes, message: str) -> None:
    if not GITHUB_ENABLED:
        return
    url = f"{GITHUB_API}/repos/{GITHUB_REPO}/contents/{path}"
    sha = await gh_get_sha(path)
    payload = {
        "message": message,
        "content": base64.b64encode(content).decode(),
        "branch": GITHUB_BRANCH,
    }
    if sha:
        payload["sha"] = sha
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.put(url, headers=GITHUB_HEADERS, json=payload)
        resp.raise_for_status()


async def publish_schedule_to_github(day: str, images: list[BytesIO], pdf_hash: str, link: str) -> None:
    if not GITHUB_ENABLED:
        return
    base = f"{GITHUB_SITE_PATH}/{day}"
    for index, img in enumerate(images):
        img.seek(0)
        data = img.read()
        img.seek(0)
        await gh_put_file(f"{base}/page-{index + 1}.png", data, f"update {day} page {index + 1}")
    manifest = {
        "day": day,
        "hash": pdf_hash,
        "pages": len(images),
        "link": link,
        "ext": "png",
        "updated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    await gh_put_file(
        f"{base}/manifest.json",
        json.dumps(manifest, ensure_ascii=True, indent=2).encode("utf-8"),
        f"update {day} manifest",
    )
