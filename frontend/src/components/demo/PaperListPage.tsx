import { useMemo, useState } from "react";

import type { DemoPaperStatus, DemoPaperSummary, DemoRole, DemoUser } from "../../types/api";

const STATUS_LABELS: Record<DemoPaperStatus, string> = {
  draft: "Faculty draft",
  faculty_finalized: "Ready to send to HOD",
  submitted_to_hod: "Waiting for HOD",
  submitted_to_coe: "Waiting for CoE",
  approved: "Approved",
};

const ROLE_QUEUE: Record<DemoRole, DemoPaperStatus[]> = {
  faculty: ["draft"],
  hod: ["submitted_to_hod"],
  coe: ["submitted_to_coe"],
};

const PAGE_COPY: Record<DemoRole, Record<"queue" | "history", { title: string; description: string }>> = {
  faculty: {
    queue: { title: "Drafts", description: "Working papers with editing and regeneration tools. Select Done when a paper is ready to become a locked generated paper." },
    history: { title: "Generated question papers", description: "Finished, locked papers in the official examination format. Open one to download it or send it to the HOD." },
  },
  hod: {
    queue: { title: "Department approval queue", description: "Faculty submissions from every subject in the department. Open one to compare and select a set." },
    history: { title: "Department paper history", description: "Papers generated across all department courses and the faculty responsible for each." },
  },
  coe: {
    queue: { title: "Final examination review", description: "HOD-selected papers awaiting an accept or decline decision from the CoE." },
    history: { title: "CoE decision history", description: "Accepted papers and papers returned for revision across all years and subjects." },
  },
};

interface PaperListPageProps {
  mode: "queue" | "history";
  user: DemoUser;
  papers: DemoPaperSummary[];
  loading: boolean;
  error: string | null;
  onOpen: (paperId: string) => void;
  onRefresh: () => void;
}

export function PaperListPage({ mode, user, papers, loading, error, onOpen, onRefresh }: PaperListPageProps) {
  const [subject, setSubject] = useState("all");
  const [year, setYear] = useState("all");
  const [department, setDepartment] = useState("all");
  const [examination, setExamination] = useState("all");
  const [status, setStatus] = useState("all");
  const copy = PAGE_COPY[user.role][mode];
  const accessiblePapers = user.role === "faculty"
    ? papers.filter((paper) => !paper.generated_by || paper.generated_by === user.displayName)
    : user.role === "hod"
      ? papers.filter((paper) => !["draft", "faculty_finalized"].includes(paper.status))
      : papers.filter((paper) => ["submitted_to_coe", "approved"].includes(paper.status) || Boolean(paper.last_coe_action));
  const subjects = useMemo(
    () => [...new Set(accessiblePapers.map((paper) => paper.course_name || paper.subject).filter(Boolean))].sort(),
    [accessiblePapers],
  );
  const departments = useMemo(
    () => [...new Set(accessiblePapers.map((paper) => paper.department).filter(Boolean))].sort(),
    [accessiblePapers],
  );
  const examinations = useMemo(
    () => [...new Set(accessiblePapers.map((paper) => paper.exam_label).filter(Boolean))].sort(),
    [accessiblePapers],
  );

  let rolePapers = accessiblePapers;
  if (user.role === "faculty" && mode === "history") {
    rolePapers = accessiblePapers.filter((paper) => paper.status !== "draft");
  } else if (user.role === "coe" && mode === "history") {
    rolePapers = accessiblePapers.filter((paper) => paper.status === "approved" || paper.last_coe_action === "decline");
  }
  if (mode === "queue") {
    rolePapers = rolePapers.filter((paper) => ROLE_QUEUE[user.role].includes(paper.status));
  }
  const visible = rolePapers.filter(
    (paper) =>
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
  const years = [...new Set(accessiblePapers.map((paper) => paper.year).filter(Boolean))].sort();

  return (
    <main className="demo-page page-container">
      <div className="demo-page-heading">
        <div><h1>{copy.title}</h1><p>{copy.description}</p></div>
        <button className="secondary-button" onClick={onRefresh} type="button">Refresh</button>
      </div>

      <div className="paper-list-filters">
        <label><span>Subject</span><select onChange={(event) => setSubject(event.target.value)} value={subject}><option value="all">All subjects</option>{subjects.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
        {user.role === "faculty" && mode === "history" && <label><span>Status</span><select onChange={(event) => setStatus(event.target.value)} value={status}><option value="all">All generated papers</option><option value="faculty_finalized">Ready to send</option><option value="review">Under review</option><option value="approved">Approved</option></select></label>}
        {user.role === "coe" && <label><span>Department</span><select onChange={(event) => setDepartment(event.target.value)} value={department}><option value="all">All departments</option>{departments.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>}
        {user.role === "coe" && <label><span>Academic year</span><select onChange={(event) => setYear(event.target.value)} value={year}><option value="all">All years</option>{years.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>}
        {user.role === "coe" && <label><span>Examination</span><select onChange={(event) => setExamination(event.target.value)} value={examination}><option value="all">All examinations</option>{examinations.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>}
        {user.role === "coe" && mode === "history" && <label><span>Decision</span><select onChange={(event) => setStatus(event.target.value)} value={status}><option value="all">All decisions</option><option value="approved">Approved</option><option value="declined">Returned for revision</option></select></label>}
      </div>

      {error && <div className="request-error">{error}</div>}
      {loading ? (
        <p className="demo-list-empty">Loading local papers…</p>
      ) : visible.length === 0 ? (
        <p className="demo-list-empty">No papers match this role and filter.</p>
      ) : (
        <div className="table-scroll demo-paper-table">
          <table>
            <thead><tr><th>Course</th>{user.role === "hod" && <th>Generated by</th>}{user.role === "coe" && <th>Department</th>}{user.role === "coe" && <th>Year / semester</th>}<th>Examination</th><th>Status</th><th>Updated</th><th aria-label="Actions" /></tr></thead>
            <tbody>
              {visible.map((paper) => (
                <tr key={paper.id}>
                  <td><strong>{paper.course_name || paper.subject}</strong><span className="demo-table-secondary">{paper.course_code || "Course code not set"}</span></td>
                  {user.role === "hod" && <td>{paper.generated_by || "Faculty not recorded"}</td>}
                  {user.role === "coe" && <td>{paper.department || "Department not recorded"}</td>}
                  {user.role === "coe" && <td>{paper.year || "Not specified"}<span className="demo-table-secondary">Semester {paper.semester || "—"}</span></td>}
                  <td>{paper.exam_label}</td>
                  <td>{user.role === "coe" && paper.last_coe_action === "decline" && paper.status !== "submitted_to_coe" && paper.status !== "approved" ? "Declined for revision" : STATUS_LABELS[paper.status]}</td>
                  <td>{new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(paper.updated_at))}</td>
                  <td><button className="table-action" onClick={() => onOpen(paper.id)} type="button">{user.role === "faculty" ? (mode === "queue" ? "Edit draft" : "View paper") : user.role === "coe" && mode === "history" ? "View decision" : "Review"}</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
