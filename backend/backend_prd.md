# WhyMyBabyCries Backend PRD (Implemented)
  
Date: `2026-02-08`  
Scope: Based on currently implemented backend behavior (`app.py` + `engine/` + `db/`)

---

## 1. Product Goals

1. Use one unified event schema for both manual care logs and AI crying analysis.
2. Make Gemini 3 the core reasoning engine while keeping the system explicitly non-medical.
3. Keep demo stability first: crying events must be persisted even when Gemini fails.
4. Expose measurable product impact with context uplift and A/B metrics.

## 2. Implemented Scope

1. Unified event storage in SQLite (`db.sqlite`).
2. Manual care event API.
3. Crying event API (JSON and multipart audio upload).
4. Live crying APIs (`start/chunk/finish`) with incremental guidance.
5. Feedback API writing back to the same event and updating priors.
6. Context summary API.
7. Metrics API + lightweight metrics page.
8. Self-describing API docs endpoint (`GET /docs`).
9. Gemini evidence fields (`model_name`, `latency_ms`, `request_mode`).
10. Probabilistic language enforcement, confidence level derivation, uncertainty note, and safety reminder.

## 3. Out of Scope (Current)

1. Medical diagnosis or treatment.
2. WebSocket/SSE streaming (current live flow uses HTTP chunk upload).
3. Complex online learning or model fine-tuning (current learning is explainable prior-weight update).

## 4. Architecture Modules

1. `app.py`: HTTP routes, orchestration, A/B logic, reliability fallbacks.
2. `engine/engine.py`: Gemini call, response validation, confidence/uncertainty post-processing.
3. `engine/prompt.txt`: strict non-diagnostic, probabilistic system prompt rules.
4. `engine/schema.json`: expected output contract for `audio_analysis` and `ai_guidance`.
5. `engine/learning.py`: feedback-driven prior updates with day/night buckets.
6. `db/sqlite_store.py`: SQLite initialization and event CRUD.
7. `audio/analysis.py`: `audio_id` generation and fallback analysis shape.

## 5. Unified Data Model

```json
{
  "id": "evt_xxx",
  "type": "manual|crying",
  "occurred_at": "ISO8601 UTC",
  "source": "parent|device|agent",
  "category": "feeding|diaper|sleep|crying|comfort|unknown",
  "payload": {},
  "tags": [],
  "created_at": "ISO8601 UTC"
}
```

SQLite table: `events`  
Fields: `id`, `type`, `occurred_at`, `source`, `category`, `payload_json`, `tags_json`, `created_at`

## 6. Core Business Rules

1. `payload.notice` is backend-owned and does not depend on frontend logic.
2. Every crying response includes static non-medical notice:
   - `Crying insights are generated based on sound patterns and recent care history.`
   - `They are probabilistic suggestions to assist caregivers, not medical diagnoses.`
3. Gemini failure handling:
   - Event is still saved.
   - `payload.ai_guidance` is omitted.
   - `payload.notice` adds: `Guidance unavailable due to limited data at this time.`
   - Failure is logged server-side, not surfaced as API error.
4. High-intensity crying safety reminder:
   - Added when threshold is reached in rolling window (non-diagnostic wording).
5. AI output validity requirements:
   - `most_likely_cause.confidence` must exist and be in `[0,1]`.
   - `alternative_causes[].confidence` must exist and be in `[0,1]`.
   - Invalid output => guidance is treated as unavailable.
6. Confidence level derivation:
   - `high`: `>= 0.75`
   - `medium`: `>= 0.45` and `< 0.75`
   - `low`: `< 0.45`
7. Uncertainty note:
   - If context is limited, backend adds `uncertainty_note: "Limited recent care data available"`.

## 7. Implemented API Surface

1. `POST /api/events/manual`
2. `POST /api/events/crying`
3. `POST /api/events/crying/live/start`
4. `POST /api/events/crying/live/chunk`
5. `POST /api/events/crying/live/finish`
6. `POST /api/events/feedback`
7. `GET /api/events/recent`
8. `GET /api/events/{id}`
9. `GET /api/context/summary`
10. `GET /api/metrics`
11. `GET /metrics`
12. `GET /docs`
13. `GET /health`

Response envelope:
- Success: `{ "ok": true, ... }`
- Error: `{ "ok": false, "error": "..." }`

## 8. Implemented Workflows

### 8.1 Manual Logging

1. Frontend calls `POST /api/events/manual`.
2. Backend persists event in unified schema to SQLite.
3. Frontend reads timeline via `GET /api/events/recent` or `GET /api/events/{id}`.

### 8.2 Crying Analysis (Single Request)

1. Frontend calls `POST /api/events/crying` (JSON or multipart audio upload).
2. Backend creates and stores crying event first.
3. Backend calls Gemini (multimodal when raw audio exists).
4. On success, backend writes:
   - `payload.audio_analysis`
   - `payload.ai_guidance`
   - `payload.ai_meta`
   - `payload.ab_test`
5. On failure, backend keeps event and notice fallback, no hard API failure.

### 8.3 Live Crying Analysis

1. `POST /api/events/crying/live/start` creates `stream_id` and `event_id` with status `streaming`.
2. Frontend uploads chunk every ~1-2s to `POST /api/events/crying/live/chunk`.
3. Backend triggers partial Gemini reasoning every 3 chunks.
4. `POST /api/events/crying/live/finish` runs final reasoning and marks stream `completed`.
5. If no chunk for 5 minutes, backend auto-completes stream for stability.

### 8.4 Feedback Learning

1. Frontend submits feedback to `POST /api/events/feedback`.
2. Backend stores it under `payload.user_feedback`.
3. Backend updates priors in `agent/memory.json` under:
   - `reasoning_priors_buckets.day`
   - `reasoning_priors_buckets.night`
4. Rule: `+0.05` when helpful, `-0.05` otherwise, then normalization.

## 9. A/B and Metrics

1. `POST /api/events/crying` supports `ab_variant=treatment|control`.
2. If `AB_AUTO_SPLIT=true`, backend auto-assigns variant when request does not specify one.
3. `payload.ab_test` stores:
   - `assigned_variant`, `shown_variant`
   - treatment/control outputs and metadata
   - baseline mode: `no_context_no_prior`
4. `GET /api/metrics` returns:
   - `helpful_rate`
   - `median_resolved_minutes`
   - context uplift:
     - `helpful_rate_uplift`
     - `median_resolved_minutes_delta`
   - A/B uplift:
     - `ab_uplift.helpful_rate_uplift`
     - `ab_uplift.median_resolved_minutes_delta`

## 10. Configuration and Run

`.env`:
- `GEMINI_API_KEY`
- `GEMINI_API_ENDPOINT`
- `AB_AUTO_SPLIT=false|true`

Run server:
```bash
python app.py
```

Quick checks:
- `GET /health`
- `GET /docs`

## 11. Reliability Guarantees

1. Gemini is best-effort enrichment, not a hard dependency.
2. Max single audio size: `10MB`.
3. Max live chunk size: `512KB`.
4. Partial reasoning failure returns stale result and stream continues.
5. Stale live streams are auto-closed to avoid hanging sessions.

## 12. Demo-Ready Highlights

1. True multimodal path: frontend uploads raw audio, backend sends audio directly to Gemini.
2. Strict non-medical probabilistic behavior: prompt + schema validation + backend post-checks.
3. Explainable personalization: day/night prior updates from caregiver feedback.
4. Quantified impact: context uplift and A/B uplift metrics.
5. Fast demo support: `/metrics` page and `/docs` endpoint for live walkthrough.
