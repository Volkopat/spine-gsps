"""E1: does per vertebra confidence predict a labelling error, and does the softmax
channel selection explain the difference?

The question the project has never been able to answer. Every published confidence
number came from a mapping that reads the SACRUM channel for lumbar vertebrae, and
was evaluated in sample against Likert ratings. Here the label is ground truth
correctness on public data, so a vertebra is wrong when its assigned level does not
match the VerSe ground truth level at the same location.

Arms, all computed from the SAME batch run so the only thing that varies is channel
selection:

  region_retired   channel from the first letter of the name. What produced every
                   published number. Reads the sacrum channel for all lumbar levels.
  parity_name      odd/even parity from the canonical anatomical ordinal. What the
                   deployed server does.
  parity_sequence  odd/even parity from the vertebra's position in the DETECTED
                   sequence. Correct in principle, since the model's alternation
                   follows detection order, not anatomy.
  mapping_free     no name to channel mapping at all. Uses the top-1 channel mean and
                   the top1 minus top2 margin over all channels.
  argmax_mean      applies the deployed confidence FORMULA to the highest-mean channel.

Note on naming. This arm was previously called `oracle_channel` and described as an
upper bound on any channel selection rule. **That was wrong on both counts.** It is not
ground-truth informed, so it is not an oracle, and it is not a bound, which is why two
other arms beat it. It differs from `mapping_free_top1` only in what is scored: that arm
uses the top channel's mean probability directly, while this one feeds the same channel
through the abstract's weighted formula. Renamed after an adversarial reviewer pointed
out that an arm labelled as a ceiling was not the tallest bar in the figure.

Two genuine ceilings ARE now computed, chosen with the labels and therefore real upper
bounds, reported separately from the arms so they are not mistaken for rules anyone
could deploy:

  best_fixed_channel  the single channel that, used for every vertebra, maximises AUC.
                      Bounds any fixed-channel rule.
  best_per_level      per anatomical level, the channel maximising separation. Bounds
                      any NAME-based mapping, which is the right ceiling for the region
                      and parity arms since both are name-based.

Every arm also reports a Hanley and McNeil 95 percent interval, because at this sample
size the leading arms cannot be ranked against one another and a bare ordered table
invites exactly that misreading.

The confidence formula is held fixed at the abstract's weights,
0.20*mean + 0.50*p95 + 0.30*high_conf_ratio, so the ablation isolates channel
selection rather than confounding it with a formula change.

Usage:
  python scripts/e1_ablation.py --run-dir <path>\\runs\\verse_batch_01
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import re
import statistics
import sys
from pathlib import Path

import nibabel as nib
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from spinelab.confidence import channels as CH  # noqa: E402
from spinelab.paths import DATASETS, RESULTS  # noqa: E402

# VerSe mask label value -> anatomical name
VERSE_NAME = {}
for i in range(1, 8):
    VERSE_NAME[i] = "C%d" % i
for i in range(8, 20):
    VERSE_NAME[i] = "T%d" % (i - 7)
for i in range(20, 26):
    VERSE_NAME[i] = "L%d" % (i - 19)
VERSE_NAME[26] = "SACRUM"
VERSE_NAME[27] = "COCCYX"
VERSE_NAME[28] = "T13"

MATCH_TOLERANCE_MM = 20.0   # the VerSe identification rule


def conf_from_channel(ch_stats: dict, n_voxels: int) -> float:
    """The abstract's formula, applied to one channel's statistics."""
    mean = float(ch_stats.get("mean", 0.0))
    p95 = float(ch_stats.get("p95", 0.0))
    hi = float(ch_stats.get("n_gt_0p7", 0)) / max(1, n_voxels)
    return 0.20 * mean + 0.50 * p95 + 0.30 * min(1.0, hi)


def _gt_centroids_uncached(mask_path: Path) -> dict[str, list]:
    img = nib.load(str(mask_path))
    m = np.asanyarray(img.dataobj).round().astype(np.int16)
    aff = img.affine
    out = {}
    for v in np.unique(m):
        v = int(v)
        if v <= 0 or v not in VERSE_NAME:
            continue
        idx = np.array(np.nonzero(m == v), dtype=np.float64)
        if idx.shape[1] == 0:
            continue
        c = idx.mean(axis=1)
        out[VERSE_NAME[v]] = (aff[:3, :3] @ c + aff[:3, 3]).tolist()
    return out


def gt_centroids_world(mask_path: Path, cache_dir: Path | None = None
                       ) -> dict[str, np.ndarray]:
    """Ground truth centroids in world coordinates, cached to JSON.

    Decompressing and scanning a full VerSe mask costs a few seconds, which is
    fine once and prohibitive across 202 cases on every re-run. The cache keys on
    the mask's size and modification time so a changed file invalidates it.
    """
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        st = mask_path.stat()
        key = "%s__%d_%d.json" % (mask_path.name.replace(".nii.gz", ""),
                                  st.st_size, int(st.st_mtime))
        cp = cache_dir / key
        if cp.exists():
            try:
                return {k: np.asarray(v, dtype=np.float64)
                        for k, v in json.loads(cp.read_text()).items()}
            except Exception:
                pass
        out = _gt_centroids_uncached(mask_path)
        cp.write_text(json.dumps(out))
        return {k: np.asarray(v, dtype=np.float64) for k, v in out.items()}
    return {k: np.asarray(v, dtype=np.float64)
            for k, v in _gt_centroids_uncached(mask_path).items()}


def auc(pos: list[float], neg: list[float]) -> float:
    """P(pos < neg): AUC for a LOW score identifying the positive class (an error)."""
    if not pos or not neg:
        return float("nan")
    w = t = 0
    for a in pos:
        for b in neg:
            if a < b:
                w += 1
            elif a == b:
                t += 1
    return (w + 0.5 * t) / (len(pos) * len(neg))


def auc_ci(a: float, n_pos: int, n_neg: int, z: float = 1.96) -> tuple[float, float]:
    """Hanley and McNeil 95 percent interval.

    Adversarial review Comment 5: with roughly 98 matched vertebrae the interval on an
    AUC near 0.86 is wide enough that the top arms cannot be ranked against each other.
    Reporting point estimates alone invites exactly that misreading, so every arm now
    carries an interval.
    """
    if not (a == a) or n_pos < 1 or n_neg < 1:
        return (float("nan"), float("nan"))
    q1 = a / (2.0 - a)
    q2 = 2.0 * a * a / (1.0 + a)
    var = (a * (1 - a) + (n_pos - 1) * (q1 - a * a)
           + (n_neg - 1) * (q2 - a * a)) / (n_pos * n_neg)
    se = max(var, 0.0) ** 0.5
    return (max(0.0, a - z * se), min(1.0, a + z * se))


def _arm_score_one(kind: str, r: dict, chans: dict, nvox: int):
    """One arm's confidence for one vertebra, or None where the arm is undefined.

    Module level and shared by every caller on purpose. The full-population scoring,
    the common-subset re-scoring and any test all go through this one function, so a
    change to an arm cannot be applied to one and missed by another.
    """
    try:
        if kind == "region_retired":
            ci = CH.channel_region_retired(r["name"])
            return conf_from_channel(chans.get(str(ci), {}), nvox)
        if kind == "parity_name":
            ci = CH.channel_parity(r["name"])
            return conf_from_channel(chans.get(str(ci), {}), nvox)
        if kind == "parity_region_deployed":
            # The rule the deployed service ACTUALLY ships. utils/
            # confidence_calculator.py::get_vertebra_channel takes the integer
            # inside the vertebra's own name and tests its parity, so counting
            # restarts at C1, T1 and L1 rather than running down the column.
            # tests/test_channels.py has pinned this since the suite was written:
            # it agrees with continuous parity on C1 to C7 only, and C7 and T1
            # collide. An earlier version of this ablation labelled `parity_name`
            # "the deployed rule"; it is not, and the two disagree on 90.2 percent
            # of scored vertebrae. See G20.
            ci = CH.channel_region_restart(r["name"])
            return conf_from_channel(chans.get(str(ci), {}), nvox)
        if kind == "parity_sequence":
            ci = CH.channel_parity(r["name"], ordinal=r["seq"])
            return conf_from_channel(chans.get(str(ci), {}), nvox)
        if kind == "parity_sequence_phased":
            # The model's alternation phase is arbitrary: whether the topmost
            # DETECTED vertebra landed on vertebrae_O or vertebrae_E depends on
            # where counting began, not on anatomy. Using the raw sequence index
            # assumes one phase and inverts every vertebra in the case when that
            # guess is wrong, which is why the uncalibrated arm scores below
            # chance. Estimate the phase per case from the data: pick whichever
            # offset puts more total probability on the selected channel.
            ci = CH.channel_parity(r["name"], ordinal=r["seq"] + r["phase"])
            return conf_from_channel(chans.get(str(ci), {}), nvox)
        if kind == "parity_sequence_inverted":
            # A single GLOBAL sign flip, not a per-case estimate. If this matches
            # parity_sequence_phased then the phase is effectively constant across
            # cases and the per-case machinery is not doing any work: the deployed
            # rule simply had the sign backwards.
            ci = CH.channel_parity(r["name"], ordinal=r["seq"] + 1)
            return conf_from_channel(chans.get(str(ci), {}), nvox)
        if kind in ("mapping_free_top1", "mapping_free_margin", "argmax_mean"):
            means = {int(k): float(d.get("mean", 0.0)) for k, d in chans.items()}
            if not means:
                return None
            order = sorted(means.items(), key=lambda kv: -kv[1])
            if kind == "mapping_free_top1":
                return order[0][1]
            if kind == "mapping_free_margin":
                return order[0][1] - (order[1][1] if len(order) > 1 else 0.0)
            return conf_from_channel(chans[str(order[0][0])], nvox)
        raise ValueError(kind)
    except Exception:
        return None


def _auc_fast(s: np.ndarray, wrong: np.ndarray) -> float:
    """Vectorised P(score_wrong < score_right), identical to `auc` including ties.

    Rank based rather than pairwise, so the coordinate ascent below is affordable.
    NaN scores are dropped, which reproduces the `continue` in the slow version.
    `test_e1_auc_fast_matches_slow` asserts the two agree on random inputs.
    """
    ok = ~np.isnan(s)
    s, wrong = s[ok], wrong[ok]
    pos, neg = s[wrong], s[~wrong]
    if pos.size == 0 or neg.size == 0:
        return float("nan")
    order = np.argsort(s, kind="mergesort")
    ranks = np.empty(s.size, dtype=np.float64)
    sv = s[order]
    i = 0
    while i < sv.size:                      # average ranks within each tie group
        j = i
        while j + 1 < sv.size and sv[j + 1] == sv[i]:
            j += 1
        ranks[order[i:j + 1]] = 0.5 * (i + j) + 1.0
        i = j + 1
    # U for "positive ranks LOW", i.e. P(pos < neg)
    rp = ranks[wrong].sum()
    n_p, n_n = float(pos.size), float(neg.size)
    u = n_p * n_n + n_p * (n_p + 1.0) / 2.0 - rp
    return u / (n_p * n_n)


def _score_matrix(scorable: list[dict]) -> tuple[np.ndarray, np.ndarray, list[int]]:
    """(n_rows, n_channels) confidence, NaN where the channel is absent."""
    chans = sorted({int(k) for r in scorable for k in (r["v"].get("channels") or {})})
    m = np.full((len(scorable), len(chans)), np.nan, dtype=np.float64)
    for i, r in enumerate(scorable):
        cd = r["v"].get("channels") or {}
        nv = int(r["v"].get("n_voxels") or 1)
        for j, ci in enumerate(chans):
            c = cd.get(str(ci))
            if c is not None:
                m[i, j] = conf_from_channel(c, nv)
    wrong = np.array([bool(r["wrong"]) for r in scorable], dtype=bool)
    return m, wrong, chans


def _ascend(m: np.ndarray, wrong: np.ndarray, lvl_idx: np.ndarray,
            n_levels: int, n_chans: int, sweeps: int = 8):
    """Coordinate ascent on the GLOBAL AUC over one channel per level, multi start.

    Returns (auc, assignment). Not exhaustive: the space is n_chans ** n_levels. What
    it returns is attained, so it is a lower bound on the true ceiling, never an upper
    one. Shared by the real fit, the permutation null and the held-out split so that
    all three see the identical search and their comparison means something.
    """
    rows = np.arange(m.shape[0])
    best_a, best_map = -1.0, None
    for start in range(n_chans):
        assign = np.full(n_levels, start, dtype=np.int64)
        cur = _auc_fast(m[rows, assign[lvl_idx]], wrong)
        if cur != cur:
            cur = -1.0
        for _ in range(sweeps):
            moved = False
            for li in range(n_levels):
                keep = assign[li]
                for j in range(n_chans):
                    if j == keep:
                        continue
                    assign[li] = j
                    a = _auc_fast(m[rows, assign[lvl_idx]], wrong)
                    if a == a and a > cur + 1e-12:
                        cur, keep, moved = a, j, True
                assign[li] = keep
            if not moved:
                break
        if cur > best_a:
            best_a, best_map = cur, assign.copy()
    return (float(best_a) if best_a >= 0 else float("nan")), best_map


def oracle_arms(scorable: list[dict]) -> dict:
    """Label-informed ceilings for what a channel-selection rule could achieve.

    Adversarial review Comment 2, and retired claim D5c. The previous version of
    `best_per_level` was not a ceiling at all and gave itself away by landing BELOW
    `parity_name`, which is impossible for a genuine bound on name-based rules. Two
    defects, both fixed here:

    1. It chose each level's channel by maximising the WITHIN-level AUC, then reported
       the GLOBAL AUC of that choice. Maximising within-level separation does not
       maximise global AUC, because most pairs in the global AUC cross levels.
    2. It silently dropped levels that were all-correct or all-wrong, so it scored a
       different population than the rules it claimed to bound.

    What is reported now:

    best_fixed_channel  EXACT. Exhaustive over every channel on the full population.
                        No fixed-channel rule can beat it, by construction.
    best_name_mapping   ATTAINED, NOT A BOUND. Coordinate ascent on the global AUC over
                        the full population, restarted from every fixed channel and run
                        to convergence. The search space, one channel per level, is
                        11^24 and is not enumerable, so this is the best name-based
                        mapping we found, not the best that exists. It is a lower bound
                        on the true ceiling and is >= best_fixed_channel by
                        construction. Reported so that a reader can see how much room a
                        label-informed search finds, which is the question that matters.
    """
    out = {}
    m, wrong, chans = _score_matrix(scorable)
    levels = sorted({r["name"] for r in scorable})
    lvl_idx = np.array([levels.index(r["name"]) for r in scorable], dtype=np.int64)
    rows = np.arange(m.shape[0])

    per_ch = [_auc_fast(m[:, j], wrong) for j in range(len(chans))]
    bj = int(np.nanargmax(np.array(per_ch, dtype=np.float64)))
    ok = ~np.isnan(m[:, bj])
    out["best_fixed_channel"] = {
        "auc": float(per_ch[bj]), "channel": chans[bj], "exact_bound": True,
        "n_pos": int((wrong & ok).sum()), "n_neg": int((~wrong & ok).sum()),
        "per_channel": {str(chans[j]): (None if per_ch[j] != per_ch[j] else float(per_ch[j]))
                        for j in range(len(chans))},
    }

    best_a, best_map = _ascend(m, wrong, lvl_idx, len(levels), len(chans))
    ok = ~np.isnan(m[rows, best_map[lvl_idx]])
    out["best_name_mapping"] = {
        "auc": float(best_a), "exact_bound": False,
        "n_levels": len(levels), "n_starts": len(chans),
        "n_pos": int((wrong & ok).sum()), "n_neg": int((~wrong & ok).sum()),
        "mapping": {levels[i]: chans[int(best_map[i])] for i in range(len(levels))},
    }

    # ---- how much of that is signal and how much is the search fitting labels? ----
    # 26 free parameters chosen with the labels on 1845 points. Taking the in-sample
    # value as a ceiling would be exactly the mistake this project keeps catching, so
    # measure the optimism two ways before quoting it.
    #
    # 1. Permutation null. Shuffle the wrong/right labels, destroying all signal, and
    #    run the identical search. Whatever it reaches is pure optimism.
    # 2. Split half by CASE, not by vertebra, because vertebrae within a case are
    #    correlated. Fit the mapping on one half, score it on the other, both ways.
    cases = np.array([r["case"] for r in scorable])
    uniq = sorted(set(cases.tolist()))
    rng = np.random.default_rng(20260730)

    null = []
    for _ in range(int(os.environ.get("E1_NULL_REPS", "20"))):
        perm = wrong.copy()
        rng.shuffle(perm)
        a, _mp = _ascend(m, perm, lvl_idx, len(levels), len(chans))
        if a == a:
            null.append(float(a))
    out["null_search_auc"] = {
        # keep every draw: p is currently derived from the maximum, which is
        # sufficient when no draw reaches the observed value, but a reviewer
        # should be able to recompute the whole distribution rather than trust
        # three summary statistics.
        "draws": [round(v, 6) for v in sorted(null)],
        "reps": len(null), "mean": float(np.mean(null)) if null else None,
        "max": float(np.max(null)) if null else None,
        "p95": float(np.quantile(null, 0.95)) if null else None,
        "note": "same search, labels shuffled. This is what the search reaches on "
                "no signal at all, so it is the optimism floor for best_name_mapping.",
    }

    held, held_fix = [], []
    for rep in range(int(os.environ.get("E1_SPLIT_REPS", "20"))):
        r2 = np.random.default_rng(90000 + rep)
        pick = set(r2.permutation(len(uniq))[: len(uniq) // 2].tolist())
        fit_mask = np.array([uniq.index(c) in pick for c in cases])
        for a_mask, b_mask in ((fit_mask, ~fit_mask), (~fit_mask, fit_mask)):
            if a_mask.sum() == 0 or b_mask.sum() == 0:
                continue
            sub_lvl = lvl_idx[a_mask]
            _fa, mp = _ascend(m[a_mask], wrong[a_mask], sub_lvl, len(levels), len(chans))
            if mp is not None:
                hb = _auc_fast(
                    m[b_mask][np.arange(int(b_mask.sum())), mp[lvl_idx[b_mask]]],
                    wrong[b_mask])
                if hb == hb:
                    held.append(float(hb))
            # The single-channel choice is chosen with the labels too, over 11
            # options rather than 11^26. Held out the same way so the two ceilings
            # are quoted on the same footing and the optimism of each is visible.
            fa = [_auc_fast(m[a_mask][:, j], wrong[a_mask]) for j in range(len(chans))]
            if not np.all(np.isnan(fa)):
                jb = int(np.nanargmax(np.array(fa, dtype=np.float64)))
                hf = _auc_fast(m[b_mask][:, jb], wrong[b_mask])
                if hf == hf:
                    held_fix.append(float(hf))
    out["best_name_mapping_heldout"] = {
        "folds": len(held), "mean": float(np.mean(held)) if held else None,
        "sd": float(np.std(held, ddof=1)) if len(held) > 1 else None,
        "note": "mapping fitted on half the CASES and scored on the other half, both "
                "directions, repeated. This is what a per-level mapping is actually "
                "worth. Split by case because vertebrae within a case are correlated.",
    }
    out["best_fixed_channel_heldout"] = {
        "folds": len(held_fix), "mean": float(np.mean(held_fix)) if held_fix else None,
        "sd": float(np.std(held_fix, ddof=1)) if len(held_fix) > 1 else None,
        "note": "the same split-half treatment for the one-parameter choice, so the "
                "two ceilings are comparable and neither is quoted in sample only.",
    }
    return out


def cluster_bootstrap(scores_by_arm, wrong, case_ids, reps=2000, seed=20260731):
    """95 percent intervals that respect the clustering of vertebrae within cases.

    1845 vertebrae come from 155 cases, roughly twelve per case, and vertebrae in
    one case are correlated: they share a patient, a scanner, a field of view and
    one pass of the same model. Hanley and McNeil, and DeLong, both assume
    independent observations, so on clustered data they are anti-conservative and
    the interval comes out too narrow by roughly the design effect,
    1 + (m - 1) * rho.

    The held-out split in `oracle_arms` already resamples CASES for exactly this
    reason. The intervals did not, which is an inconsistency an adversarial review
    caught. Resampling cases with replacement is the same correction with less
    machinery than Obuchowski's structural components, and it matches the split
    that is already there.

    Returns, per arm, the point estimate and the percentile interval, plus the
    paired delta between the best and the published arm, which is the comparison
    the paper's wording depends on.
    """
    rng = np.random.default_rng(seed)
    scores_by_arm = {k: np.asarray(v, dtype=float)
                     for k, v in scores_by_arm.items()}
    cases = sorted(set(case_ids))
    idx_of = {c: np.where(np.asarray(case_ids) == c)[0] for c in cases}
    w = np.asarray(wrong, dtype=bool)
    names = list(scores_by_arm)
    draws = {k: [] for k in names}
    draws["_delta_phased_minus_published"] = []

    for _ in range(reps):
        pick = [cases[i] for i in rng.integers(0, len(cases), len(cases))]
        sel = np.concatenate([idx_of[c] for c in pick])
        ww = w[sel]
        if ww.sum() == 0 or (~ww).sum() == 0:
            continue
        vals = {}
        for k in names:
            # _auc_fast, not auc(): the pairwise version is O(n_pos * n_neg) in
            # pure Python, which is 549k comparisons per call and 2000 * 9 calls
            # here. tests/test_e1_oracles.py asserts the two agree exactly,
            # including tie handling, so this is a speed change and not a
            # method change.
            vals[k] = _auc_fast(np.asarray(scores_by_arm[k], dtype=float)[sel], ww)
            if vals[k] == vals[k]:
                draws[k].append(vals[k])
        a, b = vals.get("parity_sequence_phased"), vals.get("region_retired")
        if a == a and b == b:
            draws["_delta_phased_minus_published"].append(a - b)

    out = {}
    for k, v in draws.items():
        v = np.asarray([x for x in v if x == x], dtype=float)
        if v.size < 50:
            continue
        out[k] = {"lo": float(np.percentile(v, 2.5)),
                  "hi": float(np.percentile(v, 97.5)),
                  "reps": int(v.size)}
        if k == "_delta_phased_minus_published":
            out[k]["p_le_zero"] = float((v <= 0).mean())
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--data-dir", default=None)
    ap.add_argument("--tolerance", type=float, default=MATCH_TOLERANCE_MM)
    ap.add_argument("--json", dest="out", default=None)
    ap.add_argument("--reuse-ceilings", action="store_true",
                    help="carry the previous run's ceilings and permutation null "
                         "forward instead of recomputing three hours of it")
    args = ap.parse_args(argv)

    run_dir = Path(args.run_dir)
    data_dir = Path(args.data_dir) if args.data_dir else DATASETS / "verse_4skx2"

    case_files = sorted(glob.glob(str(run_dir / "cases" / "*.json")))
    print("case JSONs found: %d" % len(case_files))

    rows = []
    skipped = collections.Counter()
    for cf in case_files:
        try:
            j = json.load(open(cf))
        except Exception:
            skipped["unreadable"] += 1
            continue
        if not str(j.get("status", "")).startswith("ok"):
            skipped[j.get("status", "?")] += 1
            continue
        verts = j.get("vertebrae") or []
        if not verts:
            skipped["no_vertebrae"] += 1
            continue
        stem = j.get("case") or os.path.basename(cf).replace(".json", "")
        masks = glob.glob(str(data_dir / (stem + "*seg-vert_msk.nii.gz")))
        if not masks:
            skipped["no_gt_mask"] += 1
            continue
        gt = gt_centroids_world(Path(masks[0]), run_dir / "_gt_centroid_cache")
        if not gt:
            skipped["empty_gt"] += 1
            continue

        # order the predicted vertebrae along the column so a DETECTED sequence
        # ordinal can be derived. Superior to inferior is the z axis in RAS.
        ordered = sorted(
            [v for v in verts if v.get("centroid_world_ras_mm")],
            key=lambda v: -float(v["centroid_world_ras_mm"][2]))

        for seq_idx, v in enumerate(ordered):
            name = CH.normalise(v.get("name", ""))
            if not name:
                continue
            c = np.asarray(v["centroid_world_ras_mm"], dtype=np.float64)
            # nearest ground truth centroid, VerSe style
            best, bestd = None, 1e18
            for gname, gc in gt.items():
                d = float(np.linalg.norm(gc - c))
                if d < bestd:
                    best, bestd = gname, d
            if best is None or bestd > args.tolerance:
                # unmatched: cannot be scored as right or wrong against GT
                rows.append({"case": stem, "name": name, "matched": False,
                             "dist_mm": bestd, "wrong": None, "seq": seq_idx,
                             "v": v})
                continue
            rows.append({"case": stem, "name": name, "matched": True,
                         "gt": best, "dist_mm": bestd,
                         "wrong": (best != name), "seq": seq_idx, "v": v})

    scorable = [r for r in rows if r["matched"]]
    print("labelled cases used     : %d" % len({r["case"] for r in rows}))
    print("predicted vertebrae     : %d" % len(rows))
    print("matched within %.0f mm   : %d" % (args.tolerance, len(scorable)))
    print("unmatched               : %d" % (len(rows) - len(scorable)))
    if skipped:
        print("\nskipped cases by status:")
        for k, n in skipped.most_common():
            print("  %-24s %d" % (k, n))
    if not scorable:
        print("\nnothing scorable yet, the batch may still be running")
        return 0

    n_wrong = sum(1 for r in scorable if r["wrong"])
    print("\nGROUND TRUTH LABEL ACCURACY on matched vertebrae")
    print("  correct %d, wrong %d, per vertebra accuracy %.1f%%"
          % (len(scorable) - n_wrong, n_wrong,
             100.0 * (len(scorable) - n_wrong) / len(scorable)))
    if n_wrong == 0:
        print("  no errors present, so no confidence arm can be scored for error detection")
        return 0

    # ---------------- build each arm ----------------
    def arm_scores(kind: str):
        pos, neg, undef = [], [], 0
        for r in scorable:
            s = _arm_score_one(kind, r, (r["v"].get("channels") or {}),
                               int(r["v"].get("n_voxels") or 1))
            if s is None:
                undef += 1
                continue
            (pos if r["wrong"] else neg).append(s)
        return pos, neg, undef

    # Estimate the alternation phase once per case, before scoring any arm.
    for case in {r["case"] for r in scorable}:
        crows = [r for r in scorable if r["case"] == case]
        totals = {}
        for off in (0, 1):
            tot = 0.0
            for r in crows:
                chans = r["v"].get("channels") or {}
                try:
                    ci = CH.channel_parity(r["name"], ordinal=r["seq"] + off)
                except Exception:
                    continue
                tot += float(chans.get(str(ci), {}).get("mean", 0.0))
            totals[off] = tot
        best_off = max(totals, key=totals.get)
        for r in crows:
            r["phase"] = best_off

    ARMS = ["region_retired", "parity_name", "parity_region_deployed",
            "parity_sequence", "parity_sequence_inverted",
            "parity_sequence_phased", "mapping_free_top1",
            "mapping_free_margin", "argmax_mean"]

    # Comment 2 from adversarial review: if the estimated phase is effectively
    # constant, the per-case machinery is a global sign flip dressed up.
    phases = {}
    for r in scorable:
        phases.setdefault(r["case"], r.get("phase"))
    from collections import Counter as _C
    pc = _C(phases.values())
    print("\nestimated alternation phase across %d cases: %s" % (len(phases), dict(pc)))
    if len(pc) == 1:
        print("  CONSTANT. The per-case estimate is a single global sign flip.")
        print("  Report it as a sign error, not as a per-case inference problem.")
    else:
        print("  varies, so per-case estimation is doing real work")

    print("\n" + "=" * 78)
    print("E1: AUC for LOW confidence identifying a WRONG level")
    print("0.50 is chance. Below 0.50 means the score points the wrong way.")
    print("=" * 78)
    print("  %-24s %5s  %-14s %5s %s" % ("arm", "AUC", "95% CI", "undef", "verdict"))
    results = {}
    for kind in ARMS:
        pos, neg, undef = arm_scores(kind)
        a = auc(pos, neg)
        verdict = ""
        if a == a:
            if a < 0.55 and a > 0.45:
                verdict = "no signal"
            elif a <= 0.45:
                verdict = "INVERTED"
            elif a >= 0.70:
                verdict = "usable"
            else:
                verdict = "weak"
        lo, hi = auc_ci(a, len(pos), len(neg))
        results[kind] = {"auc": a, "ci95": [lo, hi], "n_wrong": len(pos), "n_right": len(neg),
                         "n_undefined": undef,
                         "mean_wrong": statistics.mean(pos) if pos else None,
                         "mean_right": statistics.mean(neg) if neg else None}
        print("  %-24s %5.3f  [%.3f, %.3f] %5d %s" % (
            kind, a, lo, hi, undef, verdict))

    # Comment 2, part two: arms scored on different populations are not comparable.
    # Re-score every arm on the intersection, so the ranking above cannot be an
    # artefact of one arm dropping the vertebrae it finds hardest.
    defined = {}
    for kind in ARMS:
        d = set()
        for i, r in enumerate(scorable):
            r["_i"] = i
        pos_i, neg_i = [], []
        for r in scorable:
            v, chans_d = r["v"], (r["v"].get("channels") or {})
            nvox = int(v.get("n_voxels") or 1)
            try:
                _ = _arm_score_one(kind, r, chans_d, nvox)
            except Exception:
                continue
            if _ is None:
                continue
            d.add(r["_i"])
        defined[kind] = d
    common = set.intersection(*defined.values()) if defined else set()
    print("\ncommon subset defined for every arm: %d of %d matched vertebrae"
          % (len(common), len(scorable)))
    if len(common) < len(scorable):
        sub = [r for r in scorable if r["_i"] in common]
        print("  re-scored on the common subset, so the arms are directly comparable:")
        for kind in ARMS:
            pos, neg = [], []
            for r in sub:
                s = _arm_score_one(kind, r, (r["v"].get("channels") or {}),
                                   int(r["v"].get("n_voxels") or 1))
                if s is None:
                    continue
                (pos if r["wrong"] else neg).append(s)
            a = auc(pos, neg)
            lo, hi = auc_ci(a, len(pos), len(neg))
            results[kind]["auc_common"] = a
            results[kind]["ci95_common"] = [lo, hi]
            print("    %-24s %5.3f  [%.3f, %.3f]" % (kind, a, lo, hi))
        results["_common_subset_n"] = len(common)
    else:
        results["_common_subset_n"] = len(scorable)

    # --- clustered intervals, the correction for N9 ---
    by_arm = {}
    for kind in ARMS:
        by_arm[kind] = [(_arm_score_one(kind, r, (r["v"].get("channels") or {}),
                                        int(r["v"].get("n_voxels") or 1)))
                        for r in scorable]
        by_arm[kind] = [np.nan if x is None else x for x in by_arm[kind]]
    cb = cluster_bootstrap(by_arm,
                           [r["wrong"] for r in scorable],
                           [r["case"] for r in scorable])
    print("\n" + "=" * 78)
    print("CASE-LEVEL CLUSTER BOOTSTRAP, 2000 reps, resampling the 155 CASES")
    print("Hanley and McNeil assume independent observations. 1845 vertebrae come")
    print("from 155 cases, so the naive interval is too narrow.")
    print("=" * 78)
    print("  %-26s %7s  %-16s %-16s" % ("arm", "AUC", "naive 95%", "clustered 95%"))
    for kind in ARMS:
        if kind not in cb:
            continue
        a = results[kind]["auc"]
        nlo, nhi = results[kind]["ci95"]
        c = cb[kind]
        results[kind]["ci95_clustered"] = [c["lo"], c["hi"]]
        print("  %-26s %7.3f  [%.3f, %.3f]  [%.3f, %.3f]  x%.2f wider"
              % (kind, a, nlo, nhi, c["lo"], c["hi"],
                 (c["hi"] - c["lo"]) / max(1e-9, nhi - nlo)))
    d = cb.get("_delta_phased_minus_published")
    if d:
        print("\n  paired delta, best arm minus published rule:")
        print("    95%% [%.3f, %.3f], P(delta <= 0) = %.3f"
              % (d["lo"], d["hi"], d["p_le_zero"]))
        print("    -> %s"
              % ("CROSSES ZERO: the repair's effect is not separable at this "
                 "sample size" if d["lo"] <= 0 <= d["hi"]
                 else "excludes zero: the improvement survives clustering"))
    results["_cluster_bootstrap"] = cb

    # The ceilings block carries a 1000-repetition permutation null that costs
    # about three hours. Recomputing it to add an arm or an interval would be
    # waste, and worse, a rushed rerun at fewer reps would silently downgrade a
    # published number. --reuse-ceilings carries the previous block forward.
    orc = None
    if args.reuse_ceilings:
        prev = Path(args.out) if args.out else RESULTS / "e1_ablation.json"
        if prev.exists():
            try:
                orc = json.loads(prev.read_text())["arms"]["_oracles"]
                n = (orc.get("null_search_auc") or {}).get("reps")
                print("\nreusing ceilings from %s (permutation null: %s reps)"
                      % (prev.name, n))
            except Exception as exc:
                print("\ncould not reuse ceilings (%s), recomputing" % exc)
                orc = None
    if orc is None:
        orc = oracle_arms(scorable)
    print("\n--- label-informed ceilings ---")
    bf = orc["best_fixed_channel"]
    print("  best_fixed_channel       %5.3f   channel %s for every vertebra"
          % (bf["auc"], bf["channel"]))
    print("      EXACT bound in sample: exhaustive over all %d channels on all %d"
          % (len(bf["per_channel"]), bf["n_pos"] + bf["n_neg"]))
    print("      vertebrae, but the channel is still chosen with the labels.")
    hf = orc.get("best_fixed_channel_heldout", {})
    if hf.get("mean") is not None:
        print("      held out over %d folds: mean %.3f%s" % (
            hf["folds"], hf["mean"],
            (", sd %.3f" % hf["sd"]) if hf.get("sd") is not None else ""))
    bp = orc["best_name_mapping"]
    print("  best_name_mapping        %5.3f   one channel per level, %d levels"
          % (bp["auc"], bp["n_levels"]))
    print("      NOT a bound: coordinate ascent from %d starts over a %d^%d space,"
          % (bp["n_starts"], len(bf["per_channel"]), bp["n_levels"]))
    print("      and IN SAMPLE: %d free parameters chosen with the labels."
          % bp["n_levels"])
    nl, hd = orc["null_search_auc"], orc["best_name_mapping_heldout"]
    if nl.get("mean") is not None:
        print("      permutation null, same search on SHUFFLED labels, %d reps:"
              % nl["reps"])
        print("        mean %.3f, p95 %.3f, max %.3f   <- pure optimism, no signal"
              % (nl["mean"], nl["p95"], nl["max"]))
    if hd.get("mean") is not None:
        print("      held out, fitted on half the CASES and scored on the other half,")
        print("      %d folds: mean %.3f%s" % (
            hd["folds"], hd["mean"],
            (", sd %.3f" % hd["sd"]) if hd.get("sd") is not None else ""))
        print("      THIS is what a per-level mapping is worth. Compare it to the")
        print("      arms above, not the in-sample %.3f." % bp["auc"])
    results["_oracles"] = orc

    print("\nper level error counts, the denominator for any per level claim")
    bylv = collections.Counter(r["name"] for r in scorable if r["wrong"])
    tot = collections.Counter(r["name"] for r in scorable)
    for lv in sorted(tot, key=lambda s: (s[0], int(re.sub(r"\D", "", s) or 0))):
        print("  %-7s wrong %2d / %2d" % (lv, bylv.get(lv, 0), tot[lv]))

    out = Path(args.out) if args.out else RESULTS / "e1_ablation.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "run_dir": str(run_dir), "tolerance_mm": args.tolerance,
        "n_cases": len({r["case"] for r in rows}),
        "n_predicted": len(rows), "n_matched": len(scorable), "n_wrong": n_wrong,
        "skipped": dict(skipped), "arms": results,
    }, indent=2))
    print("\nwrote %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
