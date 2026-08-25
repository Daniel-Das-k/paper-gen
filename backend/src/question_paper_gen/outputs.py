from __future__ import annotations

import base64
import html
import json
import mimetypes
import os
import re
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import fitz

from .patterns import get_pattern
from .models import (
    AnswerKeyEntry,
    BloomLevel,
    ExamPaper,
    ContentMap,
    DocumentManifest,
    GeneratedQuestionPaper,
    PaperBlueprint,
    QuestionPaperItem,
)


@dataclass(frozen=True)
class SavedPaperPaths:
    json_path: Path
    markdown_path: Path
    pdf_path: Path


@dataclass(frozen=True)
class DemoOutputPaths:
    pdf_path: Path
    scheme_path: Path
    docx_path: Path


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
    _write_pdf(pdf_path, manifest, blueprint, paper)
    return SavedPaperPaths(
        json_path=json_path,
        markdown_path=markdown_path,
        pdf_path=pdf_path,
    )


def save_evaluation_scheme(
    *,
    manifest: DocumentManifest,
    blueprint: PaperBlueprint,
    paper: ExamPaper,
    pdf_path: Path,
) -> Path:
    """Write the scheme of evaluation that accompanies a paper to the exam cell.

    Deliberately separate from `save_generated_paper`: that function is handed the
    public, answer-free paper and must stay that way, so the only code that can
    ever put answers on a page is this one. Valuers mark from the mark-wise
    criteria, so those lead; the model answer follows as supporting detail.
    """
    _write_scheme_pdf(pdf_path, blueprint, paper)
    return pdf_path


def save_demo_edited_outputs(
    *,
    paper_id: str,
    manifest: DocumentManifest,
    blueprint: PaperBlueprint,
    paper: GeneratedQuestionPaper,
    answer_key: list[AnswerKeyEntry],
) -> DemoOutputPaths:
    """Render a faculty-edited public paper and its coordinated answer key.

    Demo edits operate on the answer-free public projection plus the separate
    answer key. Keeping the inputs separate preserves the same no-answer-leak
    boundary as normal generation.
    """
    if not re.fullmatch(r"[a-f0-9]{32}", paper_id):
        raise ValueError("invalid demo paper id")
    root = default_pdf_output_directory()
    root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    pdf_path = root / f"demo-{paper_id}-{timestamp}.pdf"
    scheme_path = root / f"demo-{paper_id}-{timestamp}-scheme.pdf"
    docx_path = root / f"demo-{paper_id}-{timestamp}.docx"
    _write_pdf(pdf_path, manifest, blueprint, paper)
    _write_public_scheme_pdf(scheme_path, blueprint, paper, answer_key)
    _write_demo_docx(docx_path, blueprint, paper)
    return DemoOutputPaths(
        pdf_path=pdf_path, scheme_path=scheme_path, docx_path=docx_path
    )


def _write_demo_docx(
    path: Path, blueprint: PaperBlueprint, paper: GeneratedQuestionPaper
) -> None:
    """Write the editable demo paper as a minimal Office Open XML document."""
    escape = html.escape

    def paragraph(text: str, *, bold: bool = False, centered: bool = False) -> str:
        properties = "<w:pPr><w:jc w:val=\"center\"/></w:pPr>" if centered else ""
        run_properties = "<w:rPr><w:b/></w:rPr>" if bold else ""
        return (
            f"<w:p>{properties}<w:r>{run_properties}"
            f'<w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'
        )

    header = paper.exam_header.completed_for(
        blueprint.pattern_id, paper.subject, paper.duration_minutes
    )
    body = [
        paragraph(header.college, bold=True, centered=True),
        paragraph(f"{header.institution_line} · {header.affiliation}", centered=True),
        paragraph(header.exam_title, bold=True, centered=True),
        paragraph(
            f"{header.subject_code}  {header.subject_name}  "
            f"Semester: {header.semester}  Date: {header.date}"
        ),
        paragraph(
            f"Time: {paper.duration_minutes} minutes  Maximum marks: {paper.total_marks}"
        ),
    ]
    section_titles = _section_titles(blueprint)
    current_section: str | None = None
    for question in paper.questions:
        if question.section_id != current_section:
            current_section = question.section_id
            body.append(
                paragraph(
                    section_titles.get(current_section, current_section.upper()),
                    bold=True,
                    centered=True,
                )
            )
        body.append(
            paragraph(
                f"{question.question_number}. {question.question_text} "
                f"[{question.course_outcome_code or 'CO—'}] [{_level_tag(question)}]"
            )
        )
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{''.join(body)}<w:sectPr/></w:body></w:document>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    relationships = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/>'
        "</Relationships>"
    )
    temporary = path.with_suffix(".docx.tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", relationships)
        archive.writestr("word/document.xml", document_xml)
    temporary.replace(path)


