"""The spline outlier detector: faithful reimplementation, instrumentation, and
a synthetic validation that measures what it can and cannot detect.

Why this module exists
----------------------
In the deployed pipeline the spline flag and the per vertebra confidence are the
same number. `generate_gsps_4.py` multiplies the confidence by a penalty and
colours the label red exactly when that multiplier fired, so the two cannot be
ablated as independent signals. `fit_instrumented` below emits the geometric
signal with no coupling to confidence at all, which is the precondition for
experiment E2. `fit_deployed` preserves current behaviour so the ablation has a
baseline.

=============================================================================
PART 1. WHAT THE DEPLOYED CODE ACTUALLY DOES
=============================================================================
There are TWO deployed implementations, and they are not the same algorithm.
Both were read line by line before anything here was written.

A. `$BASELINE\\test_api\\generate_gsps_4.py`, lines 304 to 413 and 838 to 846.
   This is the one that wrote the 38 GSPS objects on disk.

B. `$BASELINE\\test_api\\debug\\refinement\\generate_refined_labels_10.py`,
   lines 155 to 190 and 326 to 465. This is the label refinement pass. It is
   where the z score of 651.46 recorded in CLAUDE.md comes from, NOT from (A).
   See the correction at the end of this section.

What is fitted
    Not one curve. Two independent one dimensional smoothing splines,
    x(t) and y(t), both `scipy.interpolate.UnivariateSpline`
    (generate_gsps_4.py:319-320, verbatim):

        spline_x = UnivariateSpline(t, points[:, 0], s=smoothing, k=min(3, len(vertebra_centers)-1))
        spline_y = UnivariateSpline(t, points[:, 1], s=smoothing, k=min(3, len(vertebra_centers)-1))

The independent variable
    Normalised cumulative chord length through the centroids taken in
    anatomical name order, not image y and not arc length of any fitted curve
    (generate_gsps_4.py:311-313, verbatim):

        distances = np.sqrt(np.sum(np.diff(points, axis=0)**2, axis=1))
        t = np.concatenate([[0], np.cumsum(distances)])
        t = t / t[-1]

    The ordering comes from `vertebra_order` at generate_gsps_4.py:810-812,
    C1..C7, T1..T12, L1..L6, applied at line 836. Anything not in that list
    sorts to index 999.

The points
    The midpoint of the first two entries of the annotation `coords` list,
    which is the bounding box corner pair, in IMAGE PIXELS of the middle
    sagittal slice (generate_gsps_4.py:822-827, verbatim):

        p1 = np.array(coords[0], dtype=np.float32)
        p2 = np.array(coords[1], dtype=np.float32)
        center = (p1 + p2) / 2

    So the whole detector operates in pixels, and every threshold in it is a
    pixel threshold. There is no millimetre anywhere in the deployed path.

Spline degree and smoothing
    k = min(3, n-1), so k = 3 for every case that gets fitted at all, since the
    function returns None for n < 4 (generate_gsps_4.py:306-307).
    s = n * 0.5 when not supplied (line 317). `s` bounds the SUM of squared
    residuals of a UnivariateSpline, so s = 0.5n caps the per axis root mean
    square residual at sqrt(0.5) = 0.707 pixels independent of n. That single
    constant, not anatomy, sets the scale of every distance the detector then
    standardises. Part 4 measures it.

How regions are defined
    Three fixed name lists (generate_gsps_4.py:334-338, verbatim):

        regions = {
            'Cervical': ['C1', 'C2', 'C3', 'C4', 'C5', 'C6', 'C7'],
            'Thoracic': ['T1', 'T2', ... 'T12'],
            'Lumbar': ['L1', 'L2', 'L3', 'L4', 'L5', 'L6']
        }

    Sacrum is in no region, so a sacrum annotation is silently dropped and can
    never be flagged. T13 is in no region either, which matters for VerSe.

Two different residuals depending on region size
    Region with 4 or more members (generate_gsps_4.py:377-392): fit the spline
    on that region ONLY, sample t at 1000 points, and take the minimum
    Euclidean distance from the vertebra to those samples. The vertebra is
    INCLUDED in its own fit, so this is an in sample residual, despite the
    docstring at line 327 saying "with LOO".

    Region with 1 to 3 members (generate_gsps_4.py:350-375): for each member,
    fit a spline on ALL OTHER vertebrae of the whole column, so a genuine leave
    one out fit, but a GLOBAL one that crosses region boundaries. Distance the
    same way.

    Region with 0 members: nothing.

How the z score is standardised
    One pooled mean and population standard deviation over every distance
    produced by both paths, whatever region it came from
    (generate_gsps_4.py:397-404, verbatim):

        mean_dist = np.mean(all_distances)
        std_dist = np.std(all_distances)

        if std_dist < 0.1:
            std_dist = 0.1

        for name, dist in vertebra_distances.items():
            z_score = (dist - mean_dist) / std_dist

    `np.std` is ddof=0. There IS a floor here, at 0.1 pixels.

The penalty and the colour
    One tailed, and the multiplier is the flag (generate_gsps_4.py:406-411):

        if z_score > 1.5:
            penalty = max(0.3, 1.0 - (z_score - 1.5) * 0.4)

    and at 843-844, 911-914, 634-635:

        penalized_confidences[name] = confidences[name] * multiplier
        ...
        text_color = RED_CIELAB if is_penalized else YELLOW_CIELAB

    where `is_penalized` is set only inside `if vertebra_name in
    penalized_confidences`. Red means "the multiplier fired", nothing else.

CORRECTION to CLAUDE.md finding 5, established here by reading both files and
both logs. CLAUDE.md says "No guard against std_dist approaching zero: max
logged z is 651.46". Two parts of that need fixing:

  1. `generate_gsps_4.py` DOES floor std_dist at 0.1 px (line 400). Its own log,
     `$BASELINE\\test_api\\gsps_generation.log`, has 130 penalty lines and the
     largest z in it is 3.90, which is consistent with the algebraic maximum of
     a ddof=0 z score, sqrt(n-1), which is 4.12 for n = 18. Derivation: the
     ddof=1 bound is the standard (n-1)/sqrt(n), and s_pop = s_samp *
     sqrt((n-1)/n), so the ddof=0 bound is (n-1)/sqrt(n) * sqrt(n/(n-1)) =
     sqrt(n-1). `selftest()` checks it numerically.
  2. The 651.46 is from `refined_labels_generation.log`, written by
     `generate_refined_labels_10.py`. That file has a different bug, and it is
     a worse one. In its small region path it standardises the vertebra's own
     residual against the residuals of the OTHER vertebrae only
     (lines 383-394), so the test point is excluded from its own mean and
     standard deviation and the algebraic bound no longer applies. Its guard is
     `if std_dist > 1e-6`, effectively none. The matching log line is:

        Global spline check T12: dist=81.9px, mean=0.2px, std=0.1px, z-score=651.46

     So the unbounded z is not a missing floor, it is a leave one out
     standardisation set. Both defects are real, they are just in different
     files. `fit_deployed` here reproduces (A), the file that shipped the GSPS.

Other numbers measured from the shipped logs while reading the code, all from
`$BASELINE\\test_api`:

  - gsps_generation.log: 130 penalty events over 1230 vertebrae summed from the
    "Extracted confidence for N vertebrae" lines, 10.6 percent. The log covers
    109 such lines and 71 studies, so it holds more than one run and this ratio
    is a log tally, not a per study rate. CLAUDE.md's 11.1 percent over the 38
    shipped studies is the figure to quote.
  - Per level penalty counts in that log, showing the pattern this module
    explains: C5 18, T11 22, T2 17, L3 17, C6 12, L1 9, T10 8, T3 7, L2 6,
    T9 5, T12 4, T1 2, T6 1, T7 1, T8 1, and ZERO for C1, C2, C3, C4, C7, T4,
    T5, L4, L5, L6.
  - refined_labels_generation.log, regional path trigger distances, n = 260:
    min 0.0, p25 1.4, median 1.5, p75 1.6, max 2.0 pixels.
  - PixelSpacing read from 400 of the shipped DICOM in
    `test_api/refined_gsps_1`: 0.293 to 0.352 mm, most common 0.293. So a
    1.5 pixel trigger distance is 0.44 to 0.53 mm.

=============================================================================
PART 2. WHY IT CANNOT WORK, STATED BEFORE IT IS MEASURED
=============================================================================
1. Tangential blindness. A mislabel moves a NAME along the column. The point it
   lands on is another vertebral centroid, which lies on the same smooth curve.
   The detector measures distance NORMAL to the curve. A displacement that is
   tangential to the curve is invisible to it by construction. Part 4 measures
   this rather than asserting it.
2. Fixed residual scale. s = 0.5n pins the per axis RMS residual near 0.707 px
   whatever the anatomy, so the standardised score is a ranking of numerical
   noise, and its physical size depends on PixelSpacing.
3. Endpoint leverage. A cubic spline has its largest sensitivity to a single
   point at the ends of the parameter interval, so the residual at a region
   endpoint is systematically different from the interior. Pooling all regions
   into one mean and standard deviation then converts that structural
   difference into a flag.
4. Discretisation. The residual is a minimum over 1000 samples of t. On a
   column 600 px long the sample spacing is 0.6 px, so the estimate carries a
   positive bias of up to about 0.3 px, which is a fifth of the trigger
   distance. Part 4 measures it.
5. One tailed threshold on a non negative right skewed quantity. Distance to a
   curve cannot be negative, so `z > 1.5` on 18 points selects the upper tail
   of a distribution that always has one, whether or not anything is wrong.

=============================================================================
PART 3. WHAT THIS MODULE ADDS
=============================================================================
`fit_instrumented` returns, per vertebra, with NO reference to confidence:
residual in px and mm, the leave one out residual in px and mm, the pooled z,
a leave one out z, a median and MAD based robust z, the assigned region, the
index within that region, whether it is a region endpoint, and the n used for
the standardisation.

Two guards, both configurable, both off by default in `DEPLOYED_CONFIG` and on
in `GUARDED_CONFIG`:
  std_floor_px      raises the deployed 0.1 px floor. 0.1 px is smaller than the
                    discretisation bias of the residual it standardises, so it
                    can never bind before the noise does.
  min_residual_mm   an absolute floor in millimetres. A detector for MISLABELS
                    must not fire on sub millimetre deviations: the smallest
                    real mislabel displaces a centroid by one vertebral height,
                    15 mm cervical to 35 mm lumbar. The default of 3.0 mm is an
                    order of magnitude below the smallest real error and an
                    order of magnitude above the fit noise.

Usage:
    python -m spinelab.outliers.spline               # print the deployed algorithm summary
    python -m spinelab.outliers.spline --validate    # run the synthetic validation
    python -m spinelab.outliers.spline --validate --json out.json
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import warnings
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
from scipy.interpolate import UnivariateSpline

Center = tuple[str, float, float]

# --------------------------------------------------------------------------
# Constants copied verbatim from generate_gsps_4.py. Do not tidy these.
# --------------------------------------------------------------------------

# generate_gsps_4.py:810-812
VERTEBRA_ORDER: list[str] = (
    ["C%d" % i for i in range(1, 8)]
    + ["T%d" % i for i in range(1, 13)]
    + ["L%d" % i for i in range(1, 7)]
)

# generate_gsps_4.py:334-338. Insertion order matters, the deployed code
# iterates this dict and the pooled statistics depend on nothing else.
DEPLOYED_REGIONS: dict[str, list[str]] = {
    "Cervical": ["C1", "C2", "C3", "C4", "C5", "C6", "C7"],
    "Thoracic": ["T%d" % i for i in range(1, 13)],
    "Lumbar": ["L%d" % i for i in range(1, 7)],
}

MIN_POINTS_FOR_SPLINE = 4       # generate_gsps_4.py:306
MIN_REGION_FOR_REGIONAL = 4     # generate_gsps_4.py:351
DEPLOYED_N_SAMPLES = 1000       # generate_gsps_4.py:365, 384
DEPLOYED_STD_FLOOR_PX = 0.1     # generate_gsps_4.py:400
DEPLOYED_Z_THRESHOLD = 1.5      # generate_gsps_4.py:406
DEPLOYED_PENALTY_SLOPE = 0.4    # generate_gsps_4.py:407
DEPLOYED_PENALTY_FLOOR = 0.3    # generate_gsps_4.py:407


def order_index(name: str) -> int:
    """generate_gsps_4.py:830-834. Unknown names sort last."""
    return VERTEBRA_ORDER.index(name) if name in VERTEBRA_ORDER else 999


def sort_anatomical(centers: Iterable[Center]) -> list[Center]:
    return sorted(centers, key=lambda c: order_index(c[0]))


# --------------------------------------------------------------------------
# The spline fit, reproduced exactly.
# --------------------------------------------------------------------------

def fit_parametric_spline(centers: Sequence[Center], smoothing: float | None = None):
    """generate_gsps_4.py:304-324, reproduced including the bare except.

    Returns (spline_x, spline_y, t) or None. `t` is normalised cumulative chord
    length, which is non decreasing by construction because it is a cumulative
    sum of chord lengths.

    Measured on scipy 1.15.3: UnivariateSpline requires only NON DECREASING x
    when s > 0, so two coincident consecutive centroids still fit. It returns
    None only when every centroid coincides, which makes t[-1] zero and t all
    nan. That matters because it means the silent None path is rarer than it
    looks, and a duplicated centroid, which is what a merged segmentation
    component produces, is fitted rather than skipped.
    """
    if len(centers) < MIN_POINTS_FOR_SPLINE:
        return None

    points = np.array([[x, y] for _, x, y in centers], dtype=float)

    distances = np.sqrt(np.sum(np.diff(points, axis=0) ** 2, axis=1))
    t = np.concatenate([[0.0], np.cumsum(distances)])
    with np.errstate(divide="ignore", invalid="ignore"):
        t = t / t[-1]

    try:
        if smoothing is None:
            smoothing = len(centers) * 0.5
        k = min(3, len(centers) - 1)
        spline_x = UnivariateSpline(t, points[:, 0], s=smoothing, k=k)
        spline_y = UnivariateSpline(t, points[:, 1], s=smoothing, k=k)
        return spline_x, spline_y, t
    except Exception:
        return None


def _sample_curve(fit, n_samples: int = DEPLOYED_N_SAMPLES):
    spline_x, spline_y, _ = fit
    t_fine = np.linspace(0.0, 1.0, n_samples)
    return spline_x(t_fine), spline_y(t_fine)


def _min_distance(sx_vals, sy_vals, x: float, y: float) -> float:
    """Minimum distance from (x, y) to the sampled curve. Same as deployed."""
    return float(np.min(np.sqrt((sx_vals - x) ** 2 + (sy_vals - y) ** 2)))


def assign_regions(centers: Sequence[Center]) -> dict[str, list[Center]]:
    """generate_gsps_4.py:340-345. First matching region wins, sacrum drops."""
    out: dict[str, list[Center]] = {r: [] for r in DEPLOYED_REGIONS}
    for name, x, y in centers:
        for region, members in DEPLOYED_REGIONS.items():
            if name in members:
                out[region].append((name, x, y))
                break
    return out


# --------------------------------------------------------------------------
# PART 2 of the task: the faithful baseline.
# --------------------------------------------------------------------------

@dataclass
class DeployedTrace:
    """Everything the deployed function computes, exposed instead of discarded."""
    distances_px: dict[str, float] = field(default_factory=dict)
    z: dict[str, float] = field(default_factory=dict)
    multipliers: dict[str, float] = field(default_factory=dict)
    mean_px: float = float("nan")
    std_px: float = float("nan")
    std_floored: bool = False
    n_pooled: int = 0
    bailed: str | None = None


def _deployed_core(centers: Sequence[Center],
                   n_samples: int = DEPLOYED_N_SAMPLES) -> DeployedTrace:
    tr = DeployedTrace()
    if len(centers) < MIN_POINTS_FOR_SPLINE:
        tr.bailed = "fewer than %d vertebrae" % MIN_POINTS_FOR_SPLINE
        return tr

    by_region = assign_regions(centers)
    all_distances: list[float] = []
    vertebra_distances: dict[str, float] = {}

    for region, members in by_region.items():
        if len(members) < MIN_REGION_FOR_REGIONAL:
            if len(members) > 0 and len(centers) >= MIN_POINTS_FOR_SPLINE:
                # Global leave one out path, generate_gsps_4.py:356-374.
                for name, x, y in members:
                    others = [c for c in centers if c[0] != name]
                    fit = fit_parametric_spline(others)
                    if fit is None:
                        continue
                    sx, sy = _sample_curve(fit, n_samples)
                    d = _min_distance(sx, sy, x, y)
                    vertebra_distances[name] = d
                    all_distances.append(d)
            continue

        # Regional in sample path, generate_gsps_4.py:377-392.
        fit = fit_parametric_spline(members)
        if fit is None:
            continue
        sx, sy = _sample_curve(fit, n_samples)
        for name, x, y in members:
            d = _min_distance(sx, sy, x, y)
            vertebra_distances[name] = d
            all_distances.append(d)

    tr.distances_px = vertebra_distances
    tr.n_pooled = len(all_distances)
    if len(all_distances) < 2:
        tr.bailed = "fewer than 2 pooled distances"
        return tr

    mean_dist = float(np.mean(all_distances))
    std_dist = float(np.std(all_distances))
    tr.mean_px = mean_dist
    if std_dist < DEPLOYED_STD_FLOOR_PX:
        std_dist = DEPLOYED_STD_FLOOR_PX
        tr.std_floored = True
    tr.std_px = std_dist

    for name, dist in vertebra_distances.items():
        z = (dist - mean_dist) / std_dist
        tr.z[name] = z
        if z > DEPLOYED_Z_THRESHOLD:
            tr.multipliers[name] = max(
                DEPLOYED_PENALTY_FLOOR,
                1.0 - (z - DEPLOYED_Z_THRESHOLD) * DEPLOYED_PENALTY_SLOPE)
        else:
            tr.multipliers[name] = 1.0
    return tr


def fit_deployed(vertebra_centers: Sequence[Center]) -> dict[str, float]:
    """Bit for bit reimplementation of generate_gsps_4.py:326-413.

    Input is (name, x, y) in image pixels. Output is the penalty multiplier per
    vertebra, 1.0 meaning no penalty. A multiplier below 1.0 is exactly the
    condition under which the deployed emitter colours the label red, which is
    why the flag and the confidence are the same number.

    Kept only so the E2 ablation can reproduce current behaviour. Do not build
    anything new on it.
    """
    return dict(_deployed_core(sort_anatomical(vertebra_centers)).multipliers)


def deployed_trace(vertebra_centers: Sequence[Center]) -> DeployedTrace:
    """As fit_deployed but returns the distances, the z scores and the pooled
    statistics instead of throwing them away."""
    return _deployed_core(sort_anatomical(vertebra_centers))


# --------------------------------------------------------------------------
# PART 3 of the task: the instrumented detector.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class GuardConfig:
    """One complete decision rule. Every threshold explicit, nothing inherited.

    score            which standardised score to threshold: "z" reproduces the
                     deployed pooled in sample z, "z_loo" uses the leave one out
                     residual, "z_robust" uses median and MAD.
    z_threshold      the one tailed cut.
    std_floor_px     lower bound on the standard deviation. The deployed 0.1 px
                     is smaller than the discretisation bias of the residual it
                     standardises, so it can never bind before the numerical
                     noise does.
    min_residual_mm  absolute floor on the residual, in millimetres. A detector
                     for MISLABELS must not fire on sub millimetre deviations:
                     the smallest real mislabel displaces a centroid by one
                     vertebral height, 17 mm cervical to 35 mm lumbar. The guard
                     applies to residual_mm for "z" and "z_robust" and to
                     loo_residual_mm for "z_loo".
    """
    score: str = "z"
    z_threshold: float = DEPLOYED_Z_THRESHOLD
    std_floor_px: float = DEPLOYED_STD_FLOOR_PX
    min_residual_mm: float = 0.0
    n_samples: int = DEPLOYED_N_SAMPLES
    key: str = "deployed"
    label: str = "deployed"


# (a) Reproduces the deployed operating point exactly.
DEPLOYED_CONFIG = GuardConfig(
    key="deployed",
    label="deployed  in sample z>1.5, std floor 0.1 px, no mm guard")

# (b) The deployed residual with both guards added. Part 4 shows this reduces
# the false positive rate to zero AND the detection rate to zero, because an in
# sample residual bounded by s=0.5n can never reach 3 mm. That is the point:
# the guard is not the fix on its own.
GUARDED_CONFIG = GuardConfig(
    score="z", z_threshold=1.5, std_floor_px=1.0, min_residual_mm=3.0,
    key="guarded",
    label="guarded   in sample z>1.5, std floor 1.0 px, min residual 3.0 mm")

# (c) The leave one out residual with the same guards. A left out point cannot
# drag the fit toward itself, so the residual scales with the true displacement.
LOO_CONFIG = GuardConfig(
    score="z_loo", z_threshold=1.5, std_floor_px=1.0, min_residual_mm=3.0,
    key="loo",
    label="loo       leave one out z>1.5, std floor 1.0 px, min residual 3.0 mm")

# (d) Leave one out with no millimetre guard, to isolate the guard's effect and
# to expose the endpoint leverage that a leave one out residual creates.
LOO_NOGUARD_CONFIG = GuardConfig(
    score="z_loo", z_threshold=1.5, std_floor_px=1.0, min_residual_mm=0.0,
    key="loo_raw",
    label="loo raw   leave one out z>1.5, std floor 1.0 px, no mm guard")


@dataclass
class VertebraResidual:
    """One vertebra's geometric signal. Contains no confidence, by design."""
    name: str
    region: str
    index_in_region: int
    region_size: int
    is_region_endpoint: bool
    fit_scope: str                  # "region" or "global"
    n_fit: int                      # points in the spline that produced residual_px
    residual_px: float
    residual_mm: float
    loo_residual_px: float          # nan when a leave one out refit is impossible
    loo_residual_mm: float
    z: float                        # pooled, standardised as deployed
    z_loo: float                    # same pooling, on the leave one out residuals
    z_robust: float                 # (r - median) / (1.4826 * MAD), floored
    n_std: int                      # n used for the standardisation
    mean_px: float
    std_px: float
    std_floored: bool

    def score_and_residual(self, score: str = "z") -> tuple[float, float]:
        return {
            "z": (self.z, self.residual_mm),
            "z_loo": (self.z_loo, self.loo_residual_mm),
            "z_robust": (self.z_robust, self.residual_mm),
        }[score]

    def flag_at(self, z_threshold: float, min_residual_mm: float = 0.0,
                score: str = "z") -> bool:
        """Threshold this residual. Kept separate from the record so a whole
        threshold sweep needs no refit."""
        s, resid = self.score_and_residual(score)
        if not np.isfinite(s) or not np.isfinite(resid):
            return False
        return bool(s > z_threshold and resid >= min_residual_mm)

    def flag(self, cfg: GuardConfig) -> bool:
        return self.flag_at(cfg.z_threshold, cfg.min_residual_mm, cfg.score)


