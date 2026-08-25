# Question Paper Generator Backend

An early backend for generating concept-grounded examination papers from
uploaded textbooks or notes. The system preserves page evidence and extracted figures, creates
one shared Bloom-aligned blueprint, generates questions against that blueprint,
and rejects candidates that fail deterministic or independent AI review.

This is an AI-assisted drafting system. Papers require faculty approval before
they are used for an examination.

## Implemented

- PDF file, size, page-count, password, and readability gates
- Answer-key and exercise-answer pages excluded from topic evidence, with a
  model-side sufficiency refusal when the selection is mainly answers
- SHA-256 document identity and reusable artifact storage
- Page text extraction and high-resolution page renders
- Embedded figure extraction with bounding boxes, captions, and nearby text
- One-call content and bounded multimodal figure analysis
- Structured content map with topics, units, source pages, and Bloom support
- Exact sample-paper-aligned 80-mark/three-hour pattern with 18 regular MCQs,
  2 Assertion–Reason questions, 5 VSA, 6 SA, 4 LA, and 3 case studies
- Optional original-PDF page range, with full-document fallback and a physically
  isolated source PDF
- Concept-level grounding: source pages constrain concepts, methods, formulas,
  terminology, and syllabus scope without forcing generated values or scenarios
  to be copied from the PDF
- Original self-contained applications with independently reviewed names,
  contexts, datasets, quantities, and values
- Substantive case studies whose shared scenario or dataset is required by all
  three connected subquestions
- Shared paper blueprint with evidence-rich topic weighting
- Facet-diversified slots: questions sharing a topic take different angles
  (computation, concept, application, error analysis, connection,
  interpretation), so a narrow chapter cannot produce near-duplicate tasks
- Capacity fail-fast: when the selected pages cannot support the pattern's
  question count without repetition, the blueprint step rejects the request
  with guidance to widen the page range
- Source-adaptive Bloom assignment that avoids artificial higher-order demand
- Diagram slots only when a figure passes visual verification
- Candidate questions with evidence, answers, Bloom justification, and rubric
- Backend-owned evidence chunks instead of model-authored citations
- Deterministic marks, evidence, Bloom, visual, choice, case-study, and confidence checks
- Whole-paper semantic duplicate detection
- Visual-to-topic matching with visual-necessity review
- Subject-aware verification profiles for mathematics, computing, sciences,
  commerce, humanities, and general material
- Independent per-section LLM quality control for correctness, difficulty, Bloom
  demand, answer options, rubrics, choices, visuals, and pedagogical value,
  pipelined so each section is reviewed as soon as it is generated
- Per-question quality scores used to trigger improvement without acting as a
  stand-alone publication gate
- Explicit publication gate: every question must pass, then faculty must approve
- Question-only review UI with automated validation status and findings
- Five section-generation calls plus five per-section review calls
- Per-role model selection (`BEDROCK_ANALYSIS_MODEL`, `BEDROCK_GENERATION_MODEL`,
  `BEDROCK_REVIEW_MODEL`) with a temperature split: creative generation
  (default 0.7) and cold, independent review (default 0.1)
- Prepared-result reuse so Generate does not repeat PDF analysis
- Converging repair ladder with up to four attempts per defective question,
  run concurrently with bounded parallelism: attempts 1-2 retry the slot as
  specified, attempt 3 swaps the slot's facet, attempt 4 swaps its topic —
  an unsatisfiable spec is changed rather than retried forever. Repaired
  questions are reviewed individually without re-reviewing their section
- A reliability evaluation harness
  (`PYTHONPATH=src python -m question_paper_gen.evaluate pdfs/chapter.pdf
  --start-page 1 --end-page 28 --runs 3`) that reports publication-ready
  rate, rejection codes, duplicate groups, quality scores, and timing per
  run, appending JSONL records for regression comparison across versions
- Secure extracted-figure delivery for visual questions in the review UI
- FastAPI endpoints and an end-to-end upload workflow
- Automatic JSON and Markdown saving under `../test_papers/`, with downloadable
  PDF papers saved under `../outputs/`

Persistent users/projects, authentication, faculty editing, audit history, job
queues, vector-diagram cropping, handwritten OCR, and Word export are still
required before a public multi-user deployment.

