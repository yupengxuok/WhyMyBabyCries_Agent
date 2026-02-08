import argparse
import json
import os
import tempfile
import time
import wave
from datetime import datetime, timedelta, timezone

import requests


def iso_utc(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def write_silence_wav(path, duration_sec=2, sample_rate=16000):
    frames = int(duration_sec * sample_rate)
    silence = b"\x00\x00" * frames
    with wave.open(path, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(silence)


def http_json(method, url, max_retries=3, timeout=30, **kwargs):
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.request(method, url, timeout=timeout, **kwargs)
            if response.status_code >= 400:
                raise RuntimeError(f"{method} {url} -> HTTP {response.status_code}: {response.text[:300]}")
            return response.json()
        except Exception as exc:
            last_error = exc
            if attempt < max_retries:
                time.sleep(1.0 * attempt)
    raise RuntimeError(f"Request failed after {max_retries} attempts: {last_error}")


def seed_manual_events(base_url):
    now = datetime.now(timezone.utc)
    seeds = [
        {"category": "feeding", "occurred_at": iso_utc(now - timedelta(minutes=170)), "payload": {"amount_ml": 110}},
        {"category": "diaper", "occurred_at": iso_utc(now - timedelta(minutes=95)), "payload": {"note": "wet"}},
        {"category": "sleep", "occurred_at": iso_utc(now - timedelta(minutes=40)), "payload": {"duration_min": 35}},
    ]
    for item in seeds:
        body = {
            "occurred_at": item["occurred_at"],
            "category": item["category"],
            "payload": item["payload"],
            "tags": ["demo_seed"],
        }
        http_json("POST", f"{base_url}/api/events/manual", json=body)


def create_cry_event(base_url, audio_path, ab_variant, note):
    with open(audio_path, "rb") as audio_file:
        files = {"audio": (os.path.basename(audio_path), audio_file, "audio/wav")}
        data = {
            "occurred_at": iso_utc(datetime.now(timezone.utc)),
            "ab_variant": ab_variant,
            "payload": json.dumps({"note": note}),
            "tags": json.dumps(["demo_ab"]),
        }
        result = http_json("POST", f"{base_url}/api/events/crying", files=files, data=data)
    event = result.get("event", {})
    return event.get("id"), result


def submit_feedback(base_url, event_id, helpful, resolved_minutes, notes):
    body = {
        "event_id": event_id,
        "feedback": {
            "helpful": helpful,
            "resolved_in_minutes": resolved_minutes,
            "notes": notes,
        },
    }
    return http_json("POST", f"{base_url}/api/events/feedback", json=body)


def print_ab_table(metrics):
    ab = metrics.get("ab_comparison", {})
    uplift = metrics.get("ab_uplift", {})
    treatment = ab.get("treatment", {})
    control = ab.get("control", {})
    print("\nA/B Comparison")
    print("Variant     Samples  HelpfulRate  MedianResolved")
    print(
        f"treatment   {str(treatment.get('samples', '-')).ljust(7)}  "
        f"{str(treatment.get('helpful_rate', '-')).ljust(11)}  "
        f"{treatment.get('median_resolved_minutes', '-')}"
    )
    print(
        f"control     {str(control.get('samples', '-')).ljust(7)}  "
        f"{str(control.get('helpful_rate', '-')).ljust(11)}  "
        f"{control.get('median_resolved_minutes', '-')}"
    )
    print(
        f"Uplift      helpful_rate={uplift.get('helpful_rate_uplift')}  "
        f"median_resolved_minutes_delta={uplift.get('median_resolved_minutes_delta')}"
    )


def main():
    parser = argparse.ArgumentParser(description="One-click stable demo runner for WMBC API")
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")

    print(f"[Demo] Base URL: {base_url}")
    health = http_json("GET", f"{base_url}/health")
    if not health.get("ok"):
        raise RuntimeError("Health check failed")

    seed_manual_events(base_url)
    print("[Demo] Seeded manual events")

    temp_dir = tempfile.mkdtemp(prefix="wmbc_demo_")
    audio_path = os.path.join(temp_dir, "demo.wav")
    write_silence_wav(audio_path, duration_sec=2)

    treatment_event_id, treatment_resp = create_cry_event(
        base_url, audio_path, "treatment", "demo treatment sample"
    )
    if not treatment_event_id:
        raise RuntimeError(f"Failed to create treatment event: {treatment_resp}")
    print(f"[Demo] Treatment event: {treatment_event_id}")

    control_event_id, control_resp = create_cry_event(
        base_url, audio_path, "control", "demo control sample"
    )
    if not control_event_id:
        raise RuntimeError(f"Failed to create control event: {control_resp}")
    print(f"[Demo] Control event: {control_event_id}")

    submit_feedback(
        base_url,
        treatment_event_id,
        helpful=True,
        resolved_minutes=4,
        notes="Treatment guidance calmed quickly",
    )
    submit_feedback(
        base_url,
        control_event_id,
        helpful=False,
        resolved_minutes=11,
        notes="Control baseline was less helpful",
    )
    print("[Demo] Submitted feedback for both variants")

    metrics_resp = http_json("GET", f"{base_url}/api/metrics")
    metrics = metrics_resp.get("metrics", {})
    print_ab_table(metrics)
    print("\n[Demo] Full metrics JSON:")
    print(json.dumps(metrics_resp, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
