import cgi
import hashlib
import json
import os
import statistics
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

MEMORY_FILE = os.path.join("agent", "memory.json")
UPLOAD_DIR = "uploads"
MAX_AUDIO_BYTES = 10 * 1024 * 1024
AB_AUTO_SPLIT = os.getenv("AB_AUTO_SPLIT", "false").lower() == "true"

from audio.analysis import new_audio_id, stub_gemini_result
from db.sqlite_store import (
    fetch_events_by_category,
    fetch_events_since,
    fetch_recent_events,
    get_event_by_id,
    init_db,
    insert_event,
    update_event_payload,
    migrate_events_from_memory,
)
from engine.learning import load_reasoning_priors, update_reasoning_priors
from engine.engine import run_reasoning


def _iso_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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


def _safe_json_loads(raw_value, default_value):
    if not isinstance(raw_value, str):
        return default_value
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        return default_value
    return parsed


def _median(values):
    if not values:
        return None
    return float(statistics.median(values))


CRYING_NOTICE = (
    "Crying insights are generated based on sound patterns and recent care history.\n"
    "They are probabilistic suggestions to assist caregivers, not medical diagnoses."
)
GUIDANCE_UNAVAILABLE_NOTICE = (
    "Guidance unavailable due to limited data at this time."
)
SAFETY_NOTICE = (
    "If high-intensity crying continues or worsens, consider contacting a pediatric professional."
)
HIGH_INTENSITY_WINDOW_MIN = 60
HIGH_INTENSITY_THRESHOLD = 3