## Run locally

Activate the project's Conda environment, then install the project:

```bash
conda activate ques-gen
pip install -e '.[dev]'
```

Copy `.env.example` to `.env` and configure AWS credentials that have
`bedrock:InvokeModel` permission, or use an AWS profile/instance role. Never
commit real credentials. Export the values before starting the API:

```bash
set -a
source .env
set +a
uvicorn question_paper_gen.api:app --reload
```

Open `http://127.0.0.1:8000/docs` to use the interactive API.

## Fastest test

Use `POST /v1/workflows/prepare` first. It performs:

1. Local PDF inspection
2. Multimodal figure verification
3. Content-map creation
4. Paper-blueprint creation

This is faster and cheaper than generating all questions.

When the preparation output looks correct, use
`POST /v1/workflows/generate`. That endpoint additionally generates and
independently reviews every question. The response includes rejected questions
and reasons instead of silently publishing uncertain content.

The browser uses `POST /v1/workflows/generate` as a single-click workflow. A
clean generation uses eleven Bedrock calls total: one combined analysis, five
section generations, and five per-section reviews. Each section is reviewed
immediately after it is generated, so the wall-clock cost of a section is one
generation plus one small review rather than waiting for a whole-paper barrier.
Sections run with bounded concurrency (`SECTION_GENERATION_CONCURRENCY=5` by
default), preserving section ordering in the finished paper. Cross-section
duplicates are caught by the deterministic whole-paper duplicate detector.
Defective questions add one targeted regeneration and one independent review
per attempt, with at most two attempts per question; repairs for different
questions run concurrently under the same concurrency bound. Repair calls are
grounded in the slot's evidence chunks and do not re-send the source PDF unless
`REPAIR_ATTACH_SOURCE_PDF=true`.

```bash
curl -X POST \
  -F 'file=@/absolute/path/to/notes.pdf' \
  -F 'start_page=40' \
  -F 'end_page=52' \
  http://127.0.0.1:8000/v1/workflows/prepare
```

Generate a complete draft:

```bash
curl -X POST \
  -F 'file=@/absolute/path/to/notes.pdf' \
  -F 'start_page=40' \
  -F 'end_page=52' \
  http://127.0.0.1:8000/v1/workflows/generate
```

Both workflow endpoints accept optional `start_page` and `end_page` fields. If
both are omitted, the backend uses the complete PDF. If either boundary is
provided, the missing start defaults to the first page and the missing end to
the final page. The backend creates `source-selected.pdf` containing that
resolved range before any model call, so questions cannot be grounded outside
the selected context.

The default pattern follows the supplied sample paper:

- Section A: 18 MCQs + 2 Assertion–Reason questions × 1 mark
- Section B: 5 very-short answers × 2 marks
- Section C: 6 short answers × 3 marks
- Section D: 4 long answers × 5 marks
- Section E: 3 case studies × 4 marks

Successful generations save JSON and Markdown records in `../test_papers/` by
default and downloadable PDFs in `../outputs/`. Set `TEST_PAPER_OUTPUT_DIR` and
`PDF_OUTPUT_DIR` to override those locations. Answers, marking schemes, Bloom
justifications, and evidence excerpts remain temporary internal verification
data and are not returned or saved.

Other useful endpoints:

- `GET /health`
- `GET /v1/patterns/default`
- `POST /v1/documents/inspect` — local processing; no model call
- `POST /v1/documents/analyze`
- `POST /v1/blueprints/build`

## CLI inspection without an API key

```bash
PYTHONPATH=src python -m question_paper_gen.cli inspect notes.pdf --start-page 40 --end-page 52
PYTHONPATH=src python -m question_paper_gen.cli pattern
```

Artifacts are stored under `artifacts/<document-id>/`:

```text
source-selected.pdf
pages/page-0001.png
visuals/page-0001-image-01.png
```

## Tests

```bash
pytest
```

On some Conda/macOS combinations, importing the environment's `readline`
extension can crash pytest before collection. This is an environment issue, not
a test failure. The suite can be run while bypassing that broken extension:

```bash
PYTHONPATH=src python -c "import sys,types; sys.modules['readline']=types.ModuleType('readline'); import pytest; raise SystemExit(pytest.main(['-q']))"
```

