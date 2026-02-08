from datetime import datetime, timezone


def new_audio_id():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    return f"aud_{stamp}"


def stub_gemini_result():
    return {
        "top_reason": "hunger",
        "confidence": 0.82,
        "scores": {
            "hunger": 0.82,
            "discomfort": 0.10,
            "emotional_comfort": 0.06,
            "unknown": 0.02
        },
        "model": "gemini-1.5",
        "version": datetime.now(timezone.utc).strftime("%Y-%m-%d")
    }
