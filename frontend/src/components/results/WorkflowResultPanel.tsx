import { useEffect, useState } from "react";

import type {
  BloomLevel,
  DemoPaperRecord,
  DemoPaperStatus,
  DemoRole,
  PaperPattern,
} from "../../types/api";
import {
  editDemoQuestion,
  fetchPatterns,
  getApiUrl,
  regenerateDemoQuestion,
  transitionDemoPaper,
  updateDemoHeader,
} from "../../services/api";
import { AlertIcon, CheckIcon } from "../icons/Icons";
import { PaperSheet, type ExamDetails } from "./PaperSheet";

// Everything on a Rajalakshmi paper that does not change between subjects is
// filled in already; the faculty member supplies only what actually varies.
const DEFAULT_DETAILS: ExamDetails = {
  college: "RAJALAKSHMI ENGINEERING COLLEGE",
  affiliation: "An AUTONOMOUS Institution · Affiliated to ANNA UNIVERSITY, Chennai",
  examTitle: "",
  year: "",
  semester: "",
  branch: "B.E. / B.Tech.",
  subjectCode: "",
  subjectName: "",
  qpCode: "",
  regulation: "Regulations 2023",
  commonTo: "CSE, ECE, EEE, IT, AIML, CSD, AI & DS, CS",
  date: "",
};

/** The exam title follows from the pattern, so it is filled in rather than typed. */
const PATTERN_EXAM_TITLE: Record<string, string> = {
  "cat-1-75": "Continuous Assessment Test-I [CAT-I]",
  "cat-2-75": "Continuous Assessment Test-II [CAT-II]",
  "autonomous-semester-100": "End Semester Examination",
};

const DETAIL_FIELDS: Array<[keyof ExamDetails, string]> = [
  ["college", "College"],
  ["examTitle", "Examination"],
  ["year", "Year"],
  ["semester", "Semester"],
  ["branch", "Branch"],
  ["subjectCode", "Sub. Code"],
  ["subjectName", "Subject"],
  ["qpCode", "QP Code"],
  ["regulation", "Regulation"],
  ["date", "Date"],
  ["commonTo", "Common to"],
];

function readDetails(
  patternId: string,
  record: DemoPaperRecord,
): ExamDetails {
  const stored = record.result.paper.exam_header;
  const defaults = {
    ...DEFAULT_DETAILS,
    examTitle: PATTERN_EXAM_TITLE[patternId] ?? "Examination",
  };
  return {
    ...defaults,
    college: stored.college,
    affiliation: `${stored.institution_line} · ${stored.affiliation}`,
    examTitle: stored.exam_title || defaults.examTitle,
    year: stored.year,
    semester: stored.semester,
    branch: stored.branch,
    subjectCode: stored.subject_code,
    subjectName: stored.subject_name,
    qpCode: stored.qp_code,
    regulation: stored.regulation,
    commonTo: stored.common_to,
    date: stored.date,
  };
}

interface WorkflowResultPanelProps {
  record: DemoPaperRecord;
  role: DemoRole;
  onRecordChange: (record: DemoPaperRecord) => void;
  onReset: () => void;
}

const STATUS_LABELS: Record<DemoPaperStatus, string> = {
  draft: "Faculty draft",
  submitted_to_hod: "Waiting for HOD review",
  submitted_to_coe: "Waiting for CoE review",
  approved: "Approved and locked",
};

const BLOOM_ORDER: BloomLevel[] = [
  "remember",
  "understand",
  "apply",
  "analyze",
  "evaluate",
  "create",
];

const FINDING_LABELS: Record<string, string> = {
  duplicate_question: "Too similar to another question",
  short_question_too_long: "Too long for the assigned marks",
  long_question_too_short: "Not detailed enough for the assigned marks",
  quality_score_below_threshold: "Quality score needs improvement",
  not_grounded: "Not sufficiently supported by the uploaded material",
  incorrect_answer: "The model answer may be incorrect",
  unclear_wording: "Wording is unclear",
  difficulty_mismatch: "Difficulty does not match the blueprint",
  invalid_marking_scheme: "Marking scheme needs correction",
  low_pedagogical_quality: "Educational quality needs improvement",
  bloom_level_deviation: "Cognitive level differs from the blueprint",
  review_confidence: "Automated review confidence is low",
};