def _write_public_scheme_pdf(
    path: Path,
    blueprint: PaperBlueprint,
    paper: GeneratedQuestionPaper,
    answer_key: list[AnswerKeyEntry],
) -> None:
    entries = {entry.question_id: entry for entry in answer_key}
    section_titles = _section_titles(blueprint)
    parts = [
        f"<h1>{html.escape(paper.title)}</h1>",
        '<div class="metadata">SCHEME OF EVALUATION &nbsp;|&nbsp; '
        f"Maximum marks: {paper.total_marks} &nbsp;|&nbsp; "
        f"Subject: {html.escape(paper.subject)}</div>",
    ]
    current_section: str | None = None
    for question in paper.questions:
        if question.section_id != current_section:
            current_section = question.section_id
            parts.append(
                f"<h2>{html.escape(section_titles.get(current_section, current_section.upper()))}</h2>"
            )
        entry = entries.get(question.question_id)
        if entry is None:
            continue
        criteria = "".join(
            f'<div class="criterion">{html.escape(item.criterion)} '
            f"&mdash; {item.marks} mark{'' if item.marks == 1 else 's'}</div>"
            for item in entry.criteria
        )
        parts.append(
            '<div class="entry">'
            f'<span class="qnum">{html.escape(question.question_number)}. '
            f"[{question.marks} marks]</span>"
            f'<div class="qtext">{html.escape(question.question_text).replace(chr(10), "<br>")}</div>'
            f"{criteria}"
            f'<div class="answer"><b>Model answer:</b> '
            f'{html.escape(entry.answer).replace(chr(10), "<br>")}</div>'
            "</div>"
        )
    story = fitz.Story(
        html="<!doctype html><html><body>" + "".join(parts) + "</body></html>",
        user_css="""
            @page { size: A4; }
            body { font-family: sans-serif; font-size: 10pt; color: #202020; }
            h1 { font-size: 16pt; text-align: center; margin: 0 0 4pt; }
            h2 { font-size: 11pt; margin: 16pt 0 6pt; border-bottom: 1px solid #777; }
            .metadata { text-align: center; font-size: 9pt; margin-bottom: 10pt; }
            .entry { margin-bottom: 12pt; }
            .qnum { font-weight: bold; }
            .qtext { margin: 2pt 0 4pt; }
            .criterion { margin-left: 10pt; }
            .answer { margin: 4pt 0 0 10pt; color: #404040; }
        """,
    )
    writer = fitz.DocumentWriter(str(path))
    more = True
    while more:
        device = writer.begin_page(fitz.paper_rect("a4"))
        more, _ = story.place(fitz.paper_rect("a4") + (36, 36, -36, -36))
        story.draw(device)
        writer.end_page()
    writer.close()


def _write_scheme_pdf(
    path: Path,
    blueprint: PaperBlueprint,
    paper: ExamPaper,
) -> None:
    story = fitz.Story(
        html=_render_scheme_html(blueprint, paper),
        user_css="""
            @page { size: A4; }
            body { font-family: sans-serif; font-size: 10pt; color: #202020; }
            h1 { font-size: 16pt; text-align: center; margin: 0 0 4pt; }
            h2 { font-size: 11pt; margin: 16pt 0 6pt; border-bottom: 1px solid #777; }
            .metadata { text-align: center; font-size: 9pt; margin-bottom: 4pt; }
            .status { text-align: center; font-size: 9pt; font-weight: bold;
                      margin-bottom: 10pt; }
            .entry { margin-bottom: 12pt; }
            .qnum { font-weight: bold; font-size: 10pt; }
            .qtext { margin: 2pt 0 4pt; font-size: 9.5pt; color: #404040; }
            .criterion { font-size: 9.5pt; margin-left: 10pt; }
            .answer { font-size: 9pt; color: #404040; margin: 4pt 0 0 10pt; }
            .caution { font-size: 9pt; color: #7c3028; margin-left: 10pt; }
        """,
    )
    writer = fitz.DocumentWriter(str(path))
    more = True
    while more:
        device = writer.begin_page(fitz.paper_rect("a4"))
        more, _ = story.place(fitz.paper_rect("a4") + (36, 36, -36, -36))
        story.draw(device)
        writer.end_page()
    writer.close()


