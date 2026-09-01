import type {
  DemoJob,
  DemoPaperRecord,
  DemoPaperSummary,
  DemoRole,
  ExamHeader,
  FullWorkflowResponse,
  PaperPattern,
  SyllabusExtraction,
} from "../types/api";
import {
  mockCreateJob,
  mockEditQuestion,
  mockExtractSyllabus,
  mockGetJob,
  mockGetPaper,
  mockListPapers,
  mockPatterns,
  mockRegenerateQuestion,
  mockTransitionPaper,
  mockUpdateHeader,
} from "./mockData";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

interface ApiErrorBody {
  detail?: string;
}

/**
 * When the backend is unreachable the app switches to the built-in demo
 * dataset for the rest of the session. HTTP errors from a live backend
 * (4xx/5xx) are NOT treated as "unreachable" and still surface to the user;
 * only network-level failures (fetch rejecting with a TypeError) flip this.
 */
let usingMockData = false;

function isNetworkFailure(error: unknown): boolean {
  return error instanceof TypeError;
}

async function withMockFallback<T>(
  real: () => Promise<T>,
  mock: () => T,
): Promise<T> {
  if (usingMockData) return mock();
  try {
    return await real();
  } catch (error) {
    if (!isNetworkFailure(error)) throw error;
    usingMockData = true;
    console.info(
      "[QP Studio] Backend unreachable — serving built-in demo data for this session.",
    );
    return mock();
  }
}

async function readApiError(response: Response, fallback: string) {
  try {
    const payload = (await response.json()) as ApiErrorBody;
    return payload.detail ?? fallback;
  } catch {
    return fallback;
  }
}

export interface PageRange {
  startPage?: number;
  endPage?: number;
}

export function getVisualAssetUrl(
  documentId: string,
  assetId: string,
): string {
  return `${API_BASE_URL}/v1/documents/${encodeURIComponent(documentId)}/visuals/${encodeURIComponent(assetId)}`;
}

export function getApiUrl(path: string): string {
  return new URL(path, `${API_BASE_URL}/`).toString();
}

export async function fetchPatterns(): Promise<PaperPattern[]> {
  return withMockFallback(async () => {
    const response = await fetch(`${API_BASE_URL}/v1/patterns`);
    if (!response.ok) {
      throw new Error(`Could not load paper patterns (${response.status})`);
    }
    return (await response.json()) as PaperPattern[];
  }, mockPatterns);
}

export async function extractSyllabus(
  file: File,
): Promise<SyllabusExtraction> {
  return withMockFallback(async () => {
    const body = new FormData();
    body.append("file", file);
    const response = await fetch(`${API_BASE_URL}/v1/syllabus/extract`, {
      method: "POST",
      body,
    });
    if (!response.ok) {
      let message = `Could not read the syllabus (${response.status})`;
      try {
        const payload = (await response.json()) as ApiErrorBody;
        if (payload.detail) message = payload.detail;
      } catch {
        // Keep the status-based message when the server does not return JSON.
      }
      throw new Error(message);
    }
    return (await response.json()) as SyllabusExtraction;
  }, mockExtractSyllabus);
}

export async function runUnitWorkflow(
  uploads: Array<{
    unit: string;
    file: File;
    startPage?: number;
    endPage?: number;
  }>,
  patternId?: string,
  courseOutcomes?: string[],
  setCount = 1,
): Promise<FullWorkflowResponse> {
  const body = new FormData();
  for (const upload of uploads) {
    body.append("files", upload.file);
  }
  body.append(
    "units",
    JSON.stringify(
      uploads.map((upload) => ({
        unit: upload.unit,
        ...(upload.startPage ? { start_page: upload.startPage } : {}),
        ...(upload.endPage ? { end_page: upload.endPage } : {}),
      })),
    ),
  );
  if (patternId) body.append("pattern_id", patternId);
  if (courseOutcomes?.length) {
    body.append("course_outcomes", courseOutcomes.join("\n"));
  }
  body.append("set_count", String(setCount));

  const response = await fetch(`${API_BASE_URL}/v1/workflows/generate-units`, {
    method: "POST",
    body,
  });
  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;
    try {
      const payload = (await response.json()) as ApiErrorBody;
      if (payload.detail) message = payload.detail;
    } catch {
      // Preserve the status-based message when the server does not return JSON.
    }
    throw new Error(message);
  }
  return (await response.json()) as FullWorkflowResponse;
}

