from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
import tomllib

_TAG_PATTERN = re.compile(r"^(?:refs/tags/)?v(?P<version>\d+\.\d+\.\d+)$")


def extract_tag_version(value: str) -> str:
    match = _TAG_PATTERN.fullmatch(value)
    if match is None:
        raise ValueError('Expected a tag like "vX.Y.Z" or "refs/tags/vX.Y.Z"')
    return match.group("version")


def read_package_version(pyproject_path: Path) -> str:
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    return data["project"]["version"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("tag")
    parser.add_argument("pyproject_path", nargs="?", default="pyproject.toml")
    args = parser.parse_args(argv)

    try:
        tag_version = extract_tag_version(args.tag)
        package_version = read_package_version(Path(args.pyproject_path))
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if tag_version != package_version:
        print(
            f'Tag version "{tag_version}" does not match package version "{package_version}"',
            file=sys.stderr,
        )
        return 1

    print(tag_version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
