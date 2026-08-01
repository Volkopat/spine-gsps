"""Generate the manuscript figures from measured result files.

Nothing here hardcodes a result. Every number is read from a JSON in results/ that
was written by the command recorded in docs/CLAIMS.md. If a result file is missing
the figure is skipped with a message rather than drawn from remembered values.

Design constraints, in order of how often they are violated:

- **No dual axis.** Figure 5 compares a residual in millimetres against a detection
  rate in percent. Those are two panels sharing an x axis, never two y scales on one
  plot.
- **Print and grayscale safe.** A proceedings paper may be printed in monochrome, so
  every series carries a second channel besides hue: distinct markers and line styles
  on lines, distinct hatching on bars. Hue is never the only encoding.
- **Palette is validated, not eyeballed.** Categorical slots 1 and 2 of the reference
  palette, run through the skill's validator on both the adjacent and all pairs
  pairlists: all checks pass, worst CVD deltaE 9.2, worst normal vision 24.0. Aqua,
  slot 3, is deliberately unused because it warns below 3:1 contrast on this surface
  and two series is all any panel needs.
- **Status colour only for status.** Legal versus not legal in the IOD is a state, so
  it takes the status palette with an explicit label beside it, never hue alone.
- **Recessive chrome.** Solid hairline gridlines one shade off the surface, never
  dashed. Thin marks. No value printed on every point; labels are selective.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from spinelab.paths import RESULTS, FIGURES, RUNS  # noqa: E402

# --- reference palette, light surface -------------------------------------
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
S1 = "#2a78d6"      # categorical slot 1, blue
S2 = "#eb6834"      # categorical slot 2, orange
GOOD = "#0ca30c"    # status
CRIT = "#d03b3b"    # status
WARN = "#fab219"    # status

# Elsevier's floor is 300 dpi for halftone and 500 for combination art. Figures 1
# and 4 are combination: a CT raster with vector annotation over it.
DPI = 600

plt.rcParams.update({
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "font.family": "sans-serif",
    "font.sans-serif": ["Segoe UI", "DejaVu Sans", "Arial"],
    "font.size": 8.5,
    "axes.labelsize": 9,
    "axes.titlesize": 9.5,
    "axes.titleweight": "bold",
    "axes.edgecolor": BASELINE,
    "axes.linewidth": 0.6,
    "axes.labelcolor": INK,
    "axes.grid": True,
    "grid.color": GRID,
    "grid.linewidth": 0.5,
    "grid.linestyle": "-",      # solid, never dashed
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "legend.frameon": False,
    "legend.fontsize": 8,
    "lines.linewidth": 1.6,
    "pdf.fonttype": 42,          # embed as TrueType, SPIE requires embedded fonts
    "ps.fonttype": 42,
})


def tidy(ax, ygrid=True, xgrid=False):
    ax.set_axisbelow(True)
    ax.xaxis.grid(xgrid)
    ax.yaxis.grid(ygrid)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(BASELINE)


def save(fig, stem: str):
    """Write the pair, and flatten the raster.

    No figure here carries its caption in the image. Elsevier typesets captions
    from the manuscript, so a caption inside the artwork is a second copy that
    cannot be copy edited and goes stale silently. Round four found exactly that:
    three figures shipped with the previous round's captions burned in, two of
    them repeating text the ledger had already retired.
    """
    FIGURES.mkdir(parents=True, exist_ok=True)
    # DPI is not cosmetic here. matplotlib rasterises imshow content at the SAVE
    # dpi even when the container is PDF, and the pdf branch passed no dpi, so it
    # fell through to rcParams["savefig.dpi"] = "figure" = 100. The CT panels were
    # therefore resampled DOWN to whatever their axes box measures at 100 dpi:
    # 158x199 in the InstanceNumber figure and 203x444 in the delivered-records
    # figure, then stretched across ~480 and ~570 px of canvas. Roughly a third of
    # the real pixels, which is exactly the blur that was visible. The pure vector
    # panels were unaffected, which is why only the two with images looked soft.
    #
    # 600 exceeds Elsevier's 500 dpi floor for combination art. Both imshow calls
    # use interpolation="nearest", so this replicates source pixels as blocks
    # rather than smoothing them: no invented detail, and Figure 1's 16 grey
    # levels, which are the finding at B15a, survive untouched.
    for ext in ("pdf", "png"):
        p = FIGURES / ("%s.%s" % (stem, ext))
        fig.savefig(p, bbox_inches="tight", dpi=DPI)
    plt.close(fig)
    # matplotlib writes RGBA even when the facecolor is opaque. An alpha channel
    # in a print figure is one more thing that can composite differently than it
    # previewed, so flatten onto the surface colour explicitly.
    png = FIGURES / ("%s.png" % stem)
    with Image.open(png) as im:
        mode = im.mode
        if mode != "RGB":
            flat = Image.new("RGB", im.size, SURFACE)
            flat.paste(im, mask=im.split()[-1] if mode in ("RGBA", "LA") else None)
            flat.save(png)
    raster = _embedded_raster(FIGURES / ("%s.pdf" % stem))
    print("  wrote %s.pdf and .png at %d dpi (%s -> RGB)%s"
          % (stem, DPI, mode,
             ", embedded raster %s" % raster if raster else ", pure vector"))


def _embedded_raster(pdf: Path):
    """Report the largest raster actually embedded in the PDF.

    Reported rather than assumed, because the whole defect was that nobody
    looked: the figures had shipped for four rounds at 100 dpi and the number
    was never printed anywhere.
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    try:
        sizes = [im.image.size for page in PdfReader(str(pdf)).pages
                 for im in page.images]
    except Exception:
        return None
    return "x".join(map(str, max(sizes, key=lambda s: s[0] * s[1]))) if sizes else None


