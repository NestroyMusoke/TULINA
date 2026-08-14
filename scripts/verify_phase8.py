from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "docs/DEMO_SCRIPT_4_MIN.md",
    "docs/DEVPOST_SUBMISSION.md",
    "docs/JUDGE_QA.md",
    "docs/CREDENTIAL_CHECKLIST.md",
    "docs/QA_REPORT.md",
    "docs/architecture.svg",
    "devpost-submission.md",
    "frontend/e2e/tulina-demo.spec.ts",
    "frontend/playwright.config.ts",
    "scripts/e2e.ps1",
    "scripts/capture_submission.ps1",
    "scripts/scan_secrets.py",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    missing = [relative for relative in REQUIRED if not (ROOT / relative).is_file()]
    require(not missing, f"Phase 8 files missing: {', '.join(missing)}")

    e2e = (ROOT / "frontend/e2e/tulina-demo.spec.ts").read_text(encoding="utf-8")
    for proof in (
        "TR-027",
        "Received offline",
        "Delivery confirmed",
        "Replay and tamper blocked",
        "offlineApiRequests",
        "AxeBuilder",
    ):
        require(proof in e2e, f"Browser proof is missing: {proof}")

    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    require("playwright install --with-deps chromium" in workflow, "CI does not install Chromium")
    require("run test:e2e" in workflow, "CI does not execute browser E2E tests")

    architecture = (ROOT / "docs/ARCHITECTURE.md").read_text(encoding="utf-8")
    require("```mermaid" in architecture, "Architecture document must contain Mermaid")
    require("## Phase 8 implementation boundary" in architecture, "Phase 8 boundary is undocumented")

    dist = ROOT / "frontend/dist"
    require(dist.is_dir(), "Build frontend/dist before Phase 8 verification")
    javascript_bytes = sum(path.stat().st_size for path in dist.rglob("*.js"))
    css_bytes = sum(path.stat().st_size for path in dist.rglob("*.css"))
    html_bytes = sum(path.stat().st_size for path in dist.rglob("*.html"))
    require(javascript_bytes <= 1_000_000, f"JavaScript budget exceeded: {javascript_bytes} bytes")
    require(css_bytes <= 100_000, f"CSS budget exceeded: {css_bytes} bytes")
    require(html_bytes <= 15_000, f"HTML budget exceeded: {html_bytes} bytes")

    print(
        "Phase 8 verified: submission packet, browser proof, CI gate, architecture, "
        f"and bundle budgets (JS {javascript_bytes}, CSS {css_bytes}, HTML {html_bytes} bytes)."
    )


if __name__ == "__main__":
    main()
