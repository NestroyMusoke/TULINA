from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    required = [
        "README.md", "PHASES.md", ".env.example", ".gitignore", "pyproject.toml",
        "frontend/package.json", "backend/README.md", "docs/PRODUCT.md",
        "docs/ARCHITECTURE.md", "docs/DEMO_STORY.md", "docs/SECURITY.md",
        "docs/DATA_PROVENANCE.md", "docs/DECISIONS.md", "data/fixtures/manifest.json",
    ]
    missing = [name for name in required if not (ROOT / name).exists()]
    if missing:
        raise SystemExit(f"Missing Phase 0 files: {missing}")
    manifest = json.loads((ROOT / "data/fixtures/manifest.json").read_text())
    for name, expected in manifest["files"].items():
        actual = hashlib.sha256((ROOT / "data" / "fixtures" / name).read_bytes()).hexdigest()
        if actual != expected:
            raise SystemExit(f"Fixture integrity failed: {name}")
    pack = json.loads((ROOT / "data" / "fixtures" / "tulina_source_pack_v2.json").read_text(encoding="utf-8-sig"))
    assert pack["metadata"]["contains_patient_data"] is False
    assert pack["metadata"]["contains_private_keys"] is False
    assert pack["crypto_fixture_notes"]["capsule_signature_verified"] is True
    assert len(pack["relay_test_vectors"]) == 9
    print("Phase 0 verified: docs, scaffold, provenance, 3 asset hashes, and 9 vectors")


if __name__ == "__main__":
    main()

