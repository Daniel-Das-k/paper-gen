import { useCallback, useEffect, useRef, useState } from "react";

import {
  AppHeader,
  DEMO_VIEW_PATHS,
  type DemoView,
} from "../components/layout/AppHeader";
import { DemoDashboard } from "../components/demo/DemoDashboard";
import { PaperListPage } from "../components/demo/PaperListPage";
import { WorkflowResultPanel } from "../components/results/WorkflowResultPanel";
import { PAPER_PATTERNS, UploadPanel } from "../components/upload/UploadPanel";
import {
  createDemoGenerationJob,
  getDemoJob,
  getDemoPaper,
  listDemoPapers,
  type DemoExamDetails,
} from "../services/api";
import type {
  DemoJob,
  DemoPaperRecord,
  DemoPaperSummary,
  DemoUser,
  UnitUpload,
} from "../types/api";

type PatternId = (typeof PAPER_PATTERNS)[number]["id"];

interface ExamWorkspace {
  unitUploads: UnitUpload[];
  setCount: number;
  error: string | null;
}

const PATTERN_UNITS: Record<PatternId, string[]> = {
  "cat-1-75": ["1", "2", "3"],
  "cat-2-75": ["3", "4", "5"],
  "autonomous-semester-100": ["1", "2", "3", "4", "5"],
};

const EMPTY_DETAILS: DemoExamDetails = {
  courseCode: "",
  courseName: "",
  year: "",
  semester: "",
  examDate: "",
};

function createUnitUploads(patternId: PatternId): UnitUpload[] {
  return PATTERN_UNITS[patternId].map((unit) => ({
    unit,
    file: null,
    startPage: "",
    endPage: "",
  }));
}

function createExamWorkspaces(): Record<PatternId, ExamWorkspace> {
  return Object.fromEntries(
    PAPER_PATTERNS.map((pattern) => [
      pattern.id,
      {
        unitUploads: createUnitUploads(pattern.id),
        setCount: 3,
        error: null,
      },
    ]),
  ) as Record<PatternId, ExamWorkspace>;
}

interface DashboardPageProps {
  view: DemoView;
  paperId?: string;
  user: DemoUser;
  onNavigate: (path: string, replace?: boolean) => void;
  onLogout: () => void;
  onExitDemo: () => void;
}