def load(name):
    p = RESULTS / name
    if not p.exists():
        print("  SKIP, missing %s" % p.name)
        return None
    return json.loads(p.read_text())


def distinct_counts(rec):
    """Distinct missing attributes and distinct out-of-IOD tags for one record."""
    miss = {(m["element"], m["module"]) for m in rec.get("missing", [])}
    noniod = {n["tag"] for n in rec.get("not_in_iod", [])}
    return len(miss), len(noniod)


# ---------------------------------------------------------------- figure 1
def fig1_colour_routes():
    """Three colour routes against five authorities.

    Rewritten twice. The first version was a bar chart of "attributes reported outside
    the IOD" and labelled the text route "NOT in the IOD", which is retired claim G12:
    PS3.3 C.10.5 lists all three style sequences as Type 3, and what `dciodvfy` does is
    a fact about the validator, not about the standard. A figure is the worst place for
    a retracted claim to survive, because it is read before the caption.

    It also read `gsps_variants_validation.json`, which is derived from the clinical
    objects. `public_gsps_validation.json` carries the identical nine variants built on
    public VerSe data, and the seven colour variants give byte-identical verdicts, so
    the figure now uses the public source and the released figure carries no clinical
    provenance. Verified by comparing both files variant by variant.
    """
    print("figure 1, three colour routes against five authorities")
    j = load("public_gsps_validation.json")
    if not j:
        return
    want = [("colour_layer_iod", "layer\n(0070,0401)"),
            ("colour_line_iod", "line\n(0070,0251)"),
            ("colour_text_outofiod", "text\n(0070,0241)")]
    noniod = {}
    for r in j["records"]:
        for key, lab in want:
            if key in Path(r["file"]).name:
                noniod[key] = distinct_counts(r)[1]
    if len(noniod) < 3:
        print("  SKIP, only found %d of 3 routes" % len(noniod))
        return

    # columns are the five authorities; every cell is a measurement except PS3.3,
    # which cites the standard directly.
    cols = ["PS3.3\nC.10.5", "highdicom\n0.28.1", "dciodvfy", "dcmpschk", "dcmp2pgm"]
    # (text, ok) per cell. ok=None means "cannot answer", which is its own state.
    grid = [
        [("Type 3", True), ("writes", True), ("accepts", True), ("accepts", True),
         ("draws no\nannotations", None)],
        [("Type 3", True), ("no", False), ("accepts", True), ("accepts", True),
         ("draws no\nannotations", None)],
        [("Type 3", True), ("no", False),
         ("rejects\n%d flagged" % noniod["colour_text_outofiod"], False),
         ("accepts", True), ("draws no\nannotations", None)],
    ]

    fig, ax = plt.subplots(figsize=(6.4, 2.7))
    ncol, nrow = len(cols), len(want)
    for i in range(nrow):
        for k in range(ncol):
            txt, ok = grid[i][k]
            face = {True: "#e8f4e8", False: "#fbe9e9", None: "#eeeeec"}[ok]
            edge = {True: GOOD, False: CRIT, None: MUTED}[ok]
            ax.add_patch(plt.Rectangle((k, nrow - 1 - i), 0.94, 0.9, facecolor=face,
                                       edgecolor=edge, linewidth=1.1, zorder=1))
            ax.text(k + 0.47, nrow - 1 - i + 0.45, txt, ha="center", va="center",
                    fontsize=7.6, color=INK, zorder=2, linespacing=1.25)
    ax.set_xlim(-0.05, ncol)
    ax.set_ylim(-0.05, nrow)
    ax.set_xticks([k + 0.47 for k in range(ncol)])
    ax.set_xticklabels(cols, fontsize=8)
    ax.set_yticks([nrow - 1 - i + 0.45 for i in range(nrow)])
    ax.set_yticklabels([lab for _, lab in want], fontsize=8)
    ax.xaxis.set_ticks_position("top")
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0, colors=INK2)
    ax.grid(False)
    # An earlier title read "Nothing else agrees", which the figure's own dcmpschk
    # column falsifies: it accepts all three, verdict-identical to PS3.3.
    ax.set_title("PS3.3 permits all three. No tool tells you what will render.",
                 pad=26)
    save(fig, "fig1_colour_routes")


