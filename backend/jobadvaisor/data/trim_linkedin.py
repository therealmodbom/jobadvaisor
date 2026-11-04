"""One-off repair: cut the LinkedIn postings stored before the intake cut (`linkedin-posting-body`)
down to the posting description and criteria block, without fetching the pages again.

    python -m jobadvaisor.data.trim_linkedin <data repository>           # dry run
    python -m jobadvaisor.data.trim_linkedin <data repository> --apply   # write the changes
"""

import argparse
from dataclasses import dataclass, field
from pathlib import Path

from jobadvaisor.data.writer import read_posting, update_posting
from jobadvaisor.intake.fetch import is_linkedin

START_MARKER = "Report this job"  # the description starts on the next line
END_MARKER = "Referrals increase your chances"  # the criteria block ends on the line before
SIGN_IN_START = "Use AI to assess how you fit"  # first line of the sign-in block after the marker
SIGN_IN_END = "By clicking Continue to join or sign in"  # ends each of the block's three prompts
SIGN_IN_WINDOW = 20  # lines; the block is 17 long
POSTER_START = "Direct message the job poster from"


@dataclass
class Report:
    """`trimmed` holds `(posting ID, characters before, characters after)`; `unchanged` the IDs
    of LinkedIn postings whose text does not show the whole-page layout."""

    trimmed: list[tuple[str, int, int]] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)


def trim_text(text: str) -> str | None:
    """The lines of a whole LinkedIn page text between the line `START_MARKER` and the first
    line starting with `END_MARKER` after it, without the sign-in block (`SIGN_IN_START` through
    its last `SIGN_IN_END` line) and the job poster block (`POSTER_START`, the poster's name
    twice and a headline) that some pages show there. `None` when a marker is missing, a poster
    block has another shape, or nothing is left."""
    lines = text.splitlines()
    try:
        start = lines.index(START_MARKER) + 1
        end = next(i for i in range(start, len(lines)) if lines[i].startswith(END_MARKER))
    except (ValueError, StopIteration):
        return None
    lines = lines[start:end]
    if lines[:1] == [SIGN_IN_START]:
        ends = [i for i, line in enumerate(lines[:SIGN_IN_WINDOW]) if line.startswith(SIGN_IN_END)]
        lines = lines[ends[-1] + 1:] if ends else lines
    poster = next((i for i, line in enumerate(lines) if line.startswith(POSTER_START)), None)
    if poster is not None:
        if lines[poster + 1:poster + 2] != lines[poster + 2:poster + 3] or len(lines) < poster + 4:
            return None
        del lines[poster:poster + 4]
    return "\n".join(lines) if lines else None


def trim_repository(root: Path, apply: bool) -> Report:
    """Trim the text of every LinkedIn posting (a URL on linkedin.com) under `root` that shows
    the whole-page layout. With `apply` False nothing is written. Title, company, location and
    every other field stay as they are."""
    report = Report()
    for path in sorted((root / "postings").glob("*.json")):
        posting = read_posting(root, path.stem)
        if not any(is_linkedin(url) for url in posting.urls):
            continue
        trimmed = trim_text(posting.text)
        if trimmed is None:
            report.unchanged.append(path.stem)
            continue
        report.trimmed.append((path.stem, len(posting.text), len(trimmed)))
        if apply:
            update_posting(root, path.stem, {"text": trimmed})
    return report


def main(argv: list[str] | None = None) -> None:
    """Command-line entry: print the report, one line per posting; a dry run unless `--apply`."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("repository", type=Path, help="data repository holding postings/")
    parser.add_argument("--apply", action="store_true", help="write the trimmed texts")
    args = parser.parse_args(argv)
    report = trim_repository(args.repository, args.apply)
    verb = "trimmed" if args.apply else "would trim"
    for name, before, after in report.trimmed:
        print(f"{verb} {name}: {before} -> {after} characters")
    for name in report.unchanged:
        print(f"unchanged {name}: no whole-page layout")
    print(f"{len(report.trimmed)} {verb}, {len(report.unchanged)} unchanged")


if __name__ == "__main__":
    main()
