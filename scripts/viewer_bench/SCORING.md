# Scoring rules for the GSPS versus SEG viewer matrix

Version 1, written 2026-07-30. The point of this file is inter-rater agreement:
two people scoring the same viewer and the same object must land on the same
number without talking to each other. If a case is not covered here, do not guess.
Record it verbatim under `notes` and raise it, then amend this file and rescore.

Read it end to end before scoring anything. The order of the checks matters,
because several of the levels are distinguished only by which check fails first.

## What is being scored

One cell of the matrix is one (viewer, object) pair. The object is a single DICOM
instance from a known variant set, pushed into the bench archive alongside the
image series it references. Nothing about the annotation content differs between
variants: `results/gsps_variants.md` records that all nine GSPS variants carry
17 text objects and 17 graphic objects with byte identical text strings and
identical `GraphicData`. Only conformance attributes, colour route and producer
identity vary. So any difference in outcome is attributable to those three axes.

## The four level outcome scale

Score exactly one level per cell. Levels are ordered worst to best, and each has
a single decisive test. Apply the tests in the order given and stop at the first
one that fires.

### Level 0, CRASH

The viewer process terminates, hangs with no further input accepted, or the tab
becomes unresponsive and must be killed, at any point between selecting the study
and thirty seconds after the viewport finishes its first paint.

Decisive test: the application is no longer usable without restarting it.

- A JavaScript exception in the console with the UI still usable is **not** a
  crash. That is level 1 and the exception text goes in `notes`.
- A viewer that shows an error dialog and then continues working is **not** a
  crash. That is level 1.
- Record how the crash was observed: process exit code, browser tab kill,
  "Aw, Snap", stack trace. Attach the log excerpt.

### Level 1, REFUSED

The viewer will not open the object at all, and says so, or the archive would not
take it in the first place.

Decisive test: the annotation object never reaches a viewport, and the failure is
explicit somewhere machine readable, a non 2xx HTTP status, a non zero exit code,
a named error dialog, or a logged parse failure.

Two distinct sub cases, record which:

- `1a` archive refused ingest. Measured by `load_objects.py`: the verdict is
  `REJECTED` or `ERROR` and the message is Orthanc's own text. This is scored once
  per archive, not once per viewer, and it makes every viewer cell behind that
  archive unscoreable rather than level 1.
- `1b` viewer refused to render an object the archive holds. The series is listed
  in the study but selecting it produces an error, or the object is absent from
  the series list while `check_dicomweb.py` shows it present over DICOMweb.

A command line renderer that exits non zero with a diagnostic is level 1, and the
diagnostic is the evidence. For example, `dcmp2pgm` from DCMTK 3.7.0 exits with
`F: Can't open input file(s).` for the as-is GSPS design, preceded by
`presentation state contains a display area selection SQ item with mode 'TRUE SIZE'
but presentationPixelSpacing VM != 2`. That is level 1 with a named cause.

### Level 2, LOADED BUT WRONG

The viewer opened the object without complaint and the annotation is either absent
from the display or drawn in the wrong place.

Decisive test: the object loaded, and at least one of

- **silently dropped**: the image displays, the presentation state is selected or
  listed as applied, and none of the 17 text labels and none of the 17 graphics
  appear anywhere in the viewport. No error is shown.
- **partially dropped**: some of the 34 annotation elements appear and some do
  not. Count and record how many of each kind.
- **mispositioned**: an annotation appears but not at the anatomy it labels.
  See "Position" below for the tolerance.
- **wrong frame or wrong image**: the annotation is drawn on an instance other
  than the one in `ReferencedImageSequence`.

Silently dropped is the single most important cell type in this study and the one
most easily mis-scored, because a viewer that ignores a presentation state and
just shows the image looks exactly like a viewer that has no annotation to show.
Guard against that with the negative control: `colour_none` and, better, the
purpose built object with `GraphicAnnotationSequence` removed entirely. If the
viewport looks the same for the real object and the stripped one, the viewer is
dropping the annotation, and the cell is level 2, not level 3.

