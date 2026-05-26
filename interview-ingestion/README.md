# Interview question ingestion

Pulls interview questions from the shared Google Sheet **`assessments`** tab into normalized JSON.

## Source

| Item | Value |
|------|--------|
| Sheet | [Interview data](https://docs.google.com/spreadsheets/d/1JBad-m1Wq4tkTe4zO8Gm_f0ZYc6EydlVyLxWxwItIeA/edit) |
| Tab | `assessments` |
| Config | `../config/interview_sheet.json` |

Sheet must be **Anyone with the link → Viewer** (or broader).

## Columns (assessments tab)

| Sheet column | Normalized field | PRD |
|--------------|------------------|-----|
| Question UUID | `question_uuid` | Optional |
| Question | `question` | Required |
| Question Type | `question_type` | Optional (`THEORY`, `CODING`, …) |
| Skills Assessed Remarks | `skills_assessed_remarks` | Optional |
| Remarks | `remarks` | Optional |
| Company Name | `company_name` | Required |
| Role | `role` | Optional |
| Tech Stack | `tech_stack` | Optional |
| Interview Round Date | `interview_date` | Preferred |
| Product | `product` | Optional |
| Minimum / Maximum CTC in LPA | `minimum_ctc_lpa`, `maximum_ctc_lpa` | Optional |

Job/candidate metadata (Job ID, Round Category, etc.) is also stored for context.

## Run

```bash
cd interview-ingestion
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python scripts/sync_from_sheet.py
python scripts/sync_from_sheet.py --print-sample 3
```

Output: `data/interview_questions.json`

## Relation to other workflows

| Workflow | Purpose |
|----------|---------|
| **interview-ingestion** (this) | Sheet → interview question JSON |
| **kp-mapping** | Curriculum content → KP tags |
| **Gap intelligence** (future) | Interview Q + tagged curriculum → coverage / gaps |