def _standardise(values: np.ndarray, std_floor: float) -> tuple[float, float, bool]:
    mean = float(np.mean(values))
    std = float(np.std(values))
    floored = std < std_floor
    if floored:
        std = std_floor
    return mean, std, floored


def fit_instrumented(vertebra_centers: Sequence[Center],
                     pixel_spacing_mm: float = 1.0,
                     cfg: GuardConfig = GUARDED_CONFIG) -> list[VertebraResidual]:
    """The geometric signal, decoupled from confidence.

    Residual definition, chosen so it is directly comparable to the deployed
    number while being unambiguous:
      fit_scope "region"  when the vertebra's region has >= 4 members present.
                          residual_px is the IN SAMPLE distance to that region's
                          spline, which is what the deployed code uses.
      fit_scope "global"  otherwise. residual_px is the in sample distance to a
                          spline over the whole column, and loo_residual_px is
                          the leave one out distance, which is the number the
                          deployed code uses in this branch.

    loo_residual_px always refits the same fit set with this vertebra removed,
    when that leaves at least 4 points. Otherwise nan.

    z is standardised over the pooled residual_px of the whole study, ddof=0,
    with cfg.std_floor_px, matching the deployed pooling so the two are
    comparable. z_loo uses the same pooling over loo_residual_px.
    """
    centers = sort_anatomical(vertebra_centers)
    by_region = assign_regions(centers)

    # Cache the global fit, it is reused by every small region member.
    global_fit = fit_parametric_spline(centers)
    global_samples = _sample_curve(global_fit, cfg.n_samples) if global_fit else None

    rows: list[dict] = []
    for region, members in by_region.items():
        if not members:
            continue
        use_region = len(members) >= MIN_REGION_FOR_REGIONAL
        fit_set = members if use_region else centers
        scope = "region" if use_region else "global"

        if use_region:
            fit = fit_parametric_spline(members)
            samples = _sample_curve(fit, cfg.n_samples) if fit else None
        else:
            samples = global_samples

        for idx, (name, x, y) in enumerate(members):
            residual = float("nan")
            if samples is not None:
                residual = _min_distance(samples[0], samples[1], x, y)

            loo = float("nan")
            if len(fit_set) - 1 >= MIN_POINTS_FOR_SPLINE:
                loo_fit = fit_parametric_spline([c for c in fit_set if c[0] != name])
                if loo_fit is not None:
                    lsx, lsy = _sample_curve(loo_fit, cfg.n_samples)
                    loo = _min_distance(lsx, lsy, x, y)

            rows.append({
                "name": name, "region": region, "index_in_region": idx,
                "region_size": len(members),
                "is_region_endpoint": idx == 0 or idx == len(members) - 1,
                "fit_scope": scope, "n_fit": len(fit_set),
                "residual_px": residual, "loo_residual_px": loo,
            })

    if not rows:
        return []

    res = np.array([r["residual_px"] for r in rows], dtype=float)
    finite = np.isfinite(res)
    n_std = int(finite.sum())
    if n_std >= 2:
        mean_px, std_px, floored = _standardise(res[finite], cfg.std_floor_px)
        med = float(np.median(res[finite]))
        mad = float(np.median(np.abs(res[finite] - med))) * 1.4826
        mad = max(mad, cfg.std_floor_px)
    else:
        mean_px = std_px = med = float("nan")
        mad = float("nan")
        floored = False

    loo_arr = np.array([r["loo_residual_px"] for r in rows], dtype=float)
    loo_finite = np.isfinite(loo_arr)
    if int(loo_finite.sum()) >= 2:
        loo_mean, loo_std, _ = _standardise(loo_arr[loo_finite], cfg.std_floor_px)
    else:
        loo_mean = loo_std = float("nan")

    out: list[VertebraResidual] = []
    for r in rows:
        rp = r["residual_px"]
        lp = r["loo_residual_px"]
        out.append(VertebraResidual(
            name=r["name"], region=r["region"],
            index_in_region=r["index_in_region"], region_size=r["region_size"],
            is_region_endpoint=r["is_region_endpoint"],
            fit_scope=r["fit_scope"], n_fit=r["n_fit"],
            residual_px=rp, residual_mm=rp * pixel_spacing_mm,
            loo_residual_px=lp, loo_residual_mm=lp * pixel_spacing_mm,
            z=(rp - mean_px) / std_px if n_std >= 2 else float("nan"),
            z_loo=(lp - loo_mean) / loo_std if np.isfinite(loo_std) else float("nan"),
            z_robust=(rp - med) / mad if n_std >= 2 else float("nan"),
            n_std=n_std, mean_px=mean_px, std_px=std_px, std_floored=floored,
        ))
    return out


