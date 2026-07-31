"""Score vertebral labelling with the VerSe challenge organisers' own code.

The point of this module is that the metric is NOT ours. Identification rate and
Dice are computed by calling `get_hits` and `compute_dice` from
`github.com/anjany/verse`, vendored byte identical under `_verse_upstream/`
(MIT, Copyright (c) 2020 Anjany Kumar Sekuboyina). Everything in this file is
plumbing: find the cases, put both label volumes in one frame, resample to 1 mm
isotropic the way the organisers' `utils/evaluate.ipynb` does, hand the arrays
to their functions, aggregate.

Official metric, from their `get_hits` docstring verbatim:
"Successful identification defined as the correct label being closest and
< 20mm away."

WHICH DIRECTION THE RULE ACTUALLY RUNS. Their `construct_distance_matrix`
produces `d_mat[i, k] = || pred_i - gt_k ||`, so rows are predictions and
columns are ground truth. `get_hits` then takes `argmin(axis=1)`, that is, for
each PREDICTED landmark it finds the nearest GROUND TRUTH landmark and keeps the
diagonal. The rule their code implements is therefore

    a vertebra counts as identified if, for the predicted landmark carrying its
    label, the nearest ground truth landmark is that same label and lies within
    20 mm

which is the reverse of the plain reading of the docstring. Verified, not
inferred: `python -m spinelab.eval.verse --probe-direction` runs a three point
case that the two readings score differently, and their code returns the answer
for the prediction-to-ground-truth direction. The two readings agree whenever the
prediction has one landmark per ground truth vertebra and disagree when it does
not, which is exactly the mislabelled and spurious-detection regime we care
about. We do not change it. It is their metric.

The organisers' notebook resamples to 1 mm isotropic before scoring, with the
comment "evaluation was done at 1mm because annotations were performed at 1mm".
We reproduce that.

WHAT THEIR CODE DOES AND DOES NOT COVER
- `get_hits` gives hits and a per level hit list. Identification rate is
  hits / (number of vertebrae annotated in the ground truth), which is how their
  notebook computes it.
- `compute_dice` casts both inputs to bool. Called on multi label volumes, as
  their notebook calls it, it is therefore a FOREGROUND UNION Dice and is blind
  to labelling. We report it as `dice_fg` because that is their usage, and we
  additionally call the same function once per label value to get a label aware
  Dice. Both numbers come out of their function.
- Localisation distance is NOT shipped. Their notebook says so explicitly:
  "We do not provide scripts for Hausdorff distance and localisation distance."
  So `d_mean_*_mm` below is OUR code, a plain Euclidean distance between same
  label centroids. Label it as ours, not as theirs.

TWO DELIBERATE DEVIATIONS FROM THE NOTEBOOK, both documented and switchable

1. Centroid rescaling order. The notebook does

       true_msk = resample_nib(true_msk, (1,1,1), order=0)
       true_ctd = rescale_centroids(true_ctd, true_msk, (1,1,1))

   The second line is handed the ALREADY resampled image, whose zooms are
   (1,1,1), so `rescale_centroids` multiplies every coordinate by 1/1 and is a
   no op. Centroids stay in original voxel units while the mask is at 1 mm, and
   the 20 mm threshold is then applied in units of original voxels, which for
   VerSe means roughly 0.3 mm in plane and 0.9 to 3 mm through plane. We default
   to `centroid_frame="original"`, which passes the ORIGINAL image so the
   coordinates really become millimetres. `centroid_frame="notebook"` reproduces
   the literal notebook call for comparison.

2. One frame for both sides. Distances are only meaningful if the ground truth
   and the prediction are in the same axis order and the same units. We put the
   prediction on the ground truth's own grid with the organisers'
   `resample_mask_to` (order 0) before taking centroids, and we push the ground
   truth centroid json through the organisers' `reorient_centroids_to` first. On
   the VerSe release the json `direction` record always equals the mask axcodes,
   measured on 66/66 cases in `verse_4skx2`, so that reorient is a no op, but it
   is not free to assume so.

Published comparison figures, FROM THE LITERATURE, NOT MEASURED HERE, see
`LITERATURE` below.

Usage:
    python -m spinelab.eval.verse --list
    python -m spinelab.eval.verse --self-check [--limit N] [--json out.json]
    python -m spinelab.eval.verse --pred-dir DIR [--json out.json]
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import nibabel as nib
import numpy as np

from .. import paths
from . import _verse_upstream
from ._verse_upstream import data_utilities as dutils
from ._verse_upstream import eval_utilities as eutils

# --------------------------------------------------------------------------
# constants
# --------------------------------------------------------------------------

# From the organisers' notebook: "MAX_VERT_IDX = 28 # (in VerSe20, T13 has an
# index of 28)".
MAX_VERT_IDX = 28

# The organisers' own label table, data_utilities.v_dict. VerSe mask label
# values ARE the anatomical level.
V_DICT = dict(dutils.v_dict)

DEFAULT_ROOT = Path(os.environ.get(
    "SPINELAB_VERSE", str(paths.DATASETS / "verse_4skx2")))

MASK_SUFFIX = "_seg-vert_msk.nii.gz"
CTD_SUFFIX = "_seg-subreg_ctd.json"
CT_SUFFIX = "_ct.nii.gz"

# FROM THE LITERATURE. Not measured by this project. Read off the arXiv v4 of
# Sekuboyina et al., "VerSe: A Vertebrae Labelling and Segmentation Benchmark
# for Multi-detector CT Images", arXiv:2001.09193v4, 22 Mar 2021.
#
# Care is needed with the two headline numbers. 94.3 and 96.6 percent are the
# BEST single algorithm mean id.rate on each iteration's Hidden test set, not a
# mean across the benchmarked algorithms. The paper's own across-algorithm means
# are much lower and are in its Table 5.
LITERATURE = {
    "best_hidden_id_rate": {
        "verse19": {"id_rate_pct": 94.3, "team": "Payer C.",
                    "note": "Table 4a Hidden id.rate, printed as 94.25"},
        "verse20": {"id_rate_pct": 96.6, "team": "Chen D.",
                    "note": "highest mean id.rate on Hidden, Sec 4.1"},
        "source": "Sekuboyina et al., arXiv:2001.09193v4, Sec 4.1 and Table 4",
    },
    "mean_across_algorithms_hidden_id_rate_pct": {
        # Table 5, "Mean performance (id.rate and Dice) of all the evaluated
        # algorithms". Given as mean +/- sd.
        "verse19_all": [61.6, 43.6],
        "verse19_top5": [82.4, 31.6],
        "verse20_all": [72.8, 39.96],
        "verse20_top5": [94.4, 17.5],
        "source": "Sekuboyina et al., arXiv:2001.09193v4, Table 5",
    },
}


def literature_note() -> str:
    lit = LITERATURE["best_hidden_id_rate"]
    tab5 = LITERATURE["mean_across_algorithms_hidden_id_rate_pct"]
    return "\n".join([
        "PUBLISHED FIGURES, FROM THE LITERATURE, NOT MEASURED HERE",
        "  best single algorithm mean id.rate on the Hidden test set",
        "    VerSe'19  %.1f %%  (%s)" % (lit["verse19"]["id_rate_pct"],
                                        lit["verse19"]["team"]),
        "    VerSe'20  %.1f %%  (%s)" % (lit["verse20"]["id_rate_pct"],
                                        lit["verse20"]["team"]),
        "  mean id.rate ACROSS the benchmarked algorithms, Hidden test set",
        "    VerSe'19  all %.1f +/- %.1f %%   top-5 %.1f +/- %.1f %%"
        % (*tab5["verse19_all"], *tab5["verse19_top5"]),
        "    VerSe'20  all %.1f +/- %.2f %%   top-5 %.1f +/- %.1f %%"
        % (*tab5["verse20_all"], *tab5["verse20_top5"]),
        "  source: %s" % lit["source"],
    ])


# --------------------------------------------------------------------------
# from the organisers' notebook, utils/evaluate.ipynb
# --------------------------------------------------------------------------

def prepare_ctd_array(ctd_list, max_vert_idx):
    """Verbatim from the organisers' utils/evaluate.ipynb, 'compute id_rate'.

    Builds the (max_vert_idx, 3) array that get_hits expects: row i holds the
    centroid of vertebra i+1, NaN if that vertebra is absent.
    """
    ctd_arr = np.full((max_vert_idx, 3), np.nan)
    for item in ctd_list[1:]:  # first entry contains orientation
        vert_idx = item[0]
        if vert_idx <= max_vert_idx:
            X = item[1]
            Y = item[2]
            Z = item[3]
            ctd_arr[vert_idx - 1, :] = [X, Y, Z]
    return ctd_arr


# --------------------------------------------------------------------------
# plumbing
# --------------------------------------------------------------------------

@contextlib.contextmanager
def _hush(quiet: bool = True):
    """The organisers' helpers print on every call. Swallow it when asked."""
    if not quiet:
        yield
        return
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        yield


