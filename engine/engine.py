"""
Care Reasoning Engine design notes:
- AI guidance is assistive and probabilistic.
- User feedback is not treated as ground truth.
- The system prioritizes stability over AI completeness.
"""

import base64
import json
import os
import time
from datetime import datetime, timezone

import requests


PROMPT_FILE = os.path.join("engine", "prompt.txt")
SCHEMA_FILE = os.path.join("engine", "schema.json")
CAUSE_LABELS = ("hunger", "discomfort", "emotional_need", "unknown")


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
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
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
        "last_sleep_duration_min": last_sleep_duration,
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
        if not isinstance(ai_guidance, dict):
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


def _is_probability(value):
    return isinstance(value, (int, float)) and 0 <= value <= 1


def _normalize_inference(inference):
    normalized = {label: 0.0 for label in CAUSE_LABELS}
    if isinstance(inference, dict):
        for label in CAUSE_LABELS:
            value = inference.get(label)
            if isinstance(value, (int, float)) and value >= 0:
                normalized[label] = float(value)
    total = sum(normalized.values())
    if total <= 0:
        normalized = {label: 0.0 for label in CAUSE_LABELS}
        normalized["unknown"] = 1.0
    else:
        for label in normalized:
            normalized[label] = round(normalized[label] / total, 4)
    return normalized


def _validate_audio_analysis(payload):
    if not isinstance(payload, dict):
        return False, "audio_analysis must be an object"
    transcription = payload.get("transcription")
    if transcription is not None and not isinstance(transcription, str):
        return False, "audio_analysis.transcription must be a string"
    inference = payload.get("inference")
    if not isinstance(inference, dict):
        return False, "audio_analysis.inference must be an object"
    has_prob = any(_is_probability(inference.get(label)) for label in CAUSE_LABELS)
    if not has_prob:
        return False, "audio_analysis.inference must include probability values in [0,1]"
    return True, ""


