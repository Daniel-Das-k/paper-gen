from __future__ import annotations

import re
from dataclasses import dataclass

from .models import DocumentManifest, QuestionCandidate


@dataclass(frozen=True)
class EvidenceChunk:
    chunk_id: str
    page_number: int
    text: str


def is_answer_key_page(text: str) -> bool:
    """Detect exercise-answer pages that must not serve as topic evidence.

    Deliberately conservative: an "ANSWERS" running head, or a dense list of
    enumerated items averaging under 15 words each. Instructional chapter
    pages never match; borderline answer pages are left to the model-side
    sufficiency check in the analysis prompt.
    """
    if re.match(r"\s*ANSWERS\b", text):
        return True
    words = re.findall(r"\b[\w'-]+\b", text)
    enumerators = re.findall(r"(?:^|\s)\d{1,2}\.\s", text)
    return len(enumerators) >= 8 and len(words) / max(len(enumerators), 1) < 15


def build_evidence_chunks(
    manifest: DocumentManifest,
    *,
    target_characters: int = 900,
) -> dict[str, EvidenceChunk]:
    """Create stable, backend-owned source chunks for model citations."""
    chunks: dict[str, EvidenceChunk] = {}
    for page in manifest.pages:
        if is_answer_key_page(page.text):
            continue
        pieces = [
            " ".join(piece.split())
            for piece in re.split(r"\n\s*\n|(?<=[.!?])\s+(?=[A-Z0-9])", page.text)
            if piece.strip()
        ]
        grouped: list[str] = []
        current = ""
        for piece in pieces:
            if current and len(current) + len(piece) + 1 > target_characters:
                grouped.append(current)
                current = piece
            else:
                current = f"{current} {piece}".strip()
        if current:
            grouped.append(current)
        if not grouped and page.text.strip():
            grouped = [" ".join(page.text.split())]
        for index, text in enumerate(grouped, start=1):
            chunk_id = f"p{page.page_number}-c{index}"
            chunks[chunk_id] = EvidenceChunk(
                chunk_id=chunk_id,
                page_number=page.page_number,
                text=text,
            )
    return chunks


def attach_verified_evidence(
    candidate: QuestionCandidate,
    manifest: DocumentManifest,
) -> QuestionCandidate:
    """Resolve model-selected chunk IDs and replace free-text citations."""
    chunks = build_evidence_chunks(manifest)
    selected_ids = [
        chunk_id
        for chunk_id in candidate.evidence.chunk_ids
        if chunk_id in chunks
    ]
    if not selected_ids:
        for excerpt in candidate.evidence.excerpts:
            normalized_excerpt = _normalize(excerpt)
            if len(normalized_excerpt) < 12:
                continue
            for chunk_id, chunk in chunks.items():
                if normalized_excerpt in _normalize(chunk.text):
                    selected_ids.append(chunk_id)
                    break
    selected_ids = list(dict.fromkeys(selected_ids))[:4]
    selected_chunks = [chunks[chunk_id] for chunk_id in selected_ids]
    return candidate.model_copy(
        update={
            "evidence": candidate.evidence.model_copy(
                update={
                    "chunk_ids": selected_ids,
                    "page_numbers": list(
                        dict.fromkeys(
                            chunk.page_number for chunk in selected_chunks
                        )
                    ),
                    "excerpts": [chunk.text[:500] for chunk in selected_chunks],
                }
            )
        }
    )


def _normalize(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))