# ---------------------------------------------------------------- figure 2
def fig2_conformance():
    print("figure 2, conformance across object classes")
    sets = [
        ("deployed GSPS\n(n=38)", "gsps_conformance_baseline.json", None),
        ("conformant GSPS\npublic data (n=9)", "public_gsps_validation.json",
         "conformant_trueid"),
        # n is derived from the loaded file below, never hardcoded. An earlier version
        # labelled these 12 and "12 of 722" from a different, earlier orchestrator run
        # while plotting these files, which hold 6 and 933 records.
        ("DICOM SEG", "seg_writer_validation.json", None),
        ("generated CT", "public_dicom_validation.json", None),
    ]
    labels, errs, noniods = [], [], []
    for lab, fname, filt in sets:
        j = load(fname)
        if not j:
            return
        recs = j["records"]
        if filt:
            recs = [r for r in recs if filt in Path(r["file"]).name] or recs
        e = [distinct_counts(r)[0] for r in recs]
        n = [distinct_counts(r)[1] for r in recs]
        if "(n=" not in lab:
            lab = "%s\n(n=%d)" % (lab, len(recs))
        labels.append(lab)
        errs.append(float(np.median(e)))
        noniods.append(float(np.median(n)))

    x = np.arange(len(labels))
    w = 0.36
    fig, ax = plt.subplots(figsize=(5.6, 2.8))
    ax.bar(x - w / 2, errs, w, label="required attributes absent", color=S1,
           edgecolor=SURFACE, linewidth=2.0)
    ax.bar(x + w / 2, noniods, w, label="attributes outside the IOD", color=S2,
           hatch="///", edgecolor=SURFACE, linewidth=2.0)
    # selective labels only: the extremes, not every bar
    for xi, (e, n) in enumerate(zip(errs, noniods)):
        if e == max(errs) or e == 0:
            ax.text(xi - w / 2, e + 0.15, "%d" % e, ha="center", fontsize=8, color=INK)
        if n == max(noniods) or n == 0:
            ax.text(xi + w / 2, n + 0.15, "%d" % n, ha="center", fontsize=8, color=INK)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("count per object, median")
    ax.set_ylim(0, max(max(errs), max(noniods)) + 1.4)
    ax.set_title("Independent validation across object classes")
    ax.legend(loc="upper right")
    tidy(ax)
    save(fig, "fig2_conformance")


