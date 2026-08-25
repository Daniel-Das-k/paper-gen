import { useRef } from "react";

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

/**
 * One upload per syllabus unit. A unit covered in full needs no page range; a
 * unit split between two tests needs one, which is why every row offers it.
 */
export function UnitUploads({ uploads, loading, onChange }: UnitUploadsProps) {
  const inputs = useRef<Array<HTMLInputElement | null>>([]);

  const update = (index: number, patch: Partial<UnitUpload>) =>
    onChange(
      uploads.map((upload, position) =>
        position === index ? { ...upload, ...patch } : upload,
      ),
    );

  return (
    <div className="field-group unit-uploads">
      <label>Unit material</label>
      <p>
        These are the units required by the selected exam. Upload one PDF for
        every unit. Leave the page range blank for a full unit; for a split
        unit, enter only the pages covered by this test.
      </p>

      <ol className="unit-list">
        {uploads.map((upload, index) => (
          <li key={index}>
            <span className="unit-tag">Unit {upload.unit}</span>

            <div className="unit-file">
              <input
                accept="application/pdf"
                className="visually-hidden"
                onChange={(event) =>
                  update(index, { file: event.target.files?.[0] ?? null })
                }
                ref={(element) => {
                  inputs.current[index] = element;
                }}
                type="file"
              />
              <button
                className="secondary-button"
                disabled={loading}
                onClick={() => inputs.current[index]?.click()}
                type="button"
              >
                {upload.file ? "Replace PDF" : "Choose PDF"}
              </button>
              {upload.file && (
                <span className="unit-file-name">
                  {upload.file.name} · {formatSize(upload.file.size)}
                </span>
              )}
            </div>

            <div className="unit-range">
              <input
                aria-label={`Unit ${upload.unit} start page`}
                disabled={loading}
                min={1}
                onChange={(event) =>
                  update(index, { startPage: event.target.value })
                }
                placeholder="From"
                type="number"
                value={upload.startPage}
              />
              <span>–</span>
              <input
                aria-label={`Unit ${upload.unit} end page`}
                disabled={loading}
                min={1}
                onChange={(event) =>
                  update(index, { endPage: event.target.value })
                }
                placeholder="To"
                type="number"
                value={upload.endPage}
              />
            </div>

          </li>
        ))}
      </ol>
    </div>
  );
}
