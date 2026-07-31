# spine-gsps

Evaluation harness for *"Separating conformance from trustworthiness: an end-to-end audit, and five checks, for an AI result delivered into a clinical archive."*

Every number in the article has a row in [`docs/CLAIMS.md`](docs/CLAIMS.md)
giving its status, the command that produces it, and its source file. That
ledger also records **twenty-one claims that were retired**, several of them
asserted confidently before measurement contradicted them. It is the honest
guide to how this analysis fails.

## What this is

Three measurements on one deployed DICOM service:

1. **Conformance and delivery.** All 38 presentation states the service emitted
   fail two independent validators and are refused by the reference renderer,
   while the archive indexes every one, DICOMweb returns them intact, and the
   target viewer displayed them. Nothing in the delivery path detected it.
2. **A nine-arm ablation of the quality flag.** Only the rule choosing which
   per-region sigmoid channel to read varies. All nine land between 0.427 and
   0.581 AUC. The rule that actually shipped is the **worst of the nine**, and
   its case-clustered interval contains 0.5.
3. **The geometric consistency check.** Specified as leave-one-out, implemented
   in sample on its normal path, so the spline absorbs the displacement it
   exists to detect.

## Running it

```
python -m spinelab.paths                        # check every store resolves
python -m pytest tests -q                       # 267 tests, the factual constraints
python -m spinelab.confidence.channels          # channel table vs the checkpoints
python -m spinelab.gsps.validate <dir>          # dciodvfy over a DICOM directory
python -m spinelab.eval.verse --self-check      # the scorer against known answers
python -m spinelab.outliers.spline --validate   # the synthetic evaluation
python scripts/e1_ablation.py --run-dir <run>   # ablation, ceilings, null
python scripts/make_figures.py                  # every figure, from results/*.json
```

Pins are frozen in `env/requirements.lock`. `nnunetv2==2.4.2` must be installed
explicitly: current `totalspineseg` no longer depends on it, and without it the
checkpoints will not deserialise.

**No metric in the article is computed by code written for the purpose of
computing that metric.** Conformance is scored by `dciodvfy` (dicom3tools).
Vertebral identification is scored by the VerSe organisers' own
`eval_utilities.py`, vendored rather than reimplemented.

## What is not here, and why

- **The clinical material.** The 38 delivered objects and the retrospective
  cohort they came from derive from patient examinations. The written permission
  obtained covers research use, publication of these findings and release of this
  code, not redistribution of patient data. The raw per-attribute validator dumps
  over those objects are withheld for the same reason; the `.md` write-ups in
  `results/` carry the same counts.
- **The model checkpoints.** They are the openly released upstream TotalSpineSeg
  weights, obtainable from release r20241005 at
  github.com/neuropoly/totalspineseg. They were not trained here.
- **The public datasets.** VerSe 2019 and 2020, 202 cases, by anonymous download
  from OSF (osf.io/nqjyw, osf.io/t98fz) under CC BY-SA 4.0.

## Licence

MIT, see `LICENSE`. The vendored VerSe evaluation code carries its own.
