#!/usr/bin/env python3
"""Walk-forward calibration audit for deterministic signal scores.

Input JSONL records must contain:
  timestamp, symbol, score, outcome
where outcome is 1 for a successful directional outcome and 0 otherwise.

The script deliberately does not search for an optimal threshold. It estimates
reliability from an earlier training window and evaluates it on a later holdout
window, reducing look-ahead and threshold-tuning overfit.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import datetime


MIN_TRAIN = 50
MIN_TEST = 25
BUCKETS = 10


def _load(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            timestamp = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
            score = float(row["score"])
            outcome = int(row["outcome"])
            if not -1 <= score <= 1:
                raise ValueError("score must be between -1 and 1")
            if outcome not in (0, 1):
                raise ValueError("outcome must be 0 or 1")
            rows.append({**row, "_timestamp": timestamp, "score": score, "outcome": outcome})
    return sorted(rows, key=lambda row: row["_timestamp"])


def _bucket(score: float) -> int:
    return min(BUCKETS - 1, int(abs(score) * BUCKETS))


def _report(train: list[dict], test: list[dict]) -> dict:
    train_by_bucket = defaultdict(list)
    for row in train:
        train_by_bucket[_bucket(row["score"])].append(row["outcome"])

    calibration = {}
    for bucket, outcomes in sorted(train_by_bucket.items()):
        if len(outcomes) < 10:
            continue
        calibration[bucket] = sum(outcomes) / len(outcomes)

    predictions = []
    for row in test:
        p = calibration.get(_bucket(row["score"]))
        if p is not None:
            predictions.append((p, row["outcome"]))

    brier = (
        sum((prediction - outcome) ** 2 for prediction, outcome in predictions)
        / len(predictions)
        if predictions
        else None
    )
    return {
        "train_count": len(train),
        "test_count": len(test),
        "train_period": [train[0]["_timestamp"].isoformat(), train[-1]["_timestamp"].isoformat()],
        "test_period": [test[0]["_timestamp"].isoformat(), test[-1]["_timestamp"].isoformat()],
        "calibration_buckets": {
            str(bucket): {"train_count": len(train_by_bucket[bucket]), "observed_rate": rate}
            for bucket, rate in calibration.items()
        },
        "holdout_coverage": len(predictions) / len(test) if test else 0.0,
        "holdout_brier_score": brier,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("--train-fraction", type=float, default=0.70)
    args = parser.parse_args()

    if not 0.5 <= args.train_fraction <= 0.9:
        raise SystemExit("--train-fraction must be between 0.5 and 0.9")

    rows = _load(args.input)
    if len(rows) < MIN_TRAIN + MIN_TEST:
        raise SystemExit(f"Need at least {MIN_TRAIN + MIN_TEST} chronological observations.")

    split = max(MIN_TRAIN, min(len(rows) - MIN_TEST, math.floor(len(rows) * args.train_fraction)))
    train, test = rows[:split], rows[split:]
    report = _report(train, test)
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
