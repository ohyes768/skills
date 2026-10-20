"""Explicit delivery receipt; the host rechecks current files with the fixed validator."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from artifacts import read_json, write_json

REQUIRED = ("document.json", "financials.json", "metrics.json", "extraction_manifest.json",
            "report_claims.json", "analysis.md", "report_inputs.json")
OPTIONAL = ("source.json", "source.pdf", "fact_inputs.json")


def artifact_hashes(run_dir: Path) -> dict[str, str]:
    paths = list(REQUIRED) + [name for name in OPTIONAL if (run_dir / name).exists()]
    manifest = read_json(run_dir / "extraction_manifest.json")
    paths.extend(evidence["file"] for evidence in manifest["evidences"])
    hashes = {}
    root = run_dir.resolve()
    for name in paths:
        path = (root / name).resolve()
        if not path.is_relative_to(root):
            raise ValueError(f"artifact outside run directory: {name}")
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def create_completion(run_dir: Path) -> dict:
    receipt = {"schema_version": 1, "run_id": run_dir.name, "terminal": True,
               "quality_status": "verified", "semantic_reviewed": True,
               "artifacts_sha256": artifact_hashes(run_dir)}
    write_json(run_dir / "completion.json", receipt)
    return receipt


def verify_completion(run_dir: Path, *, expected_url: str | None = None) -> str:
    """Do not trust quality_status or a receipt alone; validate the actual delivered body."""
    from validate_report import validate_report

    run_dir = Path(run_dir)
    receipt = read_json(run_dir / "completion.json")
    if (receipt.get("schema_version") != 1 or receipt.get("run_id") != run_dir.name
            or receipt.get("terminal") is not True
            or receipt.get("semantic_reviewed") is not True
            or receipt.get("quality_status") != "verified"):
        raise ValueError("invalid completion receipt")
    if read_json(run_dir / "run_state.json").get("quality_status") != "verified":
        raise ValueError("run is not verified")
    hashes = artifact_hashes(run_dir)
    if hashes != receipt.get("artifacts_sha256"):
        raise ValueError("artifacts changed after semantic review")
    if (expected_url is not None
            and read_json(run_dir / "source.json").get("requested_url") != expected_url):
        raise ValueError("source URL does not match this request")
    if not validate_report(run_dir)["passed"]:
        raise ValueError("independent report validation failed")
    body = (run_dir / "analysis.md").read_text(encoding="utf-8")
    if not body.strip() or artifact_hashes(run_dir) != hashes:
        raise ValueError("empty report or artifacts changed during verification")
    return body


def main() -> int:
    parser = argparse.ArgumentParser(description="Host-only completion verification")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--expected-url", required=True)
    args = parser.parse_args()
    try:
        body = verify_completion(args.run_dir, expected_url=args.expected_url)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"accepted": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    # This host-only command returns the artifact to the caller, never into model context.
    print(json.dumps({"accepted": True, "output": body}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
