# Storage cost: presentation state versus segmentation

Measured 2026-07-31 in response to adversarial review Comment 6, which correctly
objected that the paper's only practical argument for presentation states rested on a
cited storage claim rather than a measured one, and that the citation could not be
located.

Reproduce: read the byte sizes of the emitted objects in `runs/seg_demo/canonical/`
and `runs/public_gsps_v3/`. No analysis, just `os.path.getsize`.

## Measured

| object | KB | frames | segments or labels | encodes |
|---|---:|---:|---:|---|
| `sub-gl003_dir-ax_SEG.dcm` | 11,243 | 345 | 12 | voxel masks |
| `sub-verse525_dir-sag_SEG.dcm` | 15,719 | 203 | 6 | voxel masks |
| `sub-verse505_SEG.dcm` | 19,542 | 598 | 10 | voxel masks |
| conformant GSPS, public | **12** | n/a | 19 | 19 text labels, 19 leader lines |

Across all nine GSPS variants: mean 11.1 KB, range 9.1 to 13.6 KB.
Across the three SEG objects: mean 15,501 KB, range 11,243 to 19,542 KB.

**Ratio of means: about 1300 to 1.**

## What this does and does not show

**It is not a like-for-like comparison, and must not be presented as one.** The two
object classes encode different things. A Segmentation carries per-voxel extents for
every segment across hundreds of frames. A presentation state carries a label string
and a two-point line per vertebra. The size difference is not overhead; it is the
information content.

The defensible claim is narrower and is the one the paper needs: **for the specific
task of conveying per-vertebra level labels with a per-vertebra quality flag, a
presentation state costs about 12 KB and a segmentation costs about 15 MB, because a
segmentation must carry voxel extents that this task does not use.** If the receiving
application needs the masks for anything else, that cost is not waste and the
comparison does not apply.

Two further caveats. The GSPS and SEG objects here are from different cases, since no
case currently has both; the three orders of magnitude are far larger than any
plausible case-to-case variation, but a same-case pair would be cleaner and is cheap
to produce. And the SEG objects are BINARY segmentation type without compression, so a
compressed transfer syntax would narrow the gap, though not by three orders of
magnitude.

## Effect on the paper

This replaces a cited claim with a measured one and strengthens it. The earlier text
cited a conference abstract reporting roughly 50 percent storage reduction for
presentation states over secondary capture, a different comparison entirely, and that
citation could not be verified. Drop it and cite this measurement instead.

It also gives the paper a defensible answer to the reviewer's sharpest question, which
is why a reader should not simply use Segmentation given that Segmentation is measured
here as strictly more conformant. The answer is now evidenced rather than asserted: use
Segmentation when the receiver needs voxel extents, and a presentation state when it
needs only to draw labels, where it is three orders of magnitude cheaper and needs no
segmentation support in the viewer.