@dataclass
class Case:
    stem: str
    mask: Path
    ctd: Path
    ct: Path | None = None


def discover_cases(root: Path | str | None = None,
                   require_ct: bool = False) -> list[Case]:
    """Every case in `root` that has both a vertebra mask and a centroid json."""
    root = Path(root or DEFAULT_ROOT)
    if not root.is_dir():
        raise FileNotFoundError("VerSe root not found at %s" % root)
    stems: dict[str, dict[str, Path]] = {}
    for f in sorted(root.iterdir()):
        for key, suf in (("mask", MASK_SUFFIX), ("ctd", CTD_SUFFIX),
                         ("ct", CT_SUFFIX)):
            if f.name.endswith(suf):
                stems.setdefault(f.name[: -len(suf)], {})[key] = f
    out = []
    for stem in sorted(stems):
        got = stems[stem]
        if "mask" not in got or "ctd" not in got:
            continue
        if require_ct and "ct" not in got:
            continue
        out.append(Case(stem, got["mask"], got["ctd"], got.get("ct")))
    return out


def _axis_aligned(affine: np.ndarray, tol: float = 1e-6) -> bool:
    """True if each voxel axis maps to a single patient axis.

    When this is false, Euclidean distance in zoom scaled voxel units is only an
    approximation of physical millimetres. Two of the 66 cases in verse_4skx2
    are oblique sagittal reformats and fail this.
    """
    R = np.asarray(affine)[:3, :3]
    return all(np.count_nonzero(np.abs(R[:, j]) > tol) == 1 for j in range(3))


def _same_grid(a, b, tol: float = 1e-4) -> bool:
    return tuple(a.shape[:3]) == tuple(b.shape[:3]) and np.allclose(
        a.affine, b.affine, atol=tol)