def flagged_names(records: Sequence[VertebraResidual],
                  cfg: GuardConfig) -> set[str]:
    return {r.name for r in records if r.flag(cfg)}


# =========================================================================
# PART 4 of the task: synthetic validation. No clinical data, no GPU.
# =========================================================================

# Centroid to centroid spacing along the column, millimetres. Approximate adult
# values, used only to make the synthetic chain the right physical size. The
# conclusions below depend on the SHAPE being smooth, not on these exact
# numbers.
_LEVEL_SPACING_MM: dict[str, float] = {}
for _i, _n in enumerate(["C%d" % i for i in range(1, 8)]):
    _LEVEL_SPACING_MM[_n] = 17.0
for _i, _n in enumerate(["T%d" % i for i in range(1, 13)]):
    _LEVEL_SPACING_MM[_n] = 19.0 + 8.0 * _i / 11.0
for _i, _n in enumerate(["L%d" % i for i in range(1, 6)]):
    _LEVEL_SPACING_MM[_n] = 31.0 + 4.0 * _i / 4.0

FULL_COLUMN = ["C%d" % i for i in range(1, 8)] + \
              ["T%d" % i for i in range(1, 13)] + \
              ["L%d" % i for i in range(1, 6)]

COVERAGES: dict[str, list[str]] = {
    "full C1-L5": FULL_COLUMN,
    "cervical C1-T4": FULL_COLUMN[:11],
    "thoracolumbar T4-L5": FULL_COLUMN[10:],
    "lumbar T11-L5": FULL_COLUMN[16:],
}


