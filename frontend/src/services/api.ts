import type {
  FullWorkflowResponse,
} from "../types/api";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

interface ApiErrorBody {
  detail?: string;
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

export async function runWorkflow(
  file: File,
  pageRange: PageRange,
): Promise<FullWorkflowResponse> {
  const body = new FormData();
  body.append("file", file);
  if (pageRange.startPage !== undefined) {
    body.append("start_page", String(pageRange.startPage));
  }
  if (pageRange.endPage !== undefined) {
    body.append("end_page", String(pageRange.endPage));
  }

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