export function DashboardPage({
  view,
  paperId,
  user,
  onNavigate,
  onLogout,
  onExitDemo,
}: DashboardPageProps) {
  const role = user.role;
  const [patternId, setPatternId] = useState<PatternId>(
    "autonomous-semester-100",
  );
  const [courseOutcomes, setCourseOutcomes] = useState<string[]>([]);
  const [examDetails, setExamDetails] = useState<DemoExamDetails>(EMPTY_DETAILS);
  const [workspaces, setWorkspaces] = useState(createExamWorkspaces);
  const [job, setJob] = useState<DemoJob | null>(null);
  const [record, setRecord] = useState<DemoPaperRecord | null>(null);
  const [papers, setPapers] = useState<DemoPaperSummary[]>([]);
  const [papersLoading, setPapersLoading] = useState(false);
  const [papersError, setPapersError] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);
  const workspace = workspaces[patternId];
  const loading = job?.status === "queued" || job?.status === "running";

  const updateWorkspace = (
    target: PatternId,
    patch: Partial<ExamWorkspace>,
  ) => {
    setWorkspaces((current) => ({
      ...current,
      [target]: { ...current[target], ...patch },
    }));
  };

  const loadPapers = useCallback(async () => {
    setPapersLoading(true);
    setPapersError(null);
    try {
      setPapers(await listDemoPapers());
    } catch (cause) {
      setPapersError(
        cause instanceof Error ? cause.message : "Could not load local papers.",
      );
    } finally {
      setPapersLoading(false);
    }
  }, []);

  useEffect(() => {
    if (view !== "create") void loadPapers();
  }, [loadPapers, view]);

  useEffect(() => {
    if (view === "create" && !paperId && role !== "faculty") {
      onNavigate("/demo/dashboard", true);
    }
  }, [onNavigate, paperId, role, view]);

  useEffect(() => {
    if (!paperId) {
      if (view === "create") setRecord(null);
      return;
    }

    let active = true;
    setRecord(null);
    setPapersError(null);
    void getDemoPaper(paperId)
      .then((loaded) => {
        if (active) setRecord(loaded);
      })
      .catch((cause) => {
        if (!active) return;
        setPapersError(
          cause instanceof Error ? cause.message : "Could not open the paper.",
        );
        onNavigate("/demo/papers", true);
      });
    return () => {
      active = false;
    };
  }, [onNavigate, paperId, view]);

  useEffect(
    () => () => {
      if (pollRef.current !== null) window.clearTimeout(pollRef.current);
    },
    [],
  );

  const openPaper = (paperId: string) => {
    onNavigate(`/demo/papers/${encodeURIComponent(paperId)}`);
  };

  const pollJob = async (jobId: string) => {
    try {
      const next = await getDemoJob(jobId);
      setJob(next);
      if (next.status === "completed" && next.paper_id) {
        await loadPapers();
        onNavigate(`/demo/papers/${encodeURIComponent(next.paper_id)}`);
        return;
      }
      if (next.status === "failed") {
        updateWorkspace(patternId, {
          error: next.error ?? "The generation could not be completed.",
        });
        return;
      }
      pollRef.current = window.setTimeout(() => void pollJob(jobId), 1500);
    } catch (cause) {
      updateWorkspace(patternId, {
        error:
          cause instanceof Error
            ? cause.message
            : "Could not read generation progress.",
      });
      setJob(null);
    }
  };

  const generate = async () => {
    const requestedPattern = patternId;
    const requested = workspaces[requestedPattern];
    const missing = requested.unitUploads
      .filter((upload) => upload.file === null)
      .map((upload) => upload.unit);
    if (missing.length) {
      updateWorkspace(requestedPattern, {
        error: `Choose a PDF for unit${missing.length === 1 ? "" : "s"} ${missing.join(", ")}.`,
      });
      return;
    }
    const invalidRange = requested.unitUploads.find((upload) => {
      const start = upload.startPage ? Number(upload.startPage) : undefined;
      const end = upload.endPage ? Number(upload.endPage) : undefined;
      return (
        (start !== undefined && (!Number.isInteger(start) || start < 1)) ||
        (end !== undefined && (!Number.isInteger(end) || end < 1)) ||
        (start !== undefined && end !== undefined && end < start)
      );
    });
    if (invalidRange) {
      updateWorkspace(requestedPattern, {
        error: `Enter a valid page range for unit ${invalidRange.unit}.`,
      });
      return;
    }

    updateWorkspace(requestedPattern, { error: null });
    setRecord(null);
    try {
      const started = await createDemoGenerationJob(
        requested.unitUploads.map((upload) => ({
          unit: upload.unit,
          file: upload.file as File,
          startPage: upload.startPage ? Number(upload.startPage) : undefined,
          endPage: upload.endPage ? Number(upload.endPage) : undefined,
        })),
        requestedPattern,
        courseOutcomes.filter((outcome) => outcome.trim()),
        requested.setCount,
        examDetails,
        user.displayName,
      );
      setJob(started);
      void pollJob(started.id);
    } catch (cause) {
      updateWorkspace(requestedPattern, {
        error:
          cause instanceof Error ? cause.message : "Could not start generation.",
      });
      setJob(null);
    }
  };

  const startNew = () => {
    setRecord(null);
    setJob(null);
    updateWorkspace(patternId, {
      unitUploads: createUnitUploads(patternId),
      error: null,
    });
    onNavigate("/demo/generate");
  };

  const changeView = (nextView: DemoView) => {
    if (nextView === "create") setRecord(null);
    onNavigate(DEMO_VIEW_PATHS[nextView]);
  };

  return (
    <div className="app-shell demo-shell arc-atmosphere">
      <AppHeader
        onExitDemo={onExitDemo}
        onLogout={onLogout}
        onViewChange={changeView}
        user={user}
        view={
          paperId
            ? record?.status === "draft"
              ? "queue"
              : "history"
            : view
        }
      />

      {view === "dashboard" ? (
        <DemoDashboard
          error={papersError}
          job={job}
          loading={papersLoading}
          onCreate={startNew}
          onOpen={openPaper}
          onQueue={() => onNavigate("/demo/review")}
          onRefresh={() => void loadPapers()}
          papers={papers}
          user={user}
        />
      ) : view === "queue" || view === "history" ? (
        <PaperListPage
          error={papersError}
          loading={papersLoading}
          mode={view}
          onOpen={openPaper}
          onRefresh={() => void loadPapers()}
          papers={papers}
          user={user}
        />
      ) : paperId && !record ? (
        <main className="demo-page page-container">
          <p className="demo-list-empty" aria-live="polite">
            Loading question paper…
          </p>
        </main>
      ) : record ? (
        <main className="demo-page page-container">
          <WorkflowResultPanel
            key={record.id}
            onRecordChange={setRecord}
            record={record}
            role={role}
          />
        </main>
      ) : (
        <main className="demo-page page-container">
          <div className="demo-page-heading">
            <div>
              <h1>Create a question paper</h1>
              <p>
                Select the examination, add its course material, and generate a
                source-grounded draft for faculty review.
              </p>
            </div>
          </div>
          {workspace.error && (
            <div className="request-error" role="alert">
              <strong>Could not generate this paper</strong>
              <p>{workspace.error}</p>
            </div>
          )}
          <UploadPanel
            courseOutcomes={courseOutcomes}
            examDetails={examDetails}
            generationJob={job}
            loading={loading}
            onCourseOutcomesChange={setCourseOutcomes}
            onExamDetailsChange={setExamDetails}
            onPatternChange={(next) => setPatternId(next as PatternId)}
            onSetCountChange={(setCount) =>
              updateWorkspace(patternId, { setCount })
            }
            onSubmit={() => void generate()}
            onUnitUploadsChange={(unitUploads) =>
              updateWorkspace(patternId, { unitUploads, error: null })
            }
            patternId={patternId}
            setCount={workspace.setCount}
            unitUploads={workspace.unitUploads}
          />
        </main>
      )}
    </div>
  );
}