def _render_scheme_html(blueprint: PaperBlueprint, paper: ExamPaper) -> str:
    slots = {slot.slot_id: slot for slot in blueprint.slots}
    section_titles = _section_titles(blueprint)
    parts = [
        f"<h1>{html.escape(paper.title)}</h1>",
        '<div class="metadata">SCHEME OF EVALUATION'
        + (f" &nbsp;|&nbsp; SET {html.escape(paper.set_label)}" if paper.set_label else "")
        + ' &nbsp;|&nbsp; '
        f"Maximum marks: {paper.total_marks} &nbsp;|&nbsp; "
        f"Subject: {html.escape(paper.subject)}</div>",
        '<div class="status">DRAFT — REQUIRES FACULTY APPROVAL BEFORE VALUATION'
        "</div>",
    ]
    current_section: str | None = None
    for question in paper.questions:
        slot = slots.get(question.candidate.slot_id)
        section_id = slot.section_id if slot else ""
        if section_id and section_id != current_section:
            current_section = section_id
            heading = section_titles.get(section_id, section_id.upper())
            parts.append(f"<h2>{html.escape(heading)}</h2>")
        number = slot.question_number if slot else "?"
        candidate = question.candidate
        criteria = "".join(
            f'<div class="criterion">{html.escape(item.criterion)} '
            f"&mdash; {item.marks} mark{'' if item.marks == 1 else 's'}</div>"
            for item in candidate.marking_scheme
        )
        answer = html.escape(candidate.answer).replace("\n", "<br>")
        caution = ""
        if not question.accepted:
            caution = (
                '<div class="caution">This question did not pass automated review; '
                "confirm the key before valuation.</div>"
            )
        question_text = html.escape(candidate.question_text).replace("\n", "<br>")
        parts.append(
            '<div class="entry">'
            f'<span class="qnum">{html.escape(number)}. '
            f"[{candidate.marks} marks &middot; {candidate.bloom_level.value}]</span>"
            f'<div class="qtext">{question_text}</div>'
            f"{criteria}"
            f'<div class="answer"><b>Model answer:</b> {answer}</div>'
            f"{caution}"
            "</div>"
        )
    return "<!doctype html><html><body>" + "".join(parts) + "</body></html>"


def _write_pdf(
    path: Path,
    manifest: DocumentManifest,
    blueprint: PaperBlueprint,
    paper: GeneratedQuestionPaper,
) -> None:
    story = fitz.Story(
        html=_render_pdf_html(manifest, blueprint, paper),
        user_css="""
            @page { size: A4; }
            body { font-family: serif; font-size: 10.5pt; color: #000; }

            /* Register number grid */
            table.regno { width: 100%; margin-bottom: 6pt; }
            table.regno td.rl { text-align: right; font-weight: bold;
                                font-size: 9.5pt; padding-right: 4pt; }
            table.regno td.rn { border: 1px solid #000; width: 16pt;
                                height: 14pt; }

            /* Ruled masthead */
            table.masthead { width: 100%; border: 1px solid #000;
                             border-collapse: collapse; }
            table.masthead td { border: 1px solid #000; padding: 5pt 7pt;
                                vertical-align: middle; }
            td.college { text-align: center; padding: 6pt; }
            .cname { font-size: 14pt; font-weight: bold; }
            .cinst { font-size: 8pt; }
            td.facts { font-size: 9pt; padding: 5pt 8pt; }
            .ftitle { font-weight: bold; padding-bottom: 2pt; }
            .f { }

            .reg { text-align: center; font-style: italic; font-weight: bold;
                   font-size: 9.5pt; margin-top: 6pt; }
            .common { text-align: center; font-weight: bold; font-size: 9.5pt;
                      margin-top: 2pt; }
            .draft { text-align: center; font-weight: bold; font-size: 9pt;
                     margin-top: 4pt; }

            table.line { width: 100%; margin-top: 4pt; font-weight: bold;
                         font-size: 10pt; }
            table.line td.l { text-align: left; }
            table.line td.c { text-align: center; }
            table.line td.r { text-align: right; }

            .answerall { text-align: center; margin-top: 12pt; font-size: 10pt; }
            .part { text-align: center; font-weight: bold; font-size: 10.5pt;
                    margin: 1pt 0 6pt; }

            /* One question: number, text, then the [CO] [level] margin */
            table.q { width: 100%; margin-bottom: 6pt; }
            td.qn { width: 26pt; vertical-align: top; font-weight: bold; }
            td.qt { vertical-align: top; text-align: justify; }
            td.qtag { width: 74pt; vertical-align: top; text-align: right;
                      font-size: 9pt; }
            .or { text-align: center; font-weight: bold; margin: 4pt 0; }
            .fig { text-align: center; margin: 6pt 0; }
            .fig img { max-width: 260pt; }
        """,
    )
    page = fitz.paper_rect("a4")
    content = fitz.Rect(48, 48, page.width - 48, page.height - 48)
    document = story.write_with_links(lambda *_: (page, content, None))
    _atomic_write_bytes(path, document.tobytes(garbage=4, deflate=True))
    document.close()