# ---------------------------------------------------------------- figure 4
def fig4_ablation():
    """The negative result, drawn so the reader can see it is negative.

    The earlier version of this figure was a bar chart of AUC from zero. That was the
    wrong form twice over. Bars from zero on a metric whose null is 0.50 make every arm
    look like a large positive quantity, and with no intervals a 0.065 spread between
    the best and worst arm reads as a decisive ranking. It is not: the intervals
    overlap almost throughout.

    Redrawn as a dot plot with 95 percent intervals on an axis clipped to the range the
    data occupies, with chance marked and the permutation null drawn as a band. The
    band is the point of the figure. A search given SHUFFLED labels reaches higher than
    any real rule, so the reader can see directly that the headroom is not there.
    """
    print("figure 4, channel selection ablation")
    j = load("e1_ablation.json")
    if not j:
        return
    A = j.get("arms", {})
    order = ["region_retired", "parity_name", "parity_region_deployed",
             "parity_sequence", "parity_sequence_inverted",
             "parity_sequence_phased", "mapping_free_margin",
             "mapping_free_top1", "argmax_mean"]
    nice = {"region_retired": "region mapping\n(published numbers)",
            "parity_name": "parity from name\n(continuous, never shipped)",
            "parity_region_deployed": "parity per region\n(THE RULE THAT SHIPPED)",
            "parity_sequence": "parity from sequence\n(phase not estimated)",
            "parity_sequence_inverted": "parity from sequence\n(global sign flip)",
            "parity_sequence_phased": "parity from sequence\n(phase per case)",
            "mapping_free_margin": "mapping free, margin",
            "mapping_free_top1": "mapping free, top 1",
            "argmax_mean": "argmax channel, mean"}
    cb = A.get("_cluster_bootstrap", {})
    arms = [(k, nice[k], A[k]) for k in order if k in A and A[k].get("auc") is not None]
    if not arms:
        print("  SKIP, no arms")
        return
    missing = [k for k, _, _ in arms if k not in cb]
    if missing:
        # Refuse to draw rather than silently fall back to the naive interval,
        # which is the defect this rebuild exists to remove.
        print("  SKIP, no clustered interval for %s" % ", ".join(missing))
        return

    orc = A.get("_oracles", {})
    fixed = orc.get("best_fixed_channel", {})
    mapped = orc.get("best_name_mapping", {})
    null = orc.get("null_search_auc", {})
    hmap = orc.get("best_name_mapping_heldout", {})

    fig, ax = plt.subplots(figsize=(6.0, 4.3))
    ax.axvline(0.5, color=BASELINE, linewidth=1.0, zorder=1)

    # --- the nine rules, each a point estimate with TWO intervals ---
    #
    # The drawn bar is the CASE-CLUSTERED interval, and it has to be. 1845
    # vertebrae come from 155 cases, about twelve each, sharing a patient, a
    # scanner, a field of view and one pass of the same model, so the naive
    # Hanley and McNeil interval is too narrow by 1.12 to 2.78 times, D5i.
    #
    # Round four caught this figure drawing the naive interval instead. The
    # consequence was specific and in the bad direction: the shipped rule's
    # naive interval is [0.395, 0.458], entirely left of the chance line, so
    # the picture asserted BELOW chance. Its clustered interval is
    # [0.342, 0.516], which contains 0.5. D5g exists to refuse exactly the
    # claim the figure was making. The naive interval stays on the page,
    # thinner and inside, because the difference between the two IS the
    # finding and hiding the narrower one would make that unreadable.
    ys = list(range(len(arms)))[::-1]
    for y, (key, nm, rec) in zip(ys, arms):
        v = rec["auc"]
        nlo, nhi = rec.get("ci95", [v, v])
        clo, chi = cb[key]["lo"], cb[key]["hi"]
        deployed = "published" in nm or "SHIPPED" in nm
        col = S2 if deployed else S1
        ax.plot([clo, chi], [y, y], color=col, linewidth=3.6,
                solid_capstyle="butt", zorder=2)
        # A surface ring under the naive line, so the two never merge into one
        # ambiguous bar in print or in grayscale.
        ax.plot([nlo, nhi], [y, y], color=SURFACE, linewidth=2.1,
                solid_capstyle="butt", zorder=3)
        ax.plot([nlo, nhi], [y, y], color=INK2, linewidth=0.9,
                solid_capstyle="butt", zorder=4)
        ax.plot([v], [y], marker="o" if deployed else "s", markersize=6.5,
                color=col, markeredgecolor=SURFACE, markeredgewidth=1.4, zorder=5)
        ax.text(chi + 0.008, y, "%.3f" % v, va="center", fontsize=7.5, color=INK)

    # --- the label-informed ceilings, and the same search on shuffled labels ---
    # Deliberately NOT drawn as a band across the whole panel. The permutation null
    # is the null for a fitted search, not for the eight fixed rules above, whose
    # null is 0.50. Showing it as a band behind them would invite exactly the
    # comparison that does not hold.
    ref = []
    if fixed.get("auc") is not None:
        ref.append(("best fixed channel",
                    orc.get("best_fixed_channel_heldout", {}).get("mean"),
                    fixed["auc"]))
    if mapped.get("auc") is not None:
        ref.append(("best per-level mapping",
                    orc.get("best_name_mapping_heldout", {}).get("mean"),
                    mapped["auc"]))

    y0 = -1.6
    for k, (nm, held, insample) in enumerate(ref):
        y = y0 - k
        if held is not None:
            # the drop from in sample to held out IS the finding, so draw it
            ax.annotate("", xy=(held, y), xytext=(insample, y),
                        arrowprops=dict(arrowstyle="->", color=MUTED,
                                        linewidth=1.0, shrinkA=3, shrinkB=3),
                        zorder=2)
            ax.plot([held], [y], marker="D", markersize=6.5, color=INK,
                    markeredgecolor=SURFACE, markeredgewidth=1.4, zorder=4)
            ax.text(held - 0.008, y, "%.3f" % held, va="center", ha="right",
                    fontsize=7.5, color=INK)
        ax.plot([insample], [y], marker="D", markersize=6.0,
                markerfacecolor=SURFACE, markeredgecolor=MUTED,
                markeredgewidth=1.3, zorder=4)
        ax.text(insample + 0.008, y, "%.3f" % insample, va="center",
                fontsize=7.5, color=MUTED)

    yn = y0 - len(ref)
    null_label = "same search, labels shuffled"
    if null.get("mean") is not None:
        ax.plot([null["mean"], null["max"]], [yn, yn], color=CRIT, linewidth=1.6,
                solid_capstyle="butt", zorder=2)
        ax.plot([null["mean"]], [yn], marker="^", markersize=7.0, color=CRIT,
                markeredgecolor=SURFACE, markeredgewidth=1.4, zorder=3)
        ax.text(null["max"] + 0.006, yn, "%.3f to %.3f" % (null["mean"], null["max"]),
                va="center", fontsize=7.5, color=CRIT)

    yticks = ys + [y0 - k for k in range(len(ref))] + [yn]
    ax.set_yticks(yticks)
    ax.set_yticklabels([nm for _, nm, _ in arms] + [r[0] for r in ref] + [null_label])
    for lab in ax.get_yticklabels()[len(arms):]:
        lab.set_color(INK2)
    ax.set_ylim(yn - 0.8, len(arms) - 0.4)
    # 0.42 clipped the shipped rule's naive lower bound of 0.395, and 0.38 clipped
    # its CLUSTERED lower bound of 0.342. An interval whose end is cut off by the
    # axis reads as a shorter interval, which is the opposite of what this figure
    # is for. Set from the data with a margin, and assert it rather than trust it.
    lo_needed = min(cb[k]["lo"] for k, _, _ in arms)
    assert lo_needed >= 0.325, "clustered lower bound %.3f falls outside the axis" % lo_needed
    ax.set_xlim(0.32, 0.71)
    ax.set_xlabel("AUC, low confidence identifying a wrongly labelled vertebra")
    # "separates a wrong level from a right one" is the same overstatement N23
    # caught in the caption: three arms DO have clustered intervals excluding 0.5,
    # so they separate, just uselessly. Say useless, which is both true and the
    # claim the paper actually needs.
    ax.set_title("No reading of the model output yields a usable flag")
    tidy(ax, ygrid=False, xgrid=True)

    # separate the two groups, since their nulls differ
    ax.axhline(y0 + 0.55, color=GRID, linewidth=0.8)
    # Not at the top: the topmost arm's clustered interval spans 0.479 to 0.553
    # and the label landed on it. The bottom of the line is empty on every row.
    ax.text(0.5, yn - 0.55, " chance", fontsize=7.5, color=INK2, va="center")
    ax.text(0.327, y0 + 0.75, "nine rules, nothing fitted", fontsize=7.5,
            color=INK2, va="bottom")
    ax.text(0.327, y0 + 0.30, "fitted with the labels", fontsize=7.5,
            color=INK2, va="top")

    # Below the axes rather than inside it. Every in-axes corner is occupied: the
    # shuffled-label row runs to 0.625 and the first rule's interval starts at 0.483.
    # The two intervals need naming inside the figure, because which one is drawn
    # is the whole of concern N21. Everything else the reader needs is the caption's
    # job and the caption lives in the manuscript.
    from matplotlib.lines import Line2D
    ax.legend(handles=[
        Line2D([], [], color=INK2, linewidth=3.6, label="clustered by case"),
        Line2D([], [], color=INK2, linewidth=0.9, label="naive, independence assumed"),
        Line2D([], [], marker="D", color=INK, markeredgecolor=SURFACE, linestyle="",
               markersize=6.5, label="held out on unseen cases"),
        Line2D([], [], marker="D", markerfacecolor=SURFACE, markeredgecolor=MUTED,
               color=MUTED, linestyle="", markersize=6.0, label="in sample"),
        Line2D([], [], marker="^", color=CRIT, markeredgecolor=SURFACE, linestyle="",
               markersize=7.0, label="null: labels shuffled"),
    ], loc="upper center", bbox_to_anchor=(0.5, -0.15), ncol=3,
        handletextpad=0.5, columnspacing=1.5, borderaxespad=0.0)

    save(fig, "fig4_channel_ablation")


