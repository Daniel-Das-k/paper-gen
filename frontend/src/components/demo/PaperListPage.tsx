import type {
  DemoPaperStatus,
  DemoPaperSummary,
  DemoRole,
} from "../../types/api";

const STATUS_LABELS: Record<DemoPaperStatus, string> = {
  draft: "Faculty draft",
  submitted_to_hod: "Waiting for HOD",
  submitted_to_coe: "Waiting for CoE",
  approved: "Approved",
};

const ROLE_QUEUE: Record<DemoRole, DemoPaperStatus[]> = {
  faculty: ["draft"],
  hod: ["submitted_to_hod"],
  coe: ["submitted_to_coe"],
};

interface PaperListPageProps {
  mode: "queue" | "history";
  role: DemoRole;
  papers: DemoPaperSummary[];
  loading: boolean;
  error: string | null;
  onOpen: (paperId: string) => void;
  onRefresh: () => void;
}

export function PaperListPage({
  mode,
  role,
  papers,
  loading,
  error,
  onOpen,
  onRefresh,
}: PaperListPageProps) {
  const visible =
    mode === "queue"
      ? papers.filter((paper) => ROLE_QUEUE[role].includes(paper.status))
      : papers;

  return (
    <main className="demo-page page-container">
      <div className="demo-page-heading">
        <div>
          <h1>{mode === "queue" ? "Review queue" : "Paper history"}</h1>
          <p>
            {mode === "queue"
              ? `Papers requiring action from the selected ${role.toUpperCase()} demo role.`
              : "Generated papers and their current local approval status."}
          </p>
        </div>
        <button className="secondary-button" onClick={onRefresh} type="button">
          Refresh
        </button>
      </div>

      {error && <div className="request-error">{error}</div>}
      {loading ? (
        <p className="demo-list-empty">Loading local papers…</p>
      ) : visible.length === 0 ? (
        <p className="demo-list-empty">
          {mode === "queue"
            ? "There are no papers waiting for this role."
            : "No papers have been generated in this local demo yet."}
        </p>
      ) : (
        <div className="table-scroll demo-paper-table">
          <table>
            <thead>
              <tr>
                <th>Course</th>
                <th>Examination</th>
                <th>Status</th>
                <th>Updated</th>
                <th aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {visible.map((paper) => (
                <tr key={paper.id}>
                  <td>
                    <strong>{paper.course_name || paper.subject}</strong>
                    <span className="demo-table-secondary">
                      {paper.course_code || "Course code not set"}
                    </span>
                  </td>
                  <td>{paper.exam_label}</td>
                  <td>{STATUS_LABELS[paper.status]}</td>
                  <td>
                    {new Intl.DateTimeFormat(undefined, {
                      dateStyle: "medium",
                      timeStyle: "short",
                    }).format(new Date(paper.updated_at))}
                  </td>
                  <td>
                    <button
                      className="table-action"
                      onClick={() => onOpen(paper.id)}
                      type="button"
                    >
                      Open
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
