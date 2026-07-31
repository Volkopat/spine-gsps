"""The ablation's ceiling machinery, tested against the definition it replaces.

Retired claim D5c: the previous `best_per_level` was reported as a bound and was not
one, which showed up as a ceiling landing BELOW an arm it claimed to bound. The
replacement adds a vectorised AUC and a coordinate ascent, both of which are exactly
the kind of purpose-built code this project distrusts. So:

  1. `_auc_fast` is asserted equal to the slow pairwise `auc` on random inputs
     including heavy ties, which is where a rank based implementation goes wrong.
  2. `best_fixed_channel` is asserted to be a real bound: no channel beats it.
  3. `best_name_mapping` is asserted to be at least `best_fixed_channel`, which is
     the property that makes the old inversion impossible by construction.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
e1 = pytest.importorskip("e1_ablation")


def _slow(pos, neg):
    return e1.auc(list(pos), list(neg))


@pytest.mark.parametrize("seed", range(12))
def test_auc_fast_matches_slow_pairwise(seed):
    rng = random.Random(seed)
    n = rng.randint(4, 60)
    # Coarse quantisation on purpose: forces ties, which is the failure mode of a
    # rank based AUC that does not average ranks within a tie group.
    q = rng.choice([2, 3, 5, 1000])
    s = [float(rng.randint(0, q)) / q for _ in range(n)]
    w = [rng.random() < 0.35 for _ in range(n)]
    if not any(w) or all(w):
        pytest.skip("degenerate draw, AUC undefined")
    fast = e1._auc_fast(np.array(s), np.array(w, dtype=bool))
    slow = _slow([x for x, f in zip(s, w) if f], [x for x, f in zip(s, w) if not f])
    assert fast == pytest.approx(slow, abs=1e-12)


def test_auc_fast_drops_nan_like_the_slow_path():
    s = np.array([0.1, np.nan, 0.9, 0.4, np.nan])
    w = np.array([True, True, False, False, False])
    assert e1._auc_fast(s, w) == pytest.approx(_slow([0.1], [0.9, 0.4]), abs=1e-12)


def test_auc_fast_undefined_when_one_class_empty():
    s = np.array([0.1, 0.2, 0.3])
    assert np.isnan(e1._auc_fast(s, np.array([False, False, False])))
    assert np.isnan(e1._auc_fast(s, np.array([True, True, True])))


def _synth(seed=0, n_cases=40):
    """Rows in the shape `oracle_arms` consumes. Channel 3 carries the real signal."""
    rng = random.Random(seed)
    levels = ["C%d" % i for i in range(1, 8)] + ["T%d" % i for i in range(1, 13)]
    rows = []
    for c in range(n_cases):
        for lv in levels:
            wrong = rng.random() < 0.2
            ch = {}
            for ci in range(6):
                base = rng.random()
                if ci == 3:
                    base = rng.uniform(0.0, 0.5) if wrong else rng.uniform(0.5, 1.0)
                ch[str(ci)] = {"mean": base, "p95": base, "n_gt_0p7": 0}
            rows.append({"case": "c%03d" % c, "name": lv, "wrong": wrong,
                         "seq": levels.index(lv), "phase": 0,
                         "v": {"channels": ch, "n_voxels": 100}})
    return rows


def test_best_fixed_channel_is_a_real_bound():
    rows = _synth()
    orc = e1.oracle_arms(rows)
    bf = orc["best_fixed_channel"]
    assert bf["exact_bound"] is True
    best = max(v for v in bf["per_channel"].values() if v is not None)
    assert bf["auc"] == pytest.approx(best, abs=1e-12)
    assert bf["channel"] == 3, "the planted signal channel should win"


def test_best_name_mapping_never_falls_below_the_fixed_channel():
    """The property whose absence exposed the old implementation as not a bound."""
    orc = e1.oracle_arms(_synth(seed=1))
    assert orc["best_name_mapping"]["auc"] >= orc["best_fixed_channel"]["auc"] - 1e-12
    assert orc["best_name_mapping"]["exact_bound"] is False, (
        "coordinate ascent over an 11^24 space is not exhaustive and must not be "
        "labelled a bound")


def test_best_name_mapping_scores_the_full_population():
    """The other half of D5c: a ceiling must not drop the rows it finds awkward."""
    rows = _synth(seed=2)
    orc = e1.oracle_arms(rows)
    bp = orc["best_name_mapping"]
    assert bp["n_pos"] + bp["n_neg"] == len(rows)
    bf = orc["best_fixed_channel"]
    assert bf["n_pos"] + bf["n_neg"] == len(rows)


def test_arm_score_one_is_the_single_scoring_path():
    """Every caller must go through one function, so arms cannot drift apart."""
    src = (Path(e1.__file__)).read_text(encoding="utf-8")
    assert src.count("def _arm_score_one") == 1
    assert "CH.channel_region_retired" not in src.split("def main")[-1], (
        "main() must not re-implement an arm; call _arm_score_one")
