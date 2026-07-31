"""Two hard project rules, enforced instead of remembered.

From CLAUDE.md, verbatim: "No em-dashes in any file, comment, or document.
Commas, colons, or recast. En-dashes in numeric ranges are fine." And: "aycan is
always lowercase."

Both are the kind of thing that is easy to state and impossible to hold by hand
across a repository that several people are writing at once, which is exactly
what a test is for. These scan every tracked .py and .md in the repository, so a
failure here may point at a file this suite does not otherwise touch. The
failure message names the file and line.
"""
from __future__ import annotations

import pytest

from spinelab import paths

# Written as an escape on purpose. A literal character here would make this file
# its own first offender.
EM_DASH = "\u2014"
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".ruff_cache", ".venv",
             "node_modules"}


def _sources():
    for pattern in ("*.py", "*.md"):
        for p in sorted(paths.REPO.rglob(pattern)):
            if SKIP_DIRS & set(p.parts):
                continue
            yield p


@pytest.fixture(scope="module")
def sources():
    files = list(_sources())
    assert files, "no .py or .md found under %s" % paths.REPO
    return files


def test_no_em_dash_anywhere(sources):
    offenders = []
    for p in sources:
        text = p.read_text(encoding="utf-8", errors="replace")
        for ln_no, line in enumerate(text.splitlines(), 1):
            if EM_DASH in line:
                offenders.append("%s:%d %s"
                                 % (p.relative_to(paths.REPO), ln_no, line.strip()[:90]))
    assert not offenders, "em-dash present, use a comma, a colon, or recast:\n%s" % (
        "\n".join(offenders))


def test_aycan_is_always_lowercase(sources):
    """AYCANSTORE3 is an ImplementationVersionName copied verbatim, so exempt."""
    offenders = []
    for p in sources:
        text = p.read_text(encoding="utf-8", errors="replace")
        for ln_no, line in enumerate(text.splitlines(), 1):
            low = line.lower()
            i = low.find("aycan")
            while i != -1:
                if line[i:i + 5] != "aycan" and not line[i:].startswith("AYCANSTORE"):
                    offenders.append("%s:%d %s"
                                     % (p.relative_to(paths.REPO), ln_no, line.strip()[:90]))
                i = low.find("aycan", i + 1)
    assert not offenders, "aycan must be lowercase:\n%s" % "\n".join(offenders)


def test_no_tab_indentation_in_python_sources():
    offenders = []
    for p in sorted((paths.REPO / "src").rglob("*.py")):
        for ln_no, line in enumerate(p.read_text(errors="replace").splitlines(), 1):
            if line.startswith("\t"):
                offenders.append("%s:%d" % (p.relative_to(paths.REPO), ln_no))
    assert not offenders, offenders