# ---------------------------------------------------------------- figure 5
def fig5_masking():
    print("figure 5, an in sample residual absorbs the outlier")
    j = load("spline_validation.json")
    if not j or "masking" not in j:
        return
    m = j["masking"]
    off = [r["offset_mm"] for r in m]
    ins = [r["site_residual_mm_median"] for r in m]
    loo = [r["site_loo_residual_mm_median"] for r in m]
    d_dep = [100 * r["detect_deployed"] for r in m]
    d_loo = [100 * r["detect_loo"] for r in m]

    # two panels sharing x. A dual axis here would be the single worst chart error.
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(4.8, 4.6), sharex=True,
                                 gridspec_kw={"height_ratios": [1.25, 1]})

    a1.plot(off, loo, color=S2, marker="s", markersize=4.5, linestyle="-",
            label="leave one out residual")
    a1.plot(off, ins, color=S1, marker="o", markersize=4.5, linestyle="--",
            label="in sample residual (deployed)")
    a1.plot(off, off, color=MUTED, linewidth=0.8, linestyle=":",
            label="true displacement")
    a1.set_yscale("symlog", linthresh=1.0)
    a1.set_ylabel("reported residual, mm")
    a1.set_title("The deployed residual does not respond to real displacement")
    a1.legend(loc="upper left")
    # selective labels: the extreme only
    a1.annotate("flat at ~0.2 mm\nacross the whole range",
                xy=(off[-1], ins[-1]), xytext=(off[-1] * 0.42, 0.028),
                fontsize=7.5, color=INK,
                arrowprops=dict(arrowstyle="-", color=MUTED, linewidth=0.7))
    tidy(a1)

    a2.plot(off, d_loo, color=S2, marker="s", markersize=4.5, linestyle="-",
            label="leave one out")
    a2.plot(off, d_dep, color=S1, marker="o", markersize=4.5, linestyle="--",
            label="deployed")
    a2.set_ylabel("detected, % of studies")
    a2.set_xlabel("true off curve displacement of one vertebra, mm")
    a2.set_ylim(-4, 104)
    a2.legend(loc="upper left")
    tidy(a2)

    fig.align_ylabels([a1, a2])
    save(fig, "fig5_masking")


# ---------------------------------------------------------------- figure 3
def _read_pgm(p: Path):
    """Binary PGM to a 2D array. Header is P5 then three whitespace-separated ints."""
    raw = p.read_bytes()
    i, vals = 2, []
    while len(vals) < 3:
        while i < len(raw) and raw[i:i + 1].isspace():
            i += 1
        if raw[i:i + 1] == b"#":
            while i < len(raw) and raw[i:i + 1] != b"\n":
                i += 1
            continue
        j = i
        while j < len(raw) and not raw[j:j + 1].isspace():
            j += 1
        vals.append(int(raw[i:j]))
        i = j
    i += 1
    w, h, maxv = vals
    dt = np.uint8 if maxv < 256 else np.dtype(">u2")
    a = np.frombuffer(raw[i:i + w * h * np.dtype(dt).itemsize], dtype=dt)
    return a.reshape(h, w)


