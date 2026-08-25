from __future__ import annotations

import argparse
import json

from .documents import PdfInspector
from .patterns import get_pattern


def main() -> None:
    parser = argparse.ArgumentParser(prog="question-paper-gen")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser(
        "inspect", help="extract text, page renders, and visual candidates from a PDF"
    )
    inspect_parser.add_argument("pdf")
    inspect_parser.add_argument("--artifacts", default="artifacts")
    inspect_parser.add_argument("--start-page", type=int)
    inspect_parser.add_argument("--end-page", type=int)

    subparsers.add_parser("pattern", help="print the default college paper pattern")
    arguments = parser.parse_args()

    if arguments.command == "inspect":
        manifest = PdfInspector(arguments.artifacts).inspect(
            arguments.pdf,
            start_page=arguments.start_page,
            end_page=arguments.end_page,
        )
        print(manifest.model_dump_json(indent=2))
    elif arguments.command == "pattern":
        print(get_pattern(None).model_dump_json(indent=2))


if __name__ == "__main__":
    main()
