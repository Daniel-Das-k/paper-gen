import { useEffect, useRef, useState, type DragEvent } from "react";

import { FileIcon, UploadIcon } from "../icons/Icons";

const GENERATION_STAGES = [
  { startsAt: 0, label: "Inspecting the PDF and extracting pages" },
  { startsAt: 18, label: "Analyzing content, topics and figures" },
  { startsAt: 65, label: "Generating all five sections" },
  { startsAt: 170, label: "Independent question-by-question review" },
  { startsAt: 260, label: "Repairing flagged questions and assembling the paper" },
];

function formatElapsed(totalSeconds: number) {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function GenerationProgress({ elapsed }: { elapsed: number }) {
  const activeIndex = GENERATION_STAGES.reduce(
    (current, stage, index) => (elapsed >= stage.startsAt ? index : current),
    0,
  );
  return (
    <div aria-live="polite" className="generation-progress" role="status">
      <div className="generation-progress-heading">
        <strong>Generating your paper</strong>
        <span className="generation-elapsed">{formatElapsed(elapsed)}</span>
      </div>
      <p className="generation-progress-note">
        Every question is generated, independently reviewed and repaired before
        it reaches you — this typically takes 4–7 minutes.
      </p>
      <div className="progress-track">
        <div className="progress-fill" />
      </div>
      <ul className="stage-list">
        {GENERATION_STAGES.map((stage, index) => (
          <li
            className={`stage-item${
              index === activeIndex
                ? " stage-item-active"
                : index < activeIndex
                  ? " stage-item-done"
                  : ""
            }`}
            key={stage.label}
          >
            <span className="stage-dot" />
            {stage.label}
          </li>
        ))}
      </ul>
    </div>
  );
}

interface UploadPanelProps {
  file: File | null;
  loading: boolean;
  startPage: string;
  endPage: string;
  onFileChange: (file: File | null) => void;
  onStartPageChange: (page: string) => void;
  onEndPageChange: (page: string) => void;
  onSubmit: () => void;
}

const MAX_FILE_SIZE = 50 * 1024 * 1024;

function formatFileSize(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.ceil(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function UploadPanel({
  file,
  loading,
  startPage,
  endPage,
  onFileChange,
  onStartPageChange,
  onEndPageChange,
  onSubmit,
}: UploadPanelProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dragActive, setDragActive] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!loading) {
      setElapsed(0);
      return;
    }
    const timer = window.setInterval(
      () => setElapsed((seconds) => seconds + 1),
      1000,
    );
    return () => window.clearInterval(timer);
  }, [loading]);
  const hasStartPage = startPage.trim() !== "";
  const hasEndPage = endPage.trim() !== "";
  const numericStart = hasStartPage ? Number(startPage) : undefined;
  const numericEnd = hasEndPage ? Number(endPage) : undefined;
  const pageRangeValid =
    (numericStart === undefined ||
      (Number.isInteger(numericStart) && numericStart >= 1)) &&
    (numericEnd === undefined ||
      (Number.isInteger(numericEnd) && numericEnd >= 1)) &&
    (numericStart === undefined ||
      numericEnd === undefined ||
      numericEnd >= numericStart);

  const acceptFile = (nextFile?: File) => {
    if (!nextFile || loading) return;
    if (nextFile.type !== "application/pdf" && !nextFile.name.endsWith(".pdf")) {
      setFileError("Choose a PDF document.");
      return;
    }
    if (nextFile.size > MAX_FILE_SIZE) {
      setFileError("The PDF must be 50 MB or smaller.");
      return;
    }
    setFileError(null);
    onFileChange(nextFile);
  };

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragActive(false);
    acceptFile(event.dataTransfer.files[0]);
  };

  return (
    <section aria-labelledby="upload-title" className="workspace-panel upload-panel">
      <div className="panel-heading">
        <div>
          <h2 id="upload-title">Source material</h2>
          <p>Upload the notes used to ground every generated question.</p>
        </div>
        <span className="step-count">1 of 2</span>
      </div>

      <div
        className={`drop-zone${dragActive ? " drop-zone-active" : ""}`}
        onDragEnter={(event) => {
          event.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        onDragOver={(event) => event.preventDefault()}
        onDrop={onDrop}
      >
        <input
          accept=".pdf,application/pdf"
          aria-label="Upload notes PDF"
          className="visually-hidden"
          onChange={(event) => acceptFile(event.target.files?.[0])}
          ref={fileInputRef}
          type="file"
        />
        <UploadIcon className="drop-zone-icon" />
        <strong>Drop your notes here</strong>
        <span>PDF only, up to 50 MB</span>
        <button
          className="secondary-button"
          onClick={() => fileInputRef.current?.click()}
          type="button"
        >
          Choose PDF
        </button>
      </div>

      {fileError && <p className="field-error">{fileError}</p>}

      {file && (
        <div className="selected-file">
          <FileIcon />
          <div className="selected-file-copy">
            <strong>{file.name}</strong>
            <span>{formatFileSize(file.size)}</span>
          </div>
          <button
            aria-label={`Remove ${file.name}`}
            className="text-button"
            disabled={loading}
            onClick={() => onFileChange(null)}
            type="button"
          >
            Remove
          </button>
        </div>
      )}

      <div className="setup-fields" id="paper-pattern">
        <div className="field-group page-range-field">
          <label>Textbook page range</label>
          <div className="page-range-inputs">
            <div>
              <span>Start page</span>
              <input
                disabled={loading}
                min="1"
                onChange={(event) => onStartPageChange(event.target.value)}
                placeholder="Optional"
                type="number"
                value={startPage}
              />
            </div>
            <span className="page-range-separator">to</span>
            <div>
              <span>End page</span>
              <input
                disabled={loading}
                min={startPage || "1"}
                onChange={(event) => onEndPageChange(event.target.value)}
                placeholder="Optional"
                type="number"
                value={endPage}
              />
            </div>
          </div>
          <p>
            Leave both fields blank to use the complete PDF. Otherwise, only the
            selected original pages are sent to the AI.
          </p>
          {(startPage || endPage) && !pageRangeValid && (
            <p className="field-error">
              Enter a valid range where the end page is not before the start page.
            </p>
          )}
        </div>

        <div className="field-group">
          <label htmlFor="paper-pattern-select">Paper pattern</label>
          <select disabled id="paper-pattern-select" value="sample-paper-80">
            <option value="sample-paper-80">
              Fixed five-section pattern · 80 marks · 3 hours
            </option>
          </select>
          <p>
            18 MCQ, 2 assertion–reason, 5 VSA, 6 SA, 4 LA and 3 case studies.
          </p>
        </div>
      </div>

      <button
        className="primary-button submit-button"
        disabled={!file || loading || !pageRangeValid}
        onClick={onSubmit}
        type="button"
      >
        {loading ? "Generating paper…" : "Generate paper"}
      </button>

      {loading && <GenerationProgress elapsed={elapsed} />}
    </section>
  );
}