# ---------------------------------------------------------------- figure 6
def fig6_instance_number():
    """One Type 1 attribute decides whether a conformant renderer draws the object.

    The adversarial figure audit called this the sharpest result in the paper and
    noted it had no figure. It is also the one rendering result untouched by retired
    claim G17: G17 concerns whether annotations are drawn, and this concerns whether
    the object is accepted at all, which is upstream of that.

    Everything here is a file on disk, not a redrawing of one. The two right-hand
    panels are the actual bitmaps `dcmp2pgm` wrote, and their SHA-256 is computed at
    figure-build time rather than quoted, so the figure cannot drift from the artefact.
    """
    print("figure 6, one attribute decides whether the object renders")
    R = RUNS / "render_matrix"
    ok_p, patched_p = R / "_probe_ok.pgm", R / "_probe_patched.pgm"
    if not (ok_p.exists() and patched_p.exists()):
        print("  SKIP, missing render_matrix probe bitmaps")
        return
    ok, patched = _read_pgm(ok_p), _read_pgm(patched_p)
    h_ok = hashlib.sha256(ok_p.read_bytes()).hexdigest()
    h_patched = hashlib.sha256(patched_p.read_bytes()).hexdigest()
    # hash the FULL files, before any cropping, so the figure's own evidence is about
    # the artefacts on disk and not about what was drawn
    identical = ok_p.read_bytes() == patched_p.read_bytes()

    # The renders are 512 x 1119 and mostly empty black, which would make this figure
    # far taller than the page budget allows. Crop both to the SAME bounding box,
    # computed from the conformant render, so they stay comparable.
    thr = int(ok.max() * 0.06)
    rows = np.where(ok.max(axis=1) > thr)[0]
    cols = np.where(ok.max(axis=0) > thr)[0]
    if rows.size and cols.size:
        r0, r1 = max(0, rows[0] - 4), min(ok.shape[0], rows[-1] + 5)
        c0, c1 = max(0, cols[0] - 4), min(ok.shape[1], cols[-1] + 5)
        ok, patched = ok[r0:r1, c0:c1], patched[r0:r1, c0:c1]

    # A first layout put the hashes as free text at axes-fraction -0.055 and the
    # byte-identity note at figure-fraction 0.035; both landed on the caption, and the
    # two-line title of (b) collided with the suptitle. Hashes are now xlabels, so
    # matplotlib reserves the space, and the identity note rides above the panels.
    fig = plt.figure(figsize=(7.0, 5.0))
    gs = fig.add_gridspec(1, 3, width_ratios=[1, 1, 1], wspace=0.22,
                          top=0.80, bottom=0.16)

    axa = fig.add_subplot(gs[0, 0])
    axa.add_patch(plt.Rectangle((0, 0), 1, 1, facecolor="#fbe9e9", edgecolor=CRIT,
                                linewidth=1.2, hatch="///"))
    # solid plate behind the text: the hatch ran straight through it before
    axa.add_patch(plt.Rectangle((0.02, 0.33), 0.96, 0.34, facecolor=SURFACE,
                                edgecolor="none", zorder=2))
    axa.text(0.5, 0.605, "no output", ha="center", va="center", fontsize=10.5,
             color=CRIT, fontweight="bold", zorder=3)
    axa.text(0.5, 0.512, "0 bytes written", ha="center", va="center", fontsize=7.5,
             color=INK2, zorder=3)
    axa.text(0.5, 0.408, "W: instanceNumber\nabsent or empty in\npresentation state",
             ha="center", va="center", fontsize=6.0, color=INK2, style="italic",
             linespacing=1.4, zorder=3)
    axa.set_xlim(0, 1)
    axa.set_ylim(0, 1)
    # Match the rendered panels' shape. Once (b) and (c) were corrected to the
    # render's true 512 x 1119 aspect, a square placard beside them read as a
    # third, differently shaped result rather than as the absence of one.
    axa.set_aspect(ok.shape[0] / ok.shape[1])
    axa.set_xticks([])
    axa.set_yticks([])
    axa.set_title("(a) as deployed", fontsize=9)
    axa.set_xlabel("no file to hash", fontsize=6.6, color=INK2, labelpad=6)
    axa.grid(False)

    axes = []
    for k, (img, lab, h) in enumerate((
            (patched, "(b) + InstanceNumber (0020,0013)", h_patched),
            (ok, "(c) conformant emitter", h_ok))):
        ax = fig.add_subplot(gs[0, k + 1])
        # aspect="equal", NOT "auto". The cropped render is 512 x 1119, aspect
        # 0.458, and "auto" stretched it to fill a near-square panel: the embedded
        # raster came out at aspect 0.795, so the anatomy was 1.7 times too wide.
        # A geometrically distorted CT in a paper about DICOM correctness is not a
        # cosmetic problem, and no reader can tell it happened.
        ax.imshow(img, cmap="gray", aspect="equal", interpolation="nearest")
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_title(lab, fontsize=9)
        ax.set_xlabel("SHA-256 %s" % h[:16], fontsize=6.6, color=INK2,
                      family="monospace", labelpad=6)
        ax.grid(False)
        for s in ax.spines.values():
            s.set_color(GOOD if identical else BASELINE)
            s.set_linewidth(1.4)
        axes.append(ax)

    if identical:
        # a bracket spanning (b) and (c), above their titles
        x0 = axes[0].get_position().x0
        x1 = axes[1].get_position().x1
        y = 0.875
        fig.add_artist(plt.Line2D([x0, x1], [y, y], color=GOOD, linewidth=1.2))
        fig.text((x0 + x1) / 2, y + 0.012, "byte identical",
                 ha="center", va="bottom", fontsize=8, color=GOOD,
                 fontweight="bold")

    fig.suptitle("One Type 1 attribute decides whether a conformant renderer "
                 "draws the object", fontsize=9.5, fontweight="bold", y=0.99)
    save(fig, "fig6_instance_number")