def _template_like(img) -> nib.Nifti1Image:
    """An empty image carrying only the geometry of `img`.

    The organisers' `resample_mask_to` writes into `to_img.header`, so we never
    hand it an image whose data we still need.
    """
    return nib.Nifti1Image(np.zeros(img.shape[:3], np.uint8), img.affine)


def _as_label_image(img, tag: str = "label volume",
                    notes: list[str] | None = None) -> nib.Nifti1Image:
    """Same geometry, but the array is uint8. Everything downstream assumes it.

    This is not cosmetic. In `verse_4skx2` the vertebra masks are stored in
    three different dtypes, measured 2026-07-30 over 102 files: 49 uint8,
    51 float64, 2 uint16. That matters because the organisers' `resample_nib`
    fills outside the field of view with `cval=-1024`, a CT air value, which is
    right for the CT image the function was written for and wrong for a mask.
    On a float64 mask the 1 mm resample therefore comes back carrying -1024,
    and their `calc_centroids` takes `np.unique(msk_data)[1:]`, so -1024 is
    swallowed as the background and label 0 is handed to `prepare_ctd_array`,
    which writes it into row -1, that is T13. Casting to uint8 first makes the
    fill land on 0 and removes the whole failure mode. Verified: on uint8 input
    the resampled minimum is 0.
    """
    arr = np.asanyarray(img.dataobj)
    if arr.dtype == np.uint8:
        return img
    if arr.dtype.kind == "f":
        lo, hi = float(np.nanmin(arr)), float(np.nanmax(arr))
        finite = np.isfinite(arr)
        if not bool(finite.all()):
            if notes is not None:
                notes.append("%s: non finite voxels set to 0" % tag)
            out = np.zeros(arr.shape, np.uint8)
            if lo < 0 or hi > 255:
                raise ValueError("%s values outside 0..255: %s to %s"
                                 % (tag, lo, hi))
            np.copyto(out, arr, casting="unsafe", where=finite)
            return nib.Nifti1Image(out, img.affine)
    else:
        lo, hi = float(arr.min()), float(arr.max())
    if lo < 0 or hi > 255:
        raise ValueError("%s values outside 0..255: %s to %s" % (tag, lo, hi))
    if notes is not None:
        notes.append("%s: cast %s to uint8" % (tag, arr.dtype))
    return nib.Nifti1Image(arr.astype(np.uint8), img.affine)


def _load_label_volume(src, tag: str = "prediction",
                       notes: list[str] | None = None) -> nib.Nifti1Image:
    if isinstance(src, (str, os.PathLike)):
        img = nib.load(str(src))
    else:
        img = src
    return _as_label_image(img, tag=tag, notes=notes)


def _to_gt_grid(pred_img, gt_img, quiet: bool = True):
    """Put a predicted label volume on the ground truth's own voxel grid."""
    if _same_grid(pred_img, gt_img):
        return pred_img, False
    with _hush(quiet):
        out = dutils.resample_mask_to(pred_img, _template_like(gt_img))
    return out, True


def _label_array(img) -> np.ndarray:
    """Integer label array, with a guard against negative fill values."""
    arr = np.asanyarray(img.dataobj)
    if arr.dtype.kind == "f":
        arr = np.rint(arr)
    if arr.min() < 0:
        raise ValueError(
            "label volume carries negative values (min %s). Refusing to score: "
            "a negative fill would be treated as the background label."
            % arr.min())
    return arr.astype(np.int16, copy=False)


def _labels_of(arr: np.ndarray) -> set:
    return {int(v) for v in np.unique(arr) if v > 0}


def _iso_1mm(img, quiet: bool = True, tag: str = "mask",
             notes: list[str] | None = None):
    """1 mm isotropic nearest neighbour resample, the organisers' function.

    The input is cast to uint8 first, see `_as_label_image`. The output label
    set is checked against the input label set, which is what would catch a
    stray fill value if the cast ever stopped protecting us.
    """
    img = _as_label_image(img, tag=tag, notes=notes)
    src_labels = _labels_of(_label_array(img))
    with _hush(quiet):
        out = dutils.resample_nib(img, voxel_spacing=(1, 1, 1), order=0)
    new = _labels_of(_label_array(out)) - src_labels
    if new:
        raise ValueError(
            "1 mm resample of %s invented label values %s. The organisers' "
            "resample_nib uses cval=-1024, so this is almost certainly the out "
            "of field of view fill leaking in." % (tag, sorted(new)))
    return out


def _rescale(ctd_list, ref_img, quiet: bool = True):
    with _hush(quiet):
        return dutils.rescale_centroids(ctd_list, ref_img, (1, 1, 1))


def _clean_ctd(ctd_list, tag: str, notes: list[str]):
    """Drop centroid entries outside 1..MAX_VERT_IDX."""
    head, body = ctd_list[0], ctd_list[1:]
    keep = []
    for item in body:
        lab = int(item[0])
        if 1 <= lab <= MAX_VERT_IDX:
            keep.append([lab] + list(item[1:]))
        else:
            notes.append("%s: dropped out of range label %d" % (tag, lab))
    return [head] + keep