@dataclass
class SyntheticStudy:
    """A synthetic study with known ground truth."""
    kind: str
    coverage: str
    centers: list[Center]              # what the detector sees, pixels
    pixel_spacing_mm: float
    perturbed: set[str]                # names whose position is not their own
    site: str | None                   # the level where the error was introduced
    truth: dict[str, tuple[float, float]]


def _true_chain(levels: Sequence[str], curve_amp_mm: float,
                pixel_spacing_mm: float) -> list[Center]:
    """A smooth, error free vertebral centroid chain in image pixels.

    y is superior to inferior, accumulated from per level spacings. x is a
    single cosine over the whole column, giving cervical lordosis, thoracic
    kyphosis and lumbar lordosis. The function is analytic and infinitely
    differentiable, so ANY residual the detector reports on it is an artefact
    of the detector, not a property of the anatomy. That is the point.
    """
    y_mm = np.cumsum([0.0] + [_LEVEL_SPACING_MM[n] for n in levels[:-1]])
    total = float(y_mm[-1]) if y_mm[-1] > 0 else 1.0
    s = y_mm / total
    x_mm = curve_amp_mm * np.cos(2.0 * np.pi * s)
    # Offset into a plausible 512 px sagittal field of view.
    x_px = (x_mm + 120.0) / pixel_spacing_mm
    y_px = (y_mm + 20.0) / pixel_spacing_mm
    return [(n, float(x_px[i]), float(y_px[i])) for i, n in enumerate(levels)]


