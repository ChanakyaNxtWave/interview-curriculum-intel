# KP Mapping Workflow (Manual)

One-off workflow to map **Programming Foundations** curriculum content to knowledge points (KPs) using an LLM (OpenRouter by default, with Groq and Gemini fallbacks), with a human review UI.

This is **not** wired into the main interview-curriculum pipeline.

## What it does

1. **KP catalog** — `KPs-ProgrammingFoundations.csv` → `KPs-ProgrammingFoundations.json`
2. **Content discovery** — scans `curriculum/ProgrammingFoundations/**/*.json` (reading materials, coding questions, projects when present). Skips entries listed in `curriculum/rm_list.json`.
3. **AI mapping** — LLM calls assign one or more `source_kp_id` values per content piece with per-tag confidence (`high` / `medium` / `low` / `uncertain`). If the primary provider fails, the next provider in `LLM_PROVIDER_ORDER` is tried automatically.
4. **Coding / projects** — KPs are inferred **only from official solution code** in the JSON (`codes` with `default_code: true`). Missing or ambiguous solutions are **flagged**; the model must not guess from the problem statement alone.
5. **Human review UI** — filter flagged items, edit tags, approve or reject

## Setup

```bash
cd kp-mapping
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env — set OPENROUTER_API_KEY (primary) and optional GROQ_API_KEY / GEMINI_API_KEY fallbacks
```

Scripts automatically load `kp-mapping/.env`. You do **not** need to `export` variables unless you prefer shell-level config.

### LLM provider fallback

`run_mapping.py` tries providers in order (default: `openrouter` → `groq` → `gemini`). Configure in `.env`:

| Variable | Purpose |
|----------|---------|
| `LLM_PROVIDER_ORDER` | Comma-separated list, e.g. `openrouter,groq,gemini` |
| `OPENROUTER_API_KEY` / `OPENROUTER_MODEL` | Primary (OpenRouter) |
| `GROQ_API_KEY` / `GROQ_MODEL` | Fallback (OpenAI-compatible API) |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | Fallback (Google Generative Language API) |

Stored mappings record which provider succeeded (e.g. `groq:llama-3.3-70b-versatile`).

## 1. Convert CSV to JSON

```bash
python scripts/convert_kps_csv_to_json.py
```

Output: `../curriculum/KPs-ProgrammingFoundations.json`

## 2. Run mapping (manual)

List content without API calls:

```bash
python scripts/run_mapping.py --dry-run
```

Pilot on a few reading materials:

```bash
python scripts/run_mapping.py --limit 10 --types reading_material
```

Map coding questions (solution-based):

```bash
python scripts/run_mapping.py --types coding_question --limit 20
```

Full course (617 items — plan API cost and time):

```bash
python scripts/run_mapping.py
```

Single item:

```bash
python scripts/run_mapping.py --content-id 8068bbeb-83ee-444d-ac68-b99cc987d171
```

### Only unapproved (skip already approved)

Runs everything that is **not** `review_status=approved`: never-mapped files plus `pending`, `needs_review`, and `rejected` rows in the DB.

```bash
# Preview
python scripts/run_mapping.py --only-unapproved --types reading_material --dry-run

# All unapproved reading materials
python scripts/run_mapping.py --only-unapproved --types reading_material

# All unapproved coding questions
python scripts/run_mapping.py --only-unapproved --types coding_question
```

Results are stored in `data/kp_mappings.db`.

## 3. Human review UI

```bash
python scripts/run_review_ui.py
```

Open http://localhost:8765

**Sidebar filters** (server-backed; combine as needed):

| Filter | What it does |
|--------|----------------|
| Search | Title, topic name, or content ID |
| Review | AI flagged, or workflow status (`pending`, `needs_review`, `approved`, `rejected`) |
| Content type | Reading material, coding question, project |
| Topic | Unit/topic name from curriculum |
| Knowledge point | Items tagged with a specific `source_kp_id` (AI or human tags) |
| AI confidence | `high` / `medium` / `low` / `uncertain` |
| Tags | Has tags vs no tags |

Use **Clear** to reset all filters. The summary line shows how many items match.

- Edit KP tags (search by id or label), roles, confidence, rationale
- Set review status: `pending`, `needs_review`, `approved`, `rejected`
- **Save review** writes human overrides to SQLite

## Confidence and flags

| Signal | Meaning |
|--------|---------|
| `high` / `medium` / `low` / `uncertain` | Per-tag and overall confidence from the model |
| `needs_human_review` | AI or rules flagged the row (missing solution, unknown KP ids, empty mapping, etc.) |
| Review reasons | Stored on the mapping for the reviewer |

## Content types

| File suffix | Type |
|-------------|------|
| `*_reading_material.json` | `reading_material` |
| `*_coding.json` | `coding_question` |
| `*_project.json` | `project` |

## Model

Default OpenRouter model: `anthropic/claude-sonnet-4.5`. Override with `OPENROUTER_MODEL` in `.env` or `--model` on the CLI.
