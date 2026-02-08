import json
import os
from datetime import datetime, timezone

import requests


PROMPT_FILE = os.path.join("engine", "prompt.txt")
SCHEMA_FILE = os.path.join("engine", "schema.json")


def _load_prompt():
    with open(PROMPT_FILE, "r", encoding="utf-8") as f:
        return f.read().strip()


def _load_schema():
    with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _parse_iso(value):
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _minutes_since(iso_time):
    dt = _parse_iso(iso_time)
    if not dt:
        return None
    now = datetime.now(timezone.utc)
    diff = now - dt.astimezone(timezone.utc)
    return int(diff.total_seconds() / 60)


def _build_recent_summary(recent_events):
    last_feeding_minutes = None
    last_diaper_minutes = None
    last_sleep_minutes = None
    last_sleep_duration = None

    for event in recent_events:
        category = event.get("category")
        if category == "feeding" and last_feeding_minutes is None:
            last_feeding_minutes = _minutes_since(event.get("occurred_at"))
        elif category == "diaper" and last_diaper_minutes is None:
            last_diaper_minutes = _minutes_since(event.get("occurred_at"))
        elif category == "sleep" and last_sleep_minutes is None:
            last_sleep_minutes = _minutes_since(event.get("occurred_at"))
            payload = event.get("payload", {})
            if isinstance(payload, dict):
                duration = payload.get("duration_min")
                if isinstance(duration, (int, float)):
                    last_sleep_duration = int(duration)

    return {
        "last_feeding_minutes_ago": last_feeding_minutes,
        "last_diaper_minutes_ago": last_diaper_minutes,
        "last_sleep_minutes_ago": last_sleep_minutes,
        "last_sleep_duration_min": last_sleep_duration
    }


def _collect_recent_guidance(recent_events, limit=3):
    guidance = []
    for event in recent_events:
        if event.get("category") != "crying":
            continue
        payload = event.get("payload", {})
        if not isinstance(payload, dict):
            continue
        ai_guidance = payload.get("ai_guidance")
        if not ai_guidance:
            continue
        guidance.append(
            {
                "event_id": event.get("id"),
                "occurred_at": event.get("occurred_at"),
                "ai_guidance": ai_guidance,
            }
        )
        if len(guidance) >= limit:
            break
    return guidance


def _extract_json(text):
    if not text:
        return None
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    snippet = text[start:end + 1]
    try:
        return json.loads(snippet)
    except json.JSONDecodeError:
        return None


def _validate_output(payload):
    if not isinstance(payload, dict):
        return False, "Output is not a JSON object."
    required_top = [
        "most_likely_cause",
        "alternative_causes",
        "recommended_actions",
        "caregiver_notice",
        "confidence_level"
    ]
    for key in required_top:
        if key not in payload:
            return False, f"Missing field: {key}"
    mlc = payload.get("most_likely_cause")
    if not isinstance(mlc, dict):
        return False, "most_likely_cause must be object"
    for key in ("label", "confidence", "reasoning"):
        if key not in mlc:
            return False, f"most_likely_cause missing {key}"
    if not isinstance(payload.get("alternative_causes"), list):
        return False, "alternative_causes must be list"
    if not isinstance(payload.get("recommended_actions"), list):
        return False, "recommended_actions must be list"
    return True, ""


def _call_gemini(prompt, user_input, api_key, api_endpoint):
    if not api_key:
        return None, "GEMINI_API_KEY not set"
    if not api_endpoint:
        return None, "GEMINI_API_ENDPOINT not set"

    headers = {"Content-Type": "application/json"}
    if "key=" not in api_endpoint:
        api_endpoint = f"{api_endpoint}?key={api_key}"

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {"text": json.dumps(user_input, ensure_ascii=False)}
                ]
            }
        ]
    }
    try:
        response = requests.post(api_endpoint, json=payload, headers=headers, timeout=20)
        if response.status_code >= 400:
            return None, f"Gemini HTTP {response.status_code}"
        data = response.json()
    except Exception as exc:
        return None, f"Gemini request failed: {exc}"

    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        return None, "Gemini response parse failed"

    return text, ""


def run_reasoning(current_event, recent_events):
    prompt = _load_prompt()
    schema = _load_schema()

    audio_analysis = {}
    payload = current_event.get("payload", {})
    if isinstance(payload, dict):
        audio_analysis = payload.get("audio_analysis") or {}

    user_input = {
        "current_event": {
            "type": "crying",
            "time": current_event.get("occurred_at"),
            "audio_analysis": audio_analysis
        },
        "recent_care_summary": _build_recent_summary(recent_events),
        "recent_ai_guidance": _collect_recent_guidance(recent_events),
        "constraints": {
            "no_medical_advice": True,
            "tone": "supportive",
            "target_audience": "caregiver"
        }
    }

    api_key = os.getenv("GEMINI_API_KEY", "")
    api_endpoint = os.getenv("GEMINI_API_ENDPOINT", "")
    raw_text, error = _call_gemini(prompt, user_input, api_key, api_endpoint)
    if error:
        return None, {
            "error": error,
            "schema": schema,
            "input": user_input
        }

    parsed = _extract_json(raw_text)
    if parsed is None:
        return None, {
            "error": "Gemini output is not valid JSON",
            "raw_text": raw_text
        }

    ok, message = _validate_output(parsed)
    if not ok:
        return None, {
            "error": message,
            "raw_output": parsed
        }

    return parsed, None
