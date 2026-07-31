"""Estimate how many SPIE pages a markdown document will occupy, and where to cut.

Round two review, concern N7: the supplemental has grown with every revision and the
limit is 2 to 4 pages excluding acknowledgements and references but NOT excluding
tables. Discovering an overflow while building the PDF on 4 August is the failure mode
this exists to prevent.

This is an ESTIMATE, not a typesetter. It simulates line wrapping at the real column
width and charges realistic vertical space per element. It is calibrated to be slightly
pessimistic, because being told to cut and not needing to is cheap, and the reverse is
not. Build the real PDF from the SPIE template before submitting; this only tells you
whether to expect trouble and which section is responsible.

SPIE manuscript geometry, letter:
  margins   0.88 in left and right, 1.0 in top, 1.25 in bottom
  text area 6.74 in wide, 8.75 in tall
  body      10 pt Times New Roman, single spaced, one column

Usage:  python scripts/estimate_pages.py docs/spie2027/supplemental.md
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

TEXT_W_IN = 8.5 - 0.88 * 2
TEXT_H_IN = 11.0 - 1.0 - 1.25
PT = 1.0 / 72.0

BODY_PT = 10.0
LINE_PT = 12.0                      # single spaced 10 pt
# Times at 10 pt averages close to 0.5 em per character over mixed English text.
CHAR_W_IN = 0.5 * BODY_PT * PT
CPL = int(TEXT_W_IN / CHAR_W_IN)    # characters per line
LPP = TEXT_H_IN / (LINE_PT * PT)    # lines per page

# vertical cost in body lines
COST_BLANK = 0.5
COST_H1 = 3.0
COST_H2 = 2.5
COST_H3 = 2.0
COST_TABLE_ROW = 1.15               # rows are tighter but carry rule spacing
COST_TABLE_PAD = 1.2                # space above and below a table
COST_LIST_ITEM_EXTRA = 0.15
COST_FIGURE = 18.0                  # an embedded figure at column width, plus its gap


def strip_md(s: str) -> str:
    s = re.sub(r"`([^`]*)`", r"\1", s)
    s = re.sub(r"\*\*([^*]*)\*\*", r"\1", s)
    s = re.sub(r"\*([^*]*)\*", r"\1", s)
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
    return s


def measure(md: str, cpl: int = CPL):
    """Return (total_lines, per_section_lines) in body-line units.

    Paragraphs are JOINED before wrapping. The markdown source is hard wrapped at about
    88 characters and the SPIE column holds about 97, so measuring source lines counts
    the author's line breaks rather than the typeset ones. A first version did exactly
    that, which showed up as the sensitivity range collapsing to a single value: every
    source line was already shorter than every candidate column width, so varying the
    column width changed nothing. That is the signature of measuring the wrong thing.
    """
    lines = md.splitlines()
    total = 0.0
    section = "preamble"
    per = {}
    in_table = False
    stop = False
    para: list[str] = []

    def flush():
        nonlocal para
        if not para:
            return
        body = " ".join(para)
        n = max(1, -(-len(body) // cpl))
        if re.match(r"^\s*([-*]|\d+\.)\s", para[0]):
            n += COST_LIST_ITEM_EXTRA
        nonlocal total
        total += n
        per[section] = per.get(section, 0.0) + n
        para = []

    for raw in lines:
        s = raw.rstrip()
        # the limit excludes acknowledgements and references
        if re.match(r"^#{1,3}\s+.*(references|acknowledge)", s, re.I):
            stop = True
        if stop:
            continue

        # An embedded figure occupies real page height that no amount of text
        # counting will see. Charge it: a 7.0 x 4.4 in figure scaled to the 6.74 in
        # column is about 4.2 in tall, which is 25 body lines at 12 pt, plus a caption.
        m_img = re.match(r"^\s*!\[[^\]]*\]\(([^)]*)\)", s)
        if m_img:
            flush()
            total += COST_FIGURE
            per[section] = per.get(section, 0.0) + COST_FIGURE
            continue

        if re.match(r"^\s*\|", s):
            flush()
            if not in_table:
                total += COST_TABLE_PAD
                per[section] = per.get(section, 0.0) + COST_TABLE_PAD
                in_table = True
            if re.match(r"^\s*\|[\s:|-]+\|?\s*$", s):
                continue                       # the ---|--- separator draws a rule
            total += COST_TABLE_ROW
            per[section] = per.get(section, 0.0) + COST_TABLE_ROW
            continue
        if in_table:
            in_table = False
            total += COST_TABLE_PAD
            per[section] = per.get(section, 0.0) + COST_TABLE_PAD

        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            flush()
            depth = len(m.group(1))
            section = strip_md(m.group(2))[:52]
            cost = {1: COST_H1, 2: COST_H2}.get(depth, COST_H3)
            total += cost
            per[section] = per.get(section, 0.0) + cost
            continue

        if not s.strip():
            flush()
            total += COST_BLANK
            per[section] = per.get(section, 0.0) + COST_BLANK
            continue

        if re.match(r"^\s*([-*]|\d+\.)\s", s):
            flush()                            # a new list item starts a new block
        body = strip_md(s)
        body = re.sub(r"^\s*[-*>]\s+", "", body)
        body = re.sub(r"^\s*\d+\.\s+", "", body)
        para.append(body)
    flush()
    return total, per


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--limit", type=float, default=4.0)
    a = ap.parse_args(argv)
    p = Path(a.path)
    md = p.read_text(encoding="utf-8")
    total, per = measure(md, CPL)
    pages = total / LPP

    print("geometry : %.2f x %.2f in text area, %d chars per line, %.1f lines per page"
          % (TEXT_W_IN, TEXT_H_IN, CPL, LPP))
    print("document : %s" % p.name)
    print("body     : %.0f line-equivalents, excluding references and acknowledgements"
          % total)
    print("estimate : %.2f pages against a limit of %.0f" % (pages, a.limit))

    # A single number here would be false precision. The dominant unknown is the average
    # character width of Times at 10 pt, which for English prose runs about 0.46 to 0.52
    # em depending on the text. Report the resulting range so the reader knows whether
    # the answer is "clearly over" or "too close to call without building it".
    widths = [measure(md, int(TEXT_W_IN / (em * BODY_PT * PT)))[0] / LPP
              for em in (0.46, 0.52)]
    lo_pages, hi_pages = min(widths), max(widths)
    print("range    : %.2f to %.2f pages, varying Times average width 0.46 to 0.52 em"
          % (lo_pages, hi_pages))

    over = pages - a.limit
    if lo_pages > a.limit:
        print("           OVER on every assumption. Cut roughly %.0f lines."
              % ((pages - a.limit) * LPP))
    elif hi_pages > a.limit:
        print("           TOO CLOSE TO CALL. Build the PDF before deciding.")
    else:
        print("           fits on every assumption, %.2f pages of headroom" % (-over))

    print("\nwhere the space goes:")
    for k, v in sorted(per.items(), key=lambda kv: -kv[1]):
        if v < 2:
            continue
        print("  %6.1f lines  %4.1f%%  %s" % (v, 100.0 * v / total, k))

    print("\nThis is an estimate. Build the real PDF from the SPIE template before")
    print("submitting. It is calibrated slightly pessimistic on purpose.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
