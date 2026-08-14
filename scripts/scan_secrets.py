from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_PARTS = {
    ".git",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "dist",
    "node_modules",
    "playwright-report",
    "test-results",
    "work",
}
MAX_TEXT_BYTES = 2 * 1024 * 1024
PLACEHOLDER_WORDS = ("change-me", "example", "paste", "placeholder", "replace", "your-")

STRONG_PATTERNS = {
    "private-key-material": re.compile(re.escape("-----BEGIN " + "PRIVATE KEY-----")),
    "google-api-key": re.compile("AI" + r"za[0-9A-Za-z_-]{35}"),
    "github-token": re.compile("gh" + r"[ps]_[0-9A-Za-z]{36,}"),
    "github-fine-grained-token": re.compile("github" + r"_pat_[0-9A-Za-z_]{40,}"),
    "slack-token": re.compile("xo" + r"x[baprs]-[0-9A-Za-z-]{20,}"),
    "service-account-private-key": re.compile(
        r'"private' + r'_key"\s*:\s*"(?!\[REDACTED\])[^"\r\n]{24,}"'
    ),
}
ENV_ASSIGNMENT = re.compile(
    r"^\s*(GOOGLE_API_KEY|TULINA_KMS_PRIVATE_KEY|GITHUB_TOKEN|DEVPOST_TOKEN)\s*=\s*(.*?)\s*$",
    re.IGNORECASE,
)


def candidate_files() -> list[Path]:
    rows: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in SKIP_PARTS for part in path.parts):
            continue
        try:
            if path.stat().st_size <= MAX_TEXT_BYTES:
                rows.append(path)
        except OSError:
            continue
    return rows


def is_placeholder(value: str) -> bool:
    normalized = value.strip().strip('"\'').casefold()
    return (
        not normalized
        or normalized.startswith(("$", "<", "{"))
        or any(word in normalized for word in PLACEHOLDER_WORDS)
    )


def main() -> None:
    findings: list[tuple[str, int, str]] = []
    for path in candidate_files():
        try:
            raw = path.read_bytes()
            if b"\x00" in raw:
                continue
            text = raw.decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        relative = path.relative_to(ROOT).as_posix()
        for line_number, line in enumerate(text.splitlines(), start=1):
            assignment = ENV_ASSIGNMENT.match(line)
            if assignment and not is_placeholder(assignment.group(2)):
                findings.append((relative, line_number, "non-placeholder secret assignment"))
            for rule, pattern in STRONG_PATTERNS.items():
                if pattern.search(line):
                    findings.append((relative, line_number, rule))
    if findings:
        print("Potential secrets detected (values intentionally suppressed):")
        for path, line, rule in findings:
            print(f"- {path}:{line} [{rule}]")
        raise SystemExit(1)
    print("Secret scan passed: no high-confidence credentials found.")


if __name__ == "__main__":
    main()
