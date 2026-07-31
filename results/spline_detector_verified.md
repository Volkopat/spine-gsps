# Spline outlier detector: independent verification

Run by the orchestrator on 2026-07-30, after the agent that built
`spinelab/outliers/spline.py` had its verification agent killed by an API 529.
Commands:

```
python -m spinelab.outliers.spline --selftest
python -m spinelab.outliers.spline --validate --json results/spline_validation.json
```

`--selftest` passes: `fit_instrumented` reproduces the deployed trace on 24 regional
residuals, so the baseline arm is faithful to `generate_gsps_4.py`.

All numbers below are **synthetic**, 432 studies per condition with known ground
truth, no clinical data involved. Synthetic data establishes what the algorithm can
and cannot do in principle. It does not establish a clinical rate.

## The deployed algorithm, as actually implemented

Reverse engineered from `generate_gsps_4.py:304-413`:

| aspect | actual behaviour |
|---|---|
| fitted | two `UnivariateSpline`, x(t) and y(t), k=3 |
| t | normalised cumulative chord length in **name order** |
| points | bbox corner midpoint, in **image pixels** |
| smoothing | `s = n * 0.5`, capping per axis RMS residual at 0.707 px |
| regions | Cervical C1-C7, Thoracic T1-T12, Lumbar L1-L6. **sacrum and T13 belong to no region and are dropped** |
| residual, region >= 4 | **IN SAMPLE** distance to its own region spline |
| residual, region 1-3 | leave one out distance to a **global** spline |
| standardisation | one pooled mean and ddof=0 std over the whole study, **std floored at 0.1 px** |
| flag | one tailed `z > 1.5` |

**Correction to the RSNA abstract.** It describes "leave-one-out residuals". For the
normal path, regions of four or more levels, the residual is **in sample**, not
leave one out. True leave one out applies only to regions of one to three levels,
and then against a global rather than a regional spline. The abstract describes an
algorithm the code does not implement.

**Where z = 651.46 comes from.** For ddof=0 pooling the algebraic bound is
`max z = sqrt(n-1)`, so 4.12 at n=18 and 4.80 at n=24. No value near 651 is
reachable from the pooling itself. It comes from the 0.1 px std floor: a genuine
large residual divided by a floored std of 0.1 px yields an unbounded z, which then
drives the penalty straight to its 0.3x floor. The floor is three to ten times too
small.

## It has no discriminative power for the errors it exists to catch

Paired design: each rate is measured on the same 432 studies before and after
injecting a known error. The bracketed value is the control. **Equal values mean
zero discrimination.**

| injection | error site flagged | control | any bad level flagged | control |
|---|---|---|---|---|
| single level shift | **5.1%** | (22.7%) | 21.8% | (39.4%) |
| adjacent swap | 11.3% | (22.7%) | 34.0% | (29.6%) |
| whole column off by one | 0.0% | (0.0%) | **97.0%** | (97.0%) |
| lateral 10 mm, control | 23.1% | (22.7%) | 23.1% | (22.7%) |

Read the first row carefully. Injecting a single level shift makes the detector
**less** likely to flag that site, 5.1 percent against a 22.7 percent baseline. It
is worse than chance. The whole column error scores 97.0 percent against a 97.0
percent control, which is not detection, it is the detector flagging almost every
study regardless.

## The mechanism: an in sample fit absorbs the outlier it is meant to find

| true off curve displacement | in sample residual | leave one out residual | deployed flag rate |
|---|---|---|---|
| 0.0 mm | 0.212 mm | 0.553 mm | 21.5% |
| 1.0 mm | 0.265 mm | 1.171 mm | 27.8% |
| 5.0 mm | 0.290 mm | 4.923 mm | 23.6% |
| 20.0 mm | 0.235 mm | 19.843 mm | 3.5% |
| 40.0 mm | 0.153 mm | 39.532 mm | 2.1% |
| 80.0 mm | 0.118 mm | 78.553 mm | 7.6% |

The in sample residual is **flat at roughly 0.2 mm** across a 0 to 80 mm true
displacement, and if anything decreases. The spline is fitted through the displaced
point, so it accommodates the outlier completely. The leave one out residual tracks
the true displacement almost exactly, 0.553 to 78.553 mm.

This is the whole finding in one table. A residual measured in sample cannot detect
an outlier that the fit itself absorbs, no matter what threshold is applied to it.

## False positives on error free chains, and why the obvious guard fails

| configuration | FP per vertebra | FP per study | endpoints | interior |
|---|---|---|---|---|
| deployed, in sample, std floor 0.1 px | 7.4% | **91.7%** | 2.5% | 9.7% |
| guarded, std floor 1.0 px, min residual 3.0 mm | **0.0%** | 0.0% | 0.0% | 0.0% |
| true leave one out, std floor 1.0 px | 15.1% | 100.0% | **50.0%** | 0.0% |

The deployed 7.4 percent per vertebra and 91.7 percent per study closely reproduce
what was measured on the real shipped output, 11.1 percent of vertebrae and 97.4
percent of studies. Independent synthetic confirmation of a production observation.

The guarded configuration removes every false positive, but the injected error table
shows it also detects **nothing**, 0.0 percent on every injection. The 3.0 mm minimum
residual blocks everything because in sample residuals never exceed about 0.3 mm. So
a magnitude guard cannot rescue an in sample detector, it only silences it. That is
worth stating explicitly, because a magnitude guard is the obvious first fix and it
does not work.

## Two of my own hypotheses were wrong

1. **I predicted endpoint over flagging from leave one out leverage.** For the
   deployed configuration the opposite holds: endpoints 2.5 percent, interior 9.7
   percent, with the worst band at depth 1 from a region end at 21.6 percent. The
   leverage effect is real and enormous, **50.0 percent at endpoints**, but only
   under **true** leave one out, which the deployed code does not use for normal
   regions. My reasoning was sound and applied to the wrong code path, because I
   believed the abstract's description instead of reading the implementation.

2. **I framed the problem as "fires on sub millimetre noise".** True but shallow.
   The deeper problem is that it **cannot fire on real displacement at all**. That is
   a different and much stronger claim.

## The constructive result

True leave one out detects what the deployed rule cannot: 75.0 percent of single
level shifts, and on the masking table 75.0 percent at 40 mm and 100.0 percent at
80 mm displacement, against 2.1 percent and 7.6 percent for the deployed rule. It
costs 50 percent false positives at region endpoints, which is a leverage artifact
with known remedies, for example excluding endpoints, standardising per depth, or
fitting across region boundaries rather than within them.

So the paper's honest and useful claim is not "we built an outlier detector". It is
that **the choice between an in sample and a leave one out residual determines
whether a geometric consistency check works at all**, the deployed system picked the
one that cannot work, and the fix is a change of estimator rather than a change of
threshold. That is falsifiable, it is demonstrated on synthetic data with known
ground truth, and it needs no clinical data and no GPU.

The z threshold sweep supports it: across z from 1.00 to 4.00 the deployed rule's
single level shift detection never separates from the lateral control, 21.8 percent
against 23.1 percent at z = 1.5, and by z = 3.0 both reach zero together. No
threshold exists at which the deployed rule works.
