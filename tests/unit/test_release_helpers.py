from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_CHECK_TAG_VERSION = Path("scripts/release/check_tag_version.py")
_SMOKE_TEST = Path("scripts/release/smoke_test_installed_package.py")


def _write_pyproject(path: Path, version: str) -> None:
    path.write_text(
        "[project]\n"
        'name = "tracewise"\n'
        f'version = "{version}"\n',
        encoding="utf-8",
    )


def test_check_tag_version_accepts_matching_release_tag(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    _write_pyproject(pyproject, "1.2.3")

    result = subprocess.run(
        [sys.executable, str(_CHECK_TAG_VERSION), "v1.2.3", str(pyproject)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "1.2.3"


def test_check_tag_version_accepts_full_git_ref(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    _write_pyproject(pyproject, "1.2.3")

    result = subprocess.run(
        [sys.executable, str(_CHECK_TAG_VERSION), "refs/tags/v1.2.3", str(pyproject)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "1.2.3"


def test_check_tag_version_rejects_non_release_tag(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    _write_pyproject(pyproject, "1.2.3")

    result = subprocess.run(
        [sys.executable, str(_CHECK_TAG_VERSION), "main", str(pyproject)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert 'Expected a tag like "vX.Y.Z" or "refs/tags/vX.Y.Z"' in result.stderr


def test_check_tag_version_rejects_version_mismatch(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    _write_pyproject(pyproject, "1.2.3")

    result = subprocess.run(
        [sys.executable, str(_CHECK_TAG_VERSION), "v1.2.4", str(pyproject)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert 'Tag version "1.2.4" does not match package version "1.2.3"' in result.stderr


def test_smoke_test_script_initializes_tracewise():
    result = subprocess.run(
        [sys.executable, str(_SMOKE_TEST)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "artifact smoke ok"
