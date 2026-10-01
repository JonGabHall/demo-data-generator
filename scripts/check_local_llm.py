"""Probe a configured localhost narrative model before an enrichment run."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys


REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "src"))

from indoors_demo_generator.narratives import LocalJsonNarrator  # noqa: E402


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify that a localhost LLM returns an accepted asset narrative."
    )
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=60)
    return parser.parse_args()


def main() -> None:
    arguments = _arguments()
    fallback = "Deterministic probe fallback."
    narrator = LocalJsonNarrator(
        arguments.endpoint,
        arguments.model,
        timeout_seconds=arguments.timeout_seconds,
        max_requests=1,
    )
    text = narrator.narrate(
        "inspection",
        {
            "asset_type": "Air Handling Unit",
            "asset_class": "Building Services",
            "condition": "Maintenance Due",
            "criticality": "High",
            "lifecycle_stage": "Within Service Life",
        },
        fallback,
    )
    accepted = narrator.stats.accepted_responses == 1
    print(
        json.dumps(
            {
                "accepted": accepted,
                "endpoint": arguments.endpoint,
                "model": arguments.model,
                "text": text,
                "statistics": asdict(narrator.stats),
            },
            indent=2,
        )
    )
    if not accepted:
        raise SystemExit(1)


if __name__ == "__main__":
    main()