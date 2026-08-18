import { useEffect, useMemo, useRef, useState } from "react";

import { AppHeader } from "../components/layout/AppHeader";
import { ChevronIcon, FileIcon, SparkIcon } from "../components/icons/Icons";
import { WorkflowResultPanel } from "../components/results/WorkflowResultPanel";
import { UploadPanel } from "../components/upload/UploadPanel";
import { runWorkflow } from "../services/api";
import type { FullWorkflowResponse } from "../types/api";

interface RecentPaper {
  id: string;
  filename: string;
  subject: string;
  pageRange: string;
  createdAt: string;
}

const HISTORY_KEY = "paperly-recent-papers";

function greeting() {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

function readHistory(): RecentPaper[] {
  try {
    return JSON.parse(localStorage.getItem(HISTORY_KEY) ?? "[]") as RecentPaper[];
  } catch {
    return [];
  }
}

export function DashboardPage() {
  const [file, setFile] = useState<File | null>(null);
  const [startPage, setStartPage] = useState("");
  const [endPage, setEndPage] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<FullWorkflowResponse | null>(null);
  const [history, setHistory] = useState<RecentPaper[]>(readHistory);
  const uploadRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
  }, [history]);

  const actionLabel = useMemo(
    () => (result ? "Create another paper" : "Start with your notes"),
    [result],
  );

  const reset = () => {
    setFile(null);
    setError(null);
    setResult(null);
    setStartPage("");
    setEndPage("");
    requestAnimationFrame(() =>
      uploadRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }),
    );
  };

  const executeWorkflow = async () => {
    if (!file) return;
    const numericStart = startPage.trim() ? Number(startPage) : undefined;
    const numericEnd = endPage.trim() ? Number(endPage) : undefined;
    if (
      (numericStart !== undefined &&
        (!Number.isInteger(numericStart) || numericStart < 1)) ||
      (numericEnd !== undefined &&
        (!Number.isInteger(numericEnd) || numericEnd < 1)) ||
      (numericStart !== undefined &&
        numericEnd !== undefined &&
        numericEnd < numericStart)
    ) {
      setError("Enter a valid page range, or leave both page fields empty.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const workflowResult = await runWorkflow(file, {
        startPage: numericStart,
        endPage: numericEnd,
      });
      setResult(workflowResult);
      setHistory((current) =>
        [
          {
            id: workflowResult.manifest.document_id,
            filename: file.name,
            subject: workflowResult.content_map.subject,
            pageRange: `${workflowResult.manifest.selected_page_start}–${workflowResult.manifest.selected_page_end}`,
            createdAt: new Date().toISOString(),
          },
          ...current.filter(
            (item) => item.id !== workflowResult.manifest.document_id,
          ),
        ].slice(0, 6),
      );
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "The workflow could not be completed.",
      );
    } finally {
      setLoading(false);
    }
  };

  const submit = () => executeWorkflow();

  return (
    <div className="app-shell">
      <AppHeader onNewPaper={reset} />

      <main>
        <section className="welcome-band">
          <div className="page-container welcome-content">
            <div>
              <h1>{greeting()}</h1>
              <p>Turn course notes into a balanced, faculty-reviewable paper.</p>
            </div>
            <button
              className="welcome-action"
              onClick={() =>
                uploadRef.current?.scrollIntoView({
                  behavior: "smooth",
                  block: "start",
                })
              }
              type="button"
            >
              <SparkIcon />
              {actionLabel}
            </button>
          </div>
        </section>

        <div className="page-container main-content" ref={uploadRef}>
          <section className="action-strip" aria-labelledby="actions-title">
            <h2 id="actions-title">Before you generate</h2>
            <div className="action-list">
              <div className="action-item">
                <span className="action-icon">
                  <FileIcon />
                </span>
                <div>
                  <strong>Use complete source notes</strong>
                  <span>Include figures, formulas and unit headings.</span>
                </div>
                <ChevronIcon />
              </div>
              <div className="action-item">
                <span className="action-icon">
                  <SparkIcon />
                </span>
                <div>
                  <strong>Select only the required pages</strong>
                  <span>Exclude covers, contents pages and unrelated chapters.</span>
                </div>
                <ChevronIcon />
              </div>
            </div>
          </section>

          {error && (
            <div className="request-error" role="alert">
              <strong>Could not process this document</strong>
              <p>{error}</p>
            </div>
          )}

          {result ? (
            <WorkflowResultPanel
              onReset={reset}
              result={result}
            />
          ) : (
            <UploadPanel
              file={file}
              loading={loading}
              startPage={startPage}
              endPage={endPage}
              onFileChange={setFile}
              onStartPageChange={setStartPage}
              onEndPageChange={setEndPage}
              onSubmit={submit}
            />
          )}

          <section
            aria-labelledby="recent-title"
            className="workspace-panel recent-panel"
            id="recent-papers"
          >
            <div className="panel-heading">
              <div>
                <h2 id="recent-title">Recent papers</h2>
                <p>Question papers generated in this browser appear here.</p>
              </div>
            </div>

            {history.length ? (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Document</th>
                      <th>Subject</th>
                      <th>Pages</th>
                      <th>Created</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.map((paper) => (
                      <tr key={paper.id}>
                        <td>{paper.filename}</td>
                        <td>{paper.subject}</td>
                        <td>{paper.pageRange ?? "—"}</td>
                        <td>
                          {new Intl.DateTimeFormat(undefined, {
                            dateStyle: "medium",
                            timeStyle: "short",
                          }).format(new Date(paper.createdAt))}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="empty-state">
                <FileIcon />
                <div>
                  <strong>No papers yet</strong>
                  <p>Your first generated paper will appear here.</p>
                </div>
              </div>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}
