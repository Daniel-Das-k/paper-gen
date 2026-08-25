# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A monorepo for a source-grounded, Bloom-aligned examination paper generator: a FastAPI backend (`backend/`) that turns an uploaded textbook PDF into an 80-mark question paper via AWS Bedrock (Claude), and a React/TypeScript frontend (`frontend/`) for the upload-and-review workflow.

Note: the top-level `src/` and `tests/` directories contain only stale `__pycache__` leftovers from an earlier layout — the real code is in `backend/src/` and `backend/tests/`.

## Commands

### Backend (from `backend/`)

```bash
conda activate ques-gen            # project Conda env
pip install -e '.[dev]'
cp .env.example .env               # then add AWS creds with bedrock:InvokeModel
set -a && source .env && set +a
uvicorn question_paper_gen.api:app --reload   # http://127.0.0.1:8000/docs
```

Tests (pytest config lives in `pyproject.toml`; `pythonpath = ["src"]`):

```bash
pytest                              # whole suite
pytest tests/test_pipeline.py       # one file
pytest tests/test_pipeline.py -k name_of_test   # one test
```

If pytest crashes before collection on Conda/macOS due to a broken `readline` extension, bypass it:

```bash
PYTHONPATH=src python -c "import sys,types; sys.modules['readline']=types.ModuleType('readline'); import pytest; raise SystemExit(pytest.main(['-q']))"
```

CLI PDF inspection without AWS credentials (no model call):

```bash
PYTHONPATH=src python -m question_paper_gen.cli inspect notes.pdf --start-page 40 --end-page 52
PYTHONPATH=src python -m question_paper_gen.cli pattern
```

### Frontend (from `frontend/`)

```bash
npm install
npm run dev          # Vite dev server at http://127.0.0.1:5173
npm run typecheck    # tsc -b, no emit
npm run build        # tsc -b && vite build
```

The frontend expects the API at `http://127.0.0.1:8000` unless `VITE_API_BASE_URL` is set. There is no lint config or frontend test suite.

## Architecture

### Backend pipeline (backend/src/question_paper_gen/)

The generation flow is a staged pipeline; each module owns one stage:

