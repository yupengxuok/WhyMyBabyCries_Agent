import json
import os
from datetime import datetime

DEFAULT_PRIORS = {
    "hunger": 0.25,
    "discomfort": 0.25,
    "emotional_need": 0.25,
    "unknown": 0.25,
}


def _load_memory(memory_file):
    if not os.path.exists(memory_file):
        return {}
    with open(memory_file, "r", encoding="utf-8") as f:
        content = f.read().strip()
        if not content:
            return {}
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {}


def _save_memory(memory_file, data):
    with open(memory_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _normalize(priors):
    total = sum(value for value in priors.values() if isinstance(value, (int, float)))
    if total <= 0:
        return dict(DEFAULT_PRIORS)
    normalized = {}
    for key, value in priors.items():
        score = value if isinstance(value, (int, float)) else 0.0
        normalized[key] = round(score / total, 4)
    return normalized


def _parse_iso(value):
    if not value:
        return None
    try:
        if isinstance(value, str) and value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _time_bucket(occurred_at):
    dt = _parse_iso(occurred_at)
    if not dt:
        return "day"
    hour = dt.hour
    return "night" if hour >= 20 or hour < 6 else "day"


def _merge_prior_values(source):
    merged = dict(DEFAULT_PRIORS)
    if not isinstance(source, dict):
        return merged
    for key, value in source.items():
        if key in merged and isinstance(value, (int, float)):
            merged[key] = max(0.0, value)
    return merged


def load_reasoning_priors(memory_file, occurred_at=None):
    data = _load_memory(memory_file)
    bucket = _time_bucket(occurred_at)

    bucket_priors = data.get("reasoning_priors_buckets")
    if isinstance(bucket_priors, dict):
        selected = bucket_priors.get(bucket)
        merged = _merge_prior_values(selected)
        return _normalize(merged)

    # Backward compatibility with previous flat storage.
    priors = data.get("reasoning_priors")
    merged = _merge_prior_values(priors)
    return _normalize(merged)


def update_reasoning_priors(memory_file, event, feedback):
    if not isinstance(feedback, dict):
        return None

    helpful = feedback.get("helpful")
    if not isinstance(helpful, bool):
        return None

    payload = event.get("payload", {})
    if not isinstance(payload, dict):
        return None
    ai_guidance = payload.get("ai_guidance")
    if not isinstance(ai_guidance, dict):
        return None
    most_likely = ai_guidance.get("most_likely_cause")
    if not isinstance(most_likely, dict):
        return None
    label = most_likely.get("label")
    if label not in DEFAULT_PRIORS:
        return None

    data = _load_memory(memory_file)
    bucket = _time_bucket(event.get("occurred_at"))
    buckets = data.get("reasoning_priors_buckets")
    if not isinstance(buckets, dict):
        buckets = {}
    source_bucket = buckets.get(bucket)
    if not isinstance(source_bucket, dict):
        source_bucket = data.get("reasoning_priors")

    current = _normalize(_merge_prior_values(source_bucket))
    before = dict(current)

    delta = 0.05 if helpful else -0.05
    current[label] = max(0.05, min(0.9, current.get(label, 0.25) + delta))
    current = _normalize(current)

    buckets[bucket] = current
    data["reasoning_priors_buckets"] = buckets
    # Keep a flat snapshot for backward compatibility with older readers.
    data["reasoning_priors"] = current
    _save_memory(memory_file, data)

    return {
        "updated_label": label,
        "time_bucket": bucket,
        "helpful": helpful,
        "delta": delta,
        "before": before,
        "after": current,
    }
