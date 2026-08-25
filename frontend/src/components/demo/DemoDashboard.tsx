import { useMemo, useState } from "react";

import type {
  DemoJob,
  DemoPaperStatus,
  DemoPaperSummary,
  DemoRole,
} from "../../types/api";

const ROLE_COPY: Record<DemoRole, { body: string }> = {
  faculty: {
    body: "Create, review and submit examination papers from verified course material.",
  },
  hod: {
    body: "Review academic quality and forward approved papers to the Controller of Examinations.",
  },
  coe: {
    body: "Complete the final examination review and keep approved papers ready for use.",
  },
};

const ROLE_QUEUE: Record<DemoRole, DemoPaperStatus> = {
  faculty: "draft",
  hod: "submitted_to_hod",
  coe: "submitted_to_coe",
};

const STATUS_LABELS: Record<DemoPaperStatus, string> = {
  draft: "Faculty draft",
  submitted_to_hod: "HOD review",
  submitted_to_coe: "CoE review",
  approved: "Approved",
};

interface DemoDashboardProps {
  role: DemoRole;
  papers: DemoPaperSummary[];
  loading: boolean;
  error: string | null;
  job: DemoJob | null;
  onCreate: () => void;
  onOpen: (paperId: string) => void;
  onQueue: () => void;
  onRefresh: () => void;
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function DemoDashboard({
  role,
  papers,
  loading,
  error,
  job,
  onCreate,
  onOpen,
  onQueue,
  onRefresh,
}: DemoDashboardProps) {
  const [query, setQuery] = useState("");
  const copy = ROLE_COPY[role];
  const activeJob = job?.status === "queued" || job?.status === "running" ? job : null;
  const counts = {
    draft: papers.filter((paper) => paper.status === "draft").length,
    review: papers.filter((paper) =>
      ["submitted_to_hod", "submitted_to_coe"].includes(paper.status),
    ).length,
    approved: papers.filter((paper) => paper.status === "approved").length,
  };

  const matching = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return papers;
    return papers.filter((paper) =>
      [paper.course_code, paper.course_name, paper.subject, paper.exam_label]
        .join(" ")
        .toLowerCase()
        .includes(normalized),
    );
  }, [papers, query]);

  const attention = matching
    .filter((paper) => paper.status === ROLE_QUEUE[role])
    .slice(0, 5);
  const recent = matching.slice(0, 5);

  return (
    <main className="demo-page demo-dashboard page-container">
      <section className="dashboard-intro" aria-labelledby="dashboard-title">
        <div>
          <h1 id="dashboard-title">Dashboard</h1>
          <p>{copy.body}</p>
        </div>
        <button className="primary-button" onClick={onCreate} type="button">
          Generate paper
        </button>
      </section>

      <section className="dashboard-summary" aria-label="Paper summary">
        <div>
          <span>Total papers</span>
          <strong>{papers.length}</strong>
          <small>In this local workspace</small>
        </div>
        <div>
          <span>Drafts</span>
          <strong>{counts.draft}</strong>
          <small>Being prepared</small>
        </div>
        <div>
          <span>In review</span>
          <strong>{counts.review}</strong>
          <small>With HOD or CoE</small>
        </div>
        <div>
          <span>Approved</span>
          <strong>{counts.approved}</strong>
          <small>Ready for use</small>
        </div>
      </section>

      {activeJob && (
        <section className="dashboard-generation" aria-live="polite">
          <div className="dashboard-section-heading">
            <div>
              <span className="dashboard-section-kicker">Active generation</span>
              <h2>{activeJob.stage || "Preparing your question paper"}</h2>
            </div>
            <strong>{activeJob.progress}%</strong>
          </div>
          <div className="progress-track" aria-label={`${activeJob.progress}% complete`}>
            <div className="progress-fill" style={{ width: `${activeJob.progress}%` }} />
          </div>
          <p>You can continue using the dashboard while the local workflow runs.</p>
        </section>
      )}

      <div className="dashboard-toolbar">
        <label className="dashboard-search">
          <span>Search papers</span>
          <input
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Course code, name, or examination"
            type="search"
            value={query}
          />
        </label>
        <button className="secondary-button" onClick={onRefresh} type="button">
          Refresh
        </button>
      </div>

      {error && (
        <div className="request-error" role="alert">
          <strong>Dashboard data is unavailable</strong>
          <p>{error}</p>
        </div>
      )}

      <section className="dashboard-section">
        <div className="dashboard-section-heading">
          <div>
            <h2>Papers requiring attention</h2>
            <p>Open a paper to review findings, make corrections or move it forward.</p>
          </div>
          <button className="text-button" onClick={onQueue} type="button">
            View review queue
          </button>
        </div>
        <PaperRows
          emptyMessage={
            query
              ? "No waiting papers match your search."
              : "Nothing needs attention for this role right now."
          }
          loading={loading}
          onOpen={onOpen}
          papers={attention}
        />
      </section>

      <section className="dashboard-section">
        <div className="dashboard-section-heading">
          <div>
            <h2>Recent papers</h2>
            <p>The latest activity across the local demonstration.</p>
          </div>
        </div>
        <PaperRows
          emptyMessage={query ? "No papers match your search." : "Create the first paper to see it here."}
          loading={loading}
          onOpen={onOpen}
          papers={recent}
        />
      </section>

      <footer className="dashboard-readiness" aria-label="Demo readiness">
        <strong>Local demo readiness</strong>
        <span className={error ? "dashboard-readiness-error" : ""}>
          <i aria-hidden="true" />
          {loading ? "Checking backend" : error ? "Backend unavailable" : "Backend connected"}
        </span>
        <span className={error ? "dashboard-readiness-error" : ""}>
          <i aria-hidden="true" />
          {loading ? "Checking paper store" : error ? "Paper store unavailable" : "Paper store ready"}
        </span>
        <span className="dashboard-readiness-neutral">
          Bedrock is checked when generation starts
        </span>
      </footer>
    </main>
  );
}

interface PaperRowsProps {
  papers: DemoPaperSummary[];
  loading: boolean;
  emptyMessage: string;
  onOpen: (paperId: string) => void;
}

function PaperRows({ papers, loading, emptyMessage, onOpen }: PaperRowsProps) {
  if (loading) return <p className="dashboard-empty">Loading local papers…</p>;
  if (papers.length === 0) return <p className="dashboard-empty">{emptyMessage}</p>;

  return (
    <div className="dashboard-paper-list">
      {papers.map((paper) => (
        <button key={paper.id} onClick={() => onOpen(paper.id)} type="button">
          <span className="dashboard-paper-course">
            <strong>{paper.course_name || paper.subject}</strong>
            <small>{paper.course_code || "Course code not set"} · {paper.exam_label}</small>
          </span>
          <span className={`dashboard-status dashboard-status-${paper.status}`}>
            {STATUS_LABELS[paper.status]}
          </span>
          <time dateTime={paper.updated_at}>{formatDate(paper.updated_at)}</time>
          <span className="dashboard-open">Open <span aria-hidden="true">→</span></span>
        </button>
      ))}
    </div>
  );
}
