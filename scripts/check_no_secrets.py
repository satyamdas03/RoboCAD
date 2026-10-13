#!/usr/bin/env python3
"""Advisory scan for likely secrets in staged or tracked files.

Returns 0 after printing warnings so it can be used as a non-blocking
pre-commit hook. Run manually with --all to check the whole repository.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# Patterns that strongly suggest a secret or credential.
# Env-key patterns capture the value after the '=' so we can ignore placeholders.
PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"ANTHROPIC_API_KEY\s*=\s*(['\"]?)([^\s'\"]+)\1"), "ANTHROPIC_API_KEY"),
    (re.compile(r"NVIDIA_API_KEY\s*=\s*(['\"]?)([^\s'\"]+)\1"), "NVIDIA_API_KEY"),
    (re.compile(r"LIVEKIT_API_SECRET\s*=\s*(['\"]?)([^\s'\"]+)\1"), "LIVEKIT_API_SECRET"),
    (re.compile(r"ONSHAPE_SECRET_KEY\s*=\s*(['\"]?)([^\s'\"]+)\1"), "ONSHAPE_SECRET_KEY"),
    (re.compile(r"sk-ant-[a-zA-Z0-9-_]{20,}"), "Anthropic secret key"),
    (re.compile(r"sk-or-[a-zA-Z0-9-_]{20,}"), "OpenRouter secret key"),
    (re.compile(r"ghp_[a-zA-Z0-9]{36}"), "GitHub personal access token"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key id"),
    (re.compile(r"BEGIN (RSA|EC|DSA|OPENSSH) PRIVATE KEY"), "private key block"),
]

# Placeholder values that are safe to ignore in env-key matches.
_PLACEHOLDER_RE = re.compile(r"\.{3,}|your_|example|test-|placeholder|<.*>|\$\{.*\}")

# Paths/files that are expected to contain placeholder secret names and should be skipped.
SKIP_PATHS = {
    ".claude",
    "dossiers",
    "memory",
    "tests",
}
SKIP_FILES = {
    "check_no_secrets.py",
    "pre-commit",
    ".env.example",
    "README.md",
}


def _file_list(staged: bool) -> list[str]:
    if staged:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            print(f"Warning: failed to list staged files: {result.stderr.strip()}", file=sys.stderr)
            return []
        return [line for line in result.stdout.splitlines() if line]

    result = subprocess.run(
        ["git", "ls-files"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(f"Warning: failed to list tracked files: {result.stderr.strip()}", file=sys.stderr)
        return []
    return [line for line in result.stdout.splitlines() if line]


def _is_text_file(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            chunk = f.read(4096)
    except OSError:
        return False
    if b"\0" in chunk:
        return False
    return True


def _should_skip_path(rel: str) -> bool:
    parts = Path(rel).parts
    return any(part in SKIP_PATHS for part in parts) or Path(rel).name in SKIP_FILES


def scan(paths: list[str]) -> int:
    repo_root = Path(__file__).resolve().parent.parent
    findings = 0
    for rel in paths:
        if _should_skip_path(rel):
            continue
        path = repo_root / rel
        if not path.is_file() or not _is_text_file(path):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = text.splitlines()
        for lineno, line in enumerate(lines, start=1):
            for pattern, label in PATTERNS:
                match = pattern.search(line)
                if not match:
                    continue
                # For env-key patterns, group 2 is the captured value; ignore placeholders.
                if len(match.groups()) >= 2:
                    value = match.group(2)
                    if value and _PLACEHOLDER_RE.search(value):
                        continue
                print(f"[secret-scan] {rel}:{lineno}: possible {label}")
                findings += 1
                break
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Advisory secret scan.")
    parser.add_argument("--staged", action="store_true", help="scan staged files only")
    parser.add_argument("--all", action="store_true", help="scan all tracked files")
    args = parser.parse_args()

    staged = args.staged or not args.all
    paths = _file_list(staged=staged)
    if not paths:
        print("No files to scan.")
        return 0

    findings = scan(paths)
    if findings:
        print(
            f"\nAdvisory: found {findings} possible secret-like value(s). "
            "If any value is a real credential, rotate it immediately and do not commit it.",
            file=sys.stderr,
        )
    else:
        print("No obvious secret-like values found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
