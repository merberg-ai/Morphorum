"""Bounded, read-only Civitai model detail and version metadata."""
from __future__ import annotations

import os
from .civitai_auth import get_token
from typing import Any
import httpx

from .civitai_search import CivitaiSearchError, MAX_RESPONSE_BYTES
from .settings import load_settings
from .civitai import _plain_html
from html.parser import HTMLParser

class _ReadableHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0
    def handle_starttag(self, tag, attrs):
        if tag in ('style', 'script'): self.hidden += 1
        if tag in ('p', 'div', 'h1', 'h2', 'h3', 'li', 'br'): self.parts.append('\n')
        if tag == 'li': self.parts.append('• ')
    def handle_endtag(self, tag):
        if tag in ('style', 'script'): self.hidden = max(0, self.hidden - 1)
        if tag in ('p', 'div', 'h1', 'h2', 'h3', 'li'): self.parts.append('\n')
    def handle_data(self, data):
        if not self.hidden and sum(map(len,self.parts)) < 5000: self.parts.append(data)

def _readable(text):
    parser = _ReadableHTML()
    parser.feed(str(text or '')[:30000])
    return '\n'.join(' '.join(line.split()) for line in ''.join(parser.parts).split('\n') if line.strip())[:5000]


def model_details(model_id: int, *, client: httpx.Client | None = None) -> dict[str, Any]:
    settings = load_settings().get("civitai", {})
    if not settings.get("enabled", False):
        raise CivitaiSearchError("Civitai Hub is disabled.", 403)
    if not isinstance(model_id, int) or not 0 < model_id <= 2_147_483_647:
        raise CivitaiSearchError("Invalid Civitai model ID.", 422)
    headers = {"Accept": "application/json", "User-Agent": "Morphorum/0.1 (model details)"}
    token = get_token()
    if token:
        headers["Authorization"] = "Bearer " + token
    owned = client is None
    if owned:
        client = httpx.Client(timeout=15.0, trust_env=False, follow_redirects=False)
    try:
        with client.stream("GET", f"https://civitai.com/api/v1/models/{model_id}", headers=headers) as response:
            if response.status_code == 404:
                raise CivitaiSearchError("Model not found on Civitai.", 404)
            if response.status_code == 429:
                raise CivitaiSearchError("Civitai rate limit reached.", 429)
            if response.status_code >= 400:
                raise CivitaiSearchError(f"Civitai detail request failed (HTTP {response.status_code}).", 502)
            chunks, size = [], 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > MAX_RESPONSE_BYTES:
                    raise CivitaiSearchError("Civitai model detail exceeded size limit.", 502)
                chunks.append(chunk)
        import json
        data = json.loads(b"".join(chunks))
        if not isinstance(data, dict) or data.get("id") != model_id:
            raise CivitaiSearchError("Unexpected Civitai model detail response.", 502)
        if data.get("nsfw") and not settings.get("allow_mature", False):
            raise CivitaiSearchError("This model is hidden by mature-content settings.", 403)
        creator = data.get("creator") if isinstance(data.get("creator"), dict) else {}
        versions = []
        for version in (data.get("modelVersions") or [])[:40]:
            if not isinstance(version, dict) or not isinstance(version.get("id"), int):
                continue
            images = []
            if settings.get("load_previews", True):
                for image in (version.get("images") or [])[:16]:
                    if not isinstance(image, dict) or not isinstance(image.get("url"), str):
                        continue
                    if not image["url"].startswith("https://"):
                        continue
                    # The gallery can include video previews; the local cache serves images only.
                    if str(image.get("type") or "image").lower() not in ("image", ""):
                        continue
                    mature = image.get("nsfw") not in (None, False, "None", "Soft")
                    if not settings.get("allow_mature", False) and mature:
                        continue
                    images.append({"url": image["url"], "width": image.get("width"),
                                   "height": image.get("height"), "mature": mature})
            files = []
            for file in (version.get("files") or [])[:30]:
                if not isinstance(file, dict):
                    continue
                hashes = file.get("hashes") if isinstance(file.get("hashes"), dict) else {}
                files.append({"id": file.get("id"), "name": str(file.get("name") or "")[:180], "size_kb": file.get("sizeKB"),
                              "format": str((file.get("metadata") or {}).get("format") or "")[:40] if isinstance(file.get("metadata"), dict) else "",
                              "sha256": str(hashes.get("SHA256") or "")[:64]})
            base = str(version.get("baseModel") or "")[:100]
            supported = base in ("SDXL 1.0", "SDXL Turbo", "SDXL Lightning", "Flux.1 D", "Flux.1 S", "ZImageTurbo")
            versions.append({"id": version["id"], "name": str(version.get("name") or "")[:150],
                             "base_model": base, "created_at": str(version.get("createdAt") or "")[:40],
                             "trained_words": [str(x)[:100] for x in (version.get("trainedWords") or [])[:32] if isinstance(x, str)],
                             "description": _readable(version.get("description")),
                             "images": images, "files": files,
                             "compatibility": "Potentially compatible; verify file format and loader" if supported else "Not established for Morphorum"})
        return {"id": model_id, "name": str(data.get("name") or "")[:200],
                "type": str(data.get("type") or "")[:60],
                "creator": str(creator.get("username") or "")[:100],
                "description": _readable(data.get("description")),
                "tags": [str(t)[:80] for t in (data.get("tags") or [])[:40] if isinstance(t, str)],
                "url": f"https://civitai.com/models/{model_id}",
                "versions": versions}
    except (httpx.RequestError, httpx.TimeoutException) as exc:
        raise CivitaiSearchError("Civitai model details unavailable; check network.", 502) from exc
    except (ValueError, UnicodeError) as exc:
        if isinstance(exc, CivitaiSearchError):
            raise
        raise CivitaiSearchError("Invalid Civitai detail response.", 502) from exc
    finally:
        if owned:
            client.close()
