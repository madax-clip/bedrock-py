"""Extract the CHANGELOG.md section for a release version.

Used by the release workflow (``.github/workflows/release.yml``) to gate
publishing on a non-empty release-notes section. Replaces the historical
``sed -n '/^## [X]/,/^## [/p' | sed '1d;$d'`` pipeline, which dropped the
final content line of a section running to end-of-file and could reject a
valid one-line release as "empty".

Usage:
    python scripts/extract_release_notes.py CHANGELOG.md 0.2.0 > release_notes.md

Exit code is 0 and the section body is printed when the section exists and
contains non-whitespace content; otherwise an error is printed to stderr and
the exit code is 1.
"""

import re
import sys
from pathlib import Path

SECTION_PREFIX = "## "


def extract_section(changelog_text: str, version: str) -> str | None:
    """Return the body of the ``## [version]`` changelog section.

    The body runs from the line after the section header until the next
    ``## `` heading or end-of-file, whichever comes first. A section at EOF
    therefore keeps its final content line.

    Args:
        changelog_text: Full text of the changelog file.
        version: Release version without the leading ``v`` (e.g. ``0.2.0``).

    Returns:
        The section body with leading/trailing blank lines stripped, or
        ``None`` when the version header is absent.
    """
    header_re = re.compile(rf"^## \[{re.escape(version)}\](?:\s|$)")
    body: list[str] = []
    in_section = False
    for line in changelog_text.splitlines():
        if header_re.match(line):
            in_section = True
            continue
        if in_section and line.startswith(SECTION_PREFIX):
            break
        if in_section:
            body.append(line)
    if not in_section:
        return None
    return "\n".join(body).strip("\n")


def main(argv: list[str]) -> int:
    """CLI entry point: extract a changelog section or fail the release gate."""
    if len(argv) != 3:
        print(f"usage: {Path(argv[0]).name} CHANGELOG.md VERSION", file=sys.stderr)
        return 2
    changelog_path = Path(argv[1])
    version = argv[2].lstrip("v")
    section = extract_section(changelog_path.read_text(encoding="utf-8"), version)
    if section is None or not section.strip():
        print(
            f"::error::CHANGELOG.md has no (or empty) release notes section for [{version}]. Refusing to publish.",
            file=sys.stderr,
        )
        return 1
    print(section)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
