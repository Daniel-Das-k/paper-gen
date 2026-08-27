import { useMemo, useState, type ReactNode } from "react";

import type {
  DemoJob,
  DemoPaperStatus,
  DemoPaperSummary,
  DemoUser,
} from "../../types/api";

const STATUS_LABELS: Record<DemoPaperStatus, string> = {
  draft: "Faculty draft",
  faculty_finalized: "Ready to send",
  submitted_to_hod: "HOD review",
  submitted_to_coe: "CoE review",
  approved: "Approved",
};

interface DemoDashboardProps {
  user: DemoUser;
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

function academicYear(value: string): string {
  const normalized = value.trim().toLowerCase();
  if (/\b(iv|4th|4|fourth)\b/.test(normalized)) return "4";
  if (/\b(iii|3rd|3|third)\b/.test(normalized)) return "3";
  if (/\b(ii|2nd|2|second)\b/.test(normalized)) return "2";
  if (/\b(i|1st|1|first)\b/.test(normalized)) return "1";
  return "unspecified";
}

function matchesQuery(paper: DemoPaperSummary, query: string): boolean {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return true;
  return [
    paper.course_code,
    paper.course_name,
    paper.subject,
    paper.exam_label,
    paper.generated_by,
    paper.year,
  ]
    .join(" ")
    .toLowerCase()
    .includes(normalized);
}

function Summary({
  items,
}: {
  items: Array<{ label: string; value: number; note: string }>;
}) {
  return (
    <section className="dashboard-summary" aria-label="Paper summary">
      {items.map((item) => (
        <div key={item.label}>
          <span>{item.label}</span>
          <strong>{item.value}</strong>
          <small>{item.note}</small>
        </div>
      ))}
    </section>
  );
}

export function DemoDashboard(props: DemoDashboardProps) {
  if (props.user.role === "faculty") return <FacultyDashboard {...props} />;
  if (props.user.role === "hod") return <HodDashboard {...props} />;
  return <CoeDashboard {...props} />;
}

function FacultyDashboard({
  user,
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
  const owned = papers.filter(
    (paper) => !paper.generated_by || paper.generated_by === user.displayName,
  );
  const matching = owned.filter((paper) => matchesQuery(paper, query));
  const activeJob = job?.status === "queued" || job?.status === "running" ? job : null;

  return (
    <DashboardFrame
      action={<button className="primary-button" onClick={onCreate} type="button">Generate paper</button>}
      description="Create and manage your question papers from draft through final approval."
      error={error}
      onRefresh={onRefresh}
      query={query}
      queryPlaceholder="Course code, subject, or examination"
      setQuery={setQuery}
      title="Faculty dashboard"
    >
      <Summary items={[
        { label: "Total papers", value: owned.length, note: "All papers created by you" },
        { label: "Editable drafts", value: owned.filter((paper) => paper.status === "draft").length, note: "Still with faculty" },
        { label: "Under review", value: owned.filter((paper) => ["submitted_to_hod", "submitted_to_coe"].includes(paper.status)).length, note: "With HOD or CoE" },
        { label: "Approved", value: owned.filter((paper) => paper.status === "approved").length, note: "Completed papers" },
      ]} />

      {activeJob && (
        <section className="dashboard-generation" aria-live="polite">
          <div className="dashboard-section-heading">
            <div><h2>{activeJob.stage || "Preparing your question paper"}</h2></div>
            <strong>{activeJob.progress}%</strong>
          </div>
          <div className="progress-track" aria-label={`${activeJob.progress}% complete`}>
            <div className="progress-fill" style={{ width: `${activeJob.progress}%` }} />
          </div>
        </section>
      )}

      <PaperSection
        action={<button className="text-button" onClick={onQueue} type="button">View all drafts</button>}
        description="Working papers that can still be edited or regenerated before submission."
        emptyMessage="You have no active drafts."
        loading={loading}
        onOpen={onOpen}
        papers={matching.filter((paper) => paper.status === "draft").slice(0, 5)}
        title="Drafts"
      />
      <PaperSection
        description="Locked papers in the official format. Send them to the HOD from inside the paper view."
        emptyMessage={query ? "No finished papers match your search." : "Finish a draft to see it here."}
        loading={loading}
        onOpen={onOpen}
        papers={matching.filter((paper) => paper.status !== "draft").slice(0, 8)}
        title="Generated question papers"
      />
    </DashboardFrame>
  );
}

function HodDashboard({
  papers,
  loading,
  error,
  onOpen,
  onQueue,
  onRefresh,
}: DemoDashboardProps) {
  const [query, setQuery] = useState("");
  const departmentPapers = papers.filter(
    (paper) => !["draft", "faculty_finalized"].includes(paper.status),
  );
  const matching = departmentPapers.filter((paper) => matchesQuery(paper, query));
  const waiting = matching.filter((paper) => paper.status === "submitted_to_hod");
  const subjects = useMemo(() => {
    const grouped = new Map<string, DemoPaperSummary[]>();
    matching.forEach((paper) => {
      const key = paper.course_name || paper.subject || "Unspecified subject";
      grouped.set(key, [...(grouped.get(key) ?? []), paper]);
    });
    return [...grouped.entries()].sort(([left], [right]) => left.localeCompare(right));
  }, [matching]);

  return (
    <DashboardFrame
      description="Review papers across the department, compare candidate sets, and forward one set to the CoE."
      error={error}
      onRefresh={onRefresh}
      query={query}
      queryPlaceholder="Subject, course code, or faculty"
      setQuery={setQuery}
      title="HOD department dashboard"
    >
      <Summary items={[
        { label: "Department papers", value: departmentPapers.length, note: "Submitted by faculty" },
        { label: "Awaiting your review", value: departmentPapers.filter((paper) => paper.status === "submitted_to_hod").length, note: "Action required" },
        { label: "Forwarded by you", value: departmentPapers.filter((paper) => paper.hod_approved).length, note: "Sent to CoE" },
        { label: "Approved by CoE", value: departmentPapers.filter((paper) => paper.status === "approved").length, note: "Final approval complete" },
      ]} />

      <PaperSection
        action={<button className="text-button" onClick={onQueue} type="button">Open department queue</button>}
        description="Each row identifies the subject and the faculty member who submitted it."
        emptyMessage="No papers are waiting for HOD review."
        loading={loading}
        onOpen={onOpen}
        papers={waiting}
        showOwner
        title="Papers awaiting HOD approval"
      />
      <PaperSection
        description="Papers for which the HOD selected a candidate set and completed department approval."
        emptyMessage="No papers have been forwarded to the CoE yet."
        loading={loading}
        onOpen={onOpen}
        papers={matching.filter((paper) => paper.hod_approved).slice(0, 6)}
        showOwner
        title="Recently approved by HOD"
      />

      <section className="dashboard-section">
        <div className="dashboard-section-heading">
          <div><h2>Subject-wise department overview</h2><p>Submission and approval position for every course handled by the department.</p></div>
        </div>
        <div className="table-scroll role-summary-table">
          <table>
            <thead><tr><th>Subject</th><th>Faculty</th><th>Total</th><th>With HOD</th><th>Forwarded</th><th>Approved</th></tr></thead>
            <tbody>
              {subjects.map(([subject, entries]) => (
                <tr key={subject}>
                  <td><strong>{subject}</strong><span className="demo-table-secondary">{entries[0]?.course_code || "Code not set"}</span></td>
                  <td>{new Set(entries.map((paper) => paper.generated_by).filter(Boolean)).size || "—"}</td>
                  <td>{entries.length}</td>
                  <td>{entries.filter((paper) => paper.status === "submitted_to_hod").length}</td>
                  <td>{entries.filter((paper) => paper.hod_approved).length}</td>
                  <td>{entries.filter((paper) => paper.status === "approved").length}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </DashboardFrame>
  );
}

function CoeDashboard({
  papers,
  loading,
  error,
  onOpen,
  onQueue,
  onRefresh,
}: DemoDashboardProps) {
  const [query, setQuery] = useState("");
  const [year, setYear] = useState("all");
  const coePapers = papers.filter(
    (paper) =>
      ["submitted_to_coe", "approved"].includes(paper.status) ||
      Boolean(paper.last_coe_action),
  );
  const scoped = coePapers.filter(
    (paper) =>
      matchesQuery(paper, query) &&
      (year === "all" || academicYear(paper.year) === year),
  );
  const pending = scoped.filter((paper) => paper.status === "submitted_to_coe");
  const approved = scoped.filter((paper) => paper.status === "approved");
  const yearSubjectRows = useMemo(() => {
    const grouped = new Map<string, DemoPaperSummary[]>();
    scoped.forEach((paper) => {
      const key = `${academicYear(paper.year)}|${paper.course_name || paper.subject || "Unspecified subject"}`;
      grouped.set(key, [...(grouped.get(key) ?? []), paper]);
    });
    return [...grouped.entries()].sort(([left], [right]) => left.localeCompare(right));
  }, [scoped]);

  return (
    <DashboardFrame
      description="Perform final examination review across all academic years and subjects. This account cannot generate or edit papers."
      error={error}
      onRefresh={onRefresh}
      query={query}
      queryPlaceholder="Subject, course code, department, or year"
      setQuery={setQuery}
      title="CoE final review dashboard"
      toolbarExtra={
        <label className="dashboard-filter"><span>Academic year</span><select onChange={(event) => setYear(event.target.value)} value={year}><option value="all">All years</option><option value="1">1st year</option><option value="2">2nd year</option><option value="3">3rd year</option><option value="4">4th year</option><option value="unspecified">Year not specified</option></select></label>
      }
    >
      <Summary items={[
        { label: "Awaiting final decision", value: coePapers.filter((paper) => paper.status === "submitted_to_coe").length, note: "Accept or decline" },
        { label: "Accepted papers", value: coePapers.filter((paper) => paper.status === "approved").length, note: "Finalised by CoE" },
        { label: "Declined papers", value: coePapers.filter((paper) => paper.last_coe_action === "decline").length, note: "Returned for revision" },
        { label: "Subjects represented", value: new Set(coePapers.map((paper) => paper.course_code || paper.course_name)).size, note: "Across all years" },
      ]} />

      <PaperSection
        action={<button className="text-button" onClick={onQueue} type="button">Open final review queue</button>}
        description="Only HOD-selected papers appear here. Open a paper to accept or decline it."
        emptyMessage="No papers are awaiting a final CoE decision for this filter."
        loading={loading}
        onOpen={onOpen}
        papers={pending}
        showDepartment
        showYear
        title="Final decisions required"
      />
      <section className="dashboard-section">
        <div className="dashboard-section-heading">
          <div><h2>Year and subject overview</h2><p>Final-review workload separated by academic year and course.</p></div>
        </div>
        <div className="table-scroll role-summary-table">
          <table>
            <thead><tr><th>Year</th><th>Subject</th><th>Pending</th><th>Accepted</th><th>Declined</th></tr></thead>
            <tbody>
              {yearSubjectRows.map(([key, entries]) => {
                const [yearKey, subjectName] = key.split("|");
                const yearLabel = yearKey === "unspecified" ? "Not specified" : `${yearKey}${yearKey === "1" ? "st" : yearKey === "2" ? "nd" : yearKey === "3" ? "rd" : "th"} year`;
                return (
                  <tr key={key}>
                    <td>{yearLabel}</td>
                    <td><strong>{subjectName}</strong><span className="demo-table-secondary">{entries[0]?.course_code || "Code not set"}</span></td>
                    <td>{entries.filter((paper) => paper.status === "submitted_to_coe").length}</td>
                    <td>{entries.filter((paper) => paper.status === "approved").length}</td>
                    <td>{entries.filter((paper) => paper.last_coe_action === "decline").length}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
      <PaperSection
        description="Recently accepted examination papers for the selected year and subject filter."
        emptyMessage="No accepted papers match this filter."
        loading={loading}
        onOpen={onOpen}
        papers={approved.slice(0, 8)}
        showDepartment
        showYear
        title="Accepted paper history"
      />
    </DashboardFrame>
  );
}

interface DashboardFrameProps {
  title: string;
  description: string;
  query: string;
  queryPlaceholder: string;
  setQuery: (value: string) => void;
  onRefresh: () => void;
  error: string | null;
  action?: ReactNode;
  toolbarExtra?: ReactNode;
  children: ReactNode;
}

function DashboardFrame({ title, description, query, queryPlaceholder, setQuery, onRefresh, error, action, toolbarExtra, children }: DashboardFrameProps) {
  return (
    <main className="demo-page demo-dashboard page-container">
      <section className="dashboard-intro" aria-labelledby="dashboard-title"><div><h1 id="dashboard-title">{title}</h1><p>{description}</p></div>{action}</section>
      <div className="dashboard-toolbar">
        <label className="dashboard-search"><span>Search papers</span><input onChange={(event) => setQuery(event.target.value)} placeholder={queryPlaceholder} type="search" value={query} /></label>
        <div className="dashboard-toolbar-filters">{toolbarExtra}<button className="secondary-button" onClick={onRefresh} type="button">Refresh</button></div>
      </div>
      {error && <div className="request-error" role="alert"><strong>Dashboard data is unavailable</strong><p>{error}</p></div>}
      {children}
    </main>
  );
}

interface PaperSectionProps {
  title: string;
  description: string;
  papers: DemoPaperSummary[];
  loading: boolean;
  emptyMessage: string;
  onOpen: (paperId: string) => void;
  action?: ReactNode;
  showOwner?: boolean;
  showDepartment?: boolean;
  showYear?: boolean;
}

function PaperSection({ title, description, papers, loading, emptyMessage, onOpen, action, showOwner, showDepartment, showYear }: PaperSectionProps) {
  return (
    <section className="dashboard-section">
      <div className="dashboard-section-heading"><div><h2>{title}</h2><p>{description}</p></div>{action}</div>
      <PaperRows emptyMessage={emptyMessage} loading={loading} onOpen={onOpen} papers={papers} showDepartment={showDepartment} showOwner={showOwner} showYear={showYear} />
    </section>
  );
}

function PaperRows({ papers, loading, emptyMessage, onOpen, showOwner, showDepartment, showYear }: Omit<PaperSectionProps, "title" | "description" | "action">) {
  if (loading) return <p className="dashboard-empty">Loading local papers…</p>;
  if (papers.length === 0) return <p className="dashboard-empty">{emptyMessage}</p>;
  return (
    <div className="dashboard-paper-list">
      {papers.map((paper) => (
        <button key={paper.id} onClick={() => onOpen(paper.id)} type="button">
          <span className="dashboard-paper-course"><strong>{paper.course_name || paper.subject}</strong><small>{paper.course_code || "Course code not set"} · {paper.exam_label}{showOwner ? ` · ${paper.generated_by || "Faculty not recorded"}` : ""}{showDepartment ? ` · ${paper.department || "Department not recorded"}` : ""}{showYear ? ` · ${paper.year || "Year not specified"}` : ""}</small></span>
          <span className={`dashboard-status dashboard-status-${paper.status}`}>{STATUS_LABELS[paper.status]}</span>
          <time dateTime={paper.updated_at}>{formatDate(paper.updated_at)}</time>
          <span className="dashboard-open">Open <span aria-hidden="true">→</span></span>
        </button>
      ))}
    </div>
  );
}
