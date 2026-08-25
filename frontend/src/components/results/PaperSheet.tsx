import type {
  BloomLevel,
  FullWorkflowResponse,
  PaperPattern,
  PaperPatternSection,
} from "../../types/api";
import { getVisualAssetUrl } from "../../services/api";

/**
 * Rajalakshmi prints the cognitive level in three tiers rather than as a Bloom
 * word: A for lower order, B for the middle, C for higher order. All six tags
 * appear across the reference papers — A1/A2 and B1/B2 throughout, C1 and C2 on
 * the Part C question. Matching the notation is what makes a generated paper
 * read like one the exam cell issued.
 */
const REC_LEVEL: Record<BloomLevel, string> = {
  remember: "A1",
  understand: "A2",
  apply: "B1",
  analyze: "B2",
  evaluate: "C1",
  create: "C2",
};

export interface ExamDetails {
  college: string;
  affiliation: string;
  examTitle: string;
  year: string;
  semester: string;
  branch: string;
  subjectCode: string;
  subjectName: string;
  qpCode: string;
  regulation: string;
  commonTo: string;
  date: string;
}

interface PaperSheetProps {
  result: FullWorkflowResponse;
  pattern: PaperPattern | null;
  details: ExamDetails;
}

type PaperQuestion = FullWorkflowResponse["paper"]["questions"][number];

function splitAlternatives(text: string): string[] {
  return text
    .split(/\n\s*OR\s*\n/)
    .map((part) => part.trim())
    .filter(Boolean);
}

function answerRule(section: PaperPatternSection | undefined): string {
  if (!section) return "Answer ALL questions";
  return section.choices_per_question > 1 && section.answers_required === 1
    ? "Answer ALL questions, choosing either alternative"
    : "Answer ALL questions";
}

export function PaperSheet({ result, pattern, details }: PaperSheetProps) {
  const questions = result.paper.questions;
  const fallbackDuration = result.blueprint.pattern_id.startsWith("cat-")
    ? 120
    : 180;
  const durationMinutes = pattern?.duration_minutes ?? fallbackDuration;
  const hours = Math.round(durationMinutes / 60);
  const duration =
    durationMinutes >= 180
      ? `${hours} Hours`
      : `${durationMinutes} Minutes`;

  const bySection = new Map<string, PaperQuestion[]>();
  for (const question of questions) {
    if (!bySection.has(question.section_id)) {
      bySection.set(question.section_id, []);
    }
    bySection.get(question.section_id)!.push(question);
  }
  const slotOrder = new Map(
    result.blueprint.slots.map((slot, index) => [slot.slot_id, index]),
  );
  for (const items of bySection.values()) {
    items.sort(
      (left, right) =>
        (slotOrder.get(left.slot_id) ?? Number.MAX_SAFE_INTEGER) -
        (slotOrder.get(right.slot_id) ?? Number.MAX_SAFE_INTEGER),
    );
  }
  const sections = new Map(
    (pattern?.sections ?? []).map((section) => [section.section_id, section]),
  );
  const order = Array.from(
    new Set([
      ...(pattern?.sections.map((section) => section.section_id) ?? []),
      ...result.blueprint.slots.map((slot) => slot.section_id),
      ...questions.map((question) => question.section_id),
    ]),
  ).filter((sectionId) => (bySection.get(sectionId)?.length ?? 0) > 0);

  return (
    <article className="sheet">
      <div className="sheet-regno">
        <span>Reg. No.</span>
        <div className="sheet-regno-boxes">
          {Array.from({ length: 12 }, (_, index) => (
            <i key={index} />
          ))}
        </div>
      </div>

      <header className="sheet-masthead">
        <div className="sheet-college">
          <strong>{details.college}</strong>
          <span>{details.affiliation}</span>
        </div>
        <dl className="sheet-facts">
          <div className="sheet-facts-title">{details.examTitle}</div>
          {[
            ["Year", details.year],
            ["Semester", details.semester],
            ["Branch", details.branch],
            ["Sub. Code", details.subjectCode],
            ["Subject", details.subjectName || result.content_map.subject],
            ["QP Code", details.qpCode],
          ].map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>: {value || "—"}</dd>
            </div>
          ))}
        </dl>
      </header>

      <p className="sheet-regulation">[{details.regulation}]</p>
      <p className="sheet-line">
        <span>Date: {details.date || "—"}</span>
        <span>Time: {duration}</span>
        <span>Max. Marks: {result.paper.total_marks}</span>
      </p>
      {details.commonTo && (
        <p className="sheet-common">(Common to {details.commonTo})</p>
      )}
      {result.paper.set_label && (
        <p className="sheet-common">SET {result.paper.set_label}</p>
      )}

      {order.map((sectionId) => {
        const section = sections.get(sectionId);
        const items = bySection.get(sectionId) ?? [];
        const marks = items.reduce((total, item) => total + item.marks, 0);
        return (
          <section key={sectionId}>
            <p className="sheet-instruction">{answerRule(section)}</p>
            <h4 className="sheet-part">
              {/* Patterns carry the exact wording the college prints. */}
              {section?.title ?? `${sectionId.replace(/_/g, " ").toUpperCase()} — ${marks} Marks`}
            </h4>

            <ol className="sheet-questions">
              {items.map((question) => {
                const alternatives = splitAlternatives(question.question_text);
                // Derived from the unit on the backend, so it is always present.
                const co = question.course_outcome_code;
                const level =
                  REC_LEVEL[
                    (question.observed_bloom_level ??
                      question.bloom_level) as BloomLevel
                  ];
                return (
                  <li
                    className={
                      question.accepted ? "sheet-q" : "sheet-q sheet-q-flagged"
                    }
                    key={question.question_id}
                  >
                    <span className="sheet-q-number">
                      {question.question_number}
                    </span>
                    <div className="sheet-q-body">
                      {alternatives.map((alternative, index) => (
                        <div key={index}>
                          {index > 0 && <p className="sheet-or">[OR]</p>}
                          <p className="sheet-q-text">
                            {alternatives.length > 1 && (
                              <span className="sheet-q-alt">
                                {index === 0 ? "a." : "b."}
                              </span>
                            )}
                            {alternative}
                          </p>
                        </div>
                      ))}
                      {question.visual_asset_id && (
                        <img
                          alt={`Figure for question ${question.question_number}`}
                          className="sheet-figure"
                          loading="lazy"
                          src={getVisualAssetUrl(
                            result.manifest.document_id,
                            question.visual_asset_id,
                          )}
                        />
                      )}
                    </div>
                    <span className="sheet-q-tags">
                      <i>[{co ?? "CO—"}]</i>
                      <i>[{level}]</i>
                    </span>
                  </li>
                );
              })}
            </ol>
          </section>
        );
      })}
    </article>
  );
}