def gt_centroids(case: Case, gt_img, iso_img=None,
                 centroid_frame: str = "original", quiet: bool = True,
                 notes: list[str] | None = None):
    """Ground truth centroids from the organisers' json, in the score frame."""
    notes = notes if notes is not None else []
    ctd = dutils.load_centroids(str(case.ctd))
    direction = tuple(ctd[0])
    axc = tuple(nib.orientations.aff2axcodes(gt_img.affine))
    if direction != axc:
        notes.append("ctd direction %s differs from mask axcodes %s, "
                     "reoriented" % (direction, axc))
        with _hush(quiet):
            ctd = dutils.reorient_centroids_to(ctd, gt_img)
    ctd = _clean_ctd(ctd, "gt_ctd", notes)
    ref = iso_img if centroid_frame == "notebook" else gt_img
    return _rescale(ctd, ref, quiet=quiet)


def mask_centroids(msk_img, ref_img, centroid_frame: str = "original",
                   iso_img=None, quiet: bool = True,
                   notes: list[str] | None = None):
    """Centroids of a label volume, by the organisers' centre of mass code.

    This is what we have for a real prediction: a label volume and no centroid
    json. Note that a centre of mass of the whole vertebra mask is NOT the same
    landmark as the organisers' `seg-subreg` centroid, which sits in the
    vertebral body. The offset is measured in results/verse_scorer.md.
    """
    notes = notes if notes is not None else []
    msk_img = _as_label_image(msk_img, tag="centroid source", notes=notes)
    arr = _label_array(msk_img)
    if arr.min() != 0:
        notes.append("label volume has no zero background, calc_centroids "
                     "would drop the lowest label")
    with _hush(quiet):
        ctd = dutils.calc_centroids(msk_img)
    ctd = _clean_ctd(ctd, "pred_ctd", notes)
    ref = iso_img if centroid_frame == "notebook" else ref_img
    return _rescale(ctd, ref, quiet=quiet)


def shift_levels(arr: np.ndarray, by: int = 1) -> np.ndarray:
    """Relabel every vertebra v -> v+by. Deliberate corruption, for validation.

    Nearest neighbour resampling commutes with a relabelling, so shifting before
    or after the 1 mm resample gives the same volume.
    """
    out = arr.copy()
    nz = out > 0
    out[nz] = out[nz] + by
    return out


def shift_ctd(ctd_list, by: int = 1):
    """Same corruption applied to a centroid list."""
    return [ctd_list[0]] + [[int(v[0]) + by] + list(v[1:])
                            for v in ctd_list[1:]]


# --------------------------------------------------------------------------
# the score itself
# --------------------------------------------------------------------------

@dataclass
class CaseScore:
    case: str
    variant: str = "pred"
    n_gt: int = 0
    n_pred: int = 0
    n_matched: int = 0
    hits: int = 0
    id_rate: float = float("nan")
    d_mean_matched_mm: float | None = None
    d_mean_hits_mm: float | None = None
    d_max_matched_mm: float | None = None
    dice_fg: float | None = None
    dice_label_mean: float | None = None
    dice_per_label: dict = field(default_factory=dict)
    hit_list: dict = field(default_factory=dict)
    dist_mm: dict = field(default_factory=dict)
    axis_aligned: bool = True
    zooms: tuple = ()
    notes: list = field(default_factory=list)

    def as_dict(self) -> dict:
        d = dict(self.__dict__)
        d["zooms"] = list(self.zooms)
        return d


def _score_centroids(name: str, variant: str,
                     gt_ctd_1mm, pred_ctd_1mm) -> CaseScore:
    """Call the organisers' get_hits and derive the distances we add ourselves."""
    gt_arr = prepare_ctd_array(gt_ctd_1mm, MAX_VERT_IDX)
    pr_arr = prepare_ctd_array(pred_ctd_1mm, MAX_VERT_IDX)

    # organisers' code, unmodified
    hits, hit_list = eutils.get_hits(gt_arr, pr_arr, MAX_VERT_IDX)

    verts_in_gt = np.argwhere(~np.isnan(gt_arr[:, 0])).reshape(-1) + 1
    verts_in_pred = np.argwhere(~np.isnan(pr_arr[:, 0])).reshape(-1) + 1
    matched = np.intersect1d(verts_in_gt, verts_in_pred)

    sc = CaseScore(case=name, variant=variant)
    sc.n_gt = int(verts_in_gt.size)
    sc.n_pred = int(verts_in_pred.size)
    sc.n_matched = int(matched.size)
    sc.hits = int(hits)
    sc.id_rate = float(hits) / sc.n_gt if sc.n_gt else float("nan")
    sc.hit_list = {int(v): (None if np.isnan(hit_list[v - 1])
                            else int(hit_list[v - 1]))
                   for v in range(1, MAX_VERT_IDX + 1)
                   if not np.isnan(hit_list[v - 1])}

    # OUR code. The organisers deliberately ship no localisation distance.
    d_all, d_hit = [], []
    for v in matched:
        d = float(np.linalg.norm(gt_arr[v - 1] - pr_arr[v - 1]))
        sc.dist_mm[int(v)] = d
        d_all.append(d)
        if hit_list[v - 1] == 1:
            d_hit.append(d)
    if d_all:
        sc.d_mean_matched_mm = float(np.mean(d_all))
        sc.d_max_matched_mm = float(np.max(d_all))
    if d_hit:
        sc.d_mean_hits_mm = float(np.mean(d_hit))
    return sc


