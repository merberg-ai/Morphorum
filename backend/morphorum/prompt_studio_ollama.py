"""PS4: bounded, opt-in loopback/private-LAN Ollama storyboard suggestions.

No render, project, draft, filesystem or model-manager mutation. The LLM only
provides scene text. Native integer frame placement and validation live here.
"""
from __future__ import annotations

import ipaddress
import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

import httpx

from .prompt_studio_drafts import PromptDraftError, _validate_tracks
from .loras import LORA_TAG

DEFAULT_ENDPOINT = "http://127.0.0.1:11434"
MAX_RESPONSE_BYTES = 256 * 1024
MAX_MODELS_BYTES = 128 * 1024
SUPPORTED_FAMILIES = ("sdxl", "flux", "zimage")
_MODEL_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:/+-]{0,160}$")


class OllamaStoryError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def endpoint_url(raw: Any, allow_lan: bool = False) -> str:
    if not isinstance(raw, str) or len(raw) > 200:
        raise OllamaStoryError("Ollama endpoint must be a short HTTP URL.")
    value = raw.strip() or DEFAULT_ENDPOINT
    try:
        parsed = urlsplit(value)
        hostname, port = parsed.hostname, parsed.port
    except ValueError as exc:
        raise OllamaStoryError("Invalid Ollama host or port.") from exc
    if (parsed.scheme != "http" or not hostname or parsed.username is not None or
            parsed.password is not None or parsed.path not in ("", "/") or
            parsed.query or parsed.fragment or not 1 <= (port or 11434) <= 65535):
        raise OllamaStoryError("Use http://localhost:11434 or an explicitly allowed private LAN IP; no credentials, paths or query strings.")
    if hostname == "localhost":
        if allow_lan:
            pass
    else:
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError as exc:
            raise OllamaStoryError("Use a numeric private LAN IP or localhost; DNS names are not supported.") from exc
        if address.is_loopback:
            pass
        elif not allow_lan:
            raise OllamaStoryError("Enable the LAN opt-in before connecting to a private network host.")
        elif not (
            address in ipaddress.ip_network("10.0.0.0/8") or
            address in ipaddress.ip_network("172.16.0.0/12") or
            address in ipaddress.ip_network("192.168.0.0/16") or
            address in ipaddress.ip_network("fc00::/7")
        ):
            raise OllamaStoryError("Only loopback and explicitly enabled private LAN addresses are supported.")
    host = f"[{hostname}]" if ":" in hostname else hostname
    return f"http://{host}:{port or 11434}"


def model_id(name: Any) -> str:
    if not isinstance(name, str) or not _MODEL_NAME.fullmatch(name) or len(name) > 160:
        raise OllamaStoryError("Select a valid installed Ollama model.")
    return name