### Level 3, RENDERS

The annotation appears, all of it, in the right place.

Decisive test: all three of

1. All 17 text labels are legible in the viewport, with the same strings as
   `UnformattedTextValue` in the object. Count them.
2. All 17 graphic objects are drawn.
3. Position passes the tolerance below.

Level 3 says nothing about colour. Colour is scored on a separate axis, next.

## Colour, a separate axis, scored only when the level is 3

Do not fold colour into the level. A viewer can render every annotation perfectly
and ignore colour entirely, and that is the finding this bench exists to measure.
Score colour only for cells that reached level 3, and use these four values.

| value | meaning |
|---|---|
| `HONOURED` | the annotation is drawn in the colour the object asks for |
| `DEFAULT` | the annotation is drawn, in some other single colour, the same colour for every element regardless of what the object asks |
| `PARTIAL` | one colour route is honoured and another is not, within the same object |
| `N/A` | the object requests no colour, that is `colour_none`, or the level is not 3 |

### How to tell HONOURED from DEFAULT without guessing

Guessing from a screenshot is not acceptable, because a viewer whose default
happens to be near the requested colour is indistinguishable from one that read
the tag. Three checks, in order. The first two are objective, use them.

**Check C1, the discriminating pair.** The variant set contains objects that
differ only in which colour tag carries the flag:

| object | 0070,0241 text | 0070,0251 line | 0070,0401 layer |
|---|---|---|---|
| `colour_none` | absent | absent | absent |
| `colour_line_iod` | absent | present | absent |
| `colour_layer_iod` | absent | absent | present |
| `colour_text_outofiod` | present | absent | absent |
| `colour_all` | present | present | present |

Open `colour_none` and the candidate object in the same viewer, same window,
same zoom. If the pixels of the annotation are identical between the two, the
viewer is not reading the colour tag, and the candidate scores `DEFAULT`. If they
differ, the viewer read something, and you go to C2. This check is decisive and
requires no knowledge of the viewer's defaults.

**Check C2, the value match.** The colour values in the objects are CIELab as
DICOM stores it, three unsigned 16 bit integers, L\* over 0 to 100 and a\*, b\*
over -128 to 127, each scaled onto 0 to 65535. There are exactly two colours in
this variant set. Read out of `colour_line_iod` and converted here, they are:

| role in the pipeline | stored US triplet | CIELab | sRGB target |
|---|---|---|---|
| normal vertebra | 49086, 39038, 53173 | 74.9, 23.9, 78.9 | **255, 165, 0** |
| flagged vertebra | 53214, 63248, 51426 | 81.2, 118.1, 72.1 | **255, 0, 75** |

Both are worth looking at before scoring. The emitter calls the first one YELLOW
and the second RED, but in sRGB the first is orange and the second is a crimson
pink. Score against the sRGB numbers, not against the names.

Sample the interior of a drawn stroke, not its antialiased edge, and take the
modal value over at least 25 pixels. Score `HONOURED` when every channel is
within 24 of the target, which is roughly 10 percent of full scale, and the hue is
unambiguously the requested one. Anything further out is `DEFAULT`, and record the
measured RGB so the disagreement is inspectable. The tolerance is deliberately
loose because viewers apply their own gamma and because CIELab to sRGB is not
round trip exact.

Note the two targets are far apart in the green channel, 165 against 0, and
identical in red. So a viewer that honours colour will show a visible orange
against pink difference between a normal and a flagged vertebra in the same image,
and a viewer that does not will show one colour throughout. That difference is
easier to judge than either colour alone, so use it.

**Check C3, the route split.** Only after C1 and C2. Score `PARTIAL` when
`colour_all` shows two different colours in one object, or when
`colour_line_iod` is honoured and `colour_text_outofiod` is not, or the reverse.
Name which route won. This is the finding the three colour routes were built to
produce, so state it as route names, not as "some colours worked".

