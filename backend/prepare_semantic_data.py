from __future__ import annotations

import base64
import json
import zlib
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA_DIR = BASE / "app" / "data"
BUNDLE_DIR = DATA_DIR / "semantic_bundle"
OUTPUT = DATA_DIR / "semantic_dataset.json"
EXPECTED_TARGETS = 165


def main() -> None:
    parts = sorted(BUNDLE_DIR.glob("*.txt"))
    if len(parts) != 6:
        raise RuntimeError(f"Semantic bundle is incomplete: expected 6 parts, found {len(parts)}")

    encoded = "".join(part.read_text(encoding="utf-8").strip() for part in parts)
    raw = zlib.decompress(base64.b64decode(encoded))
    data = json.loads(raw.decode("utf-8"))

    if not isinstance(data, dict) or len(data) != EXPECTED_TARGETS:
        raise RuntimeError(
            f"Semantic dataset validation failed: expected {EXPECTED_TARGETS} targets, got {len(data) if isinstance(data, dict) else 'invalid'}"
        )

    OUTPUT.write_bytes(raw)
    print(f"Semantic dataset ready: {len(data)} targets / {len(raw):,} bytes")


if __name__ == "__main__":
    main()