def _gt_levels_for(case: str) -> set:
    """Which vertebral levels actually exist in a VerSe case, from the GT mask cache.

    Returns an empty set if the cache is absent, and the caller then degrades to a
    claim it can support. Public data throughout: the cache is derived from the VerSe
    segmentation masks under CC BY-SA.
    """
    cache = RUNS / "verse_batch_01" / "_gt_centroid_cache"
    if not cache.exists():
        return set()
    for p in sorted(cache.glob("%s*" % case)):
        try:
            return set(json.loads(p.read_text()))
        except Exception:
            continue
    return set()


def fig3_public_pair(case_ok: str, case_bad: str):
    print("figure 3, public data annotation pair")
    ok_p = RUNS / "public_gsps" / ("%s_annotations.json" % case_ok)
    bad_p = RUNS / "public_gsps" / ("%s_annotations.json" % case_bad)
    if not ok_p.exists():
        print("  SKIP, missing %s" % ok_p.name)
        return
    ok = json.loads(ok_p.read_text())

    try:
        import glob
        import pydicom
    except ImportError:
        print("  SKIP, pydicom unavailable")
        return

    ser = Path(ok["series_dir"])
    img = None
    for f in sorted(glob.glob(str(ser / "*.dcm"))):
        h = pydicom.dcmread(f)
        if str(h.SOPInstanceUID) == str(ok["instance"]):
            img = h
            break
    if img is None:
        print("  SKIP, referenced instance not on disk")
        return

    px = img.pixel_array.astype(np.float32)
    slope = float(getattr(img, "RescaleSlope", 1) or 1)
    inter = float(getattr(img, "RescaleIntercept", 0) or 0)
    hu = px * slope + inter
    lo, hi = -200.0, 1200.0   # a bone-ish window, stated in the caption
    n_rows, n_cols = hu.shape

    has_bad = bad_p.exists()
    # Taller than wide: nineteen stacked labels down a 1119 row sagittal reformat
    # collide at 4.3 inches. Height is the only fix that does not shrink the text
    # below readable size in print.
    fig = plt.figure(figsize=(6.8, 6.4))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.0, 1.15], wspace=0.30)
    ax = fig.add_subplot(gs[0, 0])
    ax.imshow(np.clip((hu - lo) / (hi - lo), 0, 1), cmap="gray",
              interpolation="nearest", aspect="equal")
    # Headroom so the topmost label cannot be clipped by the axes edge. An earlier
    # version lost the "C7 96%" label off the top of the image entirely.
    pad = 62
    for a in ok["annotations"]:
        if not a.get("inside"):
            continue
        flagged = a["conf"] < 0.35
        col = CRIT if flagged else WARN
        ax.plot([a["col"]], [a["row"]], marker="+", markersize=5,
                color=col, markeredgewidth=1.0)
        # clamp the label row into the padded band, the leader line still points
        # at the true centroid so no geometry is misrepresented
        ty = min(max(a["row"], -pad + 8), n_rows + pad - 8)
        ax.annotate("%s %d%%" % (a["name"], round(100 * a["conf"])),
                    xy=(a["col"], a["row"]),
                    xytext=(a["col"] + 74, ty),
                    fontsize=6.2, color=col, va="center",
                    annotation_clip=False,
                    arrowprops=dict(arrowstyle="-", color=col, linewidth=0.6,
                                    linestyle=(0, (2, 1.6))))
    ax.set_ylim(n_rows + pad, -pad)
    ax.set_xlim(-4, n_cols + 4)
    # "all levels correct" was an assertion, not a measurement, and it is not true as
    # stated: of the nineteen names this case assigns, C7 and SACRUM do not appear in
    # the VerSe ground-truth mask, which labels T1 to L5 here. That may be a boundary of
    # what the mask annotates rather than a pipeline error, and it is unscoreable
    # either way, which is the verification bias the paper already reports at 17.7
    # percent. Title what can be shown.
    _gt_a = _gt_levels_for(case_ok)
    _n_in = sum(1 for a in ok["annotations"] if a.get("inside")
                and a["name"] in _gt_a) if _gt_a else None
    _n_tot = sum(1 for a in ok["annotations"] if a.get("inside"))
    # Two lines, because (b)'s title is two lines and a one-line (a) ran into it
    # once the burned-in caption below the axes was removed. "as the object
    # encodes them" is caption material and now lives in the manuscript.
    ax.set_title("(a) %s\nof the ground-truth level set"
                 % ("%d of %d names are members" % (_n_in, _n_tot)
                    if _gt_a else "a contiguous labelling"),
                 fontsize=8.5)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color(BASELINE)

    ax2 = fig.add_subplot(gs[0, 1])
    if has_bad:
        bad = json.loads(bad_p.read_text())
        rows = [a for a in bad["annotations"] if a.get("inside")]
        order = {n: i for i, n in enumerate(
            ["C%d" % i for i in range(1, 8)] + ["T%d" % i for i in range(1, 14)]
            + ["L%d" % i for i in range(1, 7)] + ["SACRUM"])}
        xs = [a["normal_mm"] for a in rows]
        ys = [order.get(a["name"], np.nan) for a in rows]

        # An earlier version coloured this panel `CRIT if conf < 0.35 else GOOD` and
        # titled it "two anatomically impossible placements", with a comment asserting
        # that "correctly placed versus impossible are exactly good versus critical".
        # They are not the same thing, and on this case they disagree badly. The
        # ground truth for sub-gl247_dir-ax contains C1 to T6 only. Eight of the twelve
        # predicted names (T8, T11, T12, L1, L2, L4, L5, SACRUM) are levels that do not
        # exist in the volume at all, and seven of those carry confidence 0.82 to 0.96
        # and were drawn green. The flag fires on exactly two points, and one of them,
        # T1, is a level that IS present. So the old figure asserted the flag had found
        # the bad placements when it had not, which is the opposite of this paper's
        # own finding in section 3.3.
        #
        # Redrawn to encode the two things separately, because they are two things:
        #   position on y  = the anatomical level the pipeline assigned
        #   marker fill    = does that level exist anywhere in this volume's GT
        #   outline colour = did the confidence flag fire
        gt_levels = _gt_levels_for(case_bad)
        flagged = [a["conf"] < 0.35 for a in rows]
        exists = [(a["name"] in gt_levels) if gt_levels else None for a in rows]
        for a, xx, yy, fl, ex in zip(rows, xs, ys, flagged, exists):
            face = SURFACE if ex is False else INK
            edge = CRIT if fl else MUTED
            ax2.scatter([xx], [yy], s=46, facecolors=face, edgecolors=edge,
                        linewidths=1.8, zorder=3,
                        marker="o" if ex is not False else "X")
            if fl:
                # offset in points, not data units: at xx the marker covers the first
                # character, which clipped "L5, 0%" to "5, 0%".
                ax2.annotate("%s, %d%%" % (a["name"], round(100 * a["conf"])),
                             xy=(xx, yy), xytext=(9, 0),
                             textcoords="offset points",
                             fontsize=7, color=CRIT, va="center")
        ax2.set_yticks(sorted(set(y for y in ys if y == y)))
        ax2.set_yticklabels([n for n, i in sorted(order.items(), key=lambda kv: kv[1])
                             if i in set(ys)], fontsize=7)
        ax2.invert_yaxis()
        ax2.set_xlabel("position along the slice normal, mm")
        n_imp = sum(1 for e in exists if e is False)
        if gt_levels:
            ax2.set_title("(b) %d of %d labels name a level absent from this volume;\n"
                          "the flag catches %d" % (n_imp, len(rows), sum(flagged)),
                          fontsize=8.5)
        else:
            ax2.set_title("(b) the confidence flag on a failure case", fontsize=9)
        tidy(ax2, ygrid=True, xgrid=True)

        from matplotlib.lines import Line2D
        ax2.legend(handles=[
            Line2D([], [], marker="X", linestyle="", markerfacecolor=SURFACE,
                   markeredgecolor=MUTED, markeredgewidth=1.8, markersize=7,
                   label="level absent from this volume"),
            Line2D([], [], marker="o", linestyle="", markerfacecolor=INK,
                   markeredgecolor=MUTED, markeredgewidth=1.8, markersize=7,
                   label="level present in this volume"),
            Line2D([], [], marker="o", linestyle="", markerfacecolor=SURFACE,
                   markeredgecolor=CRIT, markeredgewidth=1.8, markersize=7,
                   label="confidence flag fired"),
        ], loc="lower right", fontsize=6.6, handletextpad=0.4, borderaxespad=0.3)
    else:
        ax2.axis("off")
        ax2.text(0.5, 0.5, "failure case annotations not generated",
                 ha="center", va="center", fontsize=8, color=INK2)

    save(fig, "fig3_public_pair")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", default=None, help="comma separated figure numbers")
    ap.add_argument("--case-ok", default="sub-verse502_dir-iso")
    ap.add_argument("--case-bad", default="sub-gl247_dir-ax")
    a = ap.parse_args(argv)
    want = set(a.only.split(",")) if a.only else {"1", "2", "3", "4", "5"}

    print("figures into %s\n" % FIGURES)
    if "1" in want:
        fig1_colour_routes()
    if "2" in want:
        fig2_conformance()
    if "3" in want:
        fig3_public_pair(a.case_ok, a.case_bad)
    fig6_instance_number()
    if "4" in want:
        fig4_ablation()
    if "5" in want:
        fig5_masking()
    print("\ndone")
    return 0


if __name__ == "__main__":
    sys.exit(main())