1. **`documents.py`** — local PDF gates (file type, size, page count, password, readability), SHA-256 document identity, page text extraction, page renders, and embedded-figure extraction. Artifacts persist under `backend/artifacts/<document-id>/` (`source-selected.pdf`, `pages/*.png`, `visuals/*.png`) and are reused across requests for the same document/page-range. If the user supplies a page range, a physically isolated `source-selected.pdf` is created *before any model call* so questions cannot be grounded outside the selection.
2. **`ai.py`** — the only module that talks to AWS Bedrock. `DocumentAnalyzer` is a typed provider boundary (pydantic-ai schemas) for: one combined content/figure analysis call, one generation call and one review call per paper part, and targeted per-question repair calls. Models are selected per role (`BEDROCK_ANALYSIS_MODEL` / `BEDROCK_GENERATION_MODEL` / `BEDROCK_REVIEW_MODEL`, each defaulting to `BEDROCK_MODEL`) with a temperature split — generation warm (`GENERATION_TEMPERATURE`, default 0.7), analysis and review cold (0.1). Handles fallback models, transient-failure detection, retries, and output-token limits.
3. **`blueprints.py`** — builds one shared paper blueprint from the content map: evidence-weighted topic coverage and source-adaptive Bloom assignment (higher-order demand is not forced where the source can't support it). Slots sharing a topic get distinct *facets* (`FACET_CYCLE`: computation / concept / application / error analysis / connection / interpretation) assigned round-robin, which is the structural defense against duplicate questions. A capacity check (`topics × facets × 2`) rejects sources too thin for the pattern with a `BlueprintError` telling the user to widen the page range.
4. **`patterns.py`** — the selectable paper patterns and the registry that resolves them (`get_pattern`, `available_patterns`, `DEFAULT_PATTERN_ID`). The product ships one: `autonomous-semester-100`, the Anna University style 100-mark/3-hour end-semester paper — Part A 10 VSA ×2, Part B 5 LA ×13 with an either/or choice and (i) 7 / (ii) 6 subparts, Part C 1 LA ×15 choose-one. Subject-neutral. An unknown `pattern_id` raises rather than falling back, so a stale client cannot silently receive a different paper.
5. **`pipeline.py`** — `PaperGenerationPipeline` orchestrates everything: each section is generated and then immediately reviewed in its own pipelined task under bounded concurrency (`SECTION_GENERATION_CONCURRENCY`, ordering preserved), with deterministic validation in between; cross-section duplicates are caught by the local duplicate detector. Defective questions go through a converging repair ladder (up to 4 attempts, concurrent): attempts 1–2 retry the slot as specified, attempt 3 swaps the facet, attempt 4 swaps the topic — the spec changes rather than being retried forever (visual slots never topic-swap). Repairs are grounded in evidence chunks and skip the PDF attachment unless `REPAIR_ATTACH_SOURCE_PDF=true`. A clean generation is 1 analysis call plus one generate and one review call per part — seven for the shipped three-part pattern. `evaluate.py` is the reliability harness: `PYTHONPATH=src python -m question_paper_gen.evaluate <pdf> --runs N` reports publication-ready rate, rejection codes, and duplicate groups per run.
6. **`validation.py`** — deterministic checks (marks, evidence, Bloom, visuals, choices, case-study structure, confidence) plus whole-paper semantic duplicate detection. `subject_profiles.py` provides subject-aware verification profiles (math, computing, sciences, commerce, humanities, general).
7. **`evidence.py`** — backend-owned evidence chunks attached to questions; the model never authors its own citations. Answer-key pages (an `ANSWERS` running head, or dense enumerated answers) are excluded from chunking, so exercise-answer appendices cannot serve as topic evidence — the analysis prompt additionally refuses mainly-answers selections via `instructional_content_sufficient=false`.
8. **`outputs.py`** — saves question-only JSON + Markdown to `test_papers/` and downloadable PDFs to `outputs/`, plus a separate `-scheme.pdf` scheme of evaluation via `save_evaluation_scheme()` (override via `TEST_PAPER_OUTPUT_DIR` / `PDF_OUTPUT_DIR`).
9. **`api.py`** — FastAPI endpoints. The two workflow endpoints matter most: `POST /v1/workflows/prepare` (inspection + analysis + content map + blueprint — the fast/cheap way to test) and `POST /v1/workflows/generate` (full paper). Generate reuses prepared results so it doesn't repeat PDF analysis. Also: `/v1/documents/inspect` (local-only), `/v1/documents/analyze`, `/v1/blueprints/build`, `/v1/patterns` and `/v1/patterns/{id}`, secure figure delivery at `/v1/documents/{id}/visuals/{asset_id}`, and paper plus scheme download at `/v1/generated-papers/{filename}`.

`models.py` holds the shared pydantic models (`ContentMap`, `PaperBlueprint`, `QuestionCandidate`, `ValidatedQuestion`, `ExamPaper`, …) that flow between stages.

### Design invariants to preserve

- **Grounding contract**: source pages constrain concepts, methods, formulas, terminology, and syllabus scope — but generated questions may use original self-contained scenarios, names, datasets, and values. Case studies need a substantive shared scenario required by all three subquestions; visual questions must use a verified textbook figure that matches the topic and is necessary to solve the question.
- **Answers and marking schemes reach faculty only through the scheme of evaluation.** The question paper (JSON, Markdown, PDF) and every API response body stay answer-free — `GeneratedQuestionPaper.from_internal()` strips them. Faculty see them two ways: inline in the review panel via the separate `answer_key` field (`AnswerKeyEntry`, carried *beside* the paper in the API response, never inside it), and in the downloadable scheme PDF written by `save_evaluation_scheme()`, which colleges submit to the exam cell alongside the paper; it leads with the mark-wise criteria valuers mark from and flags any question that failed review. Evidence excerpts remain internal verification data throughout.
- Concrete defects trigger per-question regeneration; wording heuristics or the numeric quality score alone must not block an otherwise valid question. Every question must pass the publication gate, and papers still require faculty approval.
- Bedrock config lives in env vars (see `backend/.env.example`): `BEDROCK_MODEL` (default Claude Haiku 4.5 US inference profile) with `BEDROCK_FALLBACK_MODELS` for transient failures.

### Frontend (frontend/src/)

Small single-page app: `pages/DashboardPage.tsx` drives the flow, `components/upload/UploadPanel.tsx` (file + optional page range + paper pattern) → `services/api.ts` (all HTTP calls) → `components/results/WorkflowResultPanel.tsx` (part-grouped review showing either/or alternatives, per-question marks and verified Bloom level, Bloom coverage, and validation findings). API types mirror backend models in `types/api.ts`.
