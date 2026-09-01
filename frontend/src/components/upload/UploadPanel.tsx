import { useRef, useState } from "react";

import { extractSyllabus, type DemoExamDetails } from "../../services/api";
import type { DemoJob, UnitUpload } from "../../types/api";

import { UnitUploads } from "./UnitUploads";

export const PAPER_PATTERNS = [
  {
    id: "cat-1-75",
    name: "CAT-I",
    label: "CAT-I \u00B7 75 marks \u00B7 120 minutes",
    marks: 75,
    duration: "120 minutes",
    description:
      "Units 1 and 2 in full, plus the CAT-I portion of Unit 3. Each unit has its own Part A and Part B.",
  },
  {
    id: "cat-2-75",
    name: "CAT-II",
    label: "CAT-II \u00B7 75 marks \u00B7 120 minutes",
    marks: 75,
    duration: "120 minutes",
    description:
      "The CAT-II portion of Unit 3, plus Units 4 and 5 in full. Each unit has its own Part A and Part B.",
  },
  {
    id: "autonomous-semester-100",
    name: "End-semester",
    label: "End-semester \u00B7 100 marks \u00B7 3 hours",
    marks: 100,
    duration: "3 hours",
    description:
      "Units 1\u20135. Part A 10 x 2 = 20, Part B 5 x 13 = 65 with an a. [OR] b. choice, Part C 1 x 15 = 15.",
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
  return `Should begin with a Bloom action verb \u2014 "${firstWord}" is not one.`;
}

const EXAM_FIELDS: Array<{
  key: keyof DemoExamDetails;
  label: string;
  placeholder: string;
  type?: "date";
}> = [
  { key: "courseCode", label: "Course code", placeholder: "CS23C04" },
  { key: "courseName", label: "Course name", placeholder: "Data Structures" },
  { key: "year", label: "Year", placeholder: "II Year" },
  { key: "semester", label: "Semester", placeholder: "III" },
  { key: "examDate", label: "Exam date", placeholder: "", type: "date" },
];

function CheckDot({ state }: { state: "done" | "partial" | "todo" }) {
  return (
    <span aria-hidden="true" className={`gen-check gen-check-${state}`}>
      {state === "done" ? (
        <svg fill="none" height="10" viewBox="0 0 12 12" width="10">
          <path
            d="M2.5 6.5 5 9l4.5-6"
            pathLength={1}
            stroke="currentColor"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="1.8"
          />
        </svg>
      ) : null}
    </span>
  );
}

function GenerationProgress({ job }: { job: DemoJob | null }) {
  return (
    <div aria-live="polite" className="gen-progress" role="status">
      <div className="gen-progress-heading">
        <strong>Generating your paper</strong>
        <span>{job?.progress ?? 0}%</span>
      </div>
      <div className="progress-track">
        <div
          className="progress-fill"
          style={{ width: `${job?.progress ?? 2}%` }}
        />
      </div>
      <p>{job?.stage ?? "Uploading the selected unit material"}</p>
      <p className="gen-progress-note">
        Analysis, generation and independent review run in sequence. You can
        open another tab of the workspace and return while it continues.
      </p>
    </div>
  );
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
  onSetCountChange: _onSetCountChange,
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

  const pattern = PAPER_PATTERNS.find((entry) => entry.id === patternId);
  const uploadedCount = unitUploads.filter((upload) => upload.file).length;
  const missingUnits = unitUploads
    .filter((upload) => !upload.file)
    .map((upload) => upload.unit);
  const detailValues: Array<[string, string]> = [
    ["Course code", examDetails.courseCode],
    ["Course name", examDetails.courseName],
    ["Year", examDetails.year],
    ["Semester", examDetails.semester],
    ["Exam date", examDetails.examDate],
  ];
  const filledDetails = detailValues.filter(([, value]) => value.trim()).length;
  const namedOutcomes = courseOutcomes.filter((outcome) => outcome.trim());
  const ready = missingUnits.length === 0 && !loading;

  return (
    <div className="generate-layout">
      <div className="generate-main">
        <section aria-labelledby="gen-exam-title" className="gen-card">
          <header className="gen-card-heading">
            <span aria-hidden="true" className="gen-step">1</span>
            <div>
              <h2 id="gen-exam-title">Examination</h2>
              <p>Pick the paper pattern and fill in the exam details.</p>
            </div>
          </header>

          <div aria-label="Paper pattern" className="pattern-cards" role="radiogroup">
            {PAPER_PATTERNS.map((entry) => (
              <button
                aria-checked={entry.id === patternId}
                className={
                  entry.id === patternId
                    ? "pattern-card pattern-card-selected"
                    : "pattern-card"
                }
                disabled={loading}
                key={entry.id}
                onClick={() => onPatternChange(entry.id)}
                role="radio"
                type="button"
              >
                <span className="pattern-card-top">
                  <strong>{entry.name}</strong>
                  <span aria-hidden="true" className="pattern-card-radio" />
                </span>
                <span className="pattern-card-meta">
                  {entry.marks} marks {"\u00B7"} {entry.duration}
                </span>
                <span className="pattern-card-desc">{entry.description}</span>
              </button>
            ))}
          </div>

          <div className="gen-exam-grid">
            {EXAM_FIELDS.map((field) => (
              <label key={field.key}>
                <span>{field.label}</span>
                <input
                  disabled={loading}
                  onChange={(event) =>
                    onExamDetailsChange({
                      ...examDetails,
                      [field.key]: event.target.value,
                    })
                  }
                  placeholder={field.placeholder}
                  type={field.type ?? "text"}
                  value={examDetails[field.key]}
                />
              </label>
            ))}
          </div>
        </section>

        <section aria-labelledby="gen-units-title" className="gen-card">
          <header className="gen-card-heading">
            <span aria-hidden="true" className="gen-step">2</span>
            <div>
              <h2 id="gen-units-title">Unit material</h2>
              <p>
                One PDF per unit {"\u2014"} your own notes, handouts or the
                prescribed text. Every question is grounded in these pages.
              </p>
            </div>
            <span className="gen-card-count">
              {uploadedCount} of {unitUploads.length}
            </span>
          </header>
          <UnitUploads
            loading={loading}
            onChange={onUnitUploadsChange}
            uploads={unitUploads}
          />
        </section>

        <section aria-labelledby="gen-outcomes-title" className="gen-card">
          <header className="gen-card-heading">
            <span aria-hidden="true" className="gen-step">3</span>
            <div>
              <h2 id="gen-outcomes-title">
                Course outcomes <em className="gen-optional">Optional</em>
              </h2>
              <p>
                The outcomes your department approved, exactly as written in the
                syllabus. Each question is mapped to one and the paper reports
                marks per outcome.
              </p>
            </div>
          </header>

          <div className="gen-syllabus">
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
              {syllabusBusy ? "Reading syllabus\u2026" : "Fill from syllabus PDF"}
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
        </section>
      </div>

      <aside aria-label="Paper summary" className="generate-rail">
        <div className="gen-summary">
          <div className="gen-summary-heading">
            <h3>{pattern?.name ?? "Paper"} paper</h3>
            <p>
              {examDetails.courseCode.trim() || examDetails.courseName.trim()
                ? [examDetails.courseCode.trim(), examDetails.courseName.trim()]
                    .filter(Boolean)
                    .join(" \u00B7 ")
                : "Course details appear here as you fill them in."}
            </p>
          </div>

          <dl className="gen-summary-facts">
            <div>
              <dt>Marks</dt>
              <dd>{pattern?.marks ?? 100}</dd>
            </div>
            <div>
              <dt>Duration</dt>
              <dd>{pattern?.duration ?? "3 hours"}</dd>
            </div>
            <div>
              <dt>Candidate sets</dt>
              <dd>{setCount} {"\u00B7"} A, B, C</dd>
            </div>
          </dl>

          <ul className="gen-checklist">
            <li>
              <CheckDot state="done" />
              <span>
                Pattern <strong>{pattern?.name ?? patternId}</strong>
              </span>
            </li>
            <li>
              <CheckDot
                state={
                  filledDetails === detailValues.length
                    ? "done"
                    : filledDetails > 0
                      ? "partial"
                      : "todo"
                }
              />
              <span>
                Exam details{" "}
                <strong>
                  {filledDetails} of {detailValues.length}
                </strong>
              </span>
            </li>
            <li>
              <CheckDot
                state={
                  uploadedCount === unitUploads.length
                    ? "done"
                    : uploadedCount > 0
                      ? "partial"
                      : "todo"
                }
              />
              <span>
                Unit PDFs{" "}
                <strong>
                  {uploadedCount} of {unitUploads.length}
                </strong>
              </span>
            </li>
            <li>
              <CheckDot state={namedOutcomes.length > 0 ? "done" : "todo"} />
              <span>
                Course outcomes{" "}
                <strong>
                  {namedOutcomes.length > 0
                    ? `${namedOutcomes.length} added`
                    : "optional"}
                </strong>
              </span>
            </li>
          </ul>

          <button
            className="primary-button gen-submit"
            disabled={!ready}
            onClick={onSubmit}
            type="button"
          >
            {loading
              ? "Generating paper\u2026"
              : `Generate ${setCount} candidate sets`}
          </button>

          {!loading && missingUnits.length > 0 && (
            <p className="gen-summary-hint">
              Upload the PDF for unit{missingUnits.length === 1 ? "" : "s"}{" "}
              {missingUnits.join(", ")} to enable generation.
            </p>
          )}
          {!loading && missingUnits.length === 0 && (
            <p className="gen-summary-hint gen-summary-hint-ready">
              Three equivalent sets are generated. The HOD compares them and
              forwards one to the CoE.
            </p>
          )}

          {loading && <GenerationProgress job={generationJob} />}
        </div>
      </aside>
    </div>
  );
}
