import { useRef, useState } from "react";

import { extractSyllabus, type DemoExamDetails } from "../../services/api";
import type { DemoJob, UnitUpload } from "../../types/api";

import { UnitUploads } from "./UnitUploads";

function GenerationProgress({ job }: { job: DemoJob | null }) {
  return (
    <div aria-live="polite" className="generation-progress" role="status">
      <div className="generation-progress-heading">
        <strong>Generating your paper</strong>
        <span className="generation-elapsed">{job?.progress ?? 0}%</span>
      </div>
      <p className="generation-progress-note">
        {job?.stage ?? "Uploading the selected unit material"}
      </p>
      <div className="progress-track">
        <div
          className="progress-fill"
          style={{ width: `${job?.progress ?? 2}%` }}
        />
      </div>
      <p className="generation-progress-note">
        The backend is running live analysis, generation and independent review.
        You can open Paper history and return while it continues.
      </p>
    </div>
  );
}

export const PAPER_PATTERNS = [
  {
    id: "cat-1-75",
    label: "CAT-I · 75 marks · 120 minutes",
    description:
      "Units 1 and 2 in full, plus the CAT-I portion of Unit 3. Each unit has its own Part A and Part B.",
  },
  {
    id: "cat-2-75",
    label: "CAT-II · 75 marks · 120 minutes",
    description:
      "The CAT-II portion of Unit 3, plus Units 4 and 5 in full. Each unit has its own Part A and Part B.",
  },
  {
    id: "autonomous-semester-100",
    label: "End-semester · 100 marks · 3 hours",
    description:
      "Units 1–5. Part A 10 x 2 = 20, Part B 5 x 13 = 65 with an a. [OR] b. choice, Part C 1 x 15 = 15.",
  },
] as const;

interface UploadPanelProps {
  loading: boolean;
  generationJob: DemoJob | null;
  patternId: string;
  examDetails: DemoExamDetails;
  setCount: number;
  unitUploads: UnitUpload[];
  courseOutcomes: string[];
  onPatternChange: (patternId: string) => void;
  onExamDetailsChange: (details: DemoExamDetails) => void;
  onSetCountChange: (setCount: number) => void;
  onUnitUploadsChange: (uploads: UnitUpload[]) => void;
  onCourseOutcomesChange: (outcomes: string[]) => void;
  onSubmit: () => void;
}


/** NBA expects every course outcome to open with a Bloom action verb. */
const BLOOM_VERBS = [
  "define", "describe", "identify", "list", "recall", "state", "recognise",
  "recognize", "explain", "summarise", "summarize", "interpret", "classify",
  "illustrate", "apply", "compute", "construct", "demonstrate", "implement",
  "solve", "use", "analyse", "analyze", "compare", "differentiate", "examine",
  "distinguish", "evaluate", "assess", "justify", "critique", "recommend",
  "design", "develop", "formulate", "create", "build", "produce",
];

export function outcomeWarning(outcome: string): string | null {
  const trimmed = outcome.trim();
  if (!trimmed) return null;
  const firstWord = trimmed.split(/\s+/)[0].toLowerCase().replace(/[^a-z]/g, "");
  if (BLOOM_VERBS.includes(firstWord)) return null;
  return `Should begin with a Bloom action verb — "${firstWord}" is not one.`;
}

