import { useRef, useState, type DragEvent } from "react";

import type { UnitUpload } from "../../types/api";

interface UnitUploadsProps {
  uploads: UnitUpload[];
  loading: boolean;
  onChange: (uploads: UnitUpload[]) => void;
}

function formatSize(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.ceil(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function isPdf(file: File): boolean {
  return (
    file.type === "application/pdf" ||
    file.name.toLowerCase().endsWith(".pdf")
  );
}

/**
 * One upload per syllabus unit, presented as a drop zone: click anywhere on
 * the row or drag a PDF onto it. A unit covered in full needs no page range;
 * a unit split between two tests needs one, which is why every row offers it.
 */
export function UnitUploads({ uploads, loading, onChange }: UnitUploadsProps) {
  const inputs = useRef<Array<HTMLInputElement | null>>([]);
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [dropError, setDropError] = useState<string | null>(null);

  const update = (index: number, patch: Partial<UnitUpload>) =>
    onChange(
      uploads.map((upload, position) =>
        position === index ? { ...upload, ...patch } : upload,
      ),
    );

  const acceptFile = (index: number, file: File | undefined | null) => {
    if (!file) return;
    if (!isPdf(file)) {
      setDropError(
        `"${file.name}" is not a PDF. Unit material must be a PDF file.`,
      );
      return;
    }
    setDropError(null);
    update(index, { file });
  };

  const handleDrop = (index: number) => (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragIndex(null);
    if (loading) return;
    acceptFile(index, event.dataTransfer.files?.[0]);
  };

  return (
    <div className="unit-drop-list">
      {dropError && (
        <p className="field-error" role="alert">
          {dropError}
        </p>
      )}
      {uploads.map((upload, index) => (
        <div
          className={[
            "unit-drop",
            upload.file ? "unit-drop-filled" : "",
            dragIndex === index ? "unit-drop-active" : "",
          ]
            .filter(Boolean)
            .join(" ")}
          key={upload.unit}
          onDragLeave={(event) => {
            if (!event.currentTarget.contains(event.relatedTarget as Node)) {
              setDragIndex(null);
            }
          }}
          onDragOver={(event) => {
            event.preventDefault();
            if (!loading) setDragIndex(index);
          }}
          onDrop={handleDrop(index)}
        >
          <input
            accept="application/pdf"
            className="visually-hidden"
            onChange={(event) => {
              acceptFile(index, event.target.files?.[0]);
              event.target.value = "";
            }}
            ref={(element) => {
              inputs.current[index] = element;
            }}
            type="file"
          />

          <span className="unit-drop-tag">Unit {upload.unit}</span>

          {upload.file ? (
            <div className="unit-drop-file">
              <span aria-hidden="true" className="unit-drop-fileicon">
                <svg fill="none" height="14" viewBox="0 0 16 16" width="14">
                  <path
                    d="M4 1.5h5.5L13 5v9.5H4z"
                    stroke="currentColor"
                    strokeLinejoin="round"
                    strokeWidth="1.4"
                  />
                  <path
                    d="M9.5 1.5V5H13"
                    stroke="currentColor"
                    strokeLinejoin="round"
                    strokeWidth="1.4"
                  />
                </svg>
              </span>
              <span className="unit-drop-filename" title={upload.file.name}>
                {upload.file.name}
              </span>
              <span className="unit-drop-filesize">
                {formatSize(upload.file.size)}
              </span>
            </div>
          ) : (
            <button
              className="unit-drop-prompt"
              disabled={loading}
              onClick={() => inputs.current[index]?.click()}
              type="button"
            >
              <span aria-hidden="true" className="unit-drop-plus">
                <svg fill="none" height="12" viewBox="0 0 12 12" width="12">
                  <path
                    d="M6 1.5v9M1.5 6h9"
                    stroke="currentColor"
                    strokeLinecap="round"
                    strokeWidth="1.6"
                  />
                </svg>
              </span>
              Choose a PDF or drag it here
            </button>
          )}

          <div className="unit-drop-range">
            <span className="unit-drop-range-label">Pages</span>
            <input
              aria-label={`Unit ${upload.unit} start page`}
              disabled={loading}
              min={1}
              onChange={(event) => update(index, { startPage: event.target.value })}
              placeholder="From"
              type="number"
              value={upload.startPage}
            />
            <span aria-hidden="true">{"\u2013"}</span>
            <input
              aria-label={`Unit ${upload.unit} end page`}
              disabled={loading}
              min={1}
              onChange={(event) => update(index, { endPage: event.target.value })}
              placeholder="To"
              type="number"
              value={upload.endPage}
            />
          </div>

          {upload.file && (
            <div className="unit-drop-actions">
              <button
                className="text-button"
                disabled={loading}
                onClick={() => inputs.current[index]?.click()}
                type="button"
              >
                Replace
              </button>
              <button
                className="text-button unit-drop-remove"
                disabled={loading}
                onClick={() => update(index, { file: null })}
                type="button"
              >
                Remove
              </button>
            </div>
          )}
        </div>
      ))}
      <p className="unit-drop-note">
        Leave the page range blank for a full unit. For a unit split between two
        tests, enter only the pages this exam covers.
      </p>
    </div>
  );
}