def _add_dice(sc: CaseScore, gt_arr: np.ndarray, pred_arr: np.ndarray) -> None:
    """Dice through the organisers' compute_dice, twice over.

    dice_fg          their notebook's call, on the multi label volumes. Their
                     function casts to bool, so this is foreground union Dice
                     and is BLIND to labelling.
    dice_per_label   the same function, called once per label value.
    """
    if gt_arr.shape != pred_arr.shape:
        raise ValueError("Dice needs one grid: %s vs %s"
                         % (gt_arr.shape, pred_arr.shape))
    sc.dice_fg = float(eutils.compute_dice(pred_arr, gt_arr))
    gt_labels = [int(v) for v in np.unique(gt_arr) if v > 0]
    per = {}
    for v in gt_labels:
        per[int(v)] = float(eutils.compute_dice(pred_arr == v, gt_arr == v))
    sc.dice_per_label = per
    if per:
        sc.dice_label_mean = float(np.mean(list(per.values())))


def score_case(case: Case, pred, pred_ctd=None, dice: bool = True,
               centroid_frame: str = "original", quiet: bool = True,
               variant: str = "pred") -> CaseScore:
    """Score one predicted label volume against one VerSe case.

    pred        path to a label volume, or a nibabel image. Values must be VerSe
                level numbers (1-7 C1-C7, 8-19 T1-T12, 20-25 L1-L6, 26 sacrum,
                27 coccyx, 28 T13).
    pred_ctd    optional path to a centroid json in the organisers' format. If
                given it is used as the predicted landmark set, which is the
                literal challenge submission format. If not, landmarks are the
                centres of mass of the label volume.
    """
    if centroid_frame not in ("original", "notebook"):
        raise ValueError("centroid_frame must be 'original' or 'notebook'")

    notes: list[str] = []
    gt_img = nib.load(str(case.mask))
    pred_img = _load_label_volume(pred, tag="prediction", notes=notes)
    pred_img, resampled = _to_gt_grid(pred_img, gt_img, quiet=quiet)
    if resampled:
        notes.append("prediction resampled onto the ground truth grid, order 0")

    need_iso = dice or centroid_frame == "notebook"
    gt_iso = _iso_1mm(gt_img, quiet=quiet, tag="ground truth mask",
                      notes=notes) if need_iso else None

    gt_ctd_1mm = gt_centroids(case, gt_img, iso_img=gt_iso,
                              centroid_frame=centroid_frame, quiet=quiet,
                              notes=notes)
    if pred_ctd is not None:
        pctd = dutils.load_centroids(str(pred_ctd))
        pdir = tuple(pctd[0])
        axc = tuple(nib.orientations.aff2axcodes(gt_img.affine))
        if pdir != axc:
            notes.append("pred ctd direction %s differs from grid %s, "
                         "reoriented" % (pdir, axc))
            with _hush(quiet):
                pctd = dutils.reorient_centroids_to(pctd, gt_img)
        pctd = _clean_ctd(pctd, "pred_ctd", notes)
        ref = gt_iso if centroid_frame == "notebook" else gt_img
        pred_ctd_1mm = _rescale(pctd, ref, quiet=quiet)
    else:
        pred_ctd_1mm = mask_centroids(
            pred_img, gt_img, centroid_frame=centroid_frame, iso_img=gt_iso,
            quiet=quiet, notes=notes)

    sc = _score_centroids(case.stem, variant, gt_ctd_1mm, pred_ctd_1mm)
    sc.axis_aligned = _axis_aligned(gt_img.affine)
    sc.zooms = tuple(round(float(z), 4) for z in gt_img.header.get_zooms()[:3])
    if not sc.axis_aligned:
        notes.append("affine is not axis aligned, zoom scaled distances are "
                     "approximate millimetres")

    if dice:
        pred_iso, _ = _to_gt_grid(pred_img, gt_iso, quiet=quiet)
        _add_dice(sc, _label_array(gt_iso), _label_array(pred_iso))
    sc.notes = notes
    return sc


# --------------------------------------------------------------------------
# validation of the wrapper itself
# --------------------------------------------------------------------------

