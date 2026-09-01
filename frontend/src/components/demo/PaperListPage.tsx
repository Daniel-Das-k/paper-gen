import { useMemo, useState } from "react";

import type {
  DemoPaperStatus,
  DemoPaperSummary,
  DemoRole,
  DemoUser,
} from "../../types/api";

const STATUS_LABELS: Record<DemoPaperStatus, string> = {
  draft: "Faculty draft",
  faculty_finalized: "Ready to send to HOD",
  submitted_to_hod: "Waiting for HOD",
  submitted_to_coe: "Waiting for CoE",
  approved: "Approved",
};

const STATUS_TONES: Record<DemoPaperStatus, string> = {
  draft: "neutral",
  faculty_finalized: "blue",
  submitted_to_hod: "amber",
  submitted_to_coe: "amber",
  approved: "green",
};

const ROLE_QUEUE: Record<DemoRole, DemoPaperStatus[]> = {
  faculty: ["draft"],
  hod: ["submitted_to_hod"],
  coe: ["submitted_to_coe"],
};

const PAGE_COPY: Record<
  DemoRole,
  Record<"queue" | "history", { title: string; description: string }>
> = {
  faculty: {
    queue: {
      title: "Drafts",
      description:
        "Working papers that can still be edited or regenerated before submission.",
    },
    history: {
      title: "Generated question papers",
      description:
        "Locked papers in the official format. Send them to the HOD from inside the paper view.",
    },
  },
  hod: {
    queue: {
      title: "Department approval queue",
      description:
        "Faculty submissions awaiting review. Open one to compare and forward a set.",
    },
    history: {
      title: "Department paper history",
      description:
        "Every paper generated across the department and who is responsible for it.",
    },
  },
  coe: {
    queue: {
      title: "Final examination review",
      description:
        "HOD-selected papers awaiting a final accept or decline decision.",
    },
    history: {
      title: "CoE decision history",
      description:
        "Accepted papers and papers returned for revision.",
    },
  },
};

function courseInitials(paper: DemoPaperSummary): string {
  const code = paper.course_code.trim();
  if (code) return code.replace(/[^A-Za-z]/g, "").slice(0, 2).toUpperCase() || "QP";
  const words = (paper.course_name || paper.subject).trim().split(/\s+/);
  return words
    .slice(0, 2)
    .map((word) => word[0] ?? "")
    .join("")
    .toUpperCase() || "QP";
}

interface PaperListPageProps {
  mode: "queue" | "history";
  user: DemoUser;
  papers: DemoPaperSummary[];
  loading: boolean;
  error: string | null;
  onOpen: (paperId: string) => void;
  onRefresh: () => void;
}

