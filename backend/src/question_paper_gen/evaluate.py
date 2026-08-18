"""Reliability evaluation harness.

Runs the full generation pipeline N times against one source PDF and reports
the metrics that define "reliable": publication-ready rate, rejection codes,
duplicate rate, quality scores, model calls, and wall-clock time. Appends one
JSON line per run so changes can be compared across code versions.

Usage:
    PYTHONPATH=src python -m question_paper_gen.evaluate pdfs/chapter.pdf \
        --start-page 1 --end-page 28 --runs 3 --out eval_results.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import time
from collections import Counter
from pathlib import Path

from .ai import DocumentAnalyzer
from .blueprints import BlueprintBuilder
from .documents import PdfInspector
from .patterns import default_college_pattern
from .pipeline import PaperGenerationPipeline
from .validation import find_duplicate_questions


async def _run(args: argparse.Namespace) -> None:
    analyzer = DocumentAnalyzer()
    inspector = PdfInspector()
    manifest = inspector.inspect(
        str(args.pdf),
        start_page=args.start_page,
        end_page=args.end_page,
    )
    if not manifest.quality.passed:
        raise SystemExit(
            "document failed quality checks: " + "; ".join(manifest.quality.errors)
        )
    print(f"analyzing {args.pdf} pages {manifest.selected_page_start}-"
          f"{manifest.selected_page_end} ...")
    content_map, assets = await analyzer.analyze_document(manifest)
    manifest = manifest.model_copy(update={"visual_assets": assets})
    pattern = default_college_pattern()
    blueprint = BlueprintBuilder().build(pattern, content_map, manifest)
    print(
        f"prepared: {len(content_map.topics)} topics, "
        f"{len(blueprint.slots)} slots, {len(blueprint.warnings)} warning(s)"
    )

    results: list[dict[str, object]] = []
    for run_index in range(1, args.runs + 1):
        pipeline = PaperGenerationPipeline(analyzer)
        started = time.perf_counter()
        paper = await pipeline.generate(
            pattern=pattern,
            content_map=content_map,
            manifest=manifest,
            blueprint=blueprint,
        )
        duration = time.perf_counter() - started
        rejected = [q for q in paper.questions if not q.accepted]
        finding_codes = Counter(
            finding.code for q in rejected for finding in q.findings
        )
        scores = [
            q.quality_score for q in paper.questions if q.quality_score is not None
        ]
        record = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "pdf": str(args.pdf),
            "pages": f"{manifest.selected_page_start}-{manifest.selected_page_end}",
            "run": run_index,
            "publication_ready": paper.publication_ready,
            "questions": len(paper.questions),
            "rejected": len(rejected),
            "rejection_codes": dict(finding_codes),
            "duplicate_groups": len(find_duplicate_questions(paper.questions)),
            "quality_min": min(scores) if scores else None,
            "quality_avg": round(sum(scores) / len(scores), 1) if scores else None,
            "model_calls": pipeline._completed_model_calls,
            "duration_seconds": round(duration, 1),
        }
        results.append(record)
        print(
            f"run {run_index}/{args.runs}: "
            f"{'READY' if record['publication_ready'] else 'BLOCKED'} "
            f"rejected={record['rejected']} dup_groups={record['duplicate_groups']} "
            f"avg_score={record['quality_avg']} calls={record['model_calls']} "
            f"{record['duration_seconds']}s"
        )
        if args.out:
            with open(args.out, "a") as handle:
                handle.write(json.dumps(record) + "\n")

    ready = sum(1 for record in results if record["publication_ready"])
    total_rejected = Counter()
    for record in results:
        total_rejected.update(record["rejection_codes"])  # type: ignore[arg-type]
    print("\n=== summary ===")
    print(f"publication-ready: {ready}/{len(results)}")
    print(f"rejection codes: {dict(total_rejected) or 'none'}")
    averages = [record["quality_avg"] for record in results if record["quality_avg"]]
    if averages:
        print(f"mean quality score across runs: {sum(averages) / len(averages):.1f}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path, help="source PDF path")
    parser.add_argument("--start-page", type=int, default=None)
    parser.add_argument("--end-page", type=int, default=None)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("eval_results.jsonl"),
        help="JSONL file to append per-run records to (default eval_results.jsonl)",
    )
    asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    main()
