"""Bounded F10 analysis packets and a delivery ledger; no raw archive dump."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from artifacts import read_json

DEFAULT_MAX_CHARS = 12000
STAGES = ("analyze", "review")


def build_packet(run_dir: Path, stage: str, request_id: str, *,
                 max_chars: int = DEFAULT_MAX_CHARS, cursor: str | None = None) -> dict:
    if stage not in STAGES:
        raise ValueError("stage must be analyze or review")
    if not 1000 <= max_chars <= DEFAULT_MAX_CHARS:
        raise ValueError("max_chars must be between 1000 and 12000")
    run_dir = Path(run_dir)
    financials = read_json(run_dir / "financials.json")
    metrics = read_json(run_dir / "metrics.json")
    items = [{"kind": "fact", **fact} for fact in financials.get("facts", [])]
    items += [{"kind": "metric", **metric} for metric in metrics.get("metrics", [])]
    items += [{"kind": "check", **check} for check in metrics.get("validation", [])]
    items += [{"kind": "red_flag", **flag} for flag in metrics.get("red_flags", [])]
    version = hashlib.sha256(json.dumps(items, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    start = 0
    if cursor:
        try:
            token_version, token_index = cursor.split(":")
            start = int(token_index)
        except (ValueError, TypeError) as exc:
            raise ValueError("invalid context cursor") from exc
        if token_version != version or not 0 <= start < len(items):
            raise ValueError("stale or out-of-range context cursor")
    packet = {"stage": stage, "request_id": request_id, "items": [],
              "character_count": 0, "next_cursor": None}
    for index in range(start, len(items)):
        candidate = {**packet, "items": packet["items"] + [items[index]],
                     "next_cursor": f"{version}:{index + 1}" if index + 1 < len(items) else None}
        length = len(json.dumps(candidate, ensure_ascii=False)) + 30
        if length > max_chars:
            if not packet["items"]:
                raise ValueError("single analysis item exceeds context budget")
            break
        packet = candidate
    packet["character_count"] = len(json.dumps(packet, ensure_ascii=False)) + 10
    history_path = run_dir / "context_usage.jsonl"
    history = ([json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines()]
               if history_path.exists() else [])
    packet_sha = hashlib.sha256(json.dumps(packet, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    summary = {"total_delivered_chars": sum(h["character_count"] for h in history) + packet["character_count"],
               "unique_packets": len({h["packet_sha256"] for h in history} | {packet_sha})}
    with history_path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps({"request_id": request_id, "stage": stage,
                                 "packet_sha256": packet_sha, "character_count": packet["character_count"],
                                 "estimated_input_tokens": None}, ensure_ascii=False) + "\n")
    return {"packet": packet, "usage_summary": summary, "packet_sha256": packet_sha}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read bounded normalized F10 facts and metrics")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--stage", default="analyze", choices=STAGES)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--cursor")
    parser.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS)
    args = parser.parse_args(argv)
    result = build_packet(Path(args.run_dir), args.stage, args.request_id,
                          cursor=args.cursor, max_chars=args.max_chars)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