export function PaperListPage({
  mode,
  user,
  papers,
  loading,
  error,
  onOpen,
  onRefresh,
}: PaperListPageProps) {
  const [query, setQuery] = useState("");
  const [subject, setSubject] = useState("all");
  const [year, setYear] = useState("all");
  const [department, setDepartment] = useState("all");
  const [examination, setExamination] = useState("all");
  const [status, setStatus] = useState("all");
  const copy = PAGE_COPY[user.role][mode];

  const accessiblePapers =
    user.role === "faculty"
      ? papers.filter(
          (paper) =>
            !paper.generated_by || paper.generated_by === user.displayName,
        )
      : user.role === "hod"
        ? papers.filter(
            (paper) => !["draft", "faculty_finalized"].includes(paper.status),
          )
        : papers.filter(
            (paper) =>
              ["submitted_to_coe", "approved"].includes(paper.status) ||
              Boolean(paper.last_coe_action),
          );

  const subjects = useMemo(
    () =>
      [
        ...new Set(
          accessiblePapers
            .map((paper) => paper.course_name || paper.subject)
            .filter(Boolean),
        ),
      ].sort(),
    [accessiblePapers],
  );
  const departments = useMemo(
    () =>
      [
        ...new Set(accessiblePapers.map((paper) => paper.department).filter(Boolean)),
      ].sort(),
    [accessiblePapers],
  );
  const examinations = useMemo(
    () =>
      [
        ...new Set(accessiblePapers.map((paper) => paper.exam_label).filter(Boolean)),
      ].sort(),
    [accessiblePapers],
  );
  const years = [
    ...new Set(accessiblePapers.map((paper) => paper.year).filter(Boolean)),
  ].sort();

  let rolePapers = accessiblePapers;
  if (user.role === "faculty" && mode === "history") {
    rolePapers = accessiblePapers.filter((paper) => paper.status !== "draft");
  } else if (user.role === "coe" && mode === "history") {
    rolePapers = accessiblePapers.filter(
      (paper) =>
        paper.status === "approved" || paper.last_coe_action === "decline",
    );
  }
  if (mode === "queue") {
    rolePapers = rolePapers.filter((paper) =>
      ROLE_QUEUE[user.role].includes(paper.status),
    );
  }

  const search = query.trim().toLowerCase();
  const visible = rolePapers.filter(
    (paper) =>
      (search === "" ||
        [
          paper.course_code,
          paper.course_name,
          paper.subject,
          paper.exam_label,
          paper.generated_by,
        ]
          .join(" ")
          .toLowerCase()
          .includes(search)) &&
      (subject === "all" || (paper.course_name || paper.subject) === subject) &&
      (year === "all" || paper.year === year) &&
      (department === "all" || paper.department === department) &&
      (examination === "all" || paper.exam_label === examination) &&
      (status === "all" ||
        (user.role === "faculty" && mode === "history"
          ? status === "review"
            ? ["submitted_to_hod", "submitted_to_coe"].includes(paper.status)
            : paper.status === status
          : user.role === "coe" && mode === "history"
            ? status === "declined"
              ? paper.last_coe_action === "decline" && paper.status !== "approved"
              : paper.status === status
            : true)),
  );

  const actionLabel =
    user.role === "faculty"
      ? mode === "queue"
        ? "Edit draft"
        : "View paper"
      : user.role === "coe" && mode === "history"
        ? "View decision"
        : "Review";

  const filtersActive =
    search !== "" ||
    subject !== "all" ||
    year !== "all" ||
    department !== "all" ||
    examination !== "all" ||
    status !== "all";

  const statusFor = (paper: DemoPaperSummary): { label: string; tone: string } => {
    const declined =
      user.role === "coe" &&
      paper.last_coe_action === "decline" &&
      paper.status !== "submitted_to_coe" &&
      paper.status !== "approved";
    if (declined) return { label: "Returned for revision", tone: "red" };
    return { label: STATUS_LABELS[paper.status], tone: STATUS_TONES[paper.status] };
  };

  return (
    <main className="demo-page page-container">
      <div className="demo-page-heading">
        <div>
          <h1>{copy.title}</h1>
          <p>{copy.description}</p>
        </div>
        <button className="secondary-button" onClick={onRefresh} type="button">
          Refresh
        </button>
      </div>

      <div className="paper-toolbar">
        <label className="paper-search">
          <span className="visually-hidden">Search papers</span>
          <input
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search course code, subject, or examination"
            type="search"
            value={query}
          />
        </label>
        {subjects.length > 1 && (
          <label className="paper-filter">
            <span>Subject</span>
            <select onChange={(event) => setSubject(event.target.value)} value={subject}>
              <option value="all">All subjects</option>
              {subjects.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
        )}
        {user.role === "faculty" && mode === "history" && (
          <label className="paper-filter">
            <span>Status</span>
            <select onChange={(event) => setStatus(event.target.value)} value={status}>
              <option value="all">All generated papers</option>
              <option value="faculty_finalized">Ready to send</option>
              <option value="review">Under review</option>
              <option value="approved">Approved</option>
            </select>
          </label>
        )}
        {user.role === "coe" && departments.length > 1 && (
          <label className="paper-filter">
            <span>Department</span>
            <select
              onChange={(event) => setDepartment(event.target.value)}
              value={department}
            >
              <option value="all">All departments</option>
              {departments.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
        )}
        {user.role === "coe" && years.length > 1 && (
          <label className="paper-filter">
            <span>Academic year</span>
            <select onChange={(event) => setYear(event.target.value)} value={year}>
              <option value="all">All years</option>
              {years.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
        )}
        {user.role === "coe" && examinations.length > 1 && (
          <label className="paper-filter">
            <span>Examination</span>
            <select
              onChange={(event) => setExamination(event.target.value)}
              value={examination}
            >
              <option value="all">All examinations</option>
              {examinations.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
        )}
        {user.role === "coe" && mode === "history" && (
          <label className="paper-filter">
            <span>Decision</span>
            <select onChange={(event) => setStatus(event.target.value)} value={status}>
              <option value="all">All decisions</option>
              <option value="approved">Approved</option>
              <option value="declined">Returned for revision</option>
            </select>
          </label>
        )}
        <span aria-live="polite" className="paper-count">
          {visible.length} paper{visible.length === 1 ? "" : "s"}
        </span>
      </div>

      {error && (
        <div className="request-error" role="alert">
          {error}
        </div>
      )}

      {loading ? (
        <div aria-live="polite" className="paper-empty">
          <p>Loading papers{"\u2026"}</p>
        </div>
      ) : visible.length === 0 ? (
        <div className="paper-empty">
          <span aria-hidden="true" className="paper-empty-icon">
            <svg fill="none" height="20" viewBox="0 0 20 20" width="20">
              <path
                d="M5 2.5h7l3.5 3.5v11.5H5z"
                stroke="currentColor"
                strokeLinejoin="round"
                strokeWidth="1.4"
              />
              <path
                d="M12 2.5V6h3.5M7.5 10h5M7.5 13h5"
                stroke="currentColor"
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="1.4"
              />
            </svg>
          </span>
          <strong>
            {filtersActive ? "No papers match these filters" : "Nothing here yet"}
          </strong>
          <p>
            {filtersActive
              ? "Try clearing the search or widening the filters."
              : mode === "queue"
                ? "New papers appear here as soon as they reach this stage."
                : "Generated papers appear here once a draft is locked in."}
          </p>
        </div>
      ) : (
        <div className="table-scroll demo-paper-table">
          <table>
            <thead>
              <tr>
                <th>Course</th>
                {user.role === "hod" && <th>Generated by</th>}
                {user.role === "coe" && <th>Department</th>}
                {user.role === "coe" && <th>Year / semester</th>}
                <th>Examination</th>
                <th>Status</th>
                <th>Updated</th>
                <th aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {visible.map((paper) => {
                const paperStatus = statusFor(paper);
                return (
                  <tr key={paper.id}>
                    <td>
                      <span className="paper-course-cell">
                        <span aria-hidden="true" className="dashboard-paper-avatar">
                          {courseInitials(paper)}
                        </span>
                        <span className="paper-course-copy">
                          <strong>{paper.course_name || paper.subject}</strong>
                          <span className="demo-table-secondary">
                            {paper.course_code || "Course code not set"}
                          </span>
                        </span>
                      </span>
                    </td>
                    {user.role === "hod" && (
                      <td>{paper.generated_by || "Faculty not recorded"}</td>
                    )}
                    {user.role === "coe" && (
                      <td>{paper.department || "Department not recorded"}</td>
                    )}
                    {user.role === "coe" && (
                      <td>
                        {paper.year || "Not specified"}
                        <span className="demo-table-secondary">
                          Semester {paper.semester || "\u2014"}
                        </span>
                      </td>
                    )}
                    <td>{paper.exam_label}</td>
                    <td>
                      <span className={`dashboard-status status-${paperStatus.tone}`}>
                        {paperStatus.label}
                      </span>
                    </td>
                    <td className="paper-updated">
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
                        {actionLabel}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