def self_check_case(case: Case, dice: bool = True,
                    centroid_frame: str = "original",
                    shift_by: int = 1, quiet: bool = True) -> list[CaseScore]:
    """Score the ground truth against itself, then against a corrupted copy.

    Three variants, all on one case:

    identity_json  ground truth mask and ground truth centroid json as the
                   prediction. This is the organisers' own notebook self test.
                   MUST give id rate 1.0, Dice 1.0, distance 0.0.
    identity_com   ground truth mask as the prediction, landmarks taken from it
                   by centre of mass. MUST give id rate 1.0 and Dice 1.0. The
                   distance is not zero: it measures how far a whole vertebra
                   centre of mass sits from the organisers' vertebral body
                   centroid, which is the floor on localisation distance for any
                   method that reports mask centres of mass.
    shift_%+d      every label moved by shift_by levels, in the mask and in the
                   centroid json. The identification rate MUST collapse.

    On the shifted variant, expect AT MOST ONE residual hit per case, and only
    in the cervical and thoracic spine. It is a boundary artefact of the
    organisers' own code, not of this wrapper. Their `get_hits` restricts the
    distance matrix to labels present in BOTH sets. Under a +1 shift the
    prediction has no landmark for the topmost ground truth level, so that
    level's column is dropped, and the topmost prediction, which sits on the
    topmost ground truth vertebra, then finds the second level as its nearest
    surviving ground truth column. That counts as a hit when the two vertebrae
    are less than 20 mm apart, which holds in the cervical spine, around 17 mm,
    and fails in the lumbar spine, around 30 mm.

    The 1 mm resample is done once and reused, because nearest neighbour
    resampling commutes with a relabelling.
    """
    notes: list[str] = []
    gt_img = nib.load(str(case.mask))
    gt_iso = None
    if dice or centroid_frame == "notebook":
        gt_iso = _iso_1mm(gt_img, quiet=quiet, tag="ground truth mask",
                          notes=notes)

    gt_ctd_1mm = gt_centroids(case, gt_img, iso_img=gt_iso,
                              centroid_frame=centroid_frame, quiet=quiet,
                              notes=notes)
    com_ctd_1mm = mask_centroids(gt_img, gt_img, centroid_frame=centroid_frame,
                                 iso_img=gt_iso, quiet=quiet, notes=notes)
    shifted_ctd_1mm = shift_ctd(gt_ctd_1mm, shift_by)

    aligned = _axis_aligned(gt_img.affine)
    zooms = tuple(round(float(z), 4) for z in gt_img.header.get_zooms()[:3])

    out = []
    plans = [
        ("identity_json", gt_ctd_1mm, False),
        ("identity_com", com_ctd_1mm, False),
        ("shift_%+d" % shift_by, shifted_ctd_1mm, True),
    ]
    gt_arr = _label_array(gt_iso) if dice else None
    for variant, pctd, corrupt in plans:
        sc = _score_centroids(case.stem, variant, gt_ctd_1mm, pctd)
        sc.axis_aligned = aligned
        sc.zooms = zooms
        sc.notes = list(notes)
        if dice:
            pred_arr = shift_levels(gt_arr, shift_by) if corrupt else gt_arr
            _add_dice(sc, gt_arr, pred_arr)
        out.append(sc)
    return out


# --------------------------------------------------------------------------
# aggregation
# --------------------------------------------------------------------------

def probe_matching_direction() -> dict:
    """Ask the organisers' get_hits which direction its nearest neighbour runs.

    Three collinear landmarks. Ground truth at x = 0, 10, 100. Prediction at
    x = 0, 0.5, 100, so the second prediction has drifted onto the first ground
    truth landmark.

    read as "for each GT, the nearest PRED must share its label"
        gt 1 -> pred 1 at 0.0, hit. gt 2 -> pred 2 at 0.5 is 9.5 away and is the
        nearest, hit. gt 3 -> hit. total 3.
    read as "for each PRED, the nearest GT must share its label"
        pred 1 -> gt 1, hit. pred 2 at 0.5 -> nearest gt is gt 1 at 0.5, not its
        own label, miss. pred 3 -> hit. total 2.
    """
    n = 3
    gt = np.full((n, 3), np.nan)
    pr = np.full((n, 3), np.nan)
    gt[0], gt[1], gt[2] = [0.0, 0, 0], [10.0, 0, 0], [100.0, 0, 0]
    pr[0], pr[1], pr[2] = [0.0, 0, 0], [0.5, 0, 0], [100.0, 0, 0]
    hits, hit_list = eutils.get_hits(gt, pr, n)
    direction = {3: "gt_to_pred", 2: "pred_to_gt"}.get(int(hits), "unknown")
    out = {"hits": int(hits),
           "hit_list": [None if np.isnan(h) else int(h) for h in hit_list],
           "direction": direction}
    print("=" * 78)
    print("DIRECTION OF THE OFFICIAL MATCHING RULE, asked of get_hits itself")
    print("=" * 78)
    print("  gt   x = 0, 10, 100")
    print("  pred x = 0, 0.5, 100")
    print("  hits returned          %d" % out["hits"])
    print("  hit_list               %s" % out["hit_list"])
    print("  3 would mean           for each GT, nearest PRED must share label")
    print("  2 would mean           for each PRED, nearest GT must share label")
    print("  conclusion             %s" % direction)
    return out


def _mean(xs):
    xs = [x for x in xs if x is not None and not (isinstance(x, float)
                                                 and np.isnan(x))]
    return float(np.mean(xs)) if xs else None


def _median(xs):
    xs = [x for x in xs if x is not None and not (isinstance(x, float)
                                                 and np.isnan(x))]
    return float(statistics.median(xs)) if xs else None


def pool(scores: list[CaseScore]) -> dict:
    """Pooled and per level aggregation over cases."""
    n_gt = sum(s.n_gt for s in scores)
    hits = sum(s.hits for s in scores)
    per_level: dict[int, dict] = {}
    all_d: list[float] = []
    for s in scores:
        for lvl, h in s.hit_list.items():
            rec = per_level.setdefault(lvl, {"n_gt": 0, "hits": 0, "d": []})
            rec["n_gt"] += 1
            rec["hits"] += int(h)
        for lvl, d in s.dist_mm.items():
            per_level.setdefault(lvl, {"n_gt": 0, "hits": 0, "d": []})
            per_level[lvl]["d"].append(d)
            all_d.append(d)
    levels = {}
    for lvl in sorted(per_level):
        rec = per_level[lvl]
        levels[lvl] = {
            "name": V_DICT.get(lvl, str(lvl)),
            "n_gt": rec["n_gt"],
            "hits": rec["hits"],
            "id_rate": (rec["hits"] / rec["n_gt"]) if rec["n_gt"] else None,
            "d_mean_mm": _mean(rec["d"]),
        }
    return {
        "n_cases": len(scores),
        "n_gt_vertebrae": n_gt,
        "hits": hits,
        "id_rate_pooled": (hits / n_gt) if n_gt else None,
        "id_rate_mean_per_case": _mean([s.id_rate for s in scores]),
        "id_rate_median_per_case": _median([s.id_rate for s in scores]),
        "d_mean_matched_mm_pooled": _mean(all_d),
        "d_mean_matched_mm_mean_per_case":
            _mean([s.d_mean_matched_mm for s in scores]),
        "dice_fg_mean": _mean([s.dice_fg for s in scores]),
        "dice_fg_median": _median([s.dice_fg for s in scores]),
        "dice_label_mean": _mean([s.dice_label_mean for s in scores]),
        "dice_label_median": _median([s.dice_label_mean for s in scores]),
        "per_level": levels,
    }