def _validate_guidance_output(payload):
    if not isinstance(payload, dict):
        return False, "Guidance output is not a JSON object."
    required_top = [
        "most_likely_cause",
        "alternative_causes",
        "recommended_actions",
        "caregiver_notice",
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
    if not _is_probability(mlc.get("confidence")):
        return False, "most_likely_cause.confidence must be a number in [0, 1]"
    if not isinstance(payload.get("alternative_causes"), list):
        return False, "alternative_causes must be list"
    for item in payload.get("alternative_causes", []):
        if not isinstance(item, dict):
            return False, "alternative_causes items must be object"
        if "confidence" not in item:
            return False, "alternative_causes confidence missing"
        if not _is_probability(item.get("confidence")):
            return False, "alternative_causes confidence must be number in [0, 1]"
    if not isinstance(payload.get("recommended_actions"), list):
        return False, "recommended_actions must be list"
    return True, ""


def _derive_confidence_level(score):
    if score >= 0.75:
        return "high"
    if score >= 0.45:
        return "medium"
    return "low"


def _has_limited_context(recent_summary, recent_events):
    if not recent_events:
        return True
    key_fields = [
        "last_feeding_minutes_ago",
        "last_diaper_minutes_ago",
        "last_sleep_minutes_ago",
    ]
    missing = 0
    for key in key_fields:
        if recent_summary.get(key) is None:
            missing += 1
    return missing >= 2


def _apply_prior_blend(guidance, learned_priors):
    if not isinstance(learned_priors, dict):
        return guidance
    most_likely = guidance.get("most_likely_cause")
    if not isinstance(most_likely, dict):
        return guidance
    label = most_likely.get("label")
    prior = learned_priors.get(label)
    confidence = most_likely.get("confidence")
    if not _is_probability(prior) or not _is_probability(confidence):
        return guidance
    blended = round((0.7 * confidence) + (0.3 * prior), 4)
    most_likely["confidence"] = blended
    guidance["most_likely_cause"] = most_likely
    guidance["prior_weight"] = {
        "label": label,
        "prior": prior,
        "strategy": "0.7_model + 0.3_feedback_prior",
    }
    return guidance


def _finalize_guidance(payload, recent_summary, recent_events, learned_priors):
    payload = _apply_prior_blend(payload, learned_priors)
    confidence = payload["most_likely_cause"]["confidence"]
    payload["confidence_level"] = _derive_confidence_level(confidence)
    if _has_limited_context(recent_summary, recent_events):
        payload["uncertainty_note"] = "Limited recent care data available"
    else:
        payload.pop("uncertainty_note", None)
    return payload


def _build_output_contract():
    return (
        "Return JSON only with exactly two top-level keys: "
        "`audio_analysis` and `ai_guidance`.\n"
        "`audio_analysis` must include `transcription` and `inference` "
        "with probabilities in [0,1] for hunger, discomfort, emotional_need, unknown.\n"
        "`ai_guidance` must include: most_likely_cause(label, confidence, reasoning), "
        "alternative_causes(list of label+confidence), recommended_actions(list), "
        "caregiver_notice."
    )


def _call_gemini(prompt, user_input, api_key, api_endpoint, audio_bytes=None, audio_mime_type=None):
    request_mode = "multimodal" if audio_bytes else "text_contextual"
    if not api_key:
        return None, {
            "model_name": "gemini-3",
            "latency_ms": 0,
            "request_mode": request_mode,
        }, "GEMINI_API_KEY not set"
    if not api_endpoint:
        return None, {
            "model_name": "gemini-3",
            "latency_ms": 0,
            "request_mode": request_mode,
        }, "GEMINI_API_ENDPOINT not set"

    headers = {"Content-Type": "application/json"}
    if "key=" not in api_endpoint:
        api_endpoint = f"{api_endpoint}?key={api_key}"

    parts = [
        {"text": prompt},
        {"text": json.dumps(user_input, ensure_ascii=False)},
    ]
    if audio_bytes:
        parts.append(
            {
                "inlineData": {
                    "mimeType": audio_mime_type or "audio/wav",
                    "data": base64.b64encode(audio_bytes).decode("ascii"),
                }
            }
        )

    request_payload = {"contents": [{"role": "user", "parts": parts}]}
    start = time.perf_counter()
    model_name = "gemini-3"
    try:
        response = requests.post(
            api_endpoint,
            json=request_payload,
            headers=headers,
            timeout=30,
        )
        latency_ms = int((time.perf_counter() - start) * 1000)
        meta = {
            "model_name": model_name,
            "latency_ms": latency_ms,
            "request_mode": request_mode,
        }
        if response.status_code >= 400:
            return None, meta, f"Gemini HTTP {response.status_code}: {response.text[:300]}"
        data = response.json()
        model_name = data.get("modelVersion") or data.get("model") or model_name
        meta["model_name"] = model_name
    except Exception as exc:
        latency_ms = int((time.perf_counter() - start) * 1000)
        return None, {
            "model_name": model_name,
            "latency_ms": latency_ms,
            "request_mode": request_mode,
        }, f"Gemini request failed: {exc}"

    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        return None, meta, "Gemini response parse failed"

    return text, meta, ""


def run_reasoning(
    current_event,
    recent_events,
    audio_bytes=None,
    audio_mime_type=None,
    learned_priors=None,
):
    prompt = _load_prompt()
    schema = _load_schema()

    payload = current_event.get("payload", {})
    if not isinstance(payload, dict):
        payload = {}
    recent_summary = _build_recent_summary(recent_events)

    user_input = {
        "current_event": {
            "type": "crying",
            "time": current_event.get("occurred_at"),
        },
        "recent_care_summary": recent_summary,
        "recent_ai_guidance": _collect_recent_guidance(recent_events),
        "learned_priors": learned_priors or {},
        "constraints": {
            "no_medical_advice": True,
            "tone": "supportive",
            "target_audience": "caregiver",
        },
    }
    if not audio_bytes:
        user_input["current_event"]["audio_analysis"] = payload.get("audio_analysis") or {}

    full_prompt = f"{prompt}\n\n{_build_output_contract()}"
    api_key = os.getenv("GEMINI_API_KEY", "")
    api_endpoint = os.getenv("GEMINI_API_ENDPOINT", "")
    raw_text, ai_meta, error = _call_gemini(
        full_prompt,
        user_input,
        api_key,
        api_endpoint,
        audio_bytes=audio_bytes,
        audio_mime_type=audio_mime_type,
    )
    if error:
        return None, {
            "error": error,
            "schema": schema,
            "input": user_input,
            "ai_meta": ai_meta,
        }

    parsed = _extract_json(raw_text)
    if parsed is None:
        return None, {
            "error": "Gemini output is not valid JSON",
            "raw_text": raw_text,
            "ai_meta": ai_meta,
        }

    audio_analysis = parsed.get("audio_analysis")
    ai_guidance = parsed.get("ai_guidance")

    # Backward compatibility: if model returns guidance-only shape.
    if not isinstance(ai_guidance, dict) and isinstance(parsed.get("most_likely_cause"), dict):
        ai_guidance = parsed
    if not isinstance(audio_analysis, dict):
        audio_analysis = payload.get("audio_analysis") or {}

    ok, message = _validate_audio_analysis(audio_analysis)
    if not ok:
        return None, {
            "error": message,
            "raw_output": parsed,
            "ai_meta": ai_meta,
        }

    ok, message = _validate_guidance_output(ai_guidance)
    if not ok:
        return None, {
            "error": message,
            "raw_output": parsed,
            "ai_meta": ai_meta,
        }

    normalized_analysis = {
        "transcription": audio_analysis.get("transcription", ""),
        "inference": _normalize_inference(audio_analysis.get("inference")),
    }
    finalized_guidance = _finalize_guidance(
        ai_guidance,
        recent_summary,
        recent_events,
        learned_priors or {},
    )

    return {
        "audio_analysis": normalized_analysis,
        "ai_guidance": finalized_guidance,
        "ai_meta": ai_meta,
    }, None
