import json
import os

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


def load_reasoning_priors(memory_file):
    data = _load_memory(memory_file)
    priors = data.get("reasoning_priors")
    if not isinstance(priors, dict):
        return dict(DEFAULT_PRIORS)
    merged = dict(DEFAULT_PRIORS)
    for key, value in priors.items():
        if key in merged and isinstance(value, (int, float)):
            merged[key] = max(0.0, value)
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
    current = load_reasoning_priors(memory_file)
    before = dict(current)

    delta = 0.05 if helpful else -0.05
    current[label] = max(0.05, min(0.9, current.get(label, 0.25) + delta))
    current = _normalize(current)

    data["reasoning_priors"] = current
    _save_memory(memory_file, data)

    return {
        "updated_label": label,
        "helpful": helpful,
        "delta": delta,
        "before": before,
        "after": current,
    }
