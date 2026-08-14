from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(path: str, *needles: str) -> str:
    source = ROOT / path
    if not source.is_file():
        raise SystemExit(f"Missing Phase 7 asset: {path}")
    text = source.read_text(encoding="utf-8")
    for needle in needles:
        if needle not in text:
            raise SystemExit(f"{path} is missing required proof: {needle}")
    return text


def main() -> None:
    require("Dockerfile", "python:3.12-slim", "USER tulina", "backend.tulina.api:app")
    require("frontend/Dockerfile", "node:22-alpine", "USER node", "VITE_API_URL")
    require("frontend/server.mjs", 'url.pathname === "/healthz"', "X-Content-Type-Options")
    require(
        "infra/gcp/deploy.ps1",
        "run.googleapis.com",
        "firestore.googleapis.com",
        "pubsub.googleapis.com",
        "aiplatform.googleapis.com",
        "roles/datastore.user",
        "roles/cloudkms.signerVerifier",
        "--push-auth-service-account",
        "--startup-probe",
        "--liveness-probe",
    )
    require("infra/gcp/verify.ps1", "/healthz", "/readyz", "Google ADK")
    require("infra/gcp/seed.ps1", "ConfirmNamespace", "backend.tulina.cloud.cli")
    teardown = require(
        "infra/gcp/teardown.ps1", "Dry run only", "ConfirmProjectId", "Firestore and KMS"
    )
    if 'switch]$Execute' not in teardown:
        raise SystemExit("Teardown must default to a non-destructive dry run")
    rules = require("infra/gcp/firestore.rules", "allow read, write: if false")
    if "allow read, write: if true" in rules:
        raise SystemExit("Firestore rules must not grant direct browser access")
    indexes = json.loads((ROOT / "infra/gcp/firestore.indexes.json").read_text(encoding="utf-8"))
    groups = {item["collectionGroup"] for item in indexes["indexes"]}
    required_groups = {
        "audit_events",
        "agent_runs",
        "agent_steps",
        "stock_card_intakes",
        "reconciliation_results",
    }
    if not required_groups.issubset(groups):
        raise SystemExit("Firestore composite indexes do not cover every cloud query")
    print("Phase 7 deployment assets verified")


if __name__ == "__main__":
    main()
