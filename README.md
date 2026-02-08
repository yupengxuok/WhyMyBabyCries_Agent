# WhyMyBabyCries_Agent

---

## Frontend Integration (Quick Contract)

Base URL: `http://localhost:8000`

Time format:
- All timestamps use ISO8601 UTC, e.g. `2026-02-08T10:02:00Z`

Common response envelope:
- Success: `{ "ok": true, ... }`
- Failure: `{ "ok": false, "error": "message" }`

### `POST /api/events/manual`
Request body:
```json
{
  "occurred_at": "2026-02-08T09:30:12Z",
  "source": "parent",
  "category": "feeding",
  "payload": {
    "amount_ml": 90
  },
  "tags": ["optional"]
}
```
`category` typically uses: `feeding|diaper|sleep|comfort|unknown`

### `POST /api/events/crying`
Supported content types:
- `application/json`
- `multipart/form-data` (recommended for raw audio upload)

JSON request body:
```json
{
  "occurred_at": "2026-02-08T10:02:00Z",
  "audio_id": "aud_20260208_100200_000000",
  "audio_url": "s3://bucket/cry.wav",
  "payload": {
    "audio_analysis": {
      "transcription": "high-pitched crying",
      "inference": {
        "hunger": 0.62,
        "discomfort": 0.23,
        "emotional_need": 0.10,
        "unknown": 0.05
      }
    }
  },
  "tags": ["optional"]
}
```
Multipart example:
```bash
curl -X POST http://localhost:8000/api/events/crying \
  -F "occurred_at=2026-02-08T10:02:00Z" \
  -F "audio=@./sample.wav" \
  -F "payload={\"note\":\"night cry\"}"
```
Response notes:
- Event is always saved.
- On Gemini success: backend sends raw audio to Gemini and writes `payload.audio_analysis` + `payload.ai_guidance`.
- Gemini evidence is stored under `payload.ai_meta` with `model_name`, `latency_ms`, `request_mode`.
- On Gemini failure: `payload.ai_guidance` is omitted, and `payload.notice` includes fallback text.
- If high-intensity crying persists above threshold, `payload.notice` also includes a non-diagnostic safety reminder.
- Supports A/B control run:
  - Optional `ab_variant`: `treatment|control`
  - If omitted, backend uses treatment by default (`AB_AUTO_SPLIT=true` enables automatic split)
  - Stores both runs in `payload.ab_test` and surfaces selected one in `payload.ai_guidance`

### `POST /api/events/feedback`
Request body:
```json
{
  "event_id": "evt_20260208_100200_000000",
  "feedback": {
    "helpful": true,
    "resolved_in_minutes": 5,
    "notes": "Feeding worked quickly"
  }
}
```
Behavior:
- Writes feedback into the same event under `payload.user_feedback`.
- Updates time-bucket priors (`day`/`night`) in `agent/memory.json` for next reasoning call.

### `GET /api/events/recent`
Query params:
- `limit` (optional, default `50`)
- `since` (optional ISO8601 UTC)

### `GET /api/events/{id}`
Behavior:
- Returns one event by id, or `404` if not found.

### `GET /api/context/summary`
Behavior:
- Returns last 24h counters + latest events + `belief_state`.

### `GET /api/metrics`
Behavior:
- Returns `helpful_rate`, `median_resolved_minutes`, and context vs limited-context comparison.
- Includes uplift metrics: `helpful_rate_uplift`, `median_resolved_minutes_delta`.
- Includes A/B metrics:
  - `ab_comparison.treatment`, `ab_comparison.control`
  - `ab_uplift.helpful_rate_uplift`, `ab_uplift.median_resolved_minutes_delta`

### `GET /metrics`
Behavior:
- Lightweight HTML page rendering `/api/metrics` for demo.

Quick health/doc routes:
- `GET /health`
- `GET /docs`

---

Agent-first backend with a shared event schema for manual logs and AI crying analysis.

**Requirements**
- Python 3.9+

**Run API Mock (for frontend)**
```bash
python app.py
```
API base: `http://localhost:8000`

**Config (.env)**
Create a `.env` file in the project root:
```
GEMINI_API_KEY=your_key_here
GEMINI_API_ENDPOINT=your_endpoint_here
AB_AUTO_SPLIT=false
```

The server loads `.env` automatically.
If Gemini is not configured or the call fails, the crying event is still saved, `ai_guidance` is omitted, and `payload.notice` includes a fallback line: `Guidance unavailable due to limited data at this time.`

Endpoints:
- `POST /api/events/manual`
- `POST /api/events/crying`
- `POST /api/events/feedback`
- `GET /api/events/recent?limit=50&since=2026-02-08T00:00:00Z`
- `GET /api/events/{id}`
- `GET /api/context/summary`
- `GET /api/metrics`
- `GET /docs`
- `GET /metrics`
- `GET /health`

Manual event example:
```bash
curl -X POST http://localhost:8000/api/events/manual \
  -H "Content-Type: application/json" \
  -d '{"category":"feeding","payload":{"amount_ml":90}}'
```

Crying event example:
```bash
curl -X POST http://localhost:8000/api/events/crying \
  -H "Content-Type: application/json" \
  -d '{"audio_url":"s3://bucket/cry.wav","payload":{"note":"after nap"}}'
```

**Run the Agent (writes to the same event store)**
```bash
python agent/agent.py
```

**One-Click Stable Demo**
1. Start backend:
```bash
python app.py
```
2. In another terminal run:
```bash
python scripts/demo_stable_run.py --base-url http://localhost:8000
```
This runs: seed data -> upload audio (treatment/control) -> submit feedback -> print A/B uplift table.

**Event Store**
- All events are stored in SQLite at `db.sqlite`.
- Manual logs and AI analysis share the same schema.
- Agent belief state remains in `agent/memory.json` under `belief_state`.
 - Care reasoning module lives in `engine/`.

Event shape (simplified):
```json
{
  "id": "evt_20260208_0001",
  "type": "manual|crying",
  "occurred_at": "2026-02-08T09:30:12Z",
  "source": "parent|device|agent",
  "category": "feeding|diaper|sleep|crying|comfort|unknown",
  "payload": {},
  "tags": [],
  "created_at": "2026-02-08T09:31:00Z"
}
```

For crying events, `payload.ai_guidance` includes:
- `confidence_level`: derived by backend from `most_likely_cause.confidence` (`high`/`medium`/`low`)
- `uncertainty_note`: optional, set when recent care context is limited

Feedback learning:
- Priors are stored in `agent/memory.json` under `reasoning_priors_buckets.day` and `reasoning_priors_buckets.night`.
- Update rule: `+0.05` when feedback is helpful, `-0.05` otherwise, then normalized per time bucket.
