# Question Paper Generator

Monorepo for a concept-grounded, Bloom-aligned examination paper generator.

```text
backend/   FastAPI, PDF inspection, multimodal analysis, blueprints, validation
frontend/  React, TypeScript, upload workflow, paper preparation review
```

## Start the backend

```bash
conda activate ques-gen
cd backend
pip install -e '.[dev]'
cp .env.example .env
# Add AWS credentials with Bedrock InvokeModel permission to .env, or use an AWS profile/role
set -a && source .env && set +a
uvicorn question_paper_gen.api:app --reload
```

## Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. The frontend expects the API at
`http://127.0.0.1:8000` unless `VITE_API_BASE_URL` is configured.

The upload screen accepts an optional inclusive textbook page range. Leave both
page fields blank to use the complete PDF; otherwise, only the selected pages
are copied into the AI source document. The resulting source pages define the permitted
concepts, methods, formulas, terminology, and syllabus scope; generated questions
may use original self-contained scenarios, datasets, names, quantities, and
values. The generated draft uses the supplied sample paper's exact fixed
80-mark structure: 18 regular MCQs, 2
Assertion–Reason questions, 5 very-short answers, 6 short answers, 4 long
answers, and 3 case studies. The structure is subject-neutral and applies to
mathematics, physics, chemistry, computing, commerce, humanities, and other
supported source material.

Topic coverage is weighted by the amount and depth of verified instructional
evidence. The requested Bloom distribution is preserved where the source can
support it and adapted where higher-order demand would be artificial. Concrete
defects are regenerated question by question; wording heuristics and a numeric
quality score alone do not block an otherwise valid question.

Case studies must provide a substantive original scenario or dataset whose
information is necessary for all three connected subquestions. Visual questions
remain tied to verified textbook figures: the figure must match the assigned
topic and be necessary to solve the question.

Completed generations save question-only JSON and readable Markdown under
`test_papers/`. Downloadable PDF papers are saved separately under `outputs/`.
Internal verification solutions are not returned or persisted.

The AI provider is AWS Bedrock. By default it uses the US Claude Haiku 4.5
cross-region inference profile, with Claude 3.5 Haiku as a transient-failure
fallback. Analysis, generation, and review can each run on a different model
via `BEDROCK_ANALYSIS_MODEL`, `BEDROCK_GENERATION_MODEL`, and
`BEDROCK_REVIEW_MODEL`; generation runs warm (temperature 0.7 by default) and
review runs cold (0.1). Sections are generated and independently reviewed in a
pipelined, bounded-concurrency flow, and defective questions are repaired
concurrently through targeted per-question regeneration-and-review gates.