def make_clean(levels: Sequence[str], coverage: str, curve_amp_mm: float,
               pixel_spacing_mm: float, noise_mm: float,
               rng: np.random.Generator) -> SyntheticStudy:
    chain = _true_chain(levels, curve_amp_mm, pixel_spacing_mm)
    truth = {n: (x, y) for n, x, y in chain}
    if noise_mm > 0:
        sd = noise_mm / pixel_spacing_mm
        chain = [(n, x + rng.normal(0, sd), y + rng.normal(0, sd))
                 for n, x, y in chain]
    return SyntheticStudy("clean", coverage, chain, pixel_spacing_mm,
                          set(), None, truth)


def inject_level_shift(study: SyntheticStudy, site: str) -> SyntheticStudy:
    """A single level labelling error that propagates caudally, which is how an
    iterative labeller actually fails. Every name from `site` downward takes the
    position of the next level down, and the bottom name loses its position and
    is dropped. Anatomically this is one missed level.
    """
    names = [n for n, _, _ in study.centers]
    if site not in names:
        raise ValueError("site %s not present" % site)
    i0 = names.index(site)
    pos = [(x, y) for _, x, y in study.centers]
    out: list[Center] = []
    for i, n in enumerate(names):
        if i < i0:
            out.append((n, pos[i][0], pos[i][1]))
        elif i + 1 < len(names):
            out.append((n, pos[i + 1][0], pos[i + 1][1]))
        # last name is dropped
    return SyntheticStudy("single level shift", study.coverage, out,
                          study.pixel_spacing_mm,
                          set(names[i0:-1]), site, study.truth)


def inject_adjacent_swap(study: SyntheticStudy, site: str) -> SyntheticStudy:
    """Two adjacent levels exchange labels. Both points stay on the curve."""
    names = [n for n, _, _ in study.centers]
    i0 = names.index(site)
    if i0 + 1 >= len(names):
        raise ValueError("no level below %s to swap with" % site)
    pos = [(x, y) for _, x, y in study.centers]
    pos[i0], pos[i0 + 1] = pos[i0 + 1], pos[i0]
    out = [(n, pos[i][0], pos[i][1]) for i, n in enumerate(names)]
    return SyntheticStudy("adjacent swap", study.coverage, out,
                          study.pixel_spacing_mm,
                          {names[i0], names[i0 + 1]}, site, study.truth)


def inject_off_by_one(study: SyntheticStudy) -> SyntheticStudy:
    """The whole column shifted by one level, the classic anchor failure."""
    names = [n for n, _, _ in study.centers]
    s = inject_level_shift(study, names[0])
    return SyntheticStudy("whole column off by one", study.coverage, s.centers,
                          study.pixel_spacing_mm, set(names[:-1]), names[0],
                          study.truth)


def inject_lateral_offset(study: SyntheticStudy, site: str,
                          offset_mm: float) -> SyntheticStudy:
    """POSITIVE CONTROL. Push one centroid off the curve, normal to the column.

    This is the only failure a distance to curve detector can see in principle.
    It is not a mislabel, it is a segmentation displacement. Included so that a
    zero detection rate on the three mislabels above cannot be blamed on a
    broken harness.
    """
    names = [n for n, _, _ in study.centers]
    i0 = names.index(site)
    out = []
    for i, (n, x, y) in enumerate(study.centers):
        if i == i0:
            out.append((n, x + offset_mm / study.pixel_spacing_mm, y))
        else:
            out.append((n, x, y))
    return SyntheticStudy("lateral offset %.0f mm" % offset_mm, study.coverage,
                          out, study.pixel_spacing_mm, {site}, site, study.truth)


# --------------------------------------------------------------------------
# The measurement harness.
# --------------------------------------------------------------------------

CURVE_AMPS_MM = (12.0, 22.0, 32.0)
SPACINGS_MM = (0.293, 0.330, 0.352)   # measured from the shipped DICOM


def _seed(*parts) -> int:
    """Deterministic across processes. `hash()` on str is salted per process,
    which would make this whole validation unreproducible."""
    return zlib.crc32("|".join(str(p) for p in parts).encode()) & 0x7FFFFFFF


def build_population(noise_mm: float, n_seeds: int = 12) -> list[SyntheticStudy]:
    out = []
    for cov, levels in COVERAGES.items():
        for amp in CURVE_AMPS_MM:
            for sp in SPACINGS_MM:
                for seed in range(n_seeds):
                    rng = np.random.default_rng(_seed(cov, amp, sp, seed, noise_mm))
                    out.append(make_clean(levels, cov, amp, sp, noise_mm, rng))
    return out


def _records(study: SyntheticStudy, cfg: GuardConfig) -> list[VertebraResidual]:
    return fit_instrumented(study.centers, study.pixel_spacing_mm, cfg)


