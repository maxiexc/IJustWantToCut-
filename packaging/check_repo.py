#!/usr/bin/env python3
"""Lightweight repository & packaging sanity checks for CI and local verification."""

import ast
import pathlib
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "packaging"))
import extract_changelog  # noqa: E402


LF_REQUIRED_FILES = [
    "setup_ubuntu.sh",
    "start_ui.sh",
    "packaging/assets/ijustwanttocut.svg",
    "packaging/ubuntu/IJustWantToCut.spec",
    "packaging/ubuntu/build_deb.sh",
    "packaging/ubuntu/verify_deb.sh",
    "packaging/ubuntu/Dockerfile",
    "packaging/ubuntu/build_docker.sh",
    "packaging/windows/IJustWantToCut.spec",
]

ASCII_ONLY_FILES = [
    "packaging/windows/fetch_deps.ps1",
    "packaging/windows/build_windows.ps1",
    "packaging/windows/verify_windows.ps1",
    "packaging/windows/IJustWantToCut.iss",
    "packaging/ubuntu/build_docker.ps1",
]

SHELL_SCRIPTS = [
    "setup_ubuntu.sh",
    "start_ui.sh",
    "packaging/ubuntu/build_deb.sh",
    "packaging/ubuntu/verify_deb.sh",
    "packaging/ubuntu/build_docker.sh",
]


def main():
    errors = []

    # 1. PyInstaller spec Python AST checks
    for rel in ("packaging/ubuntu/IJustWantToCut.spec", "packaging/windows/IJustWantToCut.spec"):
        p = REPO_ROOT / rel
        try:
            ast.parse(p.read_text(encoding="utf-8"), filename=rel)
        except Exception as exc:
            errors.append(f"Spec AST parse failed for {rel}: {exc}")

    # 2. SVG XML & ICO header checks
    svg_path = REPO_ROOT / "packaging/assets/ijustwanttocut.svg"
    try:
        ET.fromstring(svg_path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"Invalid SVG XML in {svg_path}: {exc}")

    ico_path = REPO_ROOT / "packaging/assets/ijustwanttocut.ico"
    if not ico_path.is_file() or ico_path.read_bytes()[:4] != b"\x00\x00\x01\x00":
        errors.append(f"Invalid or missing ICO header in {ico_path}")

    # 3. LF line ending checks (including all workflow YAMLs)
    workflow_files = sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml"))
    if not workflow_files:
        errors.append("No workflow YAML files found under .github/workflows/")

    lf_targets = [REPO_ROOT / rel for rel in LF_REQUIRED_FILES] + workflow_files
    for p in lf_targets:
        if not p.is_file():
            errors.append(f"Expected file missing: {p.relative_to(REPO_ROOT)}")
            continue
        if b"\r\n" in p.read_bytes():
            errors.append(f"CRLF line endings found in {p.relative_to(REPO_ROOT)}")

    # 4. Workflow YAML checks
    try:
        import yaml
    except ImportError:
        yaml = None

    for wf in workflow_files:
        text = wf.read_text(encoding="utf-8")
        rel = wf.relative_to(REPO_ROOT)
        if "\t" in text:
            errors.append(f"Tab character found in YAML {rel}")
        if yaml is not None:
            try:
                parsed = yaml.safe_load(text)
                if not isinstance(parsed, dict) or "jobs" not in parsed:
                    errors.append(f"YAML {rel} missing top-level 'jobs' mapping")
            except Exception as exc:
                errors.append(f"YAML parse error in {rel}: {exc}")

    # 5. Pure ASCII check on Windows PowerShell / Inno Setup files (PowerShell 5.1 safety)
    for rel in ASCII_ONLY_FILES:
        p = REPO_ROOT / rel
        if not p.is_file():
            errors.append(f"Expected file missing: {rel}")
            continue
        if any(b > 127 for b in p.read_bytes()):
            errors.append(f"Non-ASCII byte found in {rel}")

    # 6. Shell syntax check (when running on Linux / macOS with bash)
    if sys.platform != "win32" and shutil.which("bash"):
        for rel in SHELL_SCRIPTS:
            p = REPO_ROOT / rel
            if not p.is_file():
                continue
            res = subprocess.run(["bash", "-n", str(p)], capture_output=True, text=True)
            if res.returncode != 0:
                errors.append(f"bash -n failed for {rel}: {res.stderr.strip()}")

    # 7. CHANGELOG.md format validation
    changelog_errors = extract_changelog.validate_changelog(REPO_ROOT / "CHANGELOG.md")
    errors.extend(f"CHANGELOG.md: {e}" for e in changelog_errors)

    if errors:
        for err in errors:
            print(f"[CHECK FAILED] {err}", file=sys.stderr)
        return 1

    print("[CHECK OK] All repository, packaging, workflow, and changelog checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