def provenance() -> dict:
    return {
        "scorer": _verse_upstream.UPSTREAM,
        "licence": "MIT, Copyright (c) 2020 Anjany Kumar Sekuboyina",
        "vendored_sha256": dict(_verse_upstream.SHA256),
        "functions_used": ["eval_utilities.get_hits",
                           "eval_utilities.compute_dice",
                           "data_utilities.load_centroids",
                           "data_utilities.rescale_centroids",
                           "data_utilities.reorient_centroids_to",
                           "data_utilities.calc_centroids",
                           "data_utilities.resample_nib",
                           "data_utilities.resample_mask_to"],
        "ours_not_theirs": ["localisation distance", "per level pooling",
                            "case discovery", "label shift corruption"],
        "max_vert_idx": MAX_VERT_IDX,
        "threshold_mm": 20.0,
        "numpy": np.__version__,
        "nibabel": nib.__version__,
    }


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------

def print_case_table(scores: list[CaseScore], title: str) -> None:
    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)
    print("  %-24s %-14s %4s %4s %5s %8s %9s %8s %8s"
          % ("case", "variant", "nGT", "nPr", "hits", "id.rate",
             "d_mean/mm", "dice_fg", "dice_lab"))
    for s in scores:
        print("  %-24s %-14s %4d %4d %5d %8.4f %9s %8s %8s" % (
            s.case[:24], s.variant, s.n_gt, s.n_pred, s.hits, s.id_rate,
            "n/a" if s.d_mean_matched_mm is None
            else "%.3f" % s.d_mean_matched_mm,
            "n/a" if s.dice_fg is None else "%.4f" % s.dice_fg,
            "n/a" if s.dice_label_mean is None
            else "%.4f" % s.dice_label_mean))


def print_pool(p: dict, title: str) -> None:
    print("\n" + "-" * 100)
    print(title)
    print("-" * 100)
    print("  cases                     %d" % p["n_cases"])
    print("  ground truth vertebrae    %d" % p["n_gt_vertebrae"])
    print("  hits                      %d" % p["hits"])
    for key, label in (
            ("id_rate_pooled", "id.rate pooled over vertebrae"),
            ("id_rate_mean_per_case", "id.rate mean over cases"),
            ("id_rate_median_per_case", "id.rate median over cases"),
            ("d_mean_matched_mm_pooled", "d_mean over matched vertebrae, mm"),
            ("dice_fg_mean", "dice foreground union, mean"),
            ("dice_label_mean", "dice per label, mean"),
    ):
        v = p[key]
        print("  %-40s %s" % (label, "n/a" if v is None else "%.4f" % v))
    print("\n  per level")
    print("    %-4s %-7s %5s %5s %8s %10s"
          % ("lvl", "name", "nGT", "hits", "id.rate", "d_mean/mm"))
    for lvl, rec in p["per_level"].items():
        print("    %-4d %-7s %5d %5d %8s %10s" % (
            lvl, rec["name"], rec["n_gt"], rec["hits"],
            "n/a" if rec["id_rate"] is None else "%.4f" % rec["id_rate"],
            "n/a" if rec["d_mean_mm"] is None else "%.3f" % rec["d_mean_mm"]))


