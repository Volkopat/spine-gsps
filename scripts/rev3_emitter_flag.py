"""Round 2 of review: the flag's performance from the service's own emitter, and why it differs
from the reimplementation.

The editor's first item: sensitivity, specificity and predictive values were computed with the
instrumented reimplementation of the flag (147 of 155 studies, 108 of 1845 matched vertebrae),
while the service's emitter, run unmodified on the same public cases, logged 139 of 155 studies
and 178 of 2215 vertebrae. This script scores the emitter's own flags against ground truth, and
lays out where the two counts differ.

Inputs, all written by `scripts/rev2_deployed_on_public.py` and the emitter it runs:
  <work>/emitter/gsps_generation.log   the emitter's log: "Processing patient: pat_<case>", then
      "Extracted confidence for N vertebrae", "Excluded small box: vertebrae_<level>", and one
      "Penalty for <level>: z-score=..." line for every vertebra whose z exceeded 1.5
  <work>/output/pat_<case>/<series>/json/2d_spine_per-instance-sop.json
      the per-slice records the emitter read; the union of their vertebra names is the set it
      scored, and its size must equal the log's N
  <work>/gsps/pat_<case>/<series>/*_GSPS.dcm
      the presentation states the emitter wrote; each label's text is "<level> (<confidence>%)".
      The emitter drops names outside C1 to S5 and boxes far smaller than the case's average
      before writing, so the written set is a subset of the scored one
  results/rev1_rows.json   the per-vertebra ground truth (matched, wrong) and the
      reimplementation's flag, keyed by case and level name

The emitter's flags are joined to the ground truth by case and level name. Two denominators are
reported: every vertebra the emitter scored, which is the log's and the one the editor quoted,
and every vertebra it wrote into a presentation state, since a vertebra it drops reaches no one.
Intervals are the same 2000-repetition case-level bootstrap as the rest of the article
(scripts/rev1_stats.py).

Usage (spinelab env):
    python scripts/rev3_emitter_flag.py --work <runs/rev2_deployed_public>
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from pathlib import Path

import numpy as np
import pydicom

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
sys.path.insert(0, str(HERE))
import rev1_stats as S  # noqa: E402
from spinelab.paths import RESULTS  # noqa: E402

# the emitter's own is_valid_vertebra_label
VALID = {"C%d" % i for i in range(1, 8)} | {"T%d" % i for i in range(1, 13)} | \
        {"L%d" % i for i in range(1, 6)} | {"S%d" % i for i in range(1, 6)}


def parse_log(path: Path) -> dict:
    cases, cur = {}, None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.search(r"Processing patient: pat_(\S+)", line)
        if m:
            cur = m.group(1)
            cases.setdefault(cur, {"extracted": None, "penalties": {}, "small": set()})
            continue
        if cur is None:
            continue
        m = re.search(r"Extracted confidence for (\d+) vertebrae", line)
        if m:
            cases[cur]["extracted"] = int(m.group(1))
        m = re.search(r"Excluded small box: vertebrae_(\S+)", line)
        if m:
            cases[cur]["small"].add(m.group(1))
        m = re.search(r"Penalty for (\S+): z-score=([\d.]+)", line)
        if m:
            cases[cur]["penalties"][m.group(1)] = float(m.group(2))
    return cases


def scored_names(work: Path, case: str) -> set[str]:
    names = set()
    for f in glob.glob(str(work / "output" / ("pat_" + case) / "*" / "json" / "2d_spine_per-instance-sop.json")):
        for per_slice in json.load(open(f))["data"].values():
            for k in per_slice:
                names.add(k.split("_", 1)[1] if k.startswith("vertebrae_") else k)
    return names


def written_names(work: Path, case: str) -> set[str]:
    names = set()
    for f in glob.glob(str(work / "gsps" / ("pat_" + case) / "*" / "*_GSPS.dcm")):
        for g in pydicom.dcmread(f).GraphicAnnotationSequence:
            for txt in getattr(g, "TextObjectSequence", []):
                names.add(str(txt.UnformattedTextValue).split()[0])
    return names


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work", required=True)
    ap.add_argument("--rows", default=str(RESULTS / "rev1_rows.json"))
    ap.add_argument("--out", default=str(RESULTS / "rev3_emitter_flag.json"))
    a = ap.parse_args(argv)
    work = Path(a.work)
    log = parse_log(work / "emitter" / "gsps_generation.log")
    rows = {(r["case"], r["name"]): r for r in json.load(open(a.rows))["rows"]}

    recs, problems = [], []
    for case, info in sorted(log.items()):
        names, written = scored_names(work, case), written_names(work, case)
        if info["extracted"] is not None and len(names) != info["extracted"]:
            problems.append((case, "scored %d, log says %d" % (len(names), info["extracted"])))
        if not written <= names:
            problems.append((case, "written but not scored: %s" % sorted(written - names)))
        for n in sorted(names):
            r = rows.get((case, n))
            dropped = None if n in written else ("invalid name" if n not in VALID else
                                                 "small box" if n in info["small"] else "other")
            recs.append({"case": case, "name": n, "written": n in written, "dropped_because": dropped,
                         "emitter_flag": n in info["penalties"], "emitter_z": info["penalties"].get(n),
                         "in_rows": r is not None, "matched": bool(r and r["matched"]),
                         "wrong": bool(r and r["matched"] and r["wrong"]),
                         "reimpl_flag": bool(r and r["deployed_flag"])})
    if problems:
        print("REFUSING: the emitter's inputs, log and objects disagree, e.g. %s" % problems[:3])
        return 1

    cases = np.array([x["case"] for x in recs])
    ef = np.array([x["emitter_flag"] for x in recs])
    rf = np.array([x["reimpl_flag"] for x in recs])
    matched = np.array([x["matched"] for x in recs])
    wrong = np.array([x["wrong"] for x in recs])
    inrows = np.array([x["in_rows"] for x in recs])
    wr = np.array([x["written"] for x in recs])
    worst = np.where(matched, wrong, True)       # every unmatched prediction counted wrong

    def block(flag, inc, w):
        return {"firing_rate": S.rate_with_ci(flag, inc, cases), "sensitivity": S.rate_with_ci(flag, inc & w, cases),
                "specificity": S.rate_with_ci(~flag, inc & ~w, cases), "ppv": S.rate_with_ci(w, inc & flag, cases),
                "npv": S.rate_with_ci(~w, inc & ~flag, cases), "prevalence": float(w[inc].mean())}

    dropped = [x["dropped_because"] for x in recs if not x["written"]]
    out = {
        "emitter_log": {"studies": len(log), "studies_with_a_penalty": sum(1 for v in log.values() if v["penalties"]),
                        "vertebrae_scored": len(recs), "penalties": int(ef.sum())},
        "denominators": {
            "predictions_in_ground_truth_table": len(rows),
            "predictions_the_emitter_never_saw": len(rows) - int(inrows.sum()),
            "scored": len(recs), "scored_matched": int(matched.sum()), "scored_unmatched": int((~matched).sum()),
            "flags_on_matched": int((ef & matched).sum()), "flags_on_unmatched": int((ef & ~matched).sum()),
            "written": int(wr.sum()), "written_matched": int((wr & matched).sum()),
            "written_matched_wrong": int((wr & matched & wrong).sum()),
            "dropped": int((~wr).sum()), "dropped_invalid_name": dropped.count("invalid name"),
            "dropped_small_box": dropped.count("small box"), "dropped_other": dropped.count("other"),
            "flags_on_dropped": int((ef & ~wr).sum())},
        "emitter_scored": {"matched": block(ef, matched, wrong), "unmatched_counted_wrong": block(ef, inrows, worst)},
        "emitter_written": {"matched": block(ef, wr & matched, wrong), "unmatched_counted_wrong": block(ef, wr, worst),
                            "studies_flagged": len({c for c, f, w in zip(cases, ef, wr) if f and w})},
        # the reimplementation on exactly the vertebrae the emitter scored, so the two compare like for like
        "reimplementation_scored": {"matched": block(rf, matched, wrong)},
        "agreement_on_scored": {
            "both": int((ef & rf).sum()), "emitter_only": int((ef & ~rf).sum()),
            "reimplementation_only": int((~ef & rf).sum()), "neither": int((~ef & ~rf).sum()),
            "studies_flagged_emitter": len({c for c, f in zip(cases, ef) if f}),
            "studies_flagged_reimplementation": len({c for c, f in zip(cases, rf) if f})},
    }
    Path(a.out).write_text(json.dumps({"summary": out, "vertebrae": recs}, indent=1))

    print(json.dumps(out["emitter_log"]), json.dumps(out["denominators"]), sep="\n")
    for key in ("emitter_scored", "emitter_written", "reimplementation_scored"):
        for k, b in out[key].items():
            if not isinstance(b, dict):
                continue
            print("%s, %s, prevalence %.3f" % (key, k, b["prevalence"]))
            for m in ("firing_rate", "sensitivity", "specificity", "ppv", "npv"):
                v = b[m]
                print("  %-12s %.3f [%.3f, %.3f]  (%d of %d)" % (m, v["value"], v["lo"], v["hi"], v["num"], v["den"]))
    print("written studies flagged", out["emitter_written"]["studies_flagged"])
    print(json.dumps(out["agreement_on_scored"]))
    print("wrote", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
