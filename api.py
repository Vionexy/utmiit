import asyncio
import hashlib
import time
import os
from io import BytesIO
import base64

import fitz
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

SCHEDULE_FILES = {
    "monday":    {"id": "1d7xrNLd8qpde_5jLvBdJjG9e3eOsjohK", "link": "https://drive.google.com/file/d/1d7xrNLd8qpde_5jLvBdJjG9e3eOsjohK/view"},
    "tuesday":   {"id": "1qHNHC7uwXdECuEMfDoPiuv5bX0Ip0OpQ", "link": "https://drive.google.com/file/d/1qHNHC7uwXdECuEMfDoPiuv5bX0Ip0OpQ/view"},
    "wednesday": {"id": "1hWMqMdeU2rcrNMx4jbOCr5ofGixsIJwA", "link": "https://drive.google.com/file/d/1hWMqMdeU2rcrNMx4jbOCr5ofGixsIJwA/view"},
    "thursday":  {"id": "1O649rLM_VuBO31VF49noXfp1Evr-XfCN", "link": "https://drive.google.com/file/d/1O649rLM_VuBO31VF49noXfp1Evr-XfCN/view"},
    "friday":    {"id": "1YmQGiirdBryJlI3tx0SdU-g1gGm-6AaW", "link": "https://drive.google.com/file/d/1YmQGiirdBryJlI3tx0SdU-g1gGm-6AaW/view"},
    "saturday":  {"id": "1hkXSDN-Dz86QGeyjhLZ7jlvSd9sMwmex", "link": "https://drive.google.com/file/d/1hkXSDN-Dz86QGeyjhLZ7jlvSd9sMwmex/view"},
}

CACHE_TTL  = 300
PDF_DPI    = 150
IMG_MAX_PX = 2000

_cache: dict = {}
_locks: dict = {day: asyncio.Lock() for day in SCHEDULE_FILES}


def _cache_valid(day: str) -> bool:
    e = _cache.get(day)
    return bool(e and time.time() - e["ts"] < CACHE_TTL)


async def download_pdf(file_id: str) -> bytes:
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/pdf"}
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=40, follow_redirects=True) as c:
                r = await c.get(url, headers=headers)
                if r.status_code == 429:
                    await asyncio.sleep(2 ** attempt)
                    continue
                r.raise_for_status()
                if r.content[:4] == b"%PDF":
                    return r.content
                raise ValueError("Ответ не является PDF")
        except Exception as e:
            if attempt == 2:
                raise RuntimeError(f"Не удалось скачать PDF: {e}")
            await asyncio.sleep(2 ** attempt)
    raise RuntimeError("Не удалось скачать PDF")


def pdf_to_images_b64(pdf_bytes: bytes) -> list[str]:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    result = []
    for i in range(len(doc)):
        pix = doc.load_page(i).get_pixmap(dpi=PDF_DPI)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        if img.width > IMG_MAX_PX or img.height > IMG_MAX_PX:
            img.thumbnail((IMG_MAX_PX, IMG_MAX_PX), Image.Resampling.LANCZOS)
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=88, optimize=True)
        result.append(base64.b64encode(buf.getvalue()).decode())
    doc.close()
    return result


async def get_schedule_data(day: str) -> dict:
    if _cache_valid(day):
        return _cache[day]
    async with _locks[day]:
        if _cache_valid(day):
            return _cache[day]
        pdf = await download_pdf(SCHEDULE_FILES[day]["id"])
        imgs = pdf_to_images_b64(pdf)
        _cache[day] = {"images": imgs, "hash": hashlib.sha256(pdf).hexdigest(), "pages": len(imgs), "ts": time.time()}
        print(f"[api] {day}: {len(imgs)} стр.")
        return _cache[day]


app = FastAPI()

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])


@app.get("/health")
async def health():
    return {"status": "ok", "cached_days": list(_cache.keys())}


@app.get("/api/schedule/{day}")
async def get_schedule(day: str):
    if day not in SCHEDULE_FILES:
        raise HTTPException(404, f"День '{day}' не найден")
    try:
        data = await get_schedule_data(day)
        return JSONResponse({"day": day, "pages": data["pages"], "hash": data["hash"],
                             "images": data["images"], "link": SCHEDULE_FILES[day]["link"]})
    except Exception as e:
        print(f"[api] ошибка {day}: {e}")
        raise HTTPException(502, f"Не удалось загрузить расписание: {e}")


@app.get("/api/schedule/{day}/hash")
async def get_schedule_hash(day: str):
    if day not in SCHEDULE_FILES:
        raise HTTPException(404, f"День '{day}' не найден")
    if _cache_valid(day):
        return {"day": day, "hash": _cache[day]["hash"], "cached": True}
    try:
        data = await get_schedule_data(day)
        return {"day": day, "hash": data["hash"], "cached": False}
    except Exception as e:
        raise HTTPException(502, str(e))


# Раздаём static ПОСЛЕ API-роутов — иначе "/" перехватит все запросы
app.mount("/", StaticFiles(directory="static", html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=False, log_level="info")