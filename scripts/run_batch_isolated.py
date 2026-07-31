"""Run the VerSe batch with ONE CASE PER PROCESS.

Why this exists. Running all cases in a single long lived process leaked memory:
resident set reached 40.5 GB by case 38 and large cases then died with

    MemoryError: Unable to allocate 8.45 GiB for an array with
    shape (9, 669, 434, 434) and data type float64

Nine cases failed that way in one run. The float64 allocation is inside nnU-Net's
resampling of step 1 logits back to the original image shape, not in our code, so
it cannot be fixed with a cast on our side. Note step 1 does not even request
probabilities; nnU-Net materialises them internally regardless.

Rather than patch nnU-Net, isolate each case in its own process so the operating
system reclaims everything on exit. The only cost is reloading both predictors per
case, measured at 3.4 s, against 60 to 250 s of actual work. That is a rounding
error, and it makes peak memory a per case property instead of a cumulative one.

Resume is inherited from run_batch.py, which skips any case whose JSON status
starts with "ok".

Usage:
  python scripts/run_batch_isolated.py --run-dir <path>\\runs\\verse_batch_01
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
from spinelab.paths import DATASETS  # noqa: E402

DRIVER = HERE / "run_batch.py"


def case_stems(data_dir: Path, pattern: str) -> list[str]:
    return sorted(os.path.basename(p).replace("_ct.nii.gz", "")
                  for p in glob.glob(str(data_dir / pattern)))


def is_done(run_dir: Path, stem: str) -> bool:
    p = run_dir / "cases" / (stem + ".json")
    if not p.exists():
        return False
    try:
        return str(json.loads(p.read_text()).get("status", "")).startswith("ok")
    except Exception:
        return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", default=None)
    ap.add_argument("--pattern", default="*_ct.nii.gz")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--timeout", type=int, default=1800,
                    help="per case seconds before the child is killed")
    ap.add_argument("--python", default=sys.executable)
    args = ap.parse_args(argv)

    data_dir = Path(args.data_dir) if args.data_dir else DATASETS / "verse_4skx2"
    run_dir = Path(args.run_dir)
    (run_dir / "cases").mkdir(parents=True, exist_ok=True)

    stems = case_stems(data_dir, args.pattern)
    if args.limit:
        stems = stems[:args.limit]
    todo = [s for s in stems if not is_done(run_dir, s)]

    print("data dir : %s" % data_dir, flush=True)
    print("run dir  : %s" % run_dir, flush=True)
    print("cases    : %d total, %d already ok, %d to run"
          % (len(stems), len(stems) - len(todo), len(todo)), flush=True)

    env = dict(os.environ)
    env["PYTHONPATH"] = str(HERE.parent / "src")

    outcomes: dict[str, int] = {}
    t_run = time.time()
    for i, stem in enumerate(todo, 1):
        t0 = time.time()
        # -u so a redirected log is readable while the run is in progress.
        # Without it Python buffers stdout to a file and the log stays empty
        # until exit, which made a 20 minute monitor see nothing and time out.
        cmd = [args.python, "-u", str(DRIVER), "--case", stem, "--run-dir", str(run_dir)]
        try:
            proc = subprocess.run(cmd, env=env, capture_output=True, text=True,
                                  timeout=args.timeout, cwd=str(HERE.parent))
            rc = proc.returncode
        except subprocess.TimeoutExpired:
            rc = -9
            proc = None

        dt = time.time() - t0
        status = "timeout" if rc == -9 else "?"
        if proc is not None:
            # the child prints "    <status>  <secs> s  peak ..." per case
            for ln in (proc.stdout or "").splitlines():
                s = ln.strip()
                for cand in ("ok_step1_only", "ok", "step1_no_landmark",
                             "step2_no_landmark"):
                    if s.startswith(cand):
                        status = cand
                        break
                if "EXCEPTION" in s:
                    status = "exception:" + s.split("EXCEPTION")[-1].strip()[:60]
            if status == "?" and rc != 0:
                tail = (proc.stderr or "").strip().splitlines()
                status = "rc=%d %s" % (rc, tail[-1][:70] if tail else "")
        outcomes[status.split(":")[0]] = outcomes.get(status.split(":")[0], 0) + 1

        el = time.time() - t_run
        rate = el / i
        print("[%d/%d] %-26s %-46s %5.1f s   eta %.1f h"
              % (i, len(todo), stem, status[:46], dt,
                 (len(todo) - i) * rate / 3600.0), flush=True)

    print("\n=== outcomes ===", flush=True)
    for k, v in sorted(outcomes.items(), key=lambda x: -x[1]):
        print("  %-40s %d" % (k, v), flush=True)
    print("total elapsed %.2f h" % ((time.time() - t_run) / 3600.0), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
