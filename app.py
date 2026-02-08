import json
import os
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

MEMORY_FILE = os.path.join("agent", "memory.json")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

from audio.analysis import new_audio_id, stub_gemini_result
from db.sqlite_store import (
    fetch_events_since,
    fetch_recent_events,
    get_event_by_id,
    init_db,
    insert_event,
    update_event_payload,
    migrate_events_from_memory,
)
from engine.engine import run_reasoning


def _iso_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso(value):
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _load_belief_state():
    if not os.path.exists(MEMORY_FILE):
        return {}
    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        content = f.read().strip()
        if not content:
            return {}
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return {}
        return data.get("belief_state", {})


def _new_event_id():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    return f"evt_{stamp}"


CRYING_NOTICE = (
    "Crying insights are generated based on sound patterns and recent care history.\n"
    "They are probabilistic suggestions to assist caregivers, not medical diagnoses."
)
GUIDANCE_UNAVAILABLE_NOTICE = (
    "Guidance unavailable due to limited data at this time."
)


class APIMockHandler(BaseHTTPRequestHandler):
    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/events/manual":
            self._handle_post_manual()
            return
        if parsed.path == "/api/events/crying":
            self._handle_post_crying()
            return
        if parsed.path == "/api/events/feedback":
            self._handle_post_feedback()
            return
        self._send_json(404, {"ok": False, "error": "Not found"})

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._handle_root()
            return
        if parsed.path == "/docs":
            self._handle_docs()
            return
        if parsed.path == "/health":
            self._send_json(200, {"ok": True, "status": "healthy"})
            return
        if parsed.path == "/api/events/recent":
            self._handle_get_recent(parsed.query)
            return
        if parsed.path.startswith("/api/events/"):
            self._handle_get_event_by_id(parsed.path)
            return
        if parsed.path == "/api/context/summary":
            self._handle_get_summary()
            return
        self._send_json(404, {"ok": False, "error": "Not found"})

    def _handle_post_manual(self):
        body = self._read_json()
        if body is None:
            self._send_json(400, {"ok": False, "error": "Invalid JSON"})
            return

        event = {
            "id": _new_event_id(),
            "type": "manual",
            "occurred_at": body.get("occurred_at") or _iso_now(),
            "source": body.get("source", "parent"),
            "category": body.get("category", "unknown"),
            "payload": body.get("payload", {}),
            "tags": body.get("tags", []),
            "created_at": _iso_now(),
        }
        insert_event(event)
        self._send_json(200, {"ok": True, "event": event})

    def _handle_post_crying(self):
        body = self._read_json()
        if body is None:
            self._send_json(400, {"ok": False, "error": "Invalid JSON"})
            return

        payload = body.get("payload", {})
        payload.pop("ai_guidance", None)
        payload["audio_id"] = body.get("audio_id") or payload.get("audio_id") or new_audio_id()
        payload["audio_url"] = body.get("audio_url") or payload.get("audio_url")
        payload["notice"] = CRYING_NOTICE
        if "audio_analysis" not in payload:
            payload["audio_analysis"] = payload.get("ai") or stub_gemini_result()
        if "ai" not in payload:
            payload["ai"] = payload["audio_analysis"]

        event = {
            "id": _new_event_id(),
            "type": "crying",
            "occurred_at": body.get("occurred_at") or _iso_now(),
            "source": body.get("source", "device"),
            "category": "crying",
            "payload": payload,
            "tags": body.get("tags", []),
            "created_at": _iso_now(),
        }
        insert_event(event)

        recent_events = [
            item for item in fetch_recent_events(20, None)
            if item.get("id") != event.get("id")
        ]
        ai_guidance, error = run_reasoning(event, recent_events)
        if ai_guidance:
            payload = dict(event.get("payload", {}))
            payload["ai_guidance"] = ai_guidance
            payload["notice"] = CRYING_NOTICE
            update_event_payload(event["id"], payload)
            event["payload"] = payload
        elif error:
            payload = dict(event.get("payload", {}))
            payload.pop("ai_guidance", None)
            payload["notice"] = f"{CRYING_NOTICE}\n{GUIDANCE_UNAVAILABLE_NOTICE}"
            update_event_payload(event["id"], payload)
            event["payload"] = payload
            print(f"[CareReasoning][BestEffort] Guidance unavailable: {error}")

        self._send_json(200, {"ok": True, "event": event})

    def _handle_get_recent(self, query):
        params = parse_qs(query)
        limit = int(params.get("limit", ["50"])[0])
        since = params.get("since", [None])[0]
        since_dt = _parse_iso(since)

        events = fetch_recent_events(limit, since_dt)
        self._send_json(200, {"ok": True, "events": events})

    def _handle_get_summary(self):
        events = fetch_events_since(datetime.now(timezone.utc) - timedelta(hours=24))
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=24)

        counts = {
            "feeding_count": 0,
            "diaper_count": 0,
            "sleep_sessions": 0,
            "crying_events": 0
        }
        recent_events = []
        for event in events:
            dt = _parse_iso(event.get("occurred_at")) or _parse_iso(event.get("created_at"))
            if not dt:
                continue
            if dt >= cutoff:
                recent_events.append(event)
                category = event.get("category")
                if category == "feeding":
                    counts["feeding_count"] += 1
                elif category == "diaper":
                    counts["diaper_count"] += 1
                elif category == "sleep":
                    counts["sleep_sessions"] += 1
                elif category == "crying":
                    counts["crying_events"] += 1

        latest_events = recent_events[:10]
        summary = {
            "last_24h": counts,
            "latest_events": latest_events,
            "ai_belief_state": _load_belief_state()
        }
        self._send_json(200, {"ok": True, "summary": summary})

    def _handle_get_event_by_id(self, path):
        parts = path.rstrip("/").split("/")
        if len(parts) != 4:
            self._send_json(404, {"ok": False, "error": "Not found"})
            return
        event_id = parts[-1]
        event = get_event_by_id(event_id)
        if not event:
            self._send_json(404, {"ok": False, "error": "Event not found"})
            return
        self._send_json(200, {"ok": True, "event": event})

    def _handle_post_feedback(self):
        body = self._read_json()
        if body is None:
            self._send_json(400, {"ok": False, "error": "Invalid JSON"})
            return
        event_id = body.get("event_id")
        feedback = body.get("feedback")
        if not event_id or not isinstance(feedback, dict):
            self._send_json(400, {"ok": False, "error": "event_id and feedback required"})
            return
        event = get_event_by_id(event_id)
        if not event:
            self._send_json(404, {"ok": False, "error": "Event not found"})
            return
        payload = dict(event.get("payload", {}))
        payload["user_feedback"] = feedback
        update_event_payload(event_id, payload)
        event["payload"] = payload
        self._send_json(200, {"ok": True, "event": event})

    def _handle_root(self):
        payload = {
            "ok": True,
            "service": "wmbc-api-mock",
            "endpoints": [
                "POST /api/events/manual",
                "POST /api/events/crying",
                "POST /api/events/feedback",
                "GET /api/events/recent",
                "GET /api/events/{id}",
                "GET /api/context/summary",
                "GET /docs",
                "GET /health"
            ]
        }
        self._send_json(200, payload)

    def _handle_docs(self):
        payload = {
            "ok": True,
            "title": "WhyMyBabyCries API Mock",
            "base_url": "http://localhost:8000",
            "endpoints": [
                {
                    "method": "POST",
                    "path": "/api/events/manual",
                    "body": {
                        "occurred_at": "2026-02-08T09:30:12Z",
                        "category": "feeding|diaper|sleep|comfort",
                        "payload": {"note": "optional"},
                        "tags": ["optional"]
                    }
                },
                {
                    "method": "POST",
                    "path": "/api/events/crying",
                    "body": {
                        "occurred_at": "2026-02-08T10:02:00Z",
                        "audio_id": "aud_20260208_100200_000000",
                        "audio_url": "s3://.../cry.wav",
                        "payload": {"note": "optional"},
                        "tags": ["optional"]
                    }
                },
                {
                    "method": "POST",
                    "path": "/api/events/feedback",
                    "body": {
                        "event_id": "evt_20260208_100200_000000",
                        "feedback": {
                            "helpful": True,
                            "resolved_in_minutes": 5,
                            "notes": "Feeding worked quickly"
                        }
                    }
                },
                {
                    "method": "GET",
                    "path": "/api/events/recent",
                    "query": {
                        "limit": "50",
                        "since": "2026-02-08T00:00:00Z"
                    }
                },
                {
                    "method": "GET",
                    "path": "/api/events/{id}"
                },
                {
                    "method": "GET",
                    "path": "/api/context/summary"
                },
                {
                    "method": "GET",
                    "path": "/health"
                }
            ]
        }
        self._send_json(200, payload)


def run(host="0.0.0.0", port=8000):
    init_db()
    migrated = migrate_events_from_memory(MEMORY_FILE)
    if migrated:
        print(f"[API Mock] Migrated {migrated} events from memory.json")
    server = HTTPServer((host, port), APIMockHandler)
    print(f"[API Mock] Listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run()