export interface DemoExamDetails {
  courseCode: string;
  courseName: string;
  year: string;
  semester: string;
  examDate: string;
}

export async function createDemoGenerationJob(
  uploads: Array<{
    unit: string;
    file: File;
    startPage?: number;
    endPage?: number;
  }>,
  patternId: string,
  courseOutcomes: string[],
  setCount: number,
  details: DemoExamDetails,
  generatedBy: string,
): Promise<DemoJob> {
  return withMockFallback(
    () => createDemoGenerationJobFromApi(uploads, patternId, courseOutcomes, setCount, details, generatedBy),
    () => mockCreateJob(patternId, details, generatedBy),
  );
}

async function createDemoGenerationJobFromApi(
  uploads: Array<{
    unit: string;
    file: File;
    startPage?: number;
    endPage?: number;
  }>,
  patternId: string,
  courseOutcomes: string[],
  setCount: number,
  details: DemoExamDetails,
  generatedBy: string,
): Promise<DemoJob> {
  const body = new FormData();
  uploads.forEach((upload) => body.append("files", upload.file));
  body.append(
    "units",
    JSON.stringify(
      uploads.map((upload) => ({
        unit: upload.unit,
        ...(upload.startPage ? { start_page: upload.startPage } : {}),
        ...(upload.endPage ? { end_page: upload.endPage } : {}),
      })),
    ),
  );
  body.append("pattern_id", patternId);
  body.append("course_outcomes", courseOutcomes.join("\n"));
  body.append("set_count", String(setCount));
  body.append("course_code", details.courseCode);
  body.append("course_name", details.courseName);
  body.append("year", details.year);
  body.append("semester", details.semester);
  body.append("exam_date", details.examDate);
  body.append("department", "Computer Science and Engineering");
  body.append("generated_by", generatedBy);
  const response = await fetch(`${API_BASE_URL}/v1/demo/jobs/generate-units`, {
    method: "POST",
    body,
  });
  if (!response.ok) {
    throw new Error(
      await readApiError(response, `Could not start generation (${response.status})`),
    );
  }
  return (await response.json()) as DemoJob;
}

export async function getDemoJob(jobId: string): Promise<DemoJob> {
  return withMockFallback(async () => {
    const response = await fetch(
      `${API_BASE_URL}/v1/demo/jobs/${encodeURIComponent(jobId)}`,
    );
    if (!response.ok) {
      throw new Error(
        await readApiError(response, `Could not read generation status (${response.status})`),
      );
    }
    return (await response.json()) as DemoJob;
  }, () => mockGetJob(jobId));
}

export async function listDemoPapers(): Promise<DemoPaperSummary[]> {
  return withMockFallback(async () => {
    const response = await fetch(`${API_BASE_URL}/v1/demo/papers`);
    if (!response.ok) {
      throw new Error(
        await readApiError(response, `Could not load papers (${response.status})`),
      );
    }
    return (await response.json()) as DemoPaperSummary[];
  }, mockListPapers);
}

export async function getDemoPaper(paperId: string): Promise<DemoPaperRecord> {
  return withMockFallback(async () => {
    const response = await fetch(
      `${API_BASE_URL}/v1/demo/papers/${encodeURIComponent(paperId)}`,
    );
    if (!response.ok) {
      throw new Error(
        await readApiError(response, `Could not load paper (${response.status})`),
      );
    }
    return (await response.json()) as DemoPaperRecord;
  }, () => mockGetPaper(paperId));
}

export async function editDemoQuestion(
  paperId: string,
  questionId: string,
  edit: {
    question_text: string;
    answer: string;
    criteria: Array<{ criterion: string; marks: number }>;
  },
): Promise<DemoPaperRecord> {
  return withMockFallback(
    () => editDemoQuestionFromApi(paperId, questionId, edit),
    () => mockEditQuestion(paperId, questionId, edit),
  );
}

