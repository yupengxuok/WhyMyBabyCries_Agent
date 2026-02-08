# WhyMyBabyCries_Agent

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
```

The server loads `.env` automatically.
If Gemini is not configured or the call fails, the crying event is still saved but `ai_guidance` will be omitted.

Endpoints:
- `POST /api/events/manual`
- `POST /api/events/crying`
- `POST /api/events/feedback`
- `GET /api/events/recent?limit=50&since=2026-02-08T00:00:00Z`
- `GET /api/events/{id}`
- `GET /api/context/summary`
- `GET /docs`
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