function findingLabel(code: string): string {
  return (
    FINDING_LABELS[code] ??
    code
      .replace(/_/g, " ")
      .replace(/^./, (character) => character.toUpperCase())
  );
}

export function WorkflowResultPanel({
  record,
  role,
  onRecordChange,
  onReset,
}: WorkflowResultPanelProps) {
  const result = record.result;
  const patternId = result.blueprint.pattern_id;
  const [pattern, setPattern] = useState<PaperPattern | null>(null);
  const [openAnswers, setOpenAnswers] = useState<Set<string>>(new Set());
  const [details, setDetails] = useState<ExamDetails>(() =>
    readDetails(patternId, record),
  );
  const [editingHeader, setEditingHeader] = useState(false);
  const [workflowComment, setWorkflowComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [editingQuestionId, setEditingQuestionId] = useState<string | null>(null);
  const [questionDraft, setQuestionDraft] = useState("");
  const [answerDraft, setAnswerDraft] = useState("");
  const [criteriaDraft, setCriteriaDraft] = useState<
    Array<{ criterion: string; marks: number }>
  >([]);
  const [regenerationComments, setRegenerationComments] = useState<
    Record<string, string>
  >({});
  const [regeneratingQuestionId, setRegeneratingQuestionId] = useState<
    string | null
  >(null);
  const [regenerationMode, setRegenerationMode] = useState<
    "guided" | "fresh" | null
  >(null);
  const [openRegenerationQuestionId, setOpenRegenerationQuestionId] = useState<
    string | null
  >(null);

  useEffect(() => {
    let active = true;
    setPattern(null);
    void fetchPatterns()
      .then((patterns) => {
        if (active) {
          setPattern(
            patterns.find((candidate) => candidate.pattern_id === patternId) ??
              null,
          );
        }
      })
      .catch(() => {
        // The generated blueprint below still supplies safe section ordering.
        if (active) setPattern(null);
      });
    return () => {
      active = false;
    };
  }, [patternId]);

  const answerKey = new Map(
    (result.answer_key ?? []).map((entry) => [entry.question_id, entry]),
  );
  const allOpen = answerKey.size > 0 && openAnswers.size === answerKey.size;

  const questions = result.paper.questions;
  const accepted = questions.filter((question) => question.accepted).length;
  const bloom = result.paper.bloom_summary;
  const eligibleVisuals = result.manifest.visual_assets.filter(
    (asset) => asset.question_eligible,
  ).length;
  const unitsCovered = new Set(
    result.content_map.topics.map((topic) => topic.unit),
  ).size;

  const saveHeader = async () => {
    setBusy(true);
    setActionError(null);
    try {
      const current = result.paper.exam_header;
      const updated = await updateDemoHeader(record.id, {
        ...current,
        college: details.college,
        affiliation: details.affiliation.includes("·")
          ? details.affiliation.split("·").slice(1).join("·").trim()
          : details.affiliation,
        exam_title: details.examTitle,
        year: details.year,
        semester: details.semester,
        branch: details.branch,
        subject_code: details.subjectCode,
        subject_name: details.subjectName,
        qp_code: details.qpCode,
        regulation: details.regulation,
        common_to: details.commonTo,
        date: details.date,
      });
      onRecordChange(updated);
      setEditingHeader(false);
    } catch (cause) {
      setActionError(
        cause instanceof Error ? cause.message : "Could not save exam details.",
      );
    } finally {
      setBusy(false);
    }
  };

  const runTransition = async (action: "submit" | "approve" | "return") => {
    setBusy(true);
    setActionError(null);
    try {
      const updated = await transitionDemoPaper(
        record.id,
        role,
        action,
        workflowComment,
      );
      onRecordChange(updated);
      setWorkflowComment("");
    } catch (cause) {
      setActionError(
        cause instanceof Error ? cause.message : "Could not update the review.",
      );
    } finally {
      setBusy(false);
    }
  };

  const beginQuestionEdit = (questionId: string) => {
    const question = questions.find((item) => item.question_id === questionId);
    const answer = answerKey.get(questionId);
    if (!question || !answer) return;
    setEditingQuestionId(questionId);
    setQuestionDraft(question.question_text);
    setAnswerDraft(answer.answer);
    setCriteriaDraft(answer.criteria.map((item) => ({ ...item })));
    setActionError(null);
  };

  const saveQuestion = async () => {
    if (!editingQuestionId) return;
    setBusy(true);
    setActionError(null);
    try {
      const updated = await editDemoQuestion(record.id, editingQuestionId, {
        question_text: questionDraft,
        answer: answerDraft,
        criteria: criteriaDraft,
      });
      onRecordChange(updated);
      setEditingQuestionId(null);
    } catch (cause) {
      setActionError(
        cause instanceof Error ? cause.message : "Could not save the question.",
      );
    } finally {
      setBusy(false);
    }
  };

  const regenerateQuestion = async (
    questionId: string,
    mode: "guided" | "fresh",
  ) => {
    const comment = regenerationComments[questionId]?.trim();
    if (mode === "guided" && !comment) return;
    setBusy(true);
    setRegeneratingQuestionId(questionId);
    setRegenerationMode(mode);
    setActionError(null);
    try {
      const updated = await regenerateDemoQuestion(
        record.id,
        questionId,
        mode,
        comment,
      );
      onRecordChange(updated);
      setRegenerationComments((current) => {
        const next = { ...current };
        delete next[questionId];
        return next;
      });
      setOpenRegenerationQuestionId(null);
    } catch (cause) {
      setActionError(
        cause instanceof Error
          ? cause.message
          : "Could not regenerate the question.",
      );
    } finally {
      setBusy(false);
      setRegeneratingQuestionId(null);
      setRegenerationMode(null);
    }
  };

  const canEdit = role === "faculty" && record.status === "draft";
  const canSubmit = canEdit;
  const canHodReview = role === "hod" && record.status === "submitted_to_hod";
  const canCoeReview = role === "coe" && record.status === "submitted_to_coe";

  return (
    <section aria-labelledby="review-title" className="workspace-panel result-panel">
      <div className="demo-workflow-bar">
        <div>
          <span>Demo approval status</span>
          <strong>{STATUS_LABELS[record.status]}</strong>
        </div>
        {(canSubmit || canHodReview || canCoeReview) && (
          <div className="demo-workflow-actions">
            {(canHodReview || canCoeReview) && (
              <input
                aria-label="Review comment"
                disabled={busy}
                onChange={(event) => setWorkflowComment(event.target.value)}
                placeholder="Add a review comment"
                value={workflowComment}
              />
            )}
            {canSubmit && (
              <button
                className="primary-button"
                disabled={busy || !result.paper.publication_ready}
                onClick={() => void runTransition("submit")}
                type="button"
              >
                Submit to HOD
              </button>
            )}
            {(canHodReview || canCoeReview) && (
              <>
                <button
                  className="secondary-button"
                  disabled={busy || !workflowComment.trim()}
                  onClick={() => void runTransition("return")}
                  type="button"
                >
                  Return to faculty
                </button>
                <button
                  className="primary-button"
                  disabled={busy}
                  onClick={() => void runTransition("approve")}
                  type="button"
                >
                  {canHodReview ? "Approve for CoE" : "Final approval"}
                </button>
              </>
            )}
          </div>
        )}
      </div>
      {actionError && (
        <div className="request-error" role="alert">
          {actionError}
        </div>
      )}
      <div className="panel-heading result-heading">
        <div>
          <h2 id="review-title">Review the draft paper</h2>
          <p>
            {accepted} of {questions.length} questions passed automated review.
            Every paper needs your approval before it reaches the exam cell.
          </p>
        </div>
        <div className="result-actions">
          <a
            className="primary-button"
            download
            href={getApiUrl(result.pdf_download_url)}
          >
            {result.paper.publication_ready
              ? "Download paper"
              : "Download draft"}
          </a>
          <a
            className="secondary-button"
            download
            href={getApiUrl(result.scheme_download_url)}
          >
            Download scheme of evaluation
          </a>
          {result.docx_download_url && (
            <a
              className="secondary-button"
              download
              href={getApiUrl(result.docx_download_url)}
            >
              Download Word paper
            </a>
          )}
          <button className="secondary-button" onClick={onReset} type="button">
            Start a new paper
          </button>
        </div>
      </div>

      <div className="result-summary">
        <div>
          <span>Subject</span>
          <strong>{result.content_map.subject}</strong>
        </div>
        <div>
          <span>Pattern</span>
          <strong className="wraps">
            {pattern?.name ?? result.blueprint.pattern_id}
          </strong>
        </div>
        <div>
          <span>Maximum marks</span>
          <strong>{result.paper.total_marks}</strong>
        </div>
        <div>
          <span>Units covered</span>
          <strong>{unitsCovered}</strong>
        </div>
        <div>
          <span>Source pages</span>
          <strong>
            {result.manifest.selected_page_start}–
            {result.manifest.selected_page_end}
          </strong>
        </div>
      </div>

      {result.paper.publication_ready ? (
        <div className="notice notice-success">
          <CheckIcon />
          <div>
            <strong>All questions passed automated review</strong>
            <p>
              Grounding, marks, and cognitive level were checked question by
              question. Approve the paper before examination use.
            </p>
          </div>
        </div>
      ) : (
        <div className="notice notice-warning publication-gate">
          <AlertIcon />
          <div>
            <strong>
              {questions.length - accepted} question
              {questions.length - accepted === 1 ? "" : "s"} need attention
            </strong>
            <p>
              Each flagged question now shows why it needs review. Add a faculty
              instruction to regenerate it, or edit the question and scheme directly.
            </p>
          </div>
        </div>
      )}

      {(result.sets?.length ?? 0) > 1 && (
        <section aria-labelledby="sets-title" className="bloom-coverage">
          <div className="bloom-coverage-heading">
            <h3 id="sets-title">Sets for this exam</h3>
            <p>
              Interchangeable papers with identical marks, units and cognitive
              levels. The review below shows Set A.
            </p>
          </div>
          <ol className="set-list">
            {result.sets?.map((generated) => (
              <li key={generated.pdf_download_url}>
                <span className="set-tag">
                  Set {generated.set_label ?? "—"}
                </span>
                <a download href={getApiUrl(generated.pdf_download_url)}>
                  Paper
                </a>
                <a download href={getApiUrl(generated.scheme_download_url)}>
                  Scheme of evaluation
                </a>
              </li>
            ))}
          </ol>
          {(result.cross_set_warnings?.length ?? 0) > 0 && (
            <ul className="finding-list finding-list-blocking">
              {result.cross_set_warnings?.map((warning, index) => (
                <li key={index}>{warning}</li>
              ))}
            </ul>
          )}
        </section>
      )}

      {bloom != null && bloom.total > 0 && (
        <section aria-labelledby="bloom-title" className="bloom-coverage">
          <div className="bloom-coverage-heading">
            <h3 id="bloom-title">Cognitive level coverage</h3>
            <p>
              {bloom.deviations === 0
                ? "Every question was written at the level the blueprint requested."
                : `${bloom.deviations} of ${bloom.total} questions were written at a different level than requested, because the source could not support the demand.`}
            </p>
          </div>
          <ol className="bloom-scale">
            {BLOOM_ORDER.map((level) => {
              const requested = bloom.requested[level] ?? 0;
              const written = bloom.observed[level] ?? 0;
              if (!requested && !written) return null;
              const share = Math.round((written / bloom.total) * 100);
              return (
                <li className="bloom-step" key={level}>
                  <span className="bloom-step-name">{level}</span>
                  <span
                    aria-hidden="true"
                    className="bloom-step-bar"
                    style={{ ["--share" as string]: `${share}%` }}
                  />
                  <span className="bloom-step-count">
                    {written}
                    {requested !== written && <em> from {requested}</em>}
                  </span>
                </li>
              );
            })}
          </ol>
        </section>
      )}

      {result.paper.course_outcome_coverage != null &&
        Object.keys(result.paper.course_outcome_coverage.marks_by_outcome).length >
          0 && (
          <section aria-labelledby="outcome-title" className="bloom-coverage">
            <div className="bloom-coverage-heading">
              <h3 id="outcome-title">Course outcome coverage</h3>
              <p>
                Marks carried by each approved outcome. Accreditation expects
                every outcome to be assessed somewhere in the paper.
              </p>
            </div>
            <ol className="outcome-coverage">
              {Object.entries(
                result.paper.course_outcome_coverage.marks_by_outcome,
              ).map(([outcome, marks], index) => (
                <li key={outcome}>
                  <span className="outcome-tag">CO{index + 1}</span>
                  <span className="outcome-text">{outcome}</span>
                  <span className="outcome-marks">{marks}</span>
                </li>
              ))}
              {result.paper.course_outcome_coverage.unmapped_marks > 0 && (
                <li className="outcome-unmapped">
                  <span className="outcome-tag">—</span>
                  <span className="outcome-text">Not mapped to an outcome</span>
                  <span className="outcome-marks">
                    {result.paper.course_outcome_coverage.unmapped_marks}
                  </span>
                </li>
              )}
            </ol>
          </section>
        )}

      <div className="table-heading table-heading-row">
        <div>
          <h3>The paper</h3>
          <p>
            As it will print. Fill the exam details once and they are remembered
            for the next paper.
          </p>
        </div>
        <div className="result-actions">
          {canEdit && (
            <button
              className="secondary-button"
              disabled={busy}
              onClick={() =>
                editingHeader ? void saveHeader() : setEditingHeader(true)
              }
              type="button"
            >
              {editingHeader ? "Save exam details" : "Edit exam details"}
            </button>
          )}
          {answerKey.size > 0 && (
            <button
              className="secondary-button"
              onClick={() =>
                setOpenAnswers(allOpen ? new Set() : new Set(answerKey.keys()))
              }
              type="button"
            >
              {allOpen ? "Hide answers" : "Show answers"}
            </button>
          )}
        </div>
      </div>

      {editingHeader && (
        <div className="detail-grid">
          {DETAIL_FIELDS.map(([field, label]) => (
            <label key={field}>
              <span>{label}</span>
              <input
                onChange={(event) =>
                  setDetails((current) => ({
                    ...current,
                    [field]: event.target.value,
                  }))
                }
                type="text"
                value={details[field]}
              />
            </label>
          ))}
        </div>
      )}

      {canEdit && (
        <section className="demo-question-editing">
          <div className="bloom-coverage-heading">
            <h3>Faculty question editor</h3>
            <p>
              Editing a question also requires its model answer and mark-wise
              criteria, so the scheme cannot become stale.
            </p>
          </div>
          {editingQuestionId ? (
            <div className="demo-question-form">
              <label>
                <span>Question</span>
                <textarea
                  onChange={(event) => setQuestionDraft(event.target.value)}
                  rows={6}
                  value={questionDraft}
                />
              </label>
              <label>
                <span>Model answer</span>
                <textarea
                  onChange={(event) => setAnswerDraft(event.target.value)}
                  rows={6}
                  value={answerDraft}
                />
              </label>
              <div className="demo-criteria-editor">
                <strong>Marking criteria</strong>
                {criteriaDraft.map((criterion, index) => (
                  <div key={index}>
                    <input
                      aria-label={`Criterion ${index + 1}`}
                      onChange={(event) =>
                        setCriteriaDraft((current) =>
                          current.map((item, position) =>
                            position === index
                              ? { ...item, criterion: event.target.value }
                              : item,
                          ),
                        )
                      }
                      value={criterion.criterion}
                    />
                    <input
                      aria-label={`Criterion ${index + 1} marks`}
                      min={1}
                      onChange={(event) =>
                        setCriteriaDraft((current) =>
                          current.map((item, position) =>
                            position === index
                              ? { ...item, marks: Number(event.target.value) }
                              : item,
                          ),
                        )
                      }
                      type="number"
                      value={criterion.marks}
                    />
                  </div>
                ))}
              </div>
              <div className="result-actions">
                <button
                  className="secondary-button"
                  disabled={busy}
                  onClick={() => setEditingQuestionId(null)}
                  type="button"
                >
                  Cancel
                </button>
                <button
                  className="primary-button"
                  disabled={busy || !questionDraft.trim() || !answerDraft.trim()}
                  onClick={() => void saveQuestion()}
                  type="button"
                >
                  Save question and scheme
                </button>
              </div>
            </div>
          ) : (
            <ol className="demo-question-list">
              {questions.map((question) => (
                <li
                  className={
                    question.accepted && question.findings.length === 0
                      ? undefined
                      : "question-needs-review"
                  }
                  key={question.question_id}
                >
                  <span>{question.question_number}</span>
                  <p>{question.question_text}</p>
                  {question.faculty_modified && <em>Faculty modified</em>}
                  <button
                    className="table-action"
                    onClick={() => beginQuestionEdit(question.question_id)}
                    type="button"
                  >
                    Edit
                  </button>
                  {question.accepted && question.findings.length === 0 && (
                    <button
                      className="table-action"
                      disabled={busy}
                      onClick={() =>
                        setOpenRegenerationQuestionId((current) =>
                          current === question.question_id
                            ? null
                            : question.question_id,
                        )
                      }
                      type="button"
                    >
                      {openRegenerationQuestionId === question.question_id
                        ? "Close"
                        : "Regenerate"}
                    </button>
                  )}
                  {(!question.accepted ||
                    question.findings.length > 0 ||
                    openRegenerationQuestionId === question.question_id) && (
                    <div className="question-review-details">
                      {(!question.accepted || question.findings.length > 0) && (
                        <>
                          <div className="question-review-heading">
                            <strong>Why this question was marked for review</strong>
                            {question.quality_score != null && (
                              <span>Quality score {question.quality_score}/100</span>
                            )}
                          </div>
                          {question.findings.length > 0 ? (
                            <ul className="question-review-findings">
                              {question.findings.map((finding, index) => (
                                <li key={`${finding.code}-${index}`}>
                                  <strong>{findingLabel(finding.code)}</strong>
                                  <p>{finding.message}</p>
                                </li>
                              ))}
                            </ul>
                          ) : (
                            <p>
                              Automated review did not accept this question. Regenerate
                              it or use the editor to approve a faculty-written replacement.
                            </p>
                          )}
                        </>
                      )}
                      <div className="question-regeneration-heading">
                        <strong>Regenerate question</strong>
                        <p>
                          Give a suggestion to refine this question, or generate a
                          completely different question for the same blueprint slot.
                        </p>
                      </div>
                      <label className="question-regeneration-comment">
                        <span>Faculty suggestion</span>
                        <textarea
                          disabled={busy}
                          onChange={(event) =>
                            setRegenerationComments((current) => ({
                              ...current,
                              [question.question_id]: event.target.value,
                            }))
                          }
                          placeholder="Example: Make it one direct 2-mark question and avoid repeating Question 8."
                          rows={3}
                          value={regenerationComments[question.question_id] ?? ""}
                        />
                      </label>
                      <div className="question-regeneration-actions">
                        <button
                          className="secondary-button"
                          disabled={
                            busy ||
                            !(regenerationComments[question.question_id] ?? "").trim()
                          }
                          onClick={() =>
                            void regenerateQuestion(question.question_id, "guided")
                          }
                          type="button"
                        >
                          {regeneratingQuestionId === question.question_id &&
                          regenerationMode === "guided"
                            ? "Applying suggestion…"
                            : "Regenerate with suggestion"}
                        </button>
                        <button
                          className="secondary-button question-fresh-button"
                          disabled={busy}
                          onClick={() =>
                            void regenerateQuestion(question.question_id, "fresh")
                          }
                          type="button"
                        >
                          {regeneratingQuestionId === question.question_id &&
                          regenerationMode === "fresh"
                            ? "Generating a fresh question…"
                            : "Generate a fresh question"}
                        </button>
                      </div>
                    </div>
                  )}
                </li>
              ))}
            </ol>
          )}
        </section>
      )}

      <PaperSheet details={details} pattern={pattern} result={result} />

      {openAnswers.size > 0 && (
        <section className="answer-sheet">
          <h4>Scheme of evaluation</h4>
          {(result.answer_key ?? []).map((entry) => (
            <div className="answer-sheet-entry" key={entry.question_id}>
              <strong>
                {entry.question_number}. [{entry.marks} marks]
              </strong>
              <ul className="answer-criteria">
                {entry.criteria.map((item, index) => (
                  <li key={index}>
                    <span>{item.criterion}</span>
                    <span className="answer-criterion-marks">{item.marks}</span>
                  </li>
                ))}
              </ul>
              <p className="answer-text">{entry.answer}</p>
            </div>
          ))}
        </section>
      )}

      {eligibleVisuals > 0 && (
        <p className="paper-footnote">
          {eligibleVisuals} figure{eligibleVisuals === 1 ? "" : "s"} from the
          source were verified as usable for questions.
        </p>
      )}

      <section className="demo-activity">
        <h3>Activity</h3>
        <ol>
          {record.activities.map((activity, index) => (
            <li key={`${activity.created_at}-${index}`}>
              <strong>{activity.actor_role.toUpperCase()}</strong>
              <span>{activity.action.replace(/_/g, " ")}</span>
              {activity.comment && <p>{activity.comment}</p>}
              <time dateTime={activity.created_at}>
                {new Intl.DateTimeFormat(undefined, {
                  dateStyle: "medium",
                  timeStyle: "short",
                }).format(new Date(activity.created_at))}
              </time>
            </li>
          ))}
        </ol>
      </section>
    </section>
  );
}
