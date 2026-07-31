"""Driver for the overnight two step VerSe run. Thin on purpose.

Everything of substance is in spinelab.pipeline.batch. This file only resolves
which cases to run and where to put the output.

Examples, PowerShell:

  # two case rehearsal
  & $PY scripts\\run_batch.py --limit 2 --run-dir <path>\\runs\\batch_smoke

  # the real thing, resumable: re-running skips anything already ok
  & $PY scripts\\run_batch.py --run-dir <path>\\runs\\verse_batch_01

Resume is by per case JSON: a case whose cases/<stem>.json has a status starting
with "ok" is skipped unless --overwrite. A crash mid case leaves no JSON, so the
case is retried. Never persists the probability array.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from spinelab import paths                                        # noqa: E402
from spinelab.pipeline import batch                               # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", default=str(paths.DATASETS / "verse_4skx2"),
                    help="directory of *_ct.nii.gz cases")
    ap.add_argument("--pattern", default="*_ct.nii.gz")
    ap.add_argument("--case", action="append", default=None,
                    help="explicit case file or stem, repeatable, overrides --pattern")
    ap.add_argument("--run-dir", default=str(paths.RUNS / "verse_batch"),
                    help="where manifest.json, cases/, seg/ and run_log.jsonl go")
    ap.add_argument("--limit", type=int, default=None,
                    help="run at most this many cases, in sorted order")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--step-size", type=float, default=0.5)
    ap.add_argument("--step1-only", action="store_true",
                    help="skip step 2, for diagnosing step 1 in isolation")
    ap.add_argument("--overwrite", action="store_true",
                    help="ignore existing per case JSON and redo everything")
    ap.add_argument("--keep-work", action="store_true",
                    help="keep the small intermediate niftis for inspection")
    ap.add_argument("--threshold", type=float, default=batch.PROB_THRESHOLD,
                    help="probability threshold for the count-above statistic")
    args = ap.parse_args(argv)

    data_dir = Path(args.data_dir)
    if args.case:
        cases = []
        for c in args.case:
            p = Path(c)
            if p.exists():
                cases.append(p)
                continue
            hits = sorted(data_dir.glob("%s*_ct.nii.gz" % c))
            if not hits:
                print("no case matched %r under %s" % (c, data_dir))
                return 1
            cases.extend(hits)
    else:
        if not data_dir.is_dir():
            print("data dir not found: %s" % data_dir)
            return 1
        cases = batch.find_cases(data_dir, args.pattern)

    if args.limit is not None:
        cases = cases[:args.limit]
    if not cases:
        print("no cases to run")
        return 1

    for step, folder in (("step1", paths.STEP1), ("step2", paths.STEP2)):
        if step == "step2" and args.step1_only:
            continue
        ckpt = Path(folder) / "fold_0" / "checkpoint_final.pth"
        if not ckpt.exists():
            print("%s checkpoint missing: %s" % (step, ckpt))
            return 2

    print("data dir : %s" % data_dir)
    print("run dir  : %s" % args.run_dir)
    print("cases    : %d" % len(cases))

    res = batch.run_batch(
        cases, Path(args.run_dir), device=args.device,
        step1_only=args.step1_only, step_size=args.step_size,
        overwrite=args.overwrite, keep_work=args.keep_work,
        threshold=args.threshold,
        manifest_extra={"data_dir": str(data_dir), "pattern": args.pattern,
                        "limit": args.limit},
        argv=sys.argv)
    return 0 if res["failed"] == 0 else 3


if __name__ == "__main__":
    sys.exit(main())
