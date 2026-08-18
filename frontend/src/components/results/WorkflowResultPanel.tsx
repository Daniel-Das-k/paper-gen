import type { FullWorkflowResponse } from "../../types/api";
import { getApiUrl, getVisualAssetUrl } from "../../services/api";
import { AlertIcon, CheckIcon } from "../icons/Icons";

interface WorkflowResultPanelProps {
  result: FullWorkflowResponse;
  onReset: () => void;
}

export function WorkflowResultPanel({
  result,
  onReset,
}: WorkflowResultPanelProps) {
  const eligibleVisuals = result.manifest.visual_assets.filter(
    (asset) => asset.question_eligible,
  ).length;
  const totalMarks = result.blueprint.slots.reduce(
    (total, slot) => total + slot.marks,
    0,
  );
  const acceptedQuestions = result.paper.questions.filter(
    (question) => question.accepted,
  ).length;

  return (
    <section aria-labelledby="review-title" className="workspace-panel result-panel">
      <div className="panel-heading result-heading">
        <div>
          <h2 id="review-title">
            Draft paper review
          </h2>
          <p>
            {acceptedQuestions} of {result.paper.questions.length} questions
            passed automated review.
          </p>
        </div>
        <div className="result-actions">
          <a
            className="primary-button"
            download
            href={getApiUrl(result.pdf_download_url)}
          >
            {result.paper.publication_ready
              ? "Download final PDF"
              : "Download review draft"}
          </a>
          <button
            className="secondary-button"
            onClick={onReset}
            type="button"
          >
            New upload
          </button>
        </div>
      </div>

      <div className="result-summary">
        <div>
          <span>Subject</span>
          <strong>{result.content_map.subject}</strong>
        </div>
        <div>
          <span>Pages</span>
          <strong>
            {result.manifest.selected_page_start}–
            {result.manifest.selected_page_end} of{" "}
            {result.manifest.source_total_pages}
          </strong>
        </div>
        <div>
          <span>Topics</span>
          <strong>{result.content_map.topics.length}</strong>
        </div>
        <div>
          <span>Verified figures</span>
          <strong>{eligibleVisuals}</strong>
        </div>
        <div>
          <span>Paper</span>
          <strong>{totalMarks} marks</strong>
        </div>
      </div>

      {(result.manifest.quality.warnings.length > 0 ||
        result.blueprint.warnings.length > 0) && (
        <div className="notice notice-warning">
          <AlertIcon />
          <div>
            <strong>Review needed</strong>
            {[...result.manifest.quality.warnings, ...result.blueprint.warnings].map(
              (warning) => (
                <p key={warning}>{warning}</p>
              ),
            )}
          </div>
        </div>
      )}

      {acceptedQuestions === result.paper.questions.length && (
        <div className="notice notice-success">
          <CheckIcon />
          <div>
            <strong>Automated checks passed</strong>
            <p>The paper still requires faculty approval before examination use.</p>
          </div>
        </div>
      )}
      {!result.paper.publication_ready && (
        <div className="notice notice-warning publication-gate">
          <AlertIcon />
          <div>
            <strong>Publication blocked</strong>
            <p>
              {result.paper.questions.length - acceptedQuestions} question
              {result.paper.questions.length - acceptedQuestions === 1 ? "" : "s"}{" "}
              must be replaced or approved by faculty before this paper can be used.
            </p>
          </div>
        </div>
      )}

      <div className="table-heading">
        <div>
          <h3>Generated questions</h3>
          <p>
            Rejected questions remain visible with their review findings.
          </p>
        </div>
      </div>

      <div className="table-scroll">
        <table>
            <thead>
              <tr>
                <th>Question</th>
                <th>Marks</th>
                <th>Review</th>
              </tr>
            </thead>
            <tbody>
              {result.paper.questions.map((question) => (
                <tr key={question.question_id}>
                  <td className="generated-question-cell">
                    <span className="question-number">
                      Q{question.question_number}
                    </span>
                    {question.question_text}
                    {question.visual_asset_id && (
                      <figure className="question-figure">
                        <img
                          alt={`Figure for question ${question.question_number}`}
                          loading="lazy"
                          src={getVisualAssetUrl(
                            result.manifest.document_id,
                            question.visual_asset_id,
                          )}
                        />
                        <figcaption>
                          Figure referenced in question {question.question_number}
                        </figcaption>
                      </figure>
                    )}
                  </td>
                  <td>{question.marks}</td>
                  <td>
                    <span
                      className={
                        question.accepted && question.findings.length === 0
                          ? "status-label status-approved"
                          : "status-label status-review"
                      }
                    >
                      {question.accepted
                        ? question.findings.length
                          ? "Passed with notes"
                          : "Passed"
                        : "Review"}
                    </span>
                    {question.quality_score != null && (
                      <span className="quality-score">
                        Quality {question.quality_score}/100
                      </span>
                    )}
                    {question.findings.length > 0 && (
                      <ul className="finding-list">
                        {question.findings.map((finding, findingIndex) => (
                          <li key={`${finding.code}-${findingIndex}`}>
                            {finding.severity === "warning" ? "Note: " : ""}
                            {finding.message}
                          </li>
                        ))}
                      </ul>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
        </table>
      </div>
    </section>
  );
}