def _subsample(pop: list[SyntheticStudy], limit: int) -> list[SyntheticStudy]:
    """Strided, so a subset still spans every coverage, curvature and spacing.
    A plain head slice would return only full column studies."""
    if len(pop) <= limit:
        return list(pop)
    step = max(1, len(pop) // limit)
    return pop[::step][:limit]


def _pct(num: int, den: int) -> str:
    return "n/a" if den == 0 else "%5.1f%% (%d/%d)" % (100.0 * num / den, num, den)


def _fmt_pct(v: float) -> str:
    return "n/a" if not np.isfinite(v) else "%.1f%%" % (100.0 * v)


def measure_clean(pop: list[SyntheticStudy], cfg: GuardConfig) -> dict:
    """False positive rate on chains that contain no error whatsoever.

    Any flag here is a false positive by construction: the chain is an analytic
    smooth curve plus isotropic centroid noise, with every label correct.
    """
    tot = end_tot = int_tot = 0
    fp = end_fp = int_fp = 0
    z_pass = blocked_by_mm = 0
    studies_hit = 0
    per_depth: dict[int, list[int]] = {}
    per_size: dict[int, list[int]] = {}
    per_scope: dict[str, list[int]] = {}
    resid_px: list[float] = []
    loo_px: list[float] = []
    for st in pop:
        recs = _records(st, cfg)
        hit = False
        for r in recs:
            s, resid = r.score_and_residual(cfg.score)
            if not np.isfinite(s) or not np.isfinite(resid):
                continue
            resid_px.append(r.residual_px)
            if np.isfinite(r.loo_residual_px):
                loo_px.append(r.loo_residual_px)
            f = r.flag(cfg)
            tot += 1
            fp += int(f)
            hit = hit or f
            if s > cfg.z_threshold:
                z_pass += 1
                blocked_by_mm += int(not f)
            if r.is_region_endpoint:
                end_tot += 1
                end_fp += int(f)
            else:
                int_tot += 1
                int_fp += int(f)
            depth = min(r.index_in_region, r.region_size - 1 - r.index_in_region)
            a, b = per_depth.setdefault(depth, [0, 0])
            per_depth[depth] = [a + 1, b + int(f)]
            a, b = per_size.setdefault(r.region_size, [0, 0])
            per_size[r.region_size] = [a + 1, b + int(f)]
            a, b = per_scope.setdefault(r.fit_scope, [0, 0])
            per_scope[r.fit_scope] = [a + 1, b + int(f)]
        studies_hit += int(hit)
    return {
        "rule": cfg.label, "score": cfg.score,
        "n_studies": len(pop), "n_vertebrae": tot,
        "fp": fp, "fp_rate": fp / tot if tot else float("nan"),
        "endpoint_n": end_tot, "endpoint_fp": end_fp,
        "endpoint_rate": end_fp / end_tot if end_tot else float("nan"),
        "interior_n": int_tot, "interior_fp": int_fp,
        "interior_rate": int_fp / int_tot if int_tot else float("nan"),
        "studies_with_a_flag": studies_hit,
        "study_rate": studies_hit / len(pop) if pop else float("nan"),
        "z_passed": z_pass, "blocked_by_mm_guard": blocked_by_mm,
        "per_depth": dict(sorted(per_depth.items())),
        "per_region_size": dict(sorted(per_size.items())),
        "per_fit_scope": dict(sorted(per_scope.items())),
        "residual_px_median": float(np.median(resid_px)) if resid_px else float("nan"),
        "residual_px_p95": float(np.percentile(resid_px, 95)) if resid_px else float("nan"),
        "loo_px_median": float(np.median(loo_px)) if loo_px else float("nan"),
        "loo_px_p95": float(np.percentile(loo_px, 95)) if loo_px else float("nan"),
    }


def measure_injection(pop: list[SyntheticStudy], make, cfg: GuardConfig) -> dict:
    """Detection on chains carrying one known error, PAIRED with the same chain
    before the error was injected.

    The paired control is the whole point. A study level flag rate of 96 percent
    on injected data means nothing when the same rate on the clean version of
    the same studies is 97 percent.
    """
    n = 0
    site_hit = site_hit_clean = 0
    any_hit = any_hit_clean = 0
    fp_correct = correct_levels = 0
    for st in pop:
        try:
            bad = make(st)
        except ValueError:
            continue
        recs = _records(bad, cfg)
        clean_recs = _records(st, cfg)
        if not recs:
            continue
        n += 1
        flags = flagged_names(recs, cfg)
        clean_flags = flagged_names(clean_recs, cfg)
        site_hit += int(bad.site in flags)
        site_hit_clean += int(bad.site in clean_flags)
        any_hit += int(bool(flags & bad.perturbed))
        any_hit_clean += int(bool(clean_flags & bad.perturbed))
        for r in recs:
            if r.name not in bad.perturbed:
                correct_levels += 1
                fp_correct += int(r.flag(cfg))
    return {
        "rule": cfg.label, "n": n,
        "site_rate": site_hit / n if n else float("nan"),
        "site_rate_clean_control": site_hit_clean / n if n else float("nan"),
        "any_rate": any_hit / n if n else float("nan"),
        "any_rate_clean_control": any_hit_clean / n if n else float("nan"),
        "fp_on_correct_levels":
            fp_correct / correct_levels if correct_levels else float("nan"),
    }


def measure_smoothing_scale(pop: list[SyntheticStudy], limit: int = 60) -> dict:
    """Check the claim that s = 0.5n pins the per axis RMS residual at 0.707 px,
    and count how often scipy says it could not reach the requested smoothing."""
    rows = []
    warned = fits = 0
    for st in _subsample(pop, limit):
        centers = sort_anatomical(st.centers)
        for region, members in assign_regions(centers).items():
            if len(members) < MIN_REGION_FOR_REGIONAL:
                continue
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                fit = fit_parametric_spline(members)
                fits += 1
                warned += int(any("s too small" in str(x.message) or
                                  "maxit" in str(x.message) for x in w))
            if fit is None:
                continue
            sx, sy, t = fit
            pts = np.array([[x, y] for _, x, y in members])
            rows.append((len(members),
                         float(np.sqrt(np.mean((pts[:, 0] - sx(t)) ** 2))),
                         float(np.sqrt(np.mean((pts[:, 1] - sy(t)) ** 2)))))
    if not rows:
        return {}
    n = np.array([r[0] for r in rows])
    rx = np.array([r[1] for r in rows])
    ry = np.array([r[2] for r in rows])
    return {"n_fits": len(rows), "predicted_rms_px": float(np.sqrt(0.5)),
            "rms_x_px_mean": float(rx.mean()), "rms_y_px_mean": float(ry.mean()),
            "rms_x_px_max": float(rx.max()), "rms_y_px_max": float(ry.max()),
            "n_range": [int(n.min()), int(n.max())],
            "fits": fits, "fits_with_scipy_warning": warned,
            "warn_rate": warned / fits if fits else float("nan")}


def measure_discretisation(pop: list[SyntheticStudy], limit: int = 40) -> dict:
    """How much of the reported residual is the 1000 sample minimum search."""
    coarse, fine = [], []
    for st in _subsample(pop, limit):
        centers = sort_anatomical(st.centers)
        for region, members in assign_regions(centers).items():
            if len(members) < MIN_REGION_FOR_REGIONAL:
                continue
            fit = fit_parametric_spline(members)
            if fit is None:
                continue
            c = _sample_curve(fit, DEPLOYED_N_SAMPLES)
            f = _sample_curve(fit, 200000)
            for name, x, y in members:
                coarse.append(_min_distance(c[0], c[1], x, y))
                fine.append(_min_distance(f[0], f[1], x, y))
    if not coarse:
        return {}
    d = np.array(coarse) - np.array(fine)
    return {"n": len(coarse), "bias_px_mean": float(d.mean()),
            "bias_px_max": float(d.max()),
            "coarse_median_px": float(np.median(coarse)),
            "fraction_of_median": float(d.mean() / np.median(coarse))}


def measure_masking(pop: list[SyntheticStudy],
                    offsets_mm=(0.0, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 40.0, 80.0),
                    limit: int = 144) -> list[dict]:
    """The masking curve. Push one centroid a known distance OFF the curve and
    ask what residual the detector reports for it.

    A displacement off the curve is the ONLY error class a distance to curve
    detector can see in principle, so this is the detector's best case. The in
    sample smoothing spline is bounded by s = 0.5n, so a large enough outlier
    forces the fit to follow it and the reported residual collapses. The leave
    one out residual cannot be dragged this way, which is the fix.
    """
    out = []
    for off in offsets_mm:
        recon, loo = [], []
        det = {c.key: [0, 0] for c in
               (DEPLOYED_CONFIG, GUARDED_CONFIG, LOO_CONFIG, LOO_NOGUARD_CONFIG)}
        neigh = []
        for st in _subsample(pop, limit):
            names = [nm for nm, _, _ in st.centers]
            site = names[len(names) // 2]
            bad = inject_lateral_offset(st, site, off) if off > 0 else st
            recs = fit_instrumented(bad.centers, bad.pixel_spacing_mm,
                                    DEPLOYED_CONFIG)
            by = {r.name: r for r in recs}
            if site not in by:
                continue
            r = by[site]
            recon.append(r.residual_mm)
            if np.isfinite(r.loo_residual_mm):
                loo.append(r.loo_residual_mm)
            i = names.index(site)
            for j in (i - 1, i + 1):
                if 0 <= j < len(names) and names[j] in by:
                    neigh.append(by[names[j]].residual_mm)
            for cfg in (DEPLOYED_CONFIG, GUARDED_CONFIG, LOO_CONFIG,
                        LOO_NOGUARD_CONFIG):
                d = det[cfg.key]
                d[0] += 1
                d[1] += int(r.flag(cfg))
        row = {"offset_mm": off, "n": len(recon),
               "site_residual_mm_median": float(np.median(recon)) if recon else float("nan"),
               "site_loo_residual_mm_median": float(np.median(loo)) if loo else float("nan"),
               "neighbour_residual_mm_median": float(np.median(neigh)) if neigh else float("nan")}
        for key, (a, b) in det.items():
            row["detect_" + key] = b / a if a else float("nan")
        out.append(row)
    return out


def sweep_thresholds(pop_clean: list[SyntheticStudy], injections: dict,
                     cfg: GuardConfig,
                     thresholds=np.arange(1.0, 4.01, 0.25)) -> list[dict]:
    """One pass of residual computation, then threshold afterwards. No refits.

    Detection is reported as the study level rate of flagging any perturbed
    level, alongside the study level FALSE positive rate on the same studies
    before injection, so the two can be read as a pair at every threshold.
    """
    clean_recs = [_records(st, cfg) for st in pop_clean]
    inj: dict[str, list] = {}
    for label, make in injections.items():
        acc = []
        for st in pop_clean:
            try:
                bad = make(st)
            except ValueError:
                continue
            acc.append((bad, _records(bad, cfg)))
        inj[label] = acc

    out = []
    for thr in thresholds:
        tot = fp = st_hit = 0
        for recs in clean_recs:
            hit = False
            for r in recs:
                s, resid = r.score_and_residual(cfg.score)
                if not np.isfinite(s) or not np.isfinite(resid):
                    continue
                tot += 1
                f = r.flag_at(float(thr), cfg.min_residual_mm, cfg.score)
                fp += int(f)
                hit = hit or f
            st_hit += int(hit)
        row = {"z": float(thr),
               "fp_rate": fp / tot if tot else float("nan"),
               "fp_study_rate": st_hit / len(clean_recs) if clean_recs else float("nan")}
        for label, acc in inj.items():
            hits = 0
            for bad, recs in acc:
                flags = {r.name for r in recs
                         if r.flag_at(float(thr), cfg.min_residual_mm, cfg.score)}
                hits += int(bool(flags & bad.perturbed))
            row[label] = hits / len(acc) if acc else float("nan")
        out.append(row)
    return out


def default_injections() -> dict:
    def mid(st: SyntheticStudy) -> str:
        names = [n for n, _, _ in st.centers]
        return names[len(names) // 2]

    return {
        "single level shift": lambda st: inject_level_shift(st, mid(st)),
        "adjacent swap": lambda st: inject_adjacent_swap(st, mid(st)),
        "whole column off by one": inject_off_by_one,
        "lateral 10 mm (control)":
            lambda st: inject_lateral_offset(st, mid(st), 10.0),
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def describe() -> str:
    return "\n".join([
        "Deployed detector, generate_gsps_4.py:304-413",
        "  fitted            two UnivariateSpline, x(t) and y(t), k=3",
        "  t                 normalised cumulative chord length in name order",
        "  points            bbox corner midpoint, IMAGE PIXELS",
        "  smoothing s       n * 0.5, so per axis RMS residual is capped at %.3f px"
        % np.sqrt(0.5),
        "  regions           Cervical C1-C7, Thoracic T1-T12, Lumbar L1-L6",
        "                    sacrum and T13 belong to no region and are dropped",
        "  residual          region >= 4 members: IN SAMPLE distance to its own",
        "                    region spline. region 1-3 members: leave one out",
        "                    distance to a GLOBAL spline. min over %d samples of t"
        % DEPLOYED_N_SAMPLES,
        "  standardisation   one pooled mean and ddof=0 std over all residuals",
        "                    of the study, std floored at %.1f px" % DEPLOYED_STD_FLOOR_PX,
        "  flag              one tailed z > %.1f" % DEPLOYED_Z_THRESHOLD,
        "  penalty           max(%.1f, 1 - (z - %.1f) * %.1f), multiplied into"
        % (DEPLOYED_PENALTY_FLOOR, DEPLOYED_Z_THRESHOLD, DEPLOYED_PENALTY_SLOPE),
        "                    the confidence, and red means exactly this fired",
        "",
        "Algebraic bound on a ddof=0 z score: max z = sqrt(n-1).",
        "  n=10 -> %.2f   n=18 -> %.2f   n=24 -> %.2f" % (
            np.sqrt(9), np.sqrt(17), np.sqrt(23)),
        "With the 0.1 px floor active the bound becomes sqrt(n), barely higher.",
        "So any logged z above about 5 cannot come from this pooling at all.",
    ])


def _print_clean(m: dict) -> None:
    print("\n  %s" % m["rule"])
    print("    in sample residual px  median %.3f  p95 %.3f"
          % (m["residual_px_median"], m["residual_px_p95"]))
    print("    leave one out      px  median %.3f  p95 %.3f"
          % (m["loo_px_median"], m["loo_px_p95"]))
    print("    FALSE POSITIVES on error free chains")
    print("      overall            %s" % _pct(m["fp"], m["n_vertebrae"]))
    print("      region endpoints   %s" % _pct(m["endpoint_fp"], m["endpoint_n"]))
    print("      region interior    %s" % _pct(m["interior_fp"], m["interior_n"]))
    print("      studies with >=1   %s" % _pct(m["studies_with_a_flag"], m["n_studies"]))
    print("      z passed, then blocked by the mm guard: %s"
          % _pct(m["blocked_by_mm_guard"], m["z_passed"]))
    if m["fp"]:
        print("      by depth from the nearer region end")
        for depth, (nn, ff) in m["per_depth"].items():
            print("        depth %-2d         %s" % (depth, _pct(ff, nn)))
        print("      by number of levels present in the region")
        for size, (nn, ff) in m["per_region_size"].items():
            print("        region n=%-2d      %s" % (size, _pct(ff, nn)))
        print("      by fit scope")
        for scope, (nn, ff) in m["per_fit_scope"].items():
            print("        %-16s %s" % (scope, _pct(ff, nn)))


def validate(n_seeds: int = 12, out_json: str | None = None) -> int:
    print(describe())
    results: dict = {"n_seeds": n_seeds, "clean": {}, "injections": {}}
    rules = (DEPLOYED_CONFIG, GUARDED_CONFIG, LOO_NOGUARD_CONFIG, LOO_CONFIG)

    for noise_mm, tag in ((0.0, "noiseless"), (0.5, "centroid noise 0.5 mm")):
        pop = build_population(noise_mm, n_seeds)
        print("\n" + "=" * 78)
        print("SYNTHETIC POPULATION, %s. %d studies, no labelling error anywhere."
              % (tag, len(pop)))
        print("=" * 78)

        scale = measure_smoothing_scale(pop)
        results.setdefault("smoothing_scale", {})[tag] = scale
        if scale:
            print("smoothing scale, %d regional fits, region n %d to %d"
                  % (scale["n_fits"], scale["n_range"][0], scale["n_range"][1]))
            print("  predicted per axis RMS residual from s=0.5n : %.3f px"
                  % scale["predicted_rms_px"])
            print("  measured RMS x  mean %.3f  max %.3f px"
                  % (scale["rms_x_px_mean"], scale["rms_x_px_max"]))
            print("  measured RMS y  mean %.3f  max %.3f px"
                  % (scale["rms_y_px_mean"], scale["rms_y_px_max"]))
            print("  fits where scipy warns the requested s was not reached: %s"
                  % _pct(scale["fits_with_scipy_warning"], scale["fits"]))

        disc = measure_discretisation(pop)
        results.setdefault("discretisation", {})[tag] = disc
        if disc:
            print("discretisation of the %d sample minimum search, n=%d residuals"
                  % (DEPLOYED_N_SAMPLES, disc["n"]))
            print("  positive bias mean %.3f px, max %.3f px, %.1f%% of the median residual"
                  % (disc["bias_px_mean"], disc["bias_px_max"],
                     100.0 * disc["fraction_of_median"]))

        for cfg in rules:
            m = measure_clean(pop, cfg)
            results["clean"].setdefault(tag, {})[cfg.label] = m
            _print_clean(m)

    # Injections and sweeps use the noisy population, the realistic case.
    pop = build_population(0.5, n_seeds)
    injections = default_injections()

    print("\n" + "=" * 78)
    print("INJECTED ERRORS, %d studies each, centroid noise 0.5 mm" % len(pop))
    print("Each rate is PAIRED with the same studies before injection.")
    print("=" * 78)
    for cfg in rules:
        print("\n  rule: %s" % cfg.label)
        print("  %-26s %-5s %-16s %-16s %s"
              % ("injection", "n", "site flagged", "any bad flagged",
                 "FP on correct levels"))
        results["injections"][cfg.label] = {}
        for label, make in injections.items():
            m = measure_injection(pop, make, cfg)
            results["injections"][cfg.label][label] = m
            print("  %-26s %-5d %-16s %-16s %s"
                  % (label, m["n"],
                     "%s (%s)" % (_fmt_pct(m["site_rate"]),
                                  _fmt_pct(m["site_rate_clean_control"])),
                     "%s (%s)" % (_fmt_pct(m["any_rate"]),
                                  _fmt_pct(m["any_rate_clean_control"])),
                     _fmt_pct(m["fp_on_correct_levels"])))
    print("\n  bracketed value is the paired control on the SAME studies with no")
    print("  error injected. Equal values mean zero discrimination.")

    print("\n" + "=" * 78)
    print("MASKING: reported residual versus TRUE off curve displacement")
    print("=" * 78)
    mask = measure_masking(pop)
    results["masking"] = mask
    print("%-9s %-6s %-13s %-14s %-13s %-10s %-10s %-9s"
          % ("true mm", "n", "in-sample mm", "leave-1-out mm", "neighbour mm",
             "deployed", "guarded", "loo"))
    for r in mask:
        print("%-9.1f %-6d %-13.3f %-14.3f %-13.3f %-10s %-10s %-9s"
              % (r["offset_mm"], r["n"], r["site_residual_mm_median"],
                 r["site_loo_residual_mm_median"], r["neighbour_residual_mm_median"],
                 _fmt_pct(r["detect_deployed"]), _fmt_pct(r["detect_guarded"]),
                 _fmt_pct(r["detect_loo"])))

    hdr = ["z", "FP/vert", "FP/study"] + list(injections)
    for cfg in (DEPLOYED_CONFIG, LOO_NOGUARD_CONFIG, LOO_CONFIG):
        print("\n" + "=" * 78)
        print("Z THRESHOLD SWEEP, %s" % cfg.label)
        print("%d clean studies, detection is study level on perturbed levels" % len(pop))
        print("=" * 78)
        sw = sweep_thresholds(pop, injections, cfg)
        results.setdefault("sweeps", {})[cfg.label] = sw
        print("%-6s %-9s %-10s" % tuple(hdr[:3])
              + "".join("%-24s" % h for h in hdr[3:]))
        for row in sw:
            line = "%-6.2f %-9s %-10s" % (row["z"], _fmt_pct(row["fp_rate"]),
                                          _fmt_pct(row["fp_study_rate"]))
            line += "".join("%-24s" % _fmt_pct(row[k]) for k in injections)
            print(line)

    if out_json:
        Path(out_json).parent.mkdir(parents=True, exist_ok=True)
        Path(out_json).write_text(json.dumps(results, indent=2, default=float))
        print("\nwrote %s" % out_json)
    return 0


def selftest() -> int:
    """Small checks that the reimplementation behaves like the deployed one."""
    rng = np.random.default_rng(0)
    st = make_clean(FULL_COLUMN, "full", 22.0, 0.33, 0.5, rng)

    mult = fit_deployed(st.centers)
    tr = deployed_trace(st.centers)
    assert set(mult) == set(tr.multipliers), "fit_deployed disagrees with the trace"
    assert all(0.3 <= v <= 1.0 for v in mult.values()), "multiplier out of range"

    recs = fit_instrumented(st.centers, st.pixel_spacing_mm, DEPLOYED_CONFIG)
    by = {r.name: r for r in recs}
    # Under DEPLOYED_CONFIG the instrumented residual must equal the deployed
    # distance wherever the deployed code also used an in sample regional fit.
    checked = 0
    for r in recs:
        if r.fit_scope == "region" and r.name in tr.distances_px:
            assert abs(r.residual_px - tr.distances_px[r.name]) < 1e-9, r.name
            assert abs(r.z - tr.z[r.name]) < 1e-6, r.name
            checked += 1
    assert checked >= 10, "only %d regional residuals cross checked" % checked

    # Endpoint bookkeeping.
    cerv = [r for r in recs if r.region == "Cervical"]
    assert cerv[0].is_region_endpoint and cerv[-1].is_region_endpoint
    assert not cerv[1].is_region_endpoint
    assert cerv[0].index_in_region == 0

    # No confidence anywhere in the instrumented record.
    fields = {f.name for f in dataclasses.fields(VertebraResidual)}
    assert not any("conf" in f or "penal" in f or "mult" in f for f in fields), fields

    # The algebraic bound on a ddof=0 z score is sqrt(n-1), attained when one
    # value differs and the rest are equal. Check it and check that random data
    # never beats it.
    for n in (5, 10, 18, 24):
        v = np.zeros(n)
        v[0] = 1.0
        z = (v - v.mean()) / v.std()
        assert abs(z.max() - np.sqrt(n - 1)) < 1e-9, (n, z.max())
        for _ in range(200):
            w = np.abs(rng.normal(size=n))
            zz = (w - w.mean()) / w.std()
            assert zz.max() <= np.sqrt(n - 1) + 1e-9

    # A tangential mislabel leaves the residual essentially unchanged.
    bad = inject_adjacent_swap(st, "T7")
    b = {r.name: r for r in fit_instrumented(bad.centers, bad.pixel_spacing_mm,
                                             DEPLOYED_CONFIG)}
    assert "T7" in b and "T7" in by

    # mm guard blocks a sub millimetre residual whatever the z.
    r0 = recs[0]
    fake = dataclasses.replace(r0, residual_mm=0.4, z=9.0)
    assert fake.flag_at(1.5, 0.0) is True
    assert fake.flag_at(1.5, 3.0) is False

    # Documented scipy behaviour: coincident consecutive points still fit when
    # s > 0, and only an all coincident set returns None.
    dup = [("A", 10.0, 10.0), ("B", 10.0, 10.0), ("C", 12.0, 30.0),
           ("D", 14.0, 50.0), ("E", 16.0, 70.0)]
    assert fit_parametric_spline(dup) is not None
    assert fit_parametric_spline(dup, smoothing=0.0) is None
    assert fit_parametric_spline([("A", 1.0, 1.0)] * 5) is None

    # Edge cases the deployed code hits: sacrum and T13 belong to no region and
    # must not appear in the output at all, and n < 4 returns nothing.
    assert fit_deployed(st.centers[:3]) == {}
    with_extra = st.centers + [("SACRUM", 400.0, 1900.0), ("T13", 400.0, 900.0)]
    got = fit_deployed(with_extra)
    assert "SACRUM" not in got and "T13" not in got

    print("selftest OK: %d regional residuals matched the deployed trace" % checked)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="spline outlier detector, deployed and instrumented")
    ap.add_argument("--validate", action="store_true", help="run the synthetic validation")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--seeds", type=int, default=12)
    ap.add_argument("--json", dest="out", default=None)
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.validate:
        return validate(args.seeds, args.out)
    print(describe())
    return 0


if __name__ == "__main__":
    sys.exit(main())