# --------------------------------------------------------------------------
# cli
# --------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=str(DEFAULT_ROOT),
                    help="VerSe case directory, default %s" % DEFAULT_ROOT)
    ap.add_argument("--list", action="store_true", help="list cases and exit")
    ap.add_argument("--probe-direction", action="store_true",
                    help="ask the organisers' get_hits which direction its "
                         "nearest neighbour rule runs, then exit")
    ap.add_argument("--self-check", action="store_true",
                    help="score the ground truth against itself and against a "
                         "level shifted copy")
    ap.add_argument("--pred-dir", default=None,
                    help="directory of predicted label volumes named "
                         "<stem>%s or <stem>.nii.gz" % MASK_SUFFIX)
    ap.add_argument("--pred-suffix", default=None,
                    help="explicit suffix for prediction filenames")
    ap.add_argument("--shift-by", type=int, default=1,
                    help="level shift used by --self-check, default 1")
    ap.add_argument("--limit", type=int, default=None, help="first N cases only")
    ap.add_argument("--no-dice", action="store_true",
                    help="skip Dice, which skips the 1 mm resample and is far "
                         "faster")
    ap.add_argument("--centroid-frame", default="original",
                    choices=("original", "notebook"),
                    help="'original' rescales centroids by the source spacing "
                         "so distances are millimetres. 'notebook' reproduces "
                         "the organisers' notebook call, which is a no op and "
                         "leaves distances in source voxel units.")
    ap.add_argument("--verbose", action="store_true",
                    help="let the organisers' helpers print")
    ap.add_argument("--json", dest="out", default=None, help="write records here")
    args = ap.parse_args(argv)

    if args.probe_direction:
        probe_matching_direction()
        return 0

    cases = discover_cases(args.root)
    if args.limit:
        cases = cases[: args.limit]
    if not cases:
        print("no complete cases under %s" % args.root)
        return 1

    if args.list:
        print("%d complete cases under %s" % (len(cases), args.root))
        for c in cases:
            print("  %s" % c.stem)
        return 0

    dice = not args.no_dice
    quiet = not args.verbose
    t0 = time.time()
    record = {"provenance": provenance(), "literature": LITERATURE,
              "root": str(args.root), "centroid_frame": args.centroid_frame,
              "dice": dice, "cases": [c.stem for c in cases]}

    if args.self_check:
        record["matching_direction"] = probe_matching_direction()
        by_variant: dict[str, list[CaseScore]] = {}
        rows: list[CaseScore] = []
        for i, c in enumerate(cases, 1):
            print("[%d/%d] %s" % (i, len(cases), c.stem), flush=True)
            for sc in self_check_case(c, dice=dice,
                                      centroid_frame=args.centroid_frame,
                                      shift_by=args.shift_by, quiet=quiet):
                by_variant.setdefault(sc.variant, []).append(sc)
                rows.append(sc)
        print_case_table(rows, "SELF CHECK, per case")
        record["variants"] = {}
        for variant, scs in by_variant.items():
            p = pool(scs)
            record["variants"][variant] = {
                "pooled": p, "cases": [s.as_dict() for s in scs]}
            print_pool(p, "SELF CHECK POOLED, variant %s" % variant)
        ok = _verdict(record["variants"], args.shift_by)
        record["verdict"] = ok
    else:
        if not args.pred_dir:
            print("nothing to do: pass --self-check, --pred-dir or --list")
            return 2
        pdir = Path(args.pred_dir)
        scores = []
        for i, c in enumerate(cases, 1):
            cand = _find_pred(pdir, c.stem, args.pred_suffix)
            if cand is None:
                print("[%d/%d] %s  NO PREDICTION" % (i, len(cases), c.stem))
                continue
            print("[%d/%d] %s  <- %s" % (i, len(cases), c.stem, cand.name),
                  flush=True)
            scores.append(score_case(c, cand, dice=dice,
                                     centroid_frame=args.centroid_frame,
                                     quiet=quiet))
        if not scores:
            print("no predictions matched")
            return 1
        print_case_table(scores, "PREDICTIONS, per case")
        p = pool(scores)
        record["pooled"] = p
        record["scores"] = [s.as_dict() for s in scores]
        print_pool(p, "PREDICTIONS POOLED")

    print("\n" + literature_note())
    print("\nelapsed %.1f s" % (time.time() - t0))

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(record, indent=2), encoding="utf-8")
        print("wrote %s" % args.out)
    return 0


def _find_pred(pdir: Path, stem: str, suffix: str | None) -> Path | None:
    cands = []
    if suffix:
        cands.append(pdir / (stem + suffix))
    else:
        cands += [pdir / (stem + MASK_SUFFIX), pdir / (stem + ".nii.gz"),
                  pdir / (stem + "_pred.nii.gz")]
    for c in cands:
        if c.exists():
            return c
    return None


def _verdict(variants: dict, shift_by: int) -> dict:
    """Hard pass or fail on the two checks that have a known answer."""
    out = {}
    ident = variants.get("identity_json", {}).get("pooled", {})
    out["identity_json_id_rate"] = ident.get("id_rate_pooled")
    out["identity_json_dice_fg"] = ident.get("dice_fg_mean")
    out["identity_json_dice_label"] = ident.get("dice_label_mean")
    out["identity_json_d_mean_mm"] = ident.get("d_mean_matched_mm_pooled")
    out["identity_json_PASS"] = bool(
        ident.get("id_rate_pooled") == 1.0
        and (ident.get("dice_fg_mean") is None
             or abs(ident["dice_fg_mean"] - 1.0) < 1e-12))
    com = variants.get("identity_com", {}).get("pooled", {})
    out["identity_com_id_rate"] = com.get("id_rate_pooled")
    out["identity_com_d_mean_mm"] = com.get("d_mean_matched_mm_pooled")
    out["identity_com_PASS"] = com.get("id_rate_pooled") == 1.0
    key = "shift_%+d" % shift_by
    sh = variants.get(key, {}).get("pooled", {})
    out["shift_id_rate"] = sh.get("id_rate_pooled")
    out["shift_dice_fg"] = sh.get("dice_fg_mean")
    out["shift_dice_label"] = sh.get("dice_label_mean")
    # At most one residual hit per case is expected, see self_check_case. The
    # test is that the rate collapses and that any survivor is that artefact.
    out["shift_hits"] = sh.get("hits")
    out["shift_n_cases"] = sh.get("n_cases")
    out["shift_hits_le_one_per_case"] = bool(
        sh.get("hits") is not None and sh["hits"] <= sh.get("n_cases", 0))
    out["shift_PASS"] = bool(
        sh.get("id_rate_pooled") is not None
        and sh["id_rate_pooled"] < 0.2
        and out["shift_hits_le_one_per_case"])
    print("\n" + "=" * 100)
    print("VERDICT")
    print("=" * 100)
    for k, v in out.items():
        print("  %-30s %s" % (k, v))
    return out


if __name__ == "__main__":
    sys.exit(main())
