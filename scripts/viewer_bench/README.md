# viewer bench

A reproducible rig for the GSPS versus DICOM SEG rendering matrix. It loads DICOM
objects into several free viewers and records whether the annotation renders and
whether its colour survives.

Everything here was brought up and exercised on this machine on 2026-07-30. The
measured outcomes live in `results/viewer_bench.md`. The scoring rules live in
`SCORING.md` and must be read before any cell is scored.

## One command

```
cd scripts/viewer_bench
docker compose up -d
```

Two containers, five viewers plus an archive. Wait for both to report `healthy`,
about fifteen seconds, then:

| what | URL | measured HTTP on 2026-07-30 |
|---|---|---|
| Orthanc REST `/system` | http://localhost:8142/system | 200, `application/json`, 1603 bytes |
| Orthanc Explorer 2 | http://localhost:8142/ui/app/ | 200, `text/html`, 1675 bytes |
| Stone Web Viewer | http://localhost:8142/stone-webviewer/index.html | 200, `text/html`, 49975 bytes |
| OHIF, Orthanc plugin build | http://localhost:8142/ohif/ | 200, `text/html`, 4847 bytes |
| VolView | http://localhost:8142/volview/index.html | 200, `text/html`, 1054 bytes |
| Orthanc Web Viewer, classic | http://localhost:8142/web-viewer/app/viewer.html | 200, `text/html`, 3382 bytes |
| Orthanc DICOMweb, direct | http://localhost:8142/dicom-web/studies | 200, `application/dicom+json` |
| OHIF v3 standalone | http://localhost:3110/ | 200, `text/html`, 4812 bytes |
| the same DICOMweb through OHIF's proxy | http://localhost:3110/dicom-web/studies | 200, `application/dicom+json` |

`/volview/` without `index.html` returns 404. That is the plugin's own routing, not
a bench misconfiguration.

## Ports

Every published port is deliberately non default so the bench cannot collide with
anything already running.

| service | host port | container port | upstream default |
|---|---|---|---|
| Orthanc HTTP | 8142 | 8042 | 8042 |
| Orthanc DICOM SCP | 4342 | 4242 | 4242 |
| OHIF standalone | 3110 | 8080 | 3000 |
| MedDream, `licensed` profile only | 8180 | 8080 | 8080 |

Orthanc's application entity title is `SPINEBENCH`, so a C-STORE test is

```
storescu -v -aet BENCHSCU -aec SPINEBENCH localhost 4342 <file.dcm>
```

## Reproducibility

Images are pinned by digest, not by tag. A viewer matrix is worthless if the reader
cannot get the same viewer build, and `latest` moves. Resolved and pulled
2026-07-30:

```
orthancteam/orthanc  sha256:99082b87c96d56e57472d703ad799b779da7aa35aedac830d58cce646a43643f
                     Orthanc 1.12.11, API version 30
ohif/app             sha256:48a5537ec5f19436a0d29eaba30f6402b254740a65d37a5458f885e892b69fba
                     OHIF v3 on nginx 1.27.5 unprivileged
```

To move to newer builds, resolve the new digests with `docker buildx imagetools
inspect` or `docker image inspect`, edit the compose file, and re-run everything.
Do not mix digests inside one matrix.

## Data handling

No clinical data is bind mounted into any container. Objects go in over the REST
API from the host. The Orthanc index and storage live in a named docker volume, so

```
docker compose down -v
```

wipes the bench back to empty. Do that before any run whose acceptance counts you
intend to quote, because an object already present returns `AlreadyStored` rather
than `Success` and the tally changes meaning.

Nothing under `<path>` is copied into this repository. The
Orthanc volume is outside the repository and is not committed.

## Scripts

### `load_objects.py`

Pushes a directory of DICOM objects into Orthanc over `POST /instances` and reports
which were accepted and which rejected, with Orthanc's own error text for
rejections. Also reads each accepted object back, to separate "acknowledged" from
"actually indexed", and reports which of the three colour tags survived the round
trip.

```
python load_objects.py <path>\runs\gsps_variants_v2 --pattern .dcm \
    --json <path>\runs\viewer_bench\push_variants.json
```

Exit code 0 if every object was accepted or already stored, 1 otherwise.

An archive refusing an object is one of the four outcome levels in `SCORING.md`,
and it is the only one measurable with no human looking at a screen.

### `check_dicomweb.py`

Asks the same Orthanc, over DICOMweb this time, what the browser viewers will see.
QIDO-RS series listing, WADO-RS metadata retrieval, and which colour routes are
still present in that metadata. QIDO and WADO are a different code path from
Orthanc's native REST API, so this fixes the transport as a variable: if a colour
tag were dropped here we would otherwise misread it as the viewer ignoring it.

```
python check_dicomweb.py --json <path>\runs\viewer_bench\dicomweb_check.json
python check_dicomweb.py --modality PR
```

### `slicer_setup.py`

Runs inside 3D Slicer's own python, not the spinelab interpreter. Reports the
Slicer build, installs the extensions the SEG side of the matrix needs, and lists
which DICOM plugins Slicer has.

```
Slicer.exe --no-main-window --no-splash --python-script slicer_setup.py \
           --install --exit-after-startup
```

Run it once with `--install`, then again without, because Slicer only loads newly
installed extensions after a restart.

## Command line renderers, outside docker

These are not in the compose file because they are host binaries, but they are part
of the bench and they produce the only rendering evidence obtainable without a
human.

- `dciodvfy` from dicom3tools, already at `<path>\tools\dicom3tools`. IOD
  conformance. Driven by `spinelab.gsps.validate`.
- `dcmpschk` from DCMTK 3.7.0 at
  `<path>\tools\dcmtk\dcmtk-3.7.0-win64-dynamic\bin`. A presentation state
  specific checker, independent of dciodvfy and it catches different things.
- `dcmp2pgm` from the same DCMTK. OFFIS's own reference renderer for presentation
  states. It applies the grayscale pipeline and, measured here, does **not** draw
  graphic annotations, so treat it as a loadability oracle only. `SCORING.md` has
  the measurement and the rule that follows from it.
- `dcmdjpeg` from the same DCMTK. Needed first: `dcmp2pgm` cannot decode the
  JPEG lossless source images in this cohort and fails with
  `can't change to unencapsulated representation for pixel data`.

## What this bench does NOT do

It does not score whether an annotation renders correctly on screen, or whether its
colour is honoured. Those need a human or a screenshot pass, following
`SCORING.md`. `load_objects.py` prints per viewer deep links for exactly that
purpose and labels them as untested.