async function editDemoQuestionFromApi(
  paperId: string,
  questionId: string,
  edit: {
    question_text: string;
    answer: string;
    criteria: Array<{ criterion: string; marks: number }>;
  },
): Promise<DemoPaperRecord> {
  const response = await fetch(
    `${API_BASE_URL}/v1/demo/papers/${encodeURIComponent(paperId)}/questions/${encodeURIComponent(questionId)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(edit),
    },
  );
  if (!response.ok) {
    throw new Error(
      await readApiError(response, `Could not save question (${response.status})`),
    );
  }
  return (await response.json()) as DemoPaperRecord;
}

export async function regenerateDemoQuestion(
  paperId: string,
  questionId: string,
  mode: "guided" | "fresh",
  comment = "",
): Promise<DemoPaperRecord> {
  return withMockFallback(
    () => regenerateDemoQuestionFromApi(paperId, questionId, mode, comment),
    () => mockRegenerateQuestion(paperId, questionId),
  );
}

async function regenerateDemoQuestionFromApi(
  paperId: string,
  questionId: string,
  mode: "guided" | "fresh",
  comment: string,
): Promise<DemoPaperRecord> {
  const response = await fetch(
    `${API_BASE_URL}/v1/demo/papers/${encodeURIComponent(paperId)}/questions/${encodeURIComponent(questionId)}/regenerate`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode, comment }),
    },
  );
  if (!response.ok) {
    throw new Error(
      await readApiError(
        response,
        `Could not regenerate question (${response.status})`,
      ),
    );
  }
  return (await response.json()) as DemoPaperRecord;
}

export async function updateDemoHeader(
  paperId: string,
  header: ExamHeader,
): Promise<DemoPaperRecord> {
  return withMockFallback(
    () => updateDemoHeaderFromApi(paperId, header),
    () => mockUpdateHeader(paperId, header),
  );
}

async function updateDemoHeaderFromApi(
  paperId: string,
  header: ExamHeader,
): Promise<DemoPaperRecord> {
  const response = await fetch(
    `${API_BASE_URL}/v1/demo/papers/${encodeURIComponent(paperId)}/header`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ header }),
    },
  );
  if (!response.ok) {
    throw new Error(
      await readApiError(response, `Could not save exam details (${response.status})`),
    );
  }
  return (await response.json()) as DemoPaperRecord;
}

export async function transitionDemoPaper(
  paperId: string,
  actorRole: DemoRole,
  action: "finalize" | "submit" | "approve" | "return" | "accept" | "decline",
  comment: string,
  selectedSetLabel?: string,
): Promise<DemoPaperRecord> {
  return withMockFallback(
    () => transitionDemoPaperFromApi(paperId, actorRole, action, comment, selectedSetLabel),
    () => mockTransitionPaper(paperId, actorRole, action, comment, selectedSetLabel),
  );
}

async function transitionDemoPaperFromApi(
  paperId: string,
  actorRole: DemoRole,
  action: "finalize" | "submit" | "approve" | "return" | "accept" | "decline",
  comment: string,
  selectedSetLabel?: string,
): Promise<DemoPaperRecord> {
  const response = await fetch(
    `${API_BASE_URL}/v1/demo/papers/${encodeURIComponent(paperId)}/transition`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        actor_role: actorRole,
        action,
        comment,
        selected_set_label: selectedSetLabel,
      }),
    },
  );
  if (!response.ok) {
    throw new Error(
      await readApiError(response, `Could not update review status (${response.status})`),
    );
  }
  return (await response.json()) as DemoPaperRecord;
}

export async function runWorkflow(
  file: File,
  pageRange: PageRange,
  patternId?: string,
  courseOutcomes?: string[],
  setCount = 1,
): Promise<FullWorkflowResponse> {
  const body = new FormData();
  body.append("file", file);
  if (pageRange.startPage !== undefined) {
    body.append("start_page", String(pageRange.startPage));
  }
  if (pageRange.endPage !== undefined) {
    body.append("end_page", String(pageRange.endPage));
  }
  if (patternId) {
    body.append("pattern_id", patternId);
  }
  if (courseOutcomes?.length) {
    body.append("course_outcomes", courseOutcomes.join("\n"));
  }
  body.append("set_count", String(setCount));

  const response = await fetch(`${API_BASE_URL}/v1/workflows/generate`, {
    method: "POST",
    body,
  });

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;
    try {
      const payload = (await response.json()) as ApiErrorBody;
      if (payload.detail) message = payload.detail;
    } catch {
      // Preserve the status-based message when the server does not return JSON.
    }
    throw new Error(message);
  }

  return (await response.json()) as FullWorkflowResponse;
}
