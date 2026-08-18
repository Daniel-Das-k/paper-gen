from __future__ import annotations

import base64
import html
import json
import mimetypes
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import fitz

from .models import (
    ContentMap,
    DocumentManifest,
    GeneratedQuestionPaper,
    PaperBlueprint,
)


@dataclass(frozen=True)
class SavedPaperPaths:
    json_path: Path
    markdown_path: Path
    pdf_path: Path


def default_test_paper_directory() -> Path:
    configured = os.getenv("TEST_PAPER_OUTPUT_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    repository_root = Path(__file__).resolve().parents[3]
    return repository_root / "test_papers"


def default_pdf_output_directory() -> Path:
    configured = os.getenv("PDF_OUTPUT_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    repository_root = Path(__file__).resolve().parents[3]
    return repository_root / "outputs"


def save_generated_paper(
    *,
    manifest: DocumentManifest,
    content_map: ContentMap,
    blueprint: PaperBlueprint,
    paper: GeneratedQuestionPaper,
    output_directory: str | Path | None = None,
    pdf_output_directory: str | Path | None = None,
) -> SavedPaperPaths:
    """Atomically save question-only generation data and the readable paper."""
    root = (
        Path(output_directory).expanduser().resolve()
        if output_directory is not None
        else default_test_paper_directory()
    )
    root.mkdir(parents=True, exist_ok=True)
    pdf_root = (
        Path(pdf_output_directory).expanduser().resolve()
        if pdf_output_directory is not None
        else default_pdf_output_directory()
    )
    pdf_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    subject = re.sub(r"[^a-z0-9]+", "-", paper.subject.lower()).strip("-")
    filename_base = f"{subject or 'subject'}-{manifest.document_id}-{timestamp}"

    payload = {
        "saved_at": datetime.now(UTC).isoformat(),
        "manifest": manifest.model_dump(mode="json"),
        "content_map": content_map.model_dump(mode="json"),
        "blueprint": blueprint.model_dump(mode="json"),
        "paper": paper.model_dump(mode="json"),
    }
    json_path = root / f"{filename_base}.json"
    markdown_path = root / f"{filename_base}.md"
    pdf_path = pdf_root / f"{filename_base}.pdf"
    _atomic_write(
        json_path,
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
    )
    _atomic_write(
        markdown_path,
        _render_markdown(manifest, blueprint, paper),
    )
    _write_pdf(pdf_path, manifest, paper)
    return SavedPaperPaths(
        json_path=json_path,
        markdown_path=markdown_path,
        pdf_path=pdf_path,
    )


def _write_pdf(
    path: Path,
    manifest: DocumentManifest,
    paper: GeneratedQuestionPaper,
) -> None:
    story = fitz.Story(
        html=_render_pdf_html(manifest, paper),
        user_css="""
            @page { size: A4; }
            body { font-family: sans-serif; font-size: 10.5pt; color: #202020; }
            h1 { font-size: 18pt; text-align: center; margin: 0 0 6pt; }
            h2 { font-size: 12pt; margin: 18pt 0 8pt; border-bottom: 1px solid #777; }
            .metadata { text-align: center; margin-bottom: 10pt; }
            .status { font-weight: bold; text-align: center; margin-bottom: 12pt; }
            .instructions { margin: 0 0 14pt; }
            .question { margin: 0 0 12pt; page-break-inside: avoid; }
            .question-number { font-weight: bold; }
            .question-text { margin-top: 3pt; }
            .marks { font-size: 9pt; font-style: italic; margin-top: 4pt; }
            .review { color: #8a3a24; font-size: 9pt; margin-top: 4pt; }
            img { display: block; max-width: 420pt; max-height: 260pt; margin: 7pt 0; }
        """,
    )
    page = fitz.paper_rect("a4")
    content = fitz.Rect(48, 48, page.width - 48, page.height - 48)
    document = story.write_with_links(lambda *_: (page, content, None))
    _atomic_write_bytes(path, document.tobytes(garbage=4, deflate=True))
    document.close()


def _render_pdf_html(
    manifest: DocumentManifest,
    paper: GeneratedQuestionPaper,
) -> str:
    section_titles = {
        "section_a": "SECTION A — MCQ AND ASSERTION–REASON",
        "section_b": "SECTION B — VERY SHORT ANSWER",
        "section_c": "SECTION C — SHORT ANSWER",
        "section_d": "SECTION D — LONG ANSWER",
        "section_e": "SECTION E — CASE STUDY",
    }
    assets = {asset.asset_id: asset for asset in manifest.visual_assets}
    parts = [
        f"<h1>{html.escape(paper.title)}</h1>",
        (
            '<div class="metadata">'
            f"Time allowed: {paper.duration_minutes // 60} hours &nbsp; | &nbsp; "
            f"Maximum marks: {paper.total_marks} &nbsp; | &nbsp; "
            f"Subject: {html.escape(paper.subject)}"
            "</div>"
        ),
        (
            '<div class="status">Faculty approval required</div>'
            if paper.publication_ready
            else '<div class="status">DRAFT — REVIEW REQUIRED</div>'
        ),
        "<h2>GENERAL INSTRUCTIONS</h2>",
        '<ol class="instructions">'
        + "".join(f"<li>{html.escape(item)}</li>" for item in paper.instructions)
        + "</ol>",
    ]
    current_section: str | None = None
    for question in paper.questions:
        if question.section_id != current_section:
            current_section = question.section_id
            parts.append(
                f"<h2>{html.escape(section_titles.get(current_section, current_section.upper()))}</h2>"
            )
        review = ""
        if not question.accepted:
            messages = "; ".join(
                dict.fromkeys(
                    finding.message
                    for finding in question.findings
                    if finding.severity.value == "error"
                )
            )
            review = f'<div class="review">Review required: {html.escape(messages)}</div>'
        image = ""
        asset = assets.get(question.visual_asset_id or "")
        if asset and Path(asset.image_path).is_file():
            media_type = mimetypes.guess_type(asset.image_path)[0] or "image/png"
            encoded = base64.b64encode(Path(asset.image_path).read_bytes()).decode("ascii")
            image = (
                f'<img alt="Provided figure" src="data:{media_type};base64,{encoded}">' 
            )
        question_text = html.escape(question.question_text).replace("\n", "<br>")
        plural = "" if question.marks == 1 else "s"
        parts.append(
            '<div class="question">'
            f'<div class="question-number">{html.escape(question.question_number)}.</div>'
            f'<div class="question-text">{question_text}</div>'
            f"{image}"
            f'<div class="marks">[{question.marks} mark{plural}]</div>'
            f"{review}"
            "</div>"
        )
    return "<!doctype html><html><body>" + "".join(parts) + "</body></html>"


def _render_markdown(
    manifest: DocumentManifest,
    blueprint: PaperBlueprint,
    paper: GeneratedQuestionPaper,
) -> str:
    slots = {slot.slot_id: slot for slot in blueprint.slots}
    section_titles: dict[str, str] = {
        "section_a": "SECTION A — MCQ AND ASSERTION–REASON",
        "section_b": "SECTION B — VERY SHORT ANSWER",
        "section_c": "SECTION C — SHORT ANSWER",
        "section_d": "SECTION D — LONG ANSWER",
        "section_e": "SECTION E — CASE STUDY",
    }
    lines = [
        f"# {paper.title}",
        "",
        f"**Time allowed:** {paper.duration_minutes // 60} hours  ",
        f"**Maximum marks:** {paper.total_marks}  ",
        f"**Subject:** {paper.subject}",
        (
            "**Status:** Faculty approval required"
            if paper.publication_ready
            else "**Status:** PUBLICATION BLOCKED — one or more questions require replacement"
        ),
        "",
        "## General Instructions",
        "",
        *[f"{index}. {instruction}" for index, instruction in enumerate(
            paper.instructions, start=1
        )],
        "",
    ]

    current_section: str | None = None
    for question in paper.questions:
        slot = slots.get(question.slot_id)
        if slot and slot.section_id != current_section:
            current_section = slot.section_id
            lines.extend(
                [
                    f"## {section_titles.get(current_section, current_section.upper())}",
                    "",
                ]
            )
        number = slot.question_number if slot else "?"
        review_label = " **[REVIEW REQUIRED]**" if not question.accepted else ""
        lines.extend(
            [
                f"**{number}.**{review_label} {question.question_text}",
                "",
                f"*[{question.marks} mark"
                f"{'' if question.marks == 1 else 's'}]*",
                "",
            ]
        )
        if not question.accepted and question.findings:
            lines.extend(
                [
                    "*Blocking findings:* "
                    + "; ".join(
                        finding.message
                        for finding in question.findings
                        if finding.severity.value == "error"
                    ),
                    "",
                ]
            )
        visual_id = question.visual_asset_id
        if visual_id:
            asset = next(
                (
                    item
                    for item in manifest.visual_assets
                    if item.asset_id == visual_id
                ),
                None,
            )
            if asset:
                lines.extend([f"![Provided figure]({asset.image_path})", ""])

    return "\n".join(lines).rstrip() + "\n"


def _atomic_write(path: Path, content: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(content)
    temporary.replace(path)