def validate_story_request(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise OllamaStoryError("Storyboard request must be a JSON object.")
    mode = payload.get("mode", "create")
    if mode not in ("create", "refine"):
        raise OllamaStoryError("Choose Create Storyboard or Refine Existing Prompts.")
    idea = payload.get("idea", "")
    if not isinstance(idea, str) or not 8 <= len(idea.strip()) <= 6000:
        raise OllamaStoryError("Provide a story or direction of 8–6000 characters.")
    family = payload.get("family")
    if family not in SUPPORTED_FAMILIES:
        raise OllamaStoryError("Selected project model family must be SDXL, FLUX or Z-Image.")
    frames, fps = payload.get("max_frames"), payload.get("fps")
    if type(frames) is not int or not 1 <= frames <= 1_000_000 or (
            type(fps) not in (float, int) or not 1 <= fps <= 240):
        raise OllamaStoryError("The project frame count/FPS are invalid.")
    tracks = payload.get("tracks")
    try:
        tracks = _validate_tracks(tracks, frames, "tracks")
    except PromptDraftError as exc:
        raise OllamaStoryError(str(exc)) from exc
    scenes = payload.get("scene_count", 4)
    if type(scenes) is not int or not 1 <= scenes <= 16:
        raise OllamaStoryError("Scene count must be between 1 and 16.")
    if mode == "refine":
        points = tracks["positive"]["keyframes"]
        if len(points) > 16:
            raise OllamaStoryError("Refine supports at most 16 existing positive keyframes per request.")
        scene_frames = [point["frame"] for point in points]
    else:
        if scenes > frames:
            raise OllamaStoryError("Scene count exceeds the number of available frames.")
        scene_frames = [(i * frames) // scenes for i in range(scenes)]
    negatives = payload.get("include_negative", False)
    if type(negatives) is not bool:
        raise OllamaStoryError("Negative prompt generation must be enabled explicitly.")
    return {
        "idea": idea.strip(), "mode": mode, "family": family, "max_frames": frames,
        "fps": float(fps), "tracks": tracks, "scene_frames": scene_frames,
        "include_negative": negatives, "model": model_id(payload.get("model")),
        "endpoint": endpoint_url(payload.get("endpoint", DEFAULT_ENDPOINT),
                                 payload.get("allow_lan") is True),
    }


def _prompt_messages(plan: dict[str, Any]) -> list[dict[str, str]]:
    family = plan["family"]
    profile = {
        "sdxl": "Use clear visual attributes and subjects. Avoid claiming fixed CLIP token limits.",
        "flux": "Use coherent concrete visual scenes and motion progression; no special CFG claims.",
        "zimage": "Use concise, concrete visual prompts suitable for Z-Image Turbo; avoid CFG or negative-support promises.",
    }[family]
    existing = [
        {"frame": p["frame"], "positive": p["value"]}
        for p in plan["tracks"]["positive"]["keyframes"]
    ] if plan["mode"] == "refine" else []
    system = (
        "You write cinematic still-image prompts for a frame-keyframed local animation app. "
        "Respond ONLY with one JSON object {\"scenes\":[{\"title\":\"...\","
        "\"positive\":\"...\",\"negative\":\"...\"}]}. "
        "Produce exactly the requested number of scenes in order. The server, not you, assigns frames. "
        "Never output frame indices, LoRA <lora:...> directives, file paths, commands, "
        "Python, code, formulas, model settings or markdown. Describe scene progression, "
        "subject consistency, lighting, visual style and composition. "
        "Output text only in scene fields; if negatives are disabled use empty negative strings. "
        + profile
    )
    user = json.dumps({
        "task": plan["mode"], "story": plan["idea"],
        "model_family": family, "fps": plan["fps"],
        "total_frames": plan["max_frames"], "scene_count": len(plan["scene_frames"]),
        "scene_duration_frames": [
            (plan["scene_frames"][i + 1] if i + 1 < len(plan["scene_frames"])
             else plan["max_frames"]) - frame
            for i, frame in enumerate(plan["scene_frames"])
        ],
        "include_negative": plan["include_negative"],
        "existing_positive": existing,
        "instructions": ("Refine the scene descriptions without adding or modifying LoRA directives. "
                         "Existing original LoRA tags are retained by the app after generation."
                         if plan["mode"] == "refine" else
                         "Invent coherent consecutive visual scenes from the idea."),
    }, ensure_ascii=False)
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


async def _http_json(endpoint: str, route: str, *, body: dict | None = None,
                     byte_limit: int = MAX_RESPONSE_BYTES, timeout: float = 150) -> dict:
    method = "POST" if body is not None else "GET"
    try:
        async with httpx.AsyncClient(trust_env=False, follow_redirects=False,
                                     timeout=httpx.Timeout(timeout, connect=4)) as client:
            async with client.stream(method, endpoint + route, json=body) as response:
                if response.status_code != 200:
                    if response.status_code in (301, 302, 303, 307, 308):
                        raise OllamaStoryError("Ollama redirects are refused.", 502)
                    if response.status_code == 404:
                        raise OllamaStoryError("Ollama model/API not found. Check the model is installed.", 502)
                    raise OllamaStoryError(f"Ollama returned HTTP {response.status_code}.", 502)
                chunks = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(chunks) + len(chunk) > byte_limit:
                        raise OllamaStoryError("Ollama response exceeded the allowed size.", 502)
                    chunks.extend(chunk)
        result = json.loads(chunks.decode("utf-8"))
        if not isinstance(result, dict):
            raise ValueError("not an object")
        return result
    except OllamaStoryError:
        raise
    except httpx.TimeoutException as exc:
        raise OllamaStoryError("Ollama timed out. Try a smaller model or fewer scenes.", 504) from exc
    except httpx.RequestError as exc:
        raise OllamaStoryError("Cannot reach the selected Ollama host. Check that Ollama is running and LAN access is enabled.", 503) from exc
    except (ValueError, UnicodeError) as exc:
        raise OllamaStoryError("Ollama returned invalid JSON.", 502) from exc


async def models(payload: dict) -> dict:
    endpoint = endpoint_url(payload.get("endpoint", DEFAULT_ENDPOINT),
                            payload.get("allow_lan") is True)
    response = await _http_json(endpoint, "/api/tags", byte_limit=MAX_MODELS_BYTES,
                                timeout=12)
    rows = response.get("models")
    if not isinstance(rows, list):
        raise OllamaStoryError("Ollama model-list response is malformed.", 502)
    available = []
    for record in rows[:200]:
        if not isinstance(record, dict):
            continue
        name = record.get("name")
        try:
            valid = model_id(name)
        except OllamaStoryError:
            continue
        details = record.get("details") or {}
        if not isinstance(details, dict):
            details = {}
        available.append({"name": valid, "size": record.get("size") if type(record.get("size")) is int else None,
                          "family": str(details.get("family") or "")[:80],
                          "parameter_size": str(details.get("parameter_size") or "")[:80]})
    return {"models": available, "endpoint": endpoint, "capabilities_note":
            "Text model list only. Vision and structured-output quality are not verified."}


def compile_result(plan: dict, raw: dict) -> dict:
    scenes = raw.get("scenes")
    if not isinstance(scenes, list) or len(scenes) != len(plan["scene_frames"]):
        raise OllamaStoryError("Ollama returned the wrong number of scenes. Nothing was applied.", 422)
    proposed = deepcopy(plan["tracks"])
    if plan["mode"] == "create":
        proposed["positive"]["keyframes"] = []
    generated_negative = []
    overview = []
    warnings = []
    source_points = plan["tracks"]["positive"]["keyframes"]
    for i, (scene, frame) in enumerate(zip(scenes, plan["scene_frames"])):
        if not isinstance(scene, dict) or (
                not set(scene).issubset({"title", "positive", "negative"}) or
                not isinstance(scene.get("positive"), str) or
                not 1 <= len(scene["positive"].strip()) <= 4000 or
                not isinstance(scene.get("negative", ""), str) or
                len(scene.get("negative", "")) > 2000 or
                not isinstance(scene.get("title", ""), str) or
                len(scene.get("title", "")) > 120):
            raise OllamaStoryError(f"Scene {i + 1} has missing, invalid or oversized text.", 422)
        positive = scene["positive"].strip()
        negative = scene.get("negative", "").strip()
        if "<lora" in positive.lower() or "<lora" in negative.lower():
            raise OllamaStoryError("Ollama attempted to add LoRA directives. No changes were applied.", 422)
        if plan["mode"] == "refine":
            # Preserve exact user-authored LoRA token bytes from original frame.
            tokens = [match.group(0) for match in LORA_TAG.finditer(source_points[i]["value"])]
            if tokens:
                positive = " ".join(tokens) + ", " + positive
                warnings.append("Existing LoRA tags were preserved verbatim and placed before refined scene text.")
        if len(positive) > 32768:
            raise OllamaStoryError("Refined prompt exceeds the native text limit.", 422)
        entry = {"frame": frame, "value": positive}
        if plan["mode"] == "refine":
            proposed["positive"]["keyframes"][i] = entry
        else:
            proposed["positive"]["keyframes"].append(entry)
        if plan["include_negative"]:
            generated_negative.append({"frame": frame, "value": negative})
        overview.append({
            "frame": frame, "time_seconds": round(frame / plan["fps"], 3),
            "title": scene.get("title", "").strip() or f"Scene {i+1}",
            "positive": positive, "negative": negative if plan["include_negative"] else "",
        })
    if plan["include_negative"]:
        proposed["negative"]["keyframes"] = generated_negative
    try:
        proposed = _validate_tracks(proposed, plan["max_frames"], "generated_tracks")
    except PromptDraftError as exc:
        raise OllamaStoryError("Generated prompt tracks failed native validation: " + str(exc), 422) from exc
    provenance = {
        "provider": "ollama", "model": plan["model"],
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": plan["mode"], "scene_count": len(overview), "family": plan["family"],
        "profile": "ps4-generic-v1",
    }
    return {"tracks": proposed, "scenes": overview,
            "warnings": sorted(set(warnings)), "provenance": provenance}


async def generate(payload: dict) -> dict:
    plan = validate_story_request(payload)
    answer = await _http_json(plan["endpoint"], "/api/chat", body={
        "model": plan["model"], "messages": _prompt_messages(plan),
        "stream": False, "format": "json",
        "options": {"temperature": 0.45, "num_predict": 4096},
        "keep_alive": "0",
    }, timeout=150)
    content = (answer.get("message") or {}).get("content") if isinstance(answer.get("message"), dict) else None
    if not isinstance(content, str) or len(content) > MAX_RESPONSE_BYTES:
        raise OllamaStoryError("Ollama returned no valid structured text.", 502)
    try:
        raw = json.loads(content)
    except (ValueError, TypeError) as exc:
        raise OllamaStoryError("Ollama did not return valid JSON scenes. Try another model.", 422) from exc
    if not isinstance(raw, dict) or set(raw) != {"scenes"}:
        raise OllamaStoryError("Ollama returned an unsupported scene schema.", 422)
    return compile_result(plan, raw)