function formatFileSize(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.ceil(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function UploadPanel({
  loading,
  generationJob,
  patternId,
  examDetails,
  setCount,
  unitUploads,
  courseOutcomes,
  onPatternChange,
  onExamDetailsChange,
  onSetCountChange,
  onUnitUploadsChange,
  onCourseOutcomesChange,
  onSubmit,
}: UploadPanelProps) {
  const syllabusInputRef = useRef<HTMLInputElement>(null);
  const [syllabusBusy, setSyllabusBusy] = useState(false);
  const [syllabusNote, setSyllabusNote] = useState<string | null>(null);
  const [syllabusError, setSyllabusError] = useState<string | null>(null);

  const readSyllabus = async (syllabus: File | undefined) => {
    if (!syllabus) return;
    setSyllabusBusy(true);
    setSyllabusError(null);
    setSyllabusNote(null);
    try {
      const found = await extractSyllabus(syllabus);
      if (found.course_outcomes.length === 0) {
        setSyllabusError(
          found.problem ??
            "No course outcomes found on that page. Check it is the syllabus page for one course.",
        );
        return;
      }
      onCourseOutcomesChange(found.course_outcomes);
      const name = found.subject_name ?? "this course";
      const units = found.units.length
        ? ` and ${found.units.length} units`
        : "";
      setSyllabusNote(
        `Read ${found.course_outcomes.length} outcomes${units} for ${name}. ` +
          "Check every line against your syllabus before generating.",
      );
      if (!found.extraction_confident && found.problem) {
        setSyllabusError(found.problem);
      }
    } catch (cause) {
      setSyllabusError(
        cause instanceof Error ? cause.message : "Could not read the syllabus.",
      );
    } finally {
      setSyllabusBusy(false);
    }
  };
  return (
    <section aria-labelledby="upload-title" className="workspace-panel upload-panel">
      <div className="panel-heading">
        <div>
          <h2 id="upload-title">Course material</h2>
          <p>
            Upload the unit material every question will be grounded in — your
            own notes, handouts or prescribed text.
          </p>
        </div>
        <span className="step-count">1 of 2</span>
      </div>

      <div className="setup-fields" id="paper-pattern">
        <div className="field-group">
          <label htmlFor="paper-pattern-select">Paper pattern</label>
          {PAPER_PATTERNS.length > 1 ? (
            <select
              disabled={loading}
              id="paper-pattern-select"
              onChange={(event) => onPatternChange(event.target.value)}
              value={patternId}
            >
              {PAPER_PATTERNS.map((pattern) => (
                <option key={pattern.id} value={pattern.id}>
                  {pattern.label}
                </option>
              ))}
            </select>
          ) : (
            <p className="field-static" id="paper-pattern-select">
              {PAPER_PATTERNS[0].label}
            </p>
          )}
          <p>
            {PAPER_PATTERNS.find((pattern) => pattern.id === patternId)
              ?.description}
          </p>
        </div>

        <div className="field-group">
          <label htmlFor="course-code">Examination details</label>
          <div className="demo-exam-grid">
            <label>
              <span>Course code</span>
              <input
                disabled={loading}
                id="course-code"
                onChange={(event) =>
                  onExamDetailsChange({
                    ...examDetails,
                    courseCode: event.target.value,
                  })
                }
                placeholder="CS23C04"
                value={examDetails.courseCode}
              />
            </label>
            <label>
              <span>Course name</span>
              <input
                disabled={loading}
                onChange={(event) =>
                  onExamDetailsChange({
                    ...examDetails,
                    courseName: event.target.value,
                  })
                }
                placeholder="Data Structures"
                value={examDetails.courseName}
              />
            </label>
            <label>
              <span>Year</span>
              <input
                disabled={loading}
                onChange={(event) =>
                  onExamDetailsChange({ ...examDetails, year: event.target.value })
                }
                placeholder="II Year"
                value={examDetails.year}
              />
            </label>
            <label>
              <span>Semester</span>
              <input
                disabled={loading}
                onChange={(event) =>
                  onExamDetailsChange({
                    ...examDetails,
                    semester: event.target.value,
                  })
                }
                placeholder="III"
                value={examDetails.semester}
              />
            </label>
            <label>
              <span>Exam date</span>
              <input
                disabled={loading}
                onChange={(event) =>
                  onExamDetailsChange({
                    ...examDetails,
                    examDate: event.target.value,
                  })
                }
                type="date"
                value={examDetails.examDate}
              />
            </label>
          </div>
        </div>

        <UnitUploads
          loading={loading}
          onChange={onUnitUploadsChange}
          uploads={unitUploads}
        />

        <div className="field-group course-outcome-field">
          <label htmlFor="course-outcome-0">Course outcomes</label>
          <p>
            The outcomes your department approved, one per line, exactly as
            written in the syllabus. Each question is mapped to one of these and
            the paper reports the marks per outcome. Leave blank to skip outcome
            mapping.
          </p>
          <div className="syllabus-import">
            <input
              accept="application/pdf"
              className="visually-hidden"
              onChange={(event) => {
                void readSyllabus(event.target.files?.[0]);
                event.target.value = "";
              }}
              ref={syllabusInputRef}
              type="file"
            />
            <button
              className="secondary-button"
              disabled={loading || syllabusBusy}
              onClick={() => syllabusInputRef.current?.click()}
              type="button"
            >
              {syllabusBusy ? "Reading syllabus…" : "Fill from syllabus PDF"}
            </button>
            <span>
              Reads the outcomes off your syllabus page so you can check them
              rather than retype them.
            </span>
          </div>
          {syllabusNote && <p className="syllabus-note">{syllabusNote}</p>}
          {syllabusError && <p className="field-error">{syllabusError}</p>}
          <ol className="outcome-list">
            {[...courseOutcomes, ""].map((outcome, index) => {
              const warning = outcomeWarning(outcome);
              const isNew = index === courseOutcomes.length;
              return (
                <li key={index}>
                  <span className="outcome-tag">CO{index + 1}</span>
                  <div className="outcome-entry">
                    <input
                      disabled={loading}
                      id={`course-outcome-${index}`}
                      onChange={(event) => {
                        const next = [...courseOutcomes];
                        if (isNew) next.push(event.target.value);
                        else next[index] = event.target.value;
                        onCourseOutcomesChange(
                          next.filter((entry, position) =>
                            entry.trim() !== "" || position === next.length - 1,
                          ),
                        );
                      }}
                      placeholder={
                        isNew
                          ? "Add an outcome, e.g. Apply normalization techniques to design relational schemas"
                          : ""
                      }
                      type="text"
                      value={outcome}
                    />
                    {warning && <span className="outcome-warning">{warning}</span>}
                  </div>
                  {!isNew && (
                    <button
                      aria-label={`Remove outcome ${index + 1}`}
                      className="outcome-remove"
                      disabled={loading}
                      onClick={() =>
                        onCourseOutcomesChange(
                          courseOutcomes.filter((_, position) => position !== index),
                        )
                      }
                      type="button"
                    >
                      Remove
                    </button>
                  )}
                </li>
              );
            })}
          </ol>
        </div>

        <div className="field-group">
          <label htmlFor="set-count-select">Candidate sets</label>
          <select
            disabled
            id="set-count-select"
            onChange={(event) => onSetCountChange(Number(event.target.value))}
            value={setCount}
          >
            <option value={3}>Three sets — A, B and C</option>
          </select>
          <p>
            Faculty generates three equivalent candidates. The HOD compares them
            and forwards one selected set to the CoE.
          </p>
        </div>
      </div>

      <button
        className="primary-button submit-button"
        disabled={
          loading ||
          !unitUploads.every((upload) => upload.file)
        }
        onClick={onSubmit}
        type="button"
      >
        {loading ? "Generating paper…" : "Generate paper"}
      </button>

      {loading && <GenerationProgress job={generationJob} />}
    </section>
  );
}