#: Rajalakshmi prints the cognitive level in three tiers rather than as a Bloom
#: word: A lower order, B middle, C higher order.
def _section_titles(blueprint: PaperBlueprint) -> dict[str, str]:
    """Map section_id to its printed heading, taken from the paper's own pattern.

    Headings used to be hard-coded for the five-section school pattern, which
    rendered a college paper's `part_a` as the raw id. The pattern already
    carries the exact wording each section should print, so read it from there.
    """
    try:
        pattern = get_pattern(blueprint.pattern_id)
    except KeyError:
        return {}
    return {section.section_id: section.title for section in pattern.sections}


REC_LEVEL_TAG: dict[BloomLevel, str] = {
    BloomLevel.REMEMBER: "A1",
    BloomLevel.UNDERSTAND: "A2",
    BloomLevel.APPLY: "B1",
    BloomLevel.ANALYZE: "B2",
    BloomLevel.EVALUATE: "C1",
    BloomLevel.CREATE: "C2",
}


def _level_tag(question: QuestionPaperItem) -> str:
    level = question.observed_bloom_level or question.bloom_level
    return REC_LEVEL_TAG.get(level, level.value[:2].upper())


def _render_pdf_html(
    manifest: DocumentManifest,
    blueprint: PaperBlueprint,
    paper: GeneratedQuestionPaper,
) -> str:
    """Render the paper exactly as the college issues it.

    Everything outside the questions is fixed: the register-number grid, the
    ruled masthead, the regulation line, the date/time/marks row, the part
    headings and the [CO] [level] margin. Only the questions vary, and they are
    placed into that template rather than laid out afresh each time.
    """
    header = paper.exam_header.completed_for(
        blueprint.pattern_id, paper.subject, paper.duration_minutes
    )
    section_titles = _section_titles(blueprint)
    assets = {asset.asset_id: asset for asset in manifest.visual_assets}
    duration = (
        f"{paper.duration_minutes // 60} Hours"
        if paper.duration_minutes >= 180
        else f"{paper.duration_minutes} Minutes"
    )
    esc = html.escape

    boxes = "".join(
        '<td class="rn"> </td>' for _ in range(header.register_number_boxes)
    )
    # A single-column stacked masthead. fitz.Story does not honour column
    # widths reliably, and a side-by-side layout overflowed the college name
    # across the facts; stacking renders correctly and still reads as a masthead.
    facts = "  &nbsp;&nbsp; ".join(
        f"{esc(label)}: {esc(value)}"
        for label, value in (
            ("Year", header.year),
            ("Semester", header.semester),
            ("Branch", header.branch),
            ("Sub. Code", header.subject_code),
            ("Subject", header.subject_name),
            ("QP Code", header.qp_code),
        )
        if value
    )

    parts = [
        '<table class="regno"><tr><td class="rl">Reg. No.</td>'
        f"{boxes}</tr></table>",
        '<table class="masthead">'
        f'<tr><td class="college"><div class="cname">{esc(header.college)}</div>'
        f'<div class="cinst">{esc(header.institution_line)} &nbsp;·&nbsp; '
        f'{esc(header.affiliation)}</div></td></tr>'
        f'<tr><td class="facts"><div class="ftitle">{esc(header.exam_title)}</div>'
        f'<div class="f">{facts}</div></td></tr></table>',
        f'<div class="reg">[{esc(header.regulation)}]</div>',
    ]
    if header.common_to:
        parts.append(f'<div class="common">(Common to {esc(header.common_to)})</div>')
    parts.append(
        '<table class="line"><tr>'
        f'<td class="l">Date: {esc(header.date) or "&nbsp;"}</td>'
        f'<td class="c">Time: {duration}</td>'
        f'<td class="r">Max. Marks: {paper.total_marks}</td>'
        "</tr></table>"
    )
    if paper.set_label:
        parts.append(f'<div class="common">SET {esc(paper.set_label)}</div>')
    if not paper.publication_ready:
        parts.append('<div class="draft">DRAFT — REVIEW REQUIRED</div>')

    current_section: str | None = None
    for question in paper.questions:
        if question.section_id != current_section:
            current_section = question.section_id
            heading = section_titles.get(
                current_section, current_section.replace("_", " ").upper()
            )
            parts.append('<div class="answerall">Answer ALL Questions</div>')
            parts.append(f'<div class="part">{esc(heading)}</div>')

        body = (
            esc(question.question_text)
            .replace("\nOR\n", '\n<div class="or">[OR]</div>\n')
            .replace("\n", "<br>")
        )
        asset = assets.get(question.visual_asset_id or "")
        figure = ""
        if asset and Path(asset.image_path).is_file():
            media_type = mimetypes.guess_type(asset.image_path)[0] or "image/png"
            encoded = base64.b64encode(Path(asset.image_path).read_bytes()).decode(
                "ascii"
            )
            figure = f'<div class="fig"><img src="data:{media_type};base64,{encoded}"></div>'
        tags = f"[{question.course_outcome_code or '&nbsp;'}]&nbsp;&nbsp;[{_level_tag(question)}]"
        parts.append(
            '<table class="q"><tr>'
            f'<td class="qn">{esc(question.question_number)}</td>'
            f'<td class="qt">{body}{figure}</td>'
            f'<td class="qtag">{tags}</td>'
            "</tr></table>"
        )

    return "<!doctype html><html><body>" + "".join(parts) + "</body></html>"


