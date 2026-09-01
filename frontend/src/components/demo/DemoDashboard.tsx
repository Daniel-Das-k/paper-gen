import {
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { Area, AreaChart, Grid, Tooltip, XAxis, YAxis } from "@/components/dither-kit/area-chart";
import type { ChartConfig } from "@/components/dither-kit/chart-context";
import { Sparkline } from "@/components/dither-kit/sparkline";

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

function academicYearLabel(value: string): string {
  const normalized = academicYear(value);
  if (normalized === "unspecified") return "Year not specified";
  const suffix =
    normalized === "1" ? "st" : normalized === "2" ? "nd" : normalized === "3" ? "rd" : "th";
  return `${normalized}${suffix} year`;
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

const DAY_MS = 24 * 60 * 60 * 1000;
const SPARK_DAYS = 14;
const ACTIVITY_DAYS = 28;

function dailyCounts(papers: DemoPaperSummary[]): number[] {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const origin = today.getTime();
  const counts = Array.from({ length: SPARK_DAYS }, () => 0);
  papers.forEach((paper) => {
    const updated = new Date(paper.updated_at);
    if (Number.isNaN(updated.getTime())) return;
    updated.setHours(0, 0, 0, 0);
    const diff = Math.round((origin - updated.getTime()) / DAY_MS);
    if (diff >= 0 && diff < SPARK_DAYS) counts[SPARK_DAYS - 1 - diff] += 1;
  });
  return counts;
}

const KPI_COLORS = ["purple", "orange", "green", "blue"] as const;

interface KpiItem {
  label: string;
  value: number;
  note: string;
  delta?: string;
  series: number[];
}

function KpiCard({ item, color }: { item: KpiItem; color: (typeof KPI_COLORS)[number] }) {
  const [hovered, setHovered] = useState(false);
  const fingerprint = item.series.join(",");
  const series = useMemo(
    () => fingerprint.split(",").map((value) => Number(value)),
    [fingerprint],
  );
  return (
    <article
      className="kpi-card"
      onPointerEnter={() => setHovered(true)}
      onPointerLeave={() => setHovered(false)}
    >
      <span className="kpi-label">{item.label}</span>
      <div className="kpi-line">
        <strong>{item.value}</strong>
        {item.delta ? <em className="kpi-delta">{item.delta}</em> : null}
      </div>
      <small>{item.note}</small>
      <div aria-hidden="true" className="kpi-spark">
        <Sparkline
          bloom="low"
          bloomOnHover
          color={color}
          data={series}
          hovered={hovered}
          variant="gradient"
        />
      </div>
    </article>
  );
}

function Summary({ items }: { items: KpiItem[] }) {
  return (
    <section className="dashboard-summary" aria-label="Paper summary">
      {items.map((item, index) => (
        <KpiCard
          color={KPI_COLORS[index % KPI_COLORS.length]}
          item={item}
          key={item.label}
        />
      ))}
    </section>
  );
}

function updatedWithinDays(paper: DemoPaperSummary, days: number): boolean {
  const updated = Date.parse(paper.updated_at);
  if (Number.isNaN(updated)) return false;
  return Date.now() - updated <= days * 24 * 60 * 60 * 1000;
}

function weeklyDelta(papers: DemoPaperSummary[]): string | undefined {
  const recent = papers.filter((paper) => updatedWithinDays(paper, 7)).length;
  return recent > 0 ? `+${recent} this week` : undefined;
}

const ACTIVITY_CONFIG: ChartConfig = {
  papers: { label: "Papers", color: "blue" },
};

function ActivityChart({ papers }: { papers: DemoPaperSummary[] }) {
  const days = useMemo(() => {
    const buckets: Array<{
      day: string;
      label: string;
      papers: number;
    }> = [];
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const dayLabel = new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
    });
    for (let offset = ACTIVITY_DAYS - 1; offset >= 0; offset -= 1) {
      const day = new Date(today.getTime() - offset * DAY_MS);
      buckets.push({
        day: String(day.getDate()),
        label: dayLabel.format(day),
        papers: 0,
      });
    }
    const byKey = new Map(
      buckets.map((bucket, index) => {
        const date = new Date(today.getTime() - (ACTIVITY_DAYS - 1 - index) * DAY_MS);
        return [date.toISOString().slice(0, 10), bucket];
      }),
    );
    papers.forEach((paper) => {
      const updated = new Date(paper.updated_at);
      if (Number.isNaN(updated.getTime())) return;
      const bucket = byKey.get(updated.toISOString().slice(0, 10));
      if (bucket) bucket.papers += 1;
    });
    return buckets;
  }, [papers]);

  const rangeLabel = new Intl.DateTimeFormat(undefined, {
    month: "short",
    year: "numeric",
  }).format(new Date());

  return (
    <section className="dashboard-section activity-card" aria-label="Paper activity">
      <div className="dashboard-section-heading">
        <div>
          <h2>Paper activity</h2>
          <p>Papers created or updated per day over the last four weeks.</p>
        </div>
        <span className="activity-range">{rangeLabel}</span>
      </div>
      <div className="activity-plot">
        <AreaChart bloom="aura" config={ACTIVITY_CONFIG} data={days}>
          <Grid />
          <XAxis dataKey="day" />
          <YAxis tickFormatter={(value) => String(Math.round(value))} />
          <Tooltip labelKey="label" />
          <Area dataKey="papers" variant="gradient" />
        </AreaChart>
      </div>
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
      <Summary
        items={[
          { label: "Total papers", value: owned.length, note: "All papers created by you", delta: weeklyDelta(owned), series: dailyCounts(owned) },
          { label: "Editable drafts", value: owned.filter((paper) => paper.status === "draft").length, note: "Still with faculty", series: dailyCounts(owned.filter((paper) => paper.status === "draft")) },
          { label: "Under review", value: owned.filter((paper) => ["submitted_to_hod", "submitted_to_coe"].includes(paper.status)).length, note: "With HOD or CoE", series: dailyCounts(owned.filter((paper) => ["submitted_to_hod", "submitted_to_coe"].includes(paper.status))) },
          { label: "Approved", value: owned.filter((paper) => paper.status === "approved").length, note: "Completed papers", series: dailyCounts(owned.filter((paper) => paper.status === "approved")) },
        ]}
      />

      <ActivityChart papers={owned} />

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
      <Summary
        items={[
          { label: "Department papers", value: departmentPapers.length, note: "Submitted by faculty", delta: weeklyDelta(departmentPapers), series: dailyCounts(departmentPapers) },
          { label: "Awaiting your review", value: departmentPapers.filter((paper) => paper.status === "submitted_to_hod").length, note: "Action required", series: dailyCounts(departmentPapers.filter((paper) => paper.status === "submitted_to_hod")) },
          { label: "Forwarded by you", value: departmentPapers.filter((paper) => paper.hod_approved).length, note: "Sent to CoE", series: dailyCounts(departmentPapers.filter((paper) => paper.hod_approved)) },
          { label: "Approved by CoE", value: departmentPapers.filter((paper) => paper.status === "approved").length, note: "Final approval complete", series: dailyCounts(departmentPapers.filter((paper) => paper.status === "approved")) },
        ]}
      />

      <ActivityChart papers={departmentPapers} />

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
  const [department, setDepartment] = useState("all");
  const [examination, setExamination] = useState("all");
  const coePapers = papers.filter(
    (paper) =>
      ["submitted_to_coe", "approved"].includes(paper.status) ||
      Boolean(paper.last_coe_action),
  );
  const departments = useMemo(
    () => [...new Set(coePapers.map((paper) => paper.department).filter(Boolean))].sort(),
    [coePapers],
  );
  const examinations = useMemo(
    () => [...new Set(coePapers.map((paper) => paper.exam_label).filter(Boolean))].sort(),
    [coePapers],
  );
  const scoped = coePapers.filter(
    (paper) =>
      matchesQuery(paper, query) &&
      (year === "all" || academicYear(paper.year) === year) &&
      (department === "all" || paper.department === department) &&
      (examination === "all" || paper.exam_label === examination),
  );
  const pending = scoped.filter((paper) => paper.status === "submitted_to_coe");
  const decided = scoped.filter(
    (paper) => paper.status === "approved" || paper.last_coe_action === "decline",
  );
  const readinessRows = useMemo(() => {
    const grouped = new Map<string, DemoPaperSummary[]>();
    scoped.forEach((paper) => {
      const key = [
        paper.department || "Department not specified",
        academicYear(paper.year),
        paper.exam_label || "Examination not specified",
      ].join("|");
      grouped.set(key, [...(grouped.get(key) ?? []), paper]);
    });
    return [...grouped.entries()].sort(([left], [right]) => left.localeCompare(right));
  }, [scoped]);

  return (
    <DashboardFrame
      description="College-wide examination control for HOD-selected papers. Review final submissions, record decisions, and monitor readiness across departments and years."
      error={error}
      onRefresh={onRefresh}
      query={query}
      queryPlaceholder="Subject, course code, department, or year"
      setQuery={setQuery}
      title="Controller of Examinations"
      toolbarExtra={
        <>
          <label className="dashboard-filter"><span>Department</span><select onChange={(event) => setDepartment(event.target.value)} value={department}><option value="all">All departments</option>{departments.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
          <label className="dashboard-filter"><span>Academic year</span><select onChange={(event) => setYear(event.target.value)} value={year}><option value="all">All years</option><option value="1">1st year</option><option value="2">2nd year</option><option value="3">3rd year</option><option value="4">4th year</option><option value="unspecified">Year not specified</option></select></label>
          <label className="dashboard-filter"><span>Examination</span><select onChange={(event) => setExamination(event.target.value)} value={examination}><option value="all">All examinations</option>{examinations.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
        </>
      }
    >
      <Summary
        items={[
          { label: "Pending decisions", value: pending.length, note: "Requires CoE action", delta: weeklyDelta(pending), series: dailyCounts(pending) },
          { label: "Approved", value: scoped.filter((paper) => paper.status === "approved").length, note: "Cleared for examination", series: dailyCounts(scoped.filter((paper) => paper.status === "approved")) },
          { label: "Returned", value: scoped.filter((paper) => paper.last_coe_action === "decline").length, note: "Sent back for revision", series: dailyCounts(scoped.filter((paper) => paper.last_coe_action === "decline")) },
          { label: "Departments", value: new Set(scoped.map((paper) => paper.department).filter(Boolean)).size, note: "In the current view", series: dailyCounts(scoped) },
        ]}
      />

      <ActivityChart papers={scoped} />

      <PaperSection
        action={<button className="text-button" onClick={onQueue} type="button">Open final review queue</button>}
        description="Only HOD-selected papers appear here. Open a paper to accept or decline it."
        emptyMessage="No papers are awaiting a final CoE decision for this filter."
        loading={loading}
        onOpen={onOpen}
        papers={pending}
        showDepartment
        showYear
        title="Decisions required"
      />
      <section className="dashboard-section">
        <div className="dashboard-section-heading">
          <div><h2>Examination readiness</h2><p>Submission position separated by department, academic year, and examination.</p></div>
        </div>
        <div className="table-scroll role-summary-table">
          <table>
            <thead><tr><th>Department</th><th>Year</th><th>Examination</th><th>Subjects</th><th>Pending</th><th>Approved</th><th>Returned</th></tr></thead>
            <tbody>
              {readinessRows.map(([key, entries]) => {
                const [departmentName, yearKey, examinationName] = key.split("|");
                return (
                  <tr key={key}>
                    <td><strong>{departmentName}</strong></td>
                    <td>{academicYearLabel(yearKey)}</td>
                    <td>{examinationName}</td>
                    <td>{new Set(entries.map((paper) => paper.course_code || paper.course_name)).size}</td>
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
        description="Completed CoE decisions, including papers cleared for use and papers returned for revision."
        emptyMessage="No completed decisions match the current filters."
        loading={loading}
        onOpen={onOpen}
        papers={decided.slice(0, 10)}
        showDepartment
        showDecision
        showYear
        title="Recent decisions"
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
  showDecision?: boolean;
}

function PaperSection({ title, description, papers, loading, emptyMessage, onOpen, action, showOwner, showDepartment, showYear, showDecision }: PaperSectionProps) {
  return (
    <section className="dashboard-section">
      <div className="dashboard-section-heading"><div><h2>{title}</h2><p>{description}</p></div>{action}</div>
      <PaperRows emptyMessage={emptyMessage} loading={loading} onOpen={onOpen} papers={papers} showDecision={showDecision} showDepartment={showDepartment} showOwner={showOwner} showYear={showYear} />
    </section>
  );
}

function PaperRows({ papers, loading, emptyMessage, onOpen, showOwner, showDepartment, showYear, showDecision }: Omit<PaperSectionProps, "title" | "description" | "action">) {
  if (loading) return <p className="dashboard-empty">Loading local papers…</p>;
  if (papers.length === 0) return <p className="dashboard-empty">{emptyMessage}</p>;
  return (
    <div className="dashboard-paper-list">
      {papers.map((paper) => (
        <button key={paper.id} onClick={() => onOpen(paper.id)} type="button">
          <span aria-hidden="true" className="dashboard-paper-avatar">
            {(paper.course_code || paper.course_name || paper.subject || "QP").replace(/[^A-Za-z0-9]/g, "").slice(0, 2).toUpperCase() || "QP"}
          </span>
          <span className="dashboard-paper-course"><strong>{paper.course_name || paper.subject}</strong><small>{paper.course_code || "Course code not set"} · {paper.exam_label}{showOwner ? ` · ${paper.generated_by || "Faculty not recorded"}` : ""}{showDepartment ? ` · ${paper.department || "Department not recorded"}` : ""}{showYear ? ` · ${paper.year || "Year not specified"}` : ""}</small></span>
          <span className={`dashboard-status dashboard-status-${paper.status}`}>{showDecision && paper.last_coe_action === "decline" && paper.status !== "approved" ? "Returned for revision" : STATUS_LABELS[paper.status]}</span>
          <time dateTime={paper.updated_at}>{formatDate(paper.updated_at)}</time>
          <span className="dashboard-open">Open <span aria-hidden="true">→</span></span>
        </button>
      ))}
    </div>
  );
}
