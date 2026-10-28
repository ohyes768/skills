"""Read-only input preflight using the current rendering contract, without budget writes."""

import argparse
import json
from pathlib import Path

from artifacts import read_json
from render_report import render_report


def verify_inputs(run_dir: Path, inputs: dict) -> list[dict]:
    _markdown, _claims, issues = render_report(run_dir, inputs)
    for section in inputs.get("sections", []):
        table = section.get("table") or {}
        for row in table.get("rows", []):
            cells = row.get("cells", [])
            if len(cells) + 1 != len(table.get("columns", [])):
                issues.append({"anchor": section.get("anchor"), "row_label": row.get("label"),
                               "error": "A5 table row column count differs from header"})
    return issues


def main(argv=None):
    parser = argparse.ArgumentParser(description="Report-input preflight (no repair budget spent)")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--inputs", default="report_inputs.json")
    args = parser.parse_args(argv)
    run_dir = Path(args.run_dir)
    issues = verify_inputs(run_dir, read_json(run_dir / args.inputs))
    print(json.dumps({"passed": not issues, "issues": issues}, ensure_ascii=False))
    return 2 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