def _bloom_label(question: QuestionPaperItem) -> str:
    """Describe a question's cognitive level, flagging where it left the blueprint."""
    if question.observed_bloom_level is None:
        return f"Bloom: {question.bloom_level.value} (requested)"
    if question.bloom_matches_blueprint:
        return f"Bloom: {question.observed_bloom_level.value}"
    return (
        f"Bloom: {question.observed_bloom_level.value} "
        f"(requested {question.bloom_level.value})"
    )


def _outcome_label(question: QuestionPaperItem) -> str:
    """Append the course outcome the question assesses, when one is mapped."""
    if not question.course_outcome:
        return ""
    return f" · CO: {question.course_outcome}"


def _outcome_coverage_lines(paper: GeneratedQuestionPaper) -> list[str]:
    """The CO-versus-marks table accreditation reviews ask for."""
    coverage = paper.course_outcome_coverage
    if not coverage.marks_by_outcome and not coverage.unmapped_marks:
        return []
    rows = [
        f"| CO{index} | {outcome} | {marks} |"
        for index, (outcome, marks) in enumerate(
            coverage.marks_by_outcome.items(), start=1
        )
    ]
    lines = [
        "## Course Outcome Coverage",
        "",
        "| # | Course outcome | Marks |",
        "| --- | --- | --- |",
        *rows,
    ]
    if coverage.unmapped_marks:
        lines.append(f"| — | *Not mapped to an outcome* | {coverage.unmapped_marks} |")
    lines.extend(["", f"Total: {coverage.total_marks} marks.", ""])
    return lines


def _bloom_summary_lines(paper: GeneratedQuestionPaper) -> list[str]:
    """Faculty-facing account of requested versus actual cognitive demand."""
    summary = paper.bloom_summary
    if not summary.total:
        return []
    levels = [level.value for level in BloomLevel]
    rows = [
        f"| {level} | {summary.requested.get(level, 0)} | {summary.observed.get(level, 0)} |"
        for level in levels
        if summary.requested.get(level) or summary.observed.get(level)
    ]
    lines = [
        "## Bloom Level Coverage",
        "",
        "| Level | Requested | As written |",
        "| --- | --- | --- |",
        *rows,
        "",
    ]
    if summary.deviations:
        lines.append(
            f"{summary.deviations} of {summary.total} questions were written at a "
            "different level than the blueprint requested, because the source could "
            "not support the requested demand. Each is marked on the question. This "
            "does not block publication — confirm the levels suit your cohort."
        )
    else:
        lines.append("Every question matches the level the blueprint requested.")
    if summary.unverified:
        lines.append(
            f"{summary.unverified} question(s) were not level-verified by review."
        )
    lines.append("")
    return lines


def _render_markdown(
    manifest: DocumentManifest,
    blueprint: PaperBlueprint,
    paper: GeneratedQuestionPaper,
) -> str:
    slots = {slot.slot_id: slot for slot in blueprint.slots}
    section_titles = _section_titles(blueprint)
    lines = [
        f"# {paper.title}",
        "",
        *([f"**SET {paper.set_label}**  ", ""] if paper.set_label else []),
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
        *_bloom_summary_lines(paper),
        *_outcome_coverage_lines(paper),
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
                f"**{number}.**{review_label} "
                + question.question_text.replace("\nOR\n", "\n\n[OR]\n\n"),
                "",
                f"*[{question.marks} mark"
                f"{'' if question.marks == 1 else 's'}"
                f" · {_bloom_label(question)}"
                f"{_outcome_label(question)}]*",
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
