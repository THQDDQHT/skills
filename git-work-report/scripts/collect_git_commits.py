#!/usr/bin/env python3
"""
Collect Git commits from one or more repositories within a date range.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

DEFAULT_AUTHOR_PATTERNS = [
    "heqidong",
    "何啟东",
    "soft_nts.localheqidong",
    "heqidong@cet-electric.com",
]

IGNORED_DIR_NAMES = {
    ".ace-tool",
    ".cache",
    ".claude",
    ".codex",
    ".cursor",
    ".git",
    ".idea",
    ".next",
    ".nuxt",
    ".pnpm-store",
    ".specify",
    ".svn",
    ".turbo",
    ".vscode",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "target",
}

FIELD_SEPARATOR = "\x1f"
RECORD_SEPARATOR = "\x1e"
MAX_SCAN_DEPTH = 3
SHANGHAI_TZ = timezone(timedelta(hours=8))


@dataclass(frozen=True)
class CommitRecord:
    repo_name: str
    repo_path: str
    hash: str
    author_name: str
    author_email: str
    date: str
    subject: str
    body: str
    sort_key: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect Git commits from multiple repositories as JSON."
    )
    parser.add_argument(
        "--root",
        required=True,
        help="Workspace root used for repository discovery.",
    )
    parser.add_argument(
        "--since",
        required=True,
        help="Start date in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--until",
        required=True,
        help="End date in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--repo",
        action="append",
        default=[],
        help="Optional repository path. Repeat to limit the scan to specific repos.",
    )
    parser.add_argument(
        "--author",
        action="append",
        default=[],
        help="Optional case-insensitive substring used to match author name or email. Repeat to override defaults.",
    )
    return parser.parse_args()


def parse_iso_date(raw_value: str, flag_name: str) -> date:
    try:
        return date.fromisoformat(raw_value)
    except ValueError as exc:
        raise SystemExit(f"{flag_name} must be a valid YYYY-MM-DD date: {raw_value}") from exc


def build_git_range(day_value: date, end_of_day: bool) -> str:
    clock = time(23, 59, 59) if end_of_day else time(0, 0, 0)
    return datetime.combine(day_value, clock, tzinfo=SHANGHAI_TZ).isoformat()


def run_git_command(args: list[str]) -> str:
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip() or "unknown git error"
        raise RuntimeError(stderr)
    return result.stdout


def discover_repositories(root: Path) -> list[Path]:
    repos: list[Path] = []

    for current_root, dir_names, file_names in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current_root)
        try:
            depth = len(current_path.relative_to(root).parts)
        except ValueError:
            continue

        if depth > MAX_SCAN_DEPTH:
            dir_names[:] = []
            continue

        has_git_dir = ".git" in dir_names
        has_git_file = ".git" in file_names
        dir_names[:] = [
            entry
            for entry in dir_names
            if entry not in IGNORED_DIR_NAMES and not entry.startswith(".venv")
        ]

        if has_git_dir or has_git_file:
            repos.append(current_path.resolve())
            dir_names[:] = []

    return sorted(set(repos), key=str)


def resolve_repository(repo_value: str) -> Path:
    repo_path = Path(repo_value).expanduser().resolve()
    if not repo_path.exists():
        raise RuntimeError(f"Repository path does not exist: {repo_path}")

    top_level = run_git_command(
        ["git", "-C", str(repo_path), "rev-parse", "--show-toplevel"]
    ).strip()
    return Path(top_level).resolve()


def author_matches(author_name: str, author_email: str, patterns: list[str]) -> bool:
    normalized_target = f"{author_name} <{author_email}>".lower()
    return any(pattern.lower() in normalized_target for pattern in patterns)


def parse_git_log_output(repo_path: Path, raw_output: str) -> list[CommitRecord]:
    commits: list[CommitRecord] = []

    for raw_record in raw_output.split(RECORD_SEPARATOR):
        record = raw_record.strip("\r\n")
        if not record:
            continue

        parts = record.split(FIELD_SEPARATOR, 5)
        if len(parts) != 6:
            raise RuntimeError(
                f"Unexpected git log format while parsing repository: {repo_path}"
            )

        commit_hash, author_name, author_email, authored_iso, subject, body = parts
        commits.append(
            CommitRecord(
                repo_name=repo_path.name,
                repo_path=str(repo_path),
                hash=commit_hash,
                author_name=author_name.strip(),
                author_email=author_email.strip(),
                date=authored_iso[:10],
                subject=subject.strip(),
                body=body.strip(),
                sort_key=authored_iso,
            )
        )

    return commits


def collect_repo_commits(
    repo_path: Path,
    since_iso: str,
    until_iso: str,
    author_patterns: list[str],
) -> list[CommitRecord]:
    format_string = (
        f"%H{FIELD_SEPARATOR}%an{FIELD_SEPARATOR}%ae{FIELD_SEPARATOR}"
        f"%aI{FIELD_SEPARATOR}%s{FIELD_SEPARATOR}%b{RECORD_SEPARATOR}"
    )

    raw_output = run_git_command(
        [
            "git",
            "-C",
            str(repo_path),
            "log",
            "--no-merges",
            f"--since={since_iso}",
            f"--until={until_iso}",
            f"--pretty=format:{format_string}",
        ]
    )

    commits = parse_git_log_output(repo_path, raw_output)
    return [
        commit
        for commit in commits
        if author_matches(commit.author_name, commit.author_email, author_patterns)
    ]


def serialize_output(
    root: Path,
    since_value: date,
    until_value: date,
    author_patterns: list[str],
    repository_paths: list[Path],
    commit_records: list[CommitRecord],
) -> dict:
    sorted_commits = sorted(
        commit_records,
        key=lambda record: (record.sort_key, record.repo_name, record.hash),
    )
    repo_paths_with_matches = sorted({record.repo_path for record in sorted_commits})

    return {
        "stats": {
            "root": str(root),
            "since": since_value.isoformat(),
            "until": until_value.isoformat(),
            "author_patterns": author_patterns,
            "repositories_scanned": len(repository_paths),
            "repositories_with_matches": len(repo_paths_with_matches),
            "commits_collected": len(sorted_commits),
            "repository_paths": [str(path) for path in repository_paths],
        },
        "commits": [
            {
                "repo_name": record.repo_name,
                "repo_path": record.repo_path,
                "hash": record.hash,
                "author_name": record.author_name,
                "author_email": record.author_email,
                "date": record.date,
                "subject": record.subject,
                "body": record.body,
            }
            for record in sorted_commits
        ],
    }


def main() -> int:
    args = parse_args()

    root = Path(args.root).expanduser().resolve()
    if not root.exists():
        raise SystemExit(f"--root path does not exist: {root}")
    if not root.is_dir():
        raise SystemExit(f"--root must be a directory: {root}")

    since_value = parse_iso_date(args.since, "--since")
    until_value = parse_iso_date(args.until, "--until")
    if until_value < since_value:
        raise SystemExit("--until must be greater than or equal to --since")

    author_patterns = args.author or DEFAULT_AUTHOR_PATTERNS
    if not author_patterns:
        raise SystemExit("At least one author pattern is required")

    if args.repo:
        repository_paths = sorted(
            {resolve_repository(repo_value) for repo_value in args.repo},
            key=str,
        )
    else:
        repository_paths = discover_repositories(root)

    since_iso = build_git_range(since_value, end_of_day=False)
    until_iso = build_git_range(until_value, end_of_day=True)

    commit_records: list[CommitRecord] = []
    for repo_path in repository_paths:
        commit_records.extend(
            collect_repo_commits(repo_path, since_iso, until_iso, author_patterns)
        )

    output = serialize_output(
        root=root,
        since_value=since_value,
        until_value=until_value,
        author_patterns=author_patterns,
        repository_paths=repository_paths,
        commit_records=commit_records,
    )
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
