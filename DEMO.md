# REC Question Paper Studio — Local Demo

This is a single-machine product demonstration. Faculty, HOD, and CoE roles are
simulated with the role selector; they are not authenticated accounts.

## Setup

1. Activate the `ques-gen` Conda environment.
2. Copy `backend/.env.example` to `backend/.env` and configure working AWS
   Bedrock credentials.
3. Install backend packages with `cd backend && pip install -e '.[dev]'`.
4. Install frontend packages with `cd frontend && npm install`.
5. From the repository root, run `./scripts/demo.sh`.
6. Open `http://127.0.0.1:5173`.

Generation is live and normally takes several minutes. Keep the backend terminal
visible so configuration or model errors are easy to diagnose.

## Suggested presentation

1. Stay in the Faculty role and create a CAT-I paper for Data Structures.
2. Show that the upload list requires Units 1, 2, and the CAT-I portion of Unit 3.
3. Start generation and point out the backend-owned progress stages.
4. Review grounding, CO/Bloom coverage, question findings, and the REC print preview.
5. Edit one question together with its answer and marking criteria, then download
   the recreated PDF, editable Word paper, and scheme PDF.
6. Submit to HOD, switch roles, approve for CoE, then give final CoE approval.
7. Open Paper history to show that the paper and activity trail survive restarts.

Use `./scripts/reset-demo.sh` when you deliberately want to remove all local demo
records, uploaded demo PDFs, and demo-specific exports.
