from datetime import datetime, timezone


def new_audio_id():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    return f"aud_{stamp}"


def stub_gemini_result():
    return {
        "transcription": "high-pitched crying",
        "inference": {
            "hunger": 0.62,
            "discomfort": 0.23,
            "emotional_need": 0.10,
            "unknown": 0.05,
        },
        "model": "gemini-3",
        "version": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }
