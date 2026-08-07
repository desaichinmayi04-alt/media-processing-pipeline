# Intelligent Media Processing Pipeline

An async backend that accepts uploaded vehicle field-photos, queues them for
analysis, runs 8 independent quality/fraud heuristics against each image, and
aggregates the results into a single explainable **trust score** rather than
a flat pass/fail.

Built for the Backend + AI Engineering take-home assignment.

---

## Why a trust score, not a checklist

The brief explicitly says the goal isn't ML accuracy, it's "structuring
uncertainty." Every one of these heuristics — blur, screenshot detection,
photo-of-photo, tampering — has real false-positive modes on a normal outdoor
photo. Returning `{"blurry": true}` misrepresents that uncertainty as fact.

So every check returns `{passed, confidence, message, details}`, and
`app/analyzers/scoring.py` combines them into a single 0–100 `trust_score`
plus a `clean` / `flagged` / `suspicious` verdict, using per-check weights
(duplicate + plate validation matter more than brightness for this use case)
scaled by each check's own confidence. A low-confidence flag can't tank the
score the way a high-confidence one does. This is a decision-support number
for a human reviewer, not an auto-reject gate — deliberately, since the
assignment says accuracy isn't the point.

---

## Architecture

```
                    ┌─────────────┐
  client  ──POST──▶ │  FastAPI    │──save file──▶ local disk / S3-ready
                    │  (api)      │──insert row─▶ Postgres/SQLite
                    └──────┬──────┘
                           │ enqueue(image_id)
                           ▼
                    ┌─────────────┐
                    │    Redis    │  (broker + result backend)
                    └──────┬──────┘
                           ▼
                    ┌─────────────┐
                    │   Celery    │──8 analyzers──▶ aggregate score
                    │   worker    │──update row───▶ Postgres/SQLite
                    └─────────────┘

  client ──GET /status──▶  poll until completed/failed
  client ──GET /results─▶  full check breakdown + trust_score + verdict
```

### Service flow
1. `POST /api/v1/images` — validates content-type/size, streams the file to
   storage, inserts a DB row with `status=pending`, enqueues a Celery task,
   and returns the `id` immediately (no blocking on analysis).
2. Celery worker picks up `process_image(image_id)`, flips status to
   `processing`, runs all 8 analyzers, aggregates them, writes the full
   result back to the same row, flips status to `completed` (or `failed`).
3. `GET /status` and `GET /results` are separate endpoints on purpose —
   status is cheap and pollable at high frequency; results is the heavier
   payload you fetch once, when done. `/results` returns `409` (not `200`
   with null fields) while processing is in flight, so a client can't
   mistake "not ready" for "ready but empty."

### Queue strategy
Celery + Redis, not an in-memory queue. An in-memory queue would be simpler
to demo but dies with the process — for a system whose entire premise is
"accept the upload immediately, process it after," losing the queue on a
restart is exactly the failure this architecture exists to avoid. Redis
was picked over RabbitMQ/SQS for this assignment's scope: it's a single
extra container, needs no cloud account to run locally, and Celery's Redis
transport is mature. Documented trade-off: Redis-as-broker doesn't give the
delivery guarantees a purpose-built broker (RabbitMQ) or managed queue (SQS)
would at real scale — noted below.

### Major design decisions
- **JSON column for `checks`**, not a normalized child table. At one
  analysis pass per image with a fixed-ish set of checks, a join buys
  little and costs query simplicity. If checks needed independent
  querying/filtering at scale ("show me all images that failed
  duplicate_detection this week"), this is the first thing I'd normalize —
  noted in Trade-offs.
- **`run_safely()` wrapper per analyzer** (`app/tasks.py`) — one analyzer
  throwing (e.g. OCR binary missing) degrades to a low-confidence failed
  check for *that* analyzer, not a failed job. The rest of the analysis
  still completes and is still useful to a reviewer.
- **Two-tier failure handling** — `UnprocessableImageError` (corrupt file,
  can't even decode) fails immediately with no retry, since retrying won't
  fix a corrupt file. Any other exception is treated as transient and
  retried up to 3 times with exponential backoff (5s, 10s, 20s) before
  giving up and marking `failed` with a reason.
- **Perceptual hash for duplicates**, not a byte checksum. Field photos get
  re-compressed and re-shared (WhatsApp, gig-app overlays) between the
  original camera shot and what actually reaches the server — a checksum
  would miss almost every real duplicate. Verified against the provided
  samples: sample 1 and sample 3 are byte-different-adjacent copies of the
  same photo, and duplicate detection correctly caught it at hash distance
  0 (`test_output/sample_3_pune_arena_dup_result.json`).

---

## The 8 checks

| Check | What it does | Known limitation |
|---|---|---|
| `blur_detection` | Laplacian variance (sharp edges → high variance) | Flags genuinely flat/plain surfaces as blurry |
| `brightness_analysis` | Mean pixel intensity, flags under/over-exposure | Doesn't account for intentional silhouette/backlit shots |
| `duplicate_detection` | Perceptual hash (pHash) vs. all prior completed uploads | O(n) scan against history — fine at assignment scale, needs an index/ANN structure at real scale |
| `ocr_plate_validation` | Tesseract OCR + regex for Indian plate formats (incl. BH-series) | OCR accuracy on small/angled plates in a full-frame photo is inherently limited |
| `screenshot_detection` | No camera EXIF + dimensions matching a known device screen resolution | Many legitimate photos also lack EXIF (stripped by messaging apps) — weighted as a weak signal, not conclusive alone |
| `photo_of_photo_heuristic` | FFT frequency-domain energy ratio (moire/screen-recapture signature) | False-positives on genuinely high-detail textures (seen on all 3 samples — the vinyl ad wraps have exactly this kind of high-frequency print texture) |
| `metadata_analysis` | EXIF presence + known-editor `Software` tag (Photoshop/GIMP/etc.) | Absence of EXIF alone is weak evidence, weighted accordingly |
| `tampering_heuristic_ela` | Error Level Analysis (re-save at fixed JPEG quality, diff) | Meaningful mainly for JPEG sources; auto-passes with a note on PNG input (all 3 samples were PNG, so this check is honest about contributing near-zero signal there) |

---

## AI Usage Disclosure (mandatory per assignment)

I used Claude throughout this build. Concretely:

**Where AI helped:**
- Scaffolding the boilerplate (FastAPI routing, SQLAlchemy models,
  Pydantic schemas, Celery config) — the parts with one obviously-correct
  shape, where hand-typing would just be slower.
- Drafting the initial versions of each analyzer function from a
  description of the heuristic (e.g. "use Laplacian variance for blur").
- Writing the pytest suite structure and Docker/Compose files.

**Where AI output was wrong, and how I caught it:**
- The Celery app didn't register `app.tasks.process_image` because the
  task module was never imported — the worker started clean but logged an
  **empty `[tasks]` list**. Caught by actually starting the worker and
  reading its startup log, not by reading the code. Fixed by adding
  `include=["app.tasks"]` to the Celery app constructor.
- `imagehash`'s Hamming-distance subtraction (`hash1 - hash2`) returns a
  **numpy `int64`**, not a plain Python `int`. SQLAlchemy's JSON column
  serializer doesn't know how to serialize that, so every upload after the
  first one silently failed and infinitely retried
  (`TypeError: Object of type int64 is not JSON serializable`, visible only
  in the Celery worker log, not in the API response). Caught by uploading
  the actual sample images end-to-end and watching the task retry loop in
  the logs rather than trusting the "looks right" code. Fixed with an
  explicit `int(...)` cast at the point the value leaves `imagehash` and
  enters anything that gets persisted.
- Neither bug was something I'd have caught from reading the diff — both
  only surfaced by running the real pipeline against real images and
  reading worker logs, which is why the submission includes
  `test_output/*.json` as evidence this was actually exercised, not just
  written.

**How I validated AI-generated code generally:** every analyzer was run
against the 3 real sample images (not just synthetic test fixtures) before
being considered done, and the full upload → queue → process → results
round-trip was run against a live server, not just unit-tested in
isolation. `tests/test_analyzers.py` covers the pure-logic pieces
(deterministic synthetic images); `tests/test_api.py` covers the HTTP
contract with the Celery call mocked out (so tests don't require a live
Redis); `scripts/test_with_samples.py` covers the real end-to-end path
against a live server and is what produced `test_output/`.

---

## Trade-offs

**Intentionally simplified:**
- Storage is local disk, not S3/GCS — `app/storage.py` is a thin
  interface specifically so this swap is one function, not a refactor, but
  I didn't wire up an actual cloud backend given the time box.
- No auth/API keys on the endpoints — out of scope for a take-home, would
  be required before this touches real traffic.
- Duplicate detection scans all prior completed rows linearly. Fine at
  hundreds/thousands of images; would need a proper index (e.g. a
  vector/BK-tree structure, or bucketing by hash prefix) past that.
- Heuristic thresholds (blur, brightness, FFT ratio, ELA spike) are
  reasonable starting points, not calibrated against a labeled dataset —
  they're all env-configurable (`app/config.py`) for exactly this reason.

**What I'd improve with more time:**
- Replace the plain OCR+regex plate check with a plate *detection* step
  first (crop to the plate region) before OCR, instead of running OCR over
  the full frame — would materially improve accuracy.
- Calibrate the photo-of-photo and screenshot heuristics against a labeled
  set — right now both correctly flag as "not certain" on the real samples
  (which do trigger the photo-of-photo heuristic due to the printed ad
  vinyl's texture), which is the honest outcome given no ground truth, but
  a labeled set would let me tighten the thresholds with actual precision/
  recall numbers instead of judgment calls.
- Add idempotency handling for duplicate task delivery (Celery's
  `acks_late=True` means a worker crash mid-task can redeliver it — the
  task is currently not strictly idempotent if it crashes after partial
  DB writes, though the single-transaction-per-task design makes this a
  narrow window).
- Structured logging (JSON logs with request/task IDs) instead of the
  current plain Python logging, for real observability.

**Scalability concerns:**
- Single Celery worker process shown in Compose; horizontal scaling is
  "add more worker replicas," which Celery supports natively, but wasn't
  load-tested here.
- SQLite is the local-dev default specifically because it needs no setup;
  Postgres is a one-env-var swap and is what `docker-compose.yml` uses.

**Failure-handling concerns:**
- Transient failures retry 3x with exponential backoff before landing on
  `failed` with a stored `failure_reason` — verified by the design, not
  by forcing an actual transient failure in this test run (would need
  fault injection, e.g. temporarily killing Redis mid-task, to demonstrate
  live).

---

## Running instructions

### Option A — Docker Compose (recommended, one command)
```bash
docker compose up --build
```
This starts Postgres, Redis, the API, and the worker together. API is at
`http://localhost:8000`.

### Option B — Local (no Docker)
Requires: Python 3.11+, Redis running locally, `tesseract-ocr` installed
(`apt install tesseract-ocr` / `brew install tesseract`).

```bash
pip install -r requirements.txt
redis-server --daemonize yes

# Terminal 1
uvicorn app.main:app --reload

# Terminal 2
celery -A app.celery_app worker --loglevel=info
```

Defaults to a local SQLite file at `storage/app.db` — no Postgres needed
for local dev. Set `DATABASE_URL` in `.env` (see `.env.example`) to point
at Postgres instead.

### Run the test suite
```bash
pytest tests/ -v
```

### Test against the 3 sample images
```bash
python scripts/test_with_samples.py
# or, against a deployed instance:
python scripts/test_with_samples.py https://your-deployed-url.example.com
```
Writes each result to `test_output/*.json` and a `test_output/summary.json`.

---

## API reference

### `POST /api/v1/images`
Multipart upload, field name `file`. Returns `202`:
```json
{
  "id": "dffb82a8-938d-42e4-94f6-8675fae49544",
  "status": "pending",
  "status_url": "/api/v1/images/dffb82a8.../status",
  "results_url": "/api/v1/images/dffb82a8.../results"
}
```

### `GET /api/v1/images/{id}/status`
```json
{
  "id": "dffb82a8-938d-42e4-94f6-8675fae49544",
  "status": "completed",
  "uploaded_at": "2026-08-06T08:10:00Z",
  "processing_started_at": "2026-08-06T08:10:01Z",
  "processed_at": "2026-08-06T08:10:03Z",
  "retry_count": 0,
  "failure_reason": null
}
```

### `GET /api/v1/images/{id}/results`
`409` while not yet completed. On completion:
```json
{
  "id": "dffb82a8-938d-42e4-94f6-8675fae49544",
  "status": "completed",
  "trust_score": 75.1,
  "verdict": "flagged",
  "checks": [
    {"name": "blur_detection", "passed": true, "confidence": 0.99, "message": "...", "details": {...}},
    ...
  ]
}
```
See `test_output/*.json` for full real examples from the 3 provided samples.

### `GET /api/v1/images`
Lists recent uploads with status (pagination via `?limit=`).

---

## Assumptions
- Assumed "invalid vehicle number format" means Indian plate formats
  specifically, given the sample images and context (Maharashtra/Tamil
  Nadu plates).
- Assumed the 3 provided samples (two of which are the same underlying
  photo) were partly intended to give duplicate detection something real
  to catch — treated that as a deliberate test case rather than a fluke.
- Assumed "at least 4 meaningful checks" meant 4 was a floor, not a
  target — implemented 8 to give the trust-scoring engine enough signal
  to be meaningfully weighted rather than trivial.
