#!/usr/bin/env python3
"""Validate Keep a Changelog format and extract release notes for a given version."""

import argparse
import pathlib
import re
import sys

SECTION_HEADER_RE = re.compile(r"^##\s+\[([^\]]+)\](.*)$")
SEMVER_RE = re.compile(r"^v?\d+\.\d+\.\d+(?:[.-][0-9A-Za-z.+-]+)?$")
DATE_SUFFIX_RE = re.compile(r"^\s*(?:-\s*\d{4}-\d{2}-\d{2})?\s*$")
REF_LINK_RE = re.compile(r"^\[[^\]]+\]:\s+https?://")


def _normalize_version(ver):
    return ver.strip().lstrip("vV")


def validate_changelog(path):
    """Validate CHANGELOG.md structure. Returns list of error messages."""
    errors = []
    if not path.is_file():
        return [f"Changelog file not found: {path}"]

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    if not any(line.strip() == "# Changelog" for line in lines):
        errors.append("Missing top-level '# Changelog' heading.")

    seen = set()
    has_unreleased = False

    for lineno, line in enumerate(lines, start=1):
        match = SECTION_HEADER_RE.match(line)
        if not match:
            continue

        raw_label = match.group(1).strip()
        suffix = match.group(2)

        if raw_label.lower() == "unreleased":
            if has_unreleased:
                errors.append(f"Line {lineno}: duplicate '[Unreleased]' section.")
            has_unreleased = True
            if suffix.strip():
                errors.append(f"Line {lineno}: '[Unreleased]' heading should not have trailing text: {suffix!r}")
            continue

        if not SEMVER_RE.match(raw_label):
            errors.append(
                f"Line {lineno}: invalid version heading '[{raw_label}]' (expected SemVer like [0.1.0])."
            )
            continue

        if not DATE_SUFFIX_RE.match(suffix):
            errors.append(
                f"Line {lineno}: invalid heading suffix {suffix!r} (expected optional '- YYYY-MM-DD')."
            )

        norm = _normalize_version(raw_label)
        if norm in seen:
            errors.append(f"Line {lineno}: duplicate version section '[{norm}]'.")
        seen.add(norm)

    if not has_unreleased:
        errors.append("Missing '## [Unreleased]' section.")

    return errors


def extract_version_notes(path, target_version):
    """Return markdown body for target_version, or None if not found/empty."""
    if not path.is_file():
        return None

    target_norm = _normalize_version(target_version)
    lines = path.read_text(encoding="utf-8").splitlines()

    capturing = False
    collected = []

    for line in lines:
        match = SECTION_HEADER_RE.match(line)
        if match:
            if capturing:
                break
            label = match.group(1).strip()
            if label.lower() != "unreleased" and _normalize_version(label) == target_norm:
                capturing = True
            continue

        if capturing:
            if REF_LINK_RE.match(line):
                break
            collected.append(line)

    if not capturing:
        return None

    body = "\n".join(collected).strip()
    return body if body else None


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate and extract entries from CHANGELOG.md")
    parser.add_argument("--changelog", default="CHANGELOG.md", help="Path to CHANGELOG.md")
    parser.add_argument("--validate", action="store_true", help="Validate CHANGELOG.md format")
    parser.add_argument("--version", default="", help="Version to extract (e.g. 0.1.0 or v0.1.0)")
    parser.add_argument("--output", default="", help="Optional output file path for extracted notes")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero if version section is missing")
    args = parser.parse_args(argv)

    changelog_path = pathlib.Path(args.changelog)

    if args.validate:
        errors = validate_changelog(changelog_path)
        if errors:
            for err in errors:
                print(f"[CHANGELOG ERROR] {err}", file=sys.stderr)
            return 1
        print(f"[CHANGELOG OK] {changelog_path}")
        if not args.version:
            return 0

    if not args.version:
        parser.error("Provide --validate and/or --version.")

    ver_clean = _normalize_version(args.version)
    notes = extract_version_notes(changelog_path, ver_clean)
    if notes is None:
        msg = f"No changelog entry found for version '{ver_clean}' in {changelog_path}."
        if args.strict:
            print(f"[CHANGELOG ERROR] {msg}", file=sys.stderr)
            return 1
        print(f"::warning::{msg}", file=sys.stderr)
        notes = f"- 本次發佈（`v{ver_clean}`）尚未於 `CHANGELOG.md` 填寫專屬更新日誌，請參考 GitHub Commit / PR 紀錄。"

    output_text = notes + "\n"
    if args.output:
        pathlib.Path(args.output).write_text(output_text, encoding="utf-8")
    else:
        sys.stdout.write(output_text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