class APIMockHandler(BaseHTTPRequestHandler):
    def _event_time(self, event):
        return _parse_iso(event.get("occurred_at")) or _parse_iso(event.get("created_at"))

    def _is_high_intensity(self, event):
        payload = event.get("payload", {})
        if not isinstance(payload, dict):
            return False
        analysis = payload.get("audio_analysis")
        if not isinstance(analysis, dict):
            return False
        transcription = (analysis.get("transcription") or "").lower()
        keywords = ("high", "intense", "piercing", "loud", "shrill")
        return any(keyword in transcription for keyword in keywords)

    def _should_add_safety_notice(self, current_event, recent_events):
        current_time = self._event_time(current_event)
        if not current_time:
            return False
        window_start = current_time - timedelta(minutes=HIGH_INTENSITY_WINDOW_MIN)
        high_count = 1 if self._is_high_intensity(current_event) else 0
        for event in recent_events:
            if event.get("category") != "crying":
                continue
            event_time = self._event_time(event)
            if not event_time:
                continue
            if window_start <= event_time <= current_time and self._is_high_intensity(event):
                high_count += 1
        return high_count >= HIGH_INTENSITY_THRESHOLD

    def _compose_notice(self, include_guidance_unavailable=False, include_safety=False):
        lines = [CRYING_NOTICE]
        if include_guidance_unavailable:
            lines.append(GUIDANCE_UNAVAILABLE_NOTICE)
        if include_safety:
            lines.append(SAFETY_NOTICE)
        return "\n".join(lines)

    def _resolve_ab_variant(self, requested_variant, event_id):
        if requested_variant in ("treatment", "control"):
            return requested_variant
        if AB_AUTO_SPLIT:
            digest = hashlib.md5(event_id.encode("utf-8")).hexdigest()
            bucket = int(digest[:2], 16) % 2
            return "control" if bucket == 1 else "treatment"
        return "treatment"

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

    def _read_multipart_form(self):
        form = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={
                "REQUEST_METHOD": "POST",
                "CONTENT_TYPE": self.headers.get("Content-Type", ""),
            },
            keep_blank_values=True,
        )

        body = {
            "occurred_at": form.getvalue("occurred_at"),
            "source": form.getvalue("source"),
            "audio_id": form.getvalue("audio_id"),
            "audio_url": form.getvalue("audio_url"),
            "ab_variant": form.getvalue("ab_variant"),
            "payload": {},
            "tags": [],
        }

        payload_raw = form.getvalue("payload")
        if payload_raw:
            body["payload"] = _safe_json_loads(payload_raw, {})

        tags_raw = form.getvalue("tags")
        if tags_raw:
            parsed_tags = _safe_json_loads(tags_raw, [])
            if isinstance(parsed_tags, list):
                body["tags"] = parsed_tags

        audio_file = None
        for field_name in ("audio", "audio_file", "file"):
            if field_name in form and getattr(form[field_name], "filename", None):
                audio_file = form[field_name]
                break

        if audio_file is not None:
            audio_bytes = audio_file.file.read()
            body["_audio_upload"] = {
                "bytes": audio_bytes,
                "filename": audio_file.filename or "audio.bin",
                "mime_type": audio_file.type or "application/octet-stream",
            }

        return body

    def _parse_crying_input(self):
        content_type = (self.headers.get("Content-Type", "") or "").lower()
        if content_type.startswith("multipart/form-data"):
            return self._read_multipart_form()
        return self._read_json()

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
        if parsed.path == "/metrics":
            self._handle_metrics_page()
            return
        if parsed.path == "/health":
            self._send_json(200, {"ok": True, "status": "healthy"})
            return
        if parsed.path == "/api/events/recent":
            self._handle_get_recent(parsed.query)
            return
        if parsed.path == "/api/metrics":
            self._handle_get_metrics()
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
        body = self._parse_crying_input()
        if body is None or not isinstance(body, dict):
            self._send_json(400, {"ok": False, "error": "Invalid JSON"})
            return

        payload = body.get("payload", {})
        if not isinstance(payload, dict):
            payload = {}
        tags = body.get("tags", [])
        if not isinstance(tags, list):
            tags = []

        audio_upload = body.get("_audio_upload")
        audio_bytes = None
        audio_mime_type = None
        if isinstance(audio_upload, dict):
            raw_audio = audio_upload.get("bytes")
            if isinstance(raw_audio, (bytes, bytearray)):
                audio_bytes = bytes(raw_audio)
            if audio_bytes and len(audio_bytes) > MAX_AUDIO_BYTES:
                self._send_json(413, {"ok": False, "error": "Audio file too large"})
                return
            audio_mime_type = audio_upload.get("mime_type") or "application/octet-stream"

        payload.pop("ai_guidance", None)
        payload["audio_id"] = body.get("audio_id") or payload.get("audio_id") or new_audio_id()
        if audio_bytes:
            original_name = ""
            if isinstance(audio_upload, dict):
                original_name = audio_upload.get("filename") or ""
            extension = os.path.splitext(original_name)[1] or ".bin"
            audio_file_path = os.path.join(UPLOAD_DIR, f"{payload['audio_id']}{extension}")
            with open(audio_file_path, "wb") as f:
                f.write(audio_bytes)
            payload["audio_path"] = audio_file_path.replace("\\", "/")
            payload["audio_mime_type"] = audio_mime_type

        payload["audio_url"] = body.get("audio_url") or payload.get("audio_url")
        payload["notice"] = self._compose_notice()
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
            "tags": tags,
            "created_at": _iso_now(),
        }
        insert_event(event)

        recent_events = [
            item for item in fetch_recent_events(20, None)
            if item.get("id") != event.get("id")
        ]
        assigned_variant = self._resolve_ab_variant(body.get("ab_variant"), event["id"])
        priors = load_reasoning_priors(MEMORY_FILE, event.get("occurred_at"))
        enrichment, error = run_reasoning(
            event,
            recent_events,
            audio_bytes=audio_bytes,
            audio_mime_type=audio_mime_type,
            learned_priors=priors,
        )
        control_enrichment = None
        control_error = None
        if enrichment:
            control_event = {
                "id": event["id"],
                "type": event["type"],
                "occurred_at": event["occurred_at"],
                "payload": {"audio_analysis": enrichment["audio_analysis"]},
            }
            control_enrichment, control_error = run_reasoning(
                control_event,
                [],
                audio_bytes=None,
                audio_mime_type=None,
                learned_priors={},
            )

        if enrichment:
            payload = dict(event.get("payload", {}))
            treatment_guidance = enrichment.get("ai_guidance")
            treatment_meta = enrichment.get("ai_meta", {})
            control_guidance = control_enrichment.get("ai_guidance") if isinstance(control_enrichment, dict) else None
            control_meta = control_enrichment.get("ai_meta", {}) if isinstance(control_enrichment, dict) else {}

            shown_variant = "treatment"
            shown_guidance = treatment_guidance
            shown_meta = treatment_meta
            if assigned_variant == "control" and control_guidance:
                shown_variant = "control"
                shown_guidance = control_guidance
                shown_meta = control_meta

            payload["audio_analysis"] = enrichment["audio_analysis"]
            payload["ai"] = enrichment["audio_analysis"]
            payload["ai_guidance"] = shown_guidance
            payload["ai_meta"] = shown_meta
            payload["ab_test"] = {
                "assigned_variant": assigned_variant,
                "shown_variant": shown_variant,
                "auto_split_enabled": AB_AUTO_SPLIT,
                "baseline_mode": "no_context_no_prior",
                "treatment": {
                    "ai_guidance": treatment_guidance,
                    "ai_meta": treatment_meta,
                },
                "control": {
                    "ai_guidance": control_guidance,
                    "ai_meta": control_meta,
                },
            }
            if control_error:
                payload["ab_test"]["control_error"] = control_error

            event["payload"] = payload
            add_safety = self._should_add_safety_notice(event, recent_events)
            payload["notice"] = self._compose_notice(include_safety=add_safety)
            update_event_payload(event["id"], payload)
            event["payload"] = payload
        elif error:
            payload = dict(event.get("payload", {}))
            payload.pop("ai_guidance", None)
            ai_meta = error.get("ai_meta", {}) if isinstance(error, dict) else {}
            payload["ai_meta"] = ai_meta
            payload["ab_test"] = {
                "assigned_variant": assigned_variant,
                "shown_variant": None,
                "auto_split_enabled": AB_AUTO_SPLIT,
                "baseline_mode": "no_context_no_prior",
                "treatment_error": error,
            }
            event["payload"] = payload
            add_safety = self._should_add_safety_notice(event, recent_events)
            payload["notice"] = self._compose_notice(
                include_guidance_unavailable=True,
                include_safety=add_safety,
            )
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

    def _build_metrics(self):
        crying_events = fetch_events_by_category("crying")
        helpful_total = 0
        helpful_hits = 0
        resolved_minutes = []

        with_context_total = 0
        with_context_helpful = 0
        with_context_resolved = []
        limited_context_total = 0
        limited_context_helpful = 0
        limited_context_resolved = []
        ab_treatment_total = 0
        ab_treatment_helpful = 0
        ab_treatment_resolved = []
        ab_control_total = 0
        ab_control_helpful = 0
        ab_control_resolved = []

        for event in crying_events:
            payload = event.get("payload", {})
            if not isinstance(payload, dict):
                continue

            feedback = payload.get("user_feedback")
            if not isinstance(feedback, dict):
                continue
            helpful = feedback.get("helpful")
            if not isinstance(helpful, bool):
                continue

            helpful_total += 1
            if helpful:
                helpful_hits += 1

            resolved_in = feedback.get("resolved_in_minutes")
            if isinstance(resolved_in, (int, float)):
                resolved_minutes.append(float(resolved_in))

            ai_guidance = payload.get("ai_guidance")
            has_limited_context = isinstance(ai_guidance, dict) and bool(ai_guidance.get("uncertainty_note"))
            if has_limited_context:
                limited_context_total += 1
                if helpful:
                    limited_context_helpful += 1
                if isinstance(resolved_in, (int, float)):
                    limited_context_resolved.append(float(resolved_in))
            else:
                with_context_total += 1
                if helpful:
                    with_context_helpful += 1
                if isinstance(resolved_in, (int, float)):
                    with_context_resolved.append(float(resolved_in))

            ab_test = payload.get("ab_test")
            variant = None
            if isinstance(ab_test, dict):
                variant = ab_test.get("shown_variant") or ab_test.get("assigned_variant")
            if variant == "treatment":
                ab_treatment_total += 1
                if helpful:
                    ab_treatment_helpful += 1
                if isinstance(resolved_in, (int, float)):
                    ab_treatment_resolved.append(float(resolved_in))
            elif variant == "control":
                ab_control_total += 1
                if helpful:
                    ab_control_helpful += 1
                if isinstance(resolved_in, (int, float)):
                    ab_control_resolved.append(float(resolved_in))

        helpful_rate = None
        if helpful_total > 0:
            helpful_rate = round(helpful_hits / helpful_total, 4)

        with_context_rate = None
        if with_context_total > 0:
            with_context_rate = round(with_context_helpful / with_context_total, 4)

        limited_context_rate = None
        if limited_context_total > 0:
            limited_context_rate = round(limited_context_helpful / limited_context_total, 4)

        with_context_median = _median(with_context_resolved)
        limited_context_median = _median(limited_context_resolved)

        helpful_rate_uplift = None
        if with_context_rate is not None and limited_context_rate is not None:
            helpful_rate_uplift = round(with_context_rate - limited_context_rate, 4)

        median_resolved_minutes_delta = None
        if with_context_median is not None and limited_context_median is not None:
            # Positive means context-aware guidance calmed faster.
            median_resolved_minutes_delta = round(limited_context_median - with_context_median, 2)

        ab_treatment_rate = None
        if ab_treatment_total > 0:
            ab_treatment_rate = round(ab_treatment_helpful / ab_treatment_total, 4)

        ab_control_rate = None
        if ab_control_total > 0:
            ab_control_rate = round(ab_control_helpful / ab_control_total, 4)

        ab_treatment_median = _median(ab_treatment_resolved)
        ab_control_median = _median(ab_control_resolved)

        ab_helpful_rate_uplift = None
        if ab_treatment_rate is not None and ab_control_rate is not None:
            ab_helpful_rate_uplift = round(ab_treatment_rate - ab_control_rate, 4)

        ab_median_resolved_minutes_delta = None
        if ab_treatment_median is not None and ab_control_median is not None:
            ab_median_resolved_minutes_delta = round(ab_control_median - ab_treatment_median, 2)

        return {
            "helpful_rate": helpful_rate,
            "median_resolved_minutes": _median(resolved_minutes),
            "uplift": {
                "helpful_rate_uplift": helpful_rate_uplift,
                "median_resolved_minutes_delta": median_resolved_minutes_delta,
            },
            "context_comparison": {
                "with_context": {
                    "samples": with_context_total,
                    "helpful_rate": with_context_rate,
                    "median_resolved_minutes": with_context_median,
                },
                "no_context": {
                    "samples": limited_context_total,
                    "helpful_rate": limited_context_rate,
                    "median_resolved_minutes": limited_context_median,
                },
                "limited_context": {
                    "samples": limited_context_total,
                    "helpful_rate": limited_context_rate,
                    "median_resolved_minutes": limited_context_median,
                }
            },
            "ab_comparison": {
                "treatment": {
                    "samples": ab_treatment_total,
                    "helpful_rate": ab_treatment_rate,
                    "median_resolved_minutes": ab_treatment_median,
                },
                "control": {
                    "samples": ab_control_total,
                    "helpful_rate": ab_control_rate,
                    "median_resolved_minutes": ab_control_median,
                },
            },
            "ab_uplift": {
                "helpful_rate_uplift": ab_helpful_rate_uplift,
                "median_resolved_minutes_delta": ab_median_resolved_minutes_delta,
            },
            "totals": {
                "crying_events": len(crying_events),
                "feedback_events": helpful_total,
            },
        }

    def _handle_get_metrics(self):
        self._send_json(200, {"ok": True, "metrics": self._build_metrics()})

    def _handle_metrics_page(self):
        html = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>WMBC Metrics</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 2rem; background: #f7f8fa; color: #111; }
    .card { max-width: 980px; background: white; border-radius: 12px; padding: 1.2rem; box-shadow: 0 4px 24px rgba(0,0,0,0.08); }
    table { width: 100%; border-collapse: collapse; margin-bottom: 1rem; }
    th, td { border: 1px solid #dbe1e8; padding: 0.5rem; text-align: left; }
    th { background: #f0f4f8; }
    pre { white-space: pre-wrap; background: #10151c; color: #d8ecff; border-radius: 10px; padding: 1rem; }
  </style>
</head>
<body>
  <div class="card">
    <h2>Care Guidance Metrics</h2>
    <p>Live metrics from <code>/api/metrics</code></p>
    <table>
      <thead>
        <tr><th>Variant</th><th>Samples</th><th>Helpful Rate</th><th>Median Resolved (min)</th></tr>
      </thead>
      <tbody id="ab_table">
        <tr><td colspan="4">Loading...</td></tr>
      </tbody>
    </table>
    <p id="uplift_line"></p>
    <pre id="output">Loading...</pre>
  </div>
  <script>
    fetch('/api/metrics')
      .then(function (res) { return res.json(); })
      .then(function (data) {
        var metrics = data.metrics || {};
        var ab = metrics.ab_comparison || {};
        var treatment = ab.treatment || {};
        var control = ab.control || {};
        var abUplift = metrics.ab_uplift || {};
        var show = function (value) {
          if (value === null || value === undefined) {
            return '-';
          }
          return String(value);
        };
        var rows = [
          '<tr><td>Treatment</td><td>' + show(treatment.samples) + '</td><td>' + show(treatment.helpful_rate) + '</td><td>' + show(treatment.median_resolved_minutes) + '</td></tr>',
          '<tr><td>Control</td><td>' + show(control.samples) + '</td><td>' + show(control.helpful_rate) + '</td><td>' + show(control.median_resolved_minutes) + '</td></tr>'
        ];
        document.getElementById('ab_table').innerHTML = rows.join('');
        document.getElementById('uplift_line').textContent =
          'A/B Uplift: helpful_rate=' + show(abUplift.helpful_rate_uplift) +
          ', median_resolved_minutes_delta=' + show(abUplift.median_resolved_minutes_delta);
        document.getElementById('output').textContent = JSON.stringify(data, null, 2);
      })
      .catch(function (err) {
        document.getElementById('output').textContent = 'Error: ' + err;
      });
  </script>
</body>
</html>"""
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

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
        learning_update = update_reasoning_priors(MEMORY_FILE, event, feedback)
        if learning_update:
            payload["learning_update"] = learning_update
        update_event_payload(event_id, payload)
        event["payload"] = payload
        self._send_json(200, {"ok": True, "event": event, "learning": learning_update})

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
                "GET /api/metrics",
                "GET /docs",
                "GET /metrics",
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
                    "content_types": ["application/json", "multipart/form-data"],
                    "response_additions": [
                        "payload.ai_meta.model_name",
                        "payload.ai_meta.latency_ms",
                        "payload.ai_meta.request_mode",
                        "payload.notice (may include safety reminder)"
                    ],
                    "body": {
                        "occurred_at": "2026-02-08T10:02:00Z",
                        "ab_variant": "treatment|control (optional, for A/B demo)",
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
                    "path": "/api/metrics",
                    "contains": [
                        "metrics.ab_uplift.helpful_rate_uplift",
                        "metrics.ab_uplift.median_resolved_minutes_delta",
                        "metrics.uplift.helpful_rate_uplift",
                        "metrics.uplift.median_resolved_minutes_delta"
                    ]
                },
                {
                    "method": "GET",
                    "path": "/metrics"
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
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    migrated = migrate_events_from_memory(MEMORY_FILE)
    if migrated:
        print(f"[API Mock] Migrated {migrated} events from memory.json")
    server = HTTPServer((host, port), APIMockHandler)
    print(f"[API Mock] Listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run()