### The text colour route is out of IOD, and that is the experiment

`0070,0241` Text Color CIELab Value is not part of the Grayscale Softcopy
Presentation State IOD. `dciodvfy` flags it in every object that carries it, see
`results/gsps_conformance_baseline.md`. A viewer that ignores it is behaving
correctly. A viewer that honours it is being generous. Both are legitimate
outcomes and neither is a bug in the viewer. Score what happens and do not
editorialise in the cell.

## Position tolerance

An annotation is correctly positioned when its anchor point falls within
**one half of the labelled vertebral body height** of that vertebra's centre in
the displayed image. Vertebral height is used rather than millimetres because it
is the clinically meaningful unit here: half a body height cannot be confused with
the neighbouring level, and a whole body height means the label has moved to the
wrong vertebra, which is exactly the failure mode this pipeline is meant to flag.

Judge on the displayed image at the default zoom and window the viewer chose. Do
not pan or zoom before judging position, then pan and zoom freely to count
elements.

Two systematic errors to look for specifically, because they are cheap to get
wrong in an emitter and they produce a plausible looking display:

- a uniform offset of every annotation by the same vector, which means the viewer
  is applying the wrong origin convention for `GraphicData`,
- a mirrored or rotated layout, which means the viewer applied a spatial
  transformation the object did not request.

Both are level 2, not level 3. Record which.

## Scoring procedure, per cell

1. Confirm the archive holds the object. `load_objects.py` verdict `ACCEPTED` or
   `DUPLICATE`, and `check_dicomweb.py` shows the series over DICOMweb. Without
   both, stop, the cell is unscoreable and the reason is archive side.
2. Open the referenced image series in the viewer under test, at its default
   window and zoom.
3. Apply the presentation state by whatever mechanism the viewer offers. Record
   the mechanism verbatim, for example "listed as a separate PR series and
   selected", or "offered in a Presentation State dropdown", or "no mechanism
   found". "No mechanism found" with the object present in the archive is
   level 2 silently dropped, not level 1.
4. Score the level, worst first, stopping at the first decisive test that fires.
5. If the level is 3, run C1 then C2 then C3 and score the colour axis.
6. Capture a screenshot of the viewport at default zoom, and a second one zoomed
   to a labelled vertebra. Save as
   `results/figures/viewer_<viewer>_<object>_<default|zoom>.png`.
7. Record viewer name, exact version string as the viewer itself reports it,
   how it was obtained, the browser and its version where applicable, the date,
   and the initials of the scorer.

## Things that are explicitly NOT part of the level

- Whether the object passes `dciodvfy` or `dcmpschk`. That is measured separately
  and is a property of the object, not of the viewer. Do not let it colour the
  score. An object can be non conformant and render, and conformant and not.
- Whether the viewer is fast.
- Whether the annotation is aesthetically good, font size, line weight, overlap.
  Note it, do not score it.
- Whether the producer identity in the object is truthful. That axis exists to
  test whether any viewer gates rendering on `Manufacturer` or
  `ManufacturerModelName`, which would be a real finding, but it is detected as a
  difference in level between the `_trueid` and `_meddreamid` pairs, not as a
  judgement about the identity itself.

## Known trap: a renderer that loads a presentation state and draws no graphics

`dcmp2pgm` from DCMTK applies the grayscale pipeline of a presentation state and
does **not** draw graphic annotations at all. Measured here: rendering
`colour_line_iod` and a copy of it with `GraphicAnnotationSequence` deleted gives
byte identical PGM output, md5 `22024d6cba9ef17b0723fd757c30157e` for both, while
both differ from the same image rendered with no presentation state at all.

So `dcmp2pgm` is a loadability oracle, not a rendering oracle. Scoring it level 2
"silently dropped" would be technically true against these rules and completely
misleading about the tool. Command line renderers therefore get scored on level
0 and level 1 only, and their level 2 and level 3 cells are marked
`out of scope for this tool` with a one line reason. Do not extend this exemption
to interactive viewers.
