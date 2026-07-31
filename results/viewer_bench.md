# Viewer bench, stood up and measured

Measured 2026-07-30 on this machine, Windows 11 Home 10.0.26200, Docker Desktop
4.53.0. Every number below was produced by a command run here. The bench itself,
its compose file, its scripts and its scoring rules live in
`scripts/viewer_bench/`.

**Read this first.** This document reports two very different things and keeps them
apart on purpose:

- **Measured without a human**: whether an archive accepts an object, whether the
  object survives the transport a web viewer uses, whether two independent third
  party validators accept it, and whether DCMTK's own reference renderer will load
  it. All of that is done and reported below.
- **Not done**: whether any annotation actually appears on screen, in the right
  place, in the right colour, in any of the eight interactive viewers now
  installed. **No viewport has been looked at. No screenshot has been taken. Every
  render and colour cell of the matrix is empty.** That pass needs a human
  following `scripts/viewer_bench/SCORING.md`.

## 1. What was obtained, and exactly how

No GUI installer was run. Where a target only ships an installer, it was either
extracted non interactively or reported as needing a human.

| viewer or tool | obtained | how, verbatim |
|---|---|---|
| **Orthanc 1.12.11** | yes | `docker pull orthancteam/orthanc:latest`, pinned in compose by digest `sha256:99082b87c96d…`. Reports `Orthanc 1.12.11, API 30`. |
| **Orthanc Explorer 2** | yes | bundled plugin in that image, `ORTHANC_EXPLORER_2_ENABLED=true` |
| **Stone Web Viewer** | yes | bundled plugin, `STONE_WEB_VIEWER_PLUGIN_ENABLED=true` |
| **OHIF, Orthanc plugin build** | yes | bundled plugin `libOrthancOHIF.so`, `OHIF_PLUGIN_ENABLED=true` |
| **VolView** | yes | bundled plugin, `VOLVIEW_PLUGIN_ENABLED=true` |
| **Orthanc Web Viewer, classic** | yes | bundled plugin, `ORTHANC_WEB_VIEWER_PLUGIN_ENABLED=true` |
| **OHIF v3 standalone** | yes | `docker pull ohif/app:latest`, pinned by digest `sha256:48a5537ec5f1…` |
| **Weasis 4.7.1** | yes | see below, MSI extracted with `msiexec /a`, launched, window title `Weasis v4.7.1` |
| **3D Slicer 5.12.3, revision 34627** | yes | NSIS `.exe` extracted with 7-Zip, runs headless, extensions installed non interactively |
| **DICOMscope 3.6.4** | yes | OFFIS's own GSPS reference viewer. NSIS `.exe` extracted with 7-Zip, run on a downloaded Temurin JRE, window title `DICOMscope 3.6.4` |
| **DCMTK 3.7.0 command line** | yes | `dcmtk-3.7.0-win64-dynamic.zip` from dicom.offis.de. Gives `dcmp2pgm`, `dcmpschk`, `storescu`, `dcmdjpeg` |
| **MicroDicom** | **no** | microdicom.com is unreachable from this network. See section 6 |
| **RadiAnt free** | **no** | needs a GUI installer. See section 6 |
| **dicompyler** | **no** | `pip install` fails. See section 6 |
| **Aliza MS** | **no** | no direct download link found by non interactive scrape of its download page |

### Weasis, the detail that matters

The portable zip no longer exists for the current release. Checked both
distribution points on 2026-07-30:

- GitHub `nroduit/Weasis` v4.7.1 assets are `weasis-native.zip`, an `.msi`, two
  `.pkg`, two `.deb` and an `.rpm`. `weasis-native.zip` is the native package
  build kit, not a runnable portable app.
- SourceForge `dcm4che/Weasis/4.7.1/` holds only `weasis_4.7.1-1_amd64.deb`,
  `Weasis-4.7.1-aarch64.pkg`, `weasis-4.7.1-readme.md` and
  `Weasis-4.7.1-x86-64.msi`. Requests for `weasis-portable.zip` at three plausible
  paths all returned SourceForge's 200 plus HTML error page at about 130 KB, not a
  57 MB zip.

So the portable route is dead and the MSI was extracted instead, which is still non
interactive:

```
msiexec /a Weasis-4.7.1-x86-64.msi /qn TARGETDIR=<path>\tools\viewers\weasis
```

Exit code 0. Produces `PFiles64\Weasis\Weasis.exe` and `Dicomizer.exe` with a
bundled runtime, `JAVA_VERSION="26.0.1"`. Launched, and a window titled
`Weasis v4.7.1` appeared, then the process was killed. No system Java needed.

### 3D Slicer, the detail that matters

Slicer publishes no portable archive, but its Windows `.exe` is an NSIS archive.
7-Zip 25.01 extracted it cleanly: 9170 files, 1,154,574,112 bytes uncompressed.
The extracted tree runs headless, which makes the whole Slicer leg clickless:

```
Slicer.exe --no-main-window --no-splash --python-script slicer_setup.py \
           --install --exit-after-startup
```

Measured output over three runs, report then install then verify:

```
SLICER version   5.12.3
SLICER revision  34627
SLICER installed 0 extension(s): none
SLICER install QuantitativeReporting    -> True
SLICER install SlicerDcm2nii            -> True
SLICER installed 4 extension(s): PETDICOMExtension, QuantitativeReporting,
                                 SlicerDcm2nii, SlicerDevelopmentToolbox
SLICER DICOM SEG plugin  present
```

Two extensions were asked for and four are installed, because
QuantitativeReporting pulls PETDICOMExtension and SlicerDevelopmentToolbox as
dependencies. There is no separately installable `dcmqi` extension on the 5.12.3
extension server: of 221 entries, none matches `dcmqi`. DICOM SEG support comes
through `DICOMSegmentationPlugin`, which is present after the install.

**Measured and directly relevant to the matrix.** Slicer 5.12.3 with these
extensions exposes fourteen DICOM plugins:

```
DICOMEnhancedUSVolumePlugin, DICOMGeAbusPlugin, DICOMImageSequencePlugin,
DICOMM3DPlugin, DICOMPETSUVPlugin, DICOMParametricMapPlugin, DICOMRWVMPlugin,
DICOMScalarVolumePlugin, DICOMSegmentationPlugin, DICOMSlicerDataBundlePlugin,
DICOMTID1500Plugin, DICOMVolumeSequencePlugin, Dcm2niixPlugin,
MultiVolumeImporterPlugin
```

**None of the fourteen reads a Grayscale Softcopy Presentation State.** One reads
DICOM SEG. That is a structural result, not a rendering result: Slicer sits on the
SEG side of the matrix and has no code path for the GSPS side at all. It still
needs the human pass to confirm the observable behaviour, which will presumably be
"the PR series is not offered for import", but the plugin list is the reason.

### DICOMscope, the most relevant single viewer

DICOMscope 3.6.4 is OFFIS's reference implementation for softcopy presentation
states, from the same group that wrote DCMTK. It is the one viewer whose entire
purpose is GSPS.

`DICOMscope-3.6.4-Windows.exe`, 17,421,353 bytes, is NSIS-3 and 7-Zip extracted it:
139 files, 51,241,258 bytes. It needs Java and this machine had none, so a runtime
was fetched non interactively from the Adoptium API:

```
curl -L https://api.adoptium.net/v3/binary/latest/17/ga/windows/x64/jre/hotspot/normal/eclipse
openjdk version "17.0.20" 2026-07-21, Temurin-17.0.20+8
```

Launched with that JRE on `PATH`, a `javaw` process appeared with main window title
`DICOMscope 3.6.4`, then it was killed. Its bundled `amd64\dcmqridx.exe` was then
used to register the bench objects into its local database index, so a human can
open DICOMscope and find them with no setup:

```
dcmqridx database database\bench_image_00001589.dcm database\bench_gsps_*.dcm
```

`index.dat` grew to 108,262 bytes and contains the study UID nine times plus the
registered filenames. Seven GSPS variants and the referenced image are staged:
`conformant_trueid`, `colour_none`, `colour_line_iod`, `colour_layer_iod`,
`colour_text_outofiod`, `colour_all`, `asis_trueid`.

## 2. The docker bench, brought up and confirmed serving

```
cd scripts/viewer_bench
docker compose up -d
```

Both services reached `healthy` in under fifteen seconds. Real HTTP responses,
fetched from the host with `urllib`:

| endpoint | status | content type | bytes |
|---|---|---|---|
| `http://localhost:8142/system` | **200** | `application/json; charset=utf-8` | 1603 |
| `http://localhost:8142/plugins` | **200** | `application/json; charset=utf-8` | 136 |
| `http://localhost:8142/ui/app/` | **200** | `text/html` | 1675 |
| `http://localhost:8142/stone-webviewer/index.html` | **200** | `text/html` | 49975 |
| `http://localhost:8142/ohif/` | **200** | `text/html` | 4847 |
| `http://localhost:8142/volview/index.html` | **200** | `text/html` | 1054 |
| `http://localhost:8142/web-viewer/app/viewer.html` | **200** | `text/html` | 3382 |
| `http://localhost:8142/dicom-web/studies` | **200** | `application/dicom+json` | 2, empty archive |
| `http://localhost:3110/` | **200** | `text/html` | 4812 |
| `http://localhost:3110/app-config.js` | **200** | `application/javascript` | 1550 |
| `http://localhost:3110/dicom-web/studies` | **200** | `application/dicom+json` | 2, through the proxy |

`/plugins` returned, verbatim, the loaded plugin list:

```
["explorer.js","dicom-web","gdcm","ohif","orthanc-explorer-2","stone-webviewer","volview", ...]
```

Ports are all non default, documented in `scripts/viewer_bench/README.md`: Orthanc
HTTP 8142 not 8042, Orthanc DICOM 4342 not 4242, OHIF 3110 not 3000.

Two things went wrong and are fixed in the committed files, recorded so nobody
rediscovers them:

1. `http://localhost:8142/volview/` returns **404**. The plugin needs the explicit
   `index.html`. Not a bench misconfiguration.
2. The OHIF container's same origin DICOMweb proxy first returned 404 for
   `/dicom-web/studies`. Cause: when nginx `proxy_pass` uses a variable, a URI
   written in the directive is passed verbatim instead of substituting the matched
   location, so `proxy_pass $orthanc/dicom-web/` dropped everything after the
   prefix. Fixed to `proxy_pass $orthanc$request_uri`, after which the same request
   returns 200.

A same origin proxy is used rather than CORS headers on Orthanc deliberately. A
CORS preflight failure and a viewer refusing an object look identical from outside
the browser, and this study cannot afford to confuse those two.

## 3. Archive acceptance, the level that needed no human

Bench reset to empty first, `docker compose down -v && up -d`, confirmed by
`GET /instances` returning `[]`. Then three pushes with
`scripts/viewer_bench/load_objects.py`.

| run | objects | ACCEPTED | DUPLICATE | REJECTED | ERROR | readback |
|---|---|---:|---:|---:|---:|---|
| 38 shipped GSPS from the 2025-11-21 run | 38 | **38** | 0 | 0 | 0 | 38 indexed |
| source CT series `pat_XXXX/SAGITTAL_BONE_SN007` | 41 | 40 | 1 | 0 | 0 | 41 indexed |
| the nine GSPS variants from `runs/gsps_variants_v2` | 9 | **9** | 0 | 0 | 0 | 9 indexed |

The one DUPLICATE is the shipped `00001589_GSPS.dcm`, which the first run had
already stored. The source series is 40 CT instances plus that one GSPS in the same
folder. Every object was read back over the REST API, so these are indexed, not
merely acknowledged, and every stored `SOPClassUID` matched the local file:
`1.2.840.10008.5.1.4.1.1.11.1`, Grayscale Softcopy Presentation State Storage, for
all 47 presentation states.

**Orthanc 1.12.11 refuses nothing.** It accepts the shipped objects that fail
`dciodvfy` on seven required attributes, and it accepts the out of IOD text colour.
So level 1a of `SCORING.md`, archive refuses ingest, does not fire anywhere on this
archive. That is a real negative result and it is worth stating plainly: the
"refuses to load" outcome, if it exists, will come from viewers or from a stricter
archive, not from Orthanc.

The DICOM network path was also tested, since it is a different gate from the REST
API. `storescu` from DCMTK 3.7.0 against `SPINEBENCH` on port 4342:

```
storescu -v -aet BENCHSCU -aec SPINEBENCH localhost 4342 00001589_GSPS__conformant_trueid.dcm
  I: Association Accepted   I: Received Store Response (Success)
storescu -v -aet BENCHSCU -aec SPINEBENCH localhost 4342 00001589_GSPS.dcm   (the shipped as-is object)
  W: DcmMetaInfo: No Group Length available in Meta Information Header
  I: Association Accepted   I: Received Store Response (Success)
```

Both succeed. C-STORE is not stricter than REST here.

### The nine variants, per object

Colour column is which of the three colour tags were still present when the object
was read back out of the archive.

| variant | verdict | HTTP | readback | colour tags after readback |
|---|---|---|---|---|
| `asis_trueid` | ACCEPTED | 200 | indexed | text |
| `asis_meddreamid` | ACCEPTED | 200 | indexed | text |
| `conformant_trueid` | ACCEPTED | 200 | indexed | line |
| `conformant_meddreamid` | ACCEPTED | 200 | indexed | line |
| `colour_none` | ACCEPTED | 200 | indexed | none |
| `colour_line_iod` | ACCEPTED | 200 | indexed | line |
| `colour_layer_iod` | ACCEPTED | 200 | indexed | layer |
| `colour_text_outofiod` | ACCEPTED | 200 | indexed | text |
| `colour_all` | ACCEPTED | 200 | indexed | text, line, layer |

Every route survived exactly as designed, including the out of IOD text route.

## 4. Colour survives the transport, so any loss is the viewer's

`check_dicomweb.py` then asked the same archive over DICOMweb, which is a different
code path from Orthanc's native REST API and is what the browser viewers actually
consume. QIDO-RS returned 20 studies and 48 series, WADO-RS metadata returned
HTTP 200 for all 48.

| modality | series | metadata HTTP | colour tags present in DICOMweb metadata |
|---|---:|---|---|
| PR | 38 | 200 | text and line, the 38 shipped objects |
| PR | 3 | 200 | text only |
| PR | 3 | 200 | line only |
| PR | 1 | 200 | layer only |
| PR | 1 | 200 | text, line and layer |
| PR | 1 | 200 | none |
| CT | 1 | 200 | none, the source series, 40 instances |

48 series total: 38 shipped plus 9 variants plus 1 CT. Every presentation state is
discoverable by QIDO-RS as `Modality PR` with `SeriesDescription`
`TotalSpineSeg Annotations`, and every colour route arrives intact at WADO-RS.

**Consequence.** If a viewer shows no colour, the archive and the transport are
ruled out. It is the viewer. That is the whole reason this check exists.

## 5. Two independent validators, and DCMTK's own reference renderer

These are objects under test, not viewers, but they are the only rendering side
evidence obtainable without a human, and one of them produces a hard refusal.

`dcmpschk` from DCMTK 3.7.0 is a presentation state specific checker, independent
of `dciodvfy`. `dcmp2pgm` from the same DCMTK is OFFIS's reference renderer.

| variant | `dcmpschk` | `dcmp2pgm` | rendered PGM md5 |
|---|---|---|---|
| `asis_meddreamid` | **failed** | **exit 10, no output** | none |
| `asis_trueid` | **failed** | **exit 10, no output** | none |
| `conformant_trueid` | passed | exit 0 | `22024d6cba9ef17b0723fd757c30157e` |
| `conformant_meddreamid` | passed | exit 0 | `22024d6cba9ef17b0723fd757c30157e` |
| `colour_none` | passed | exit 0 | `22024d6cba9ef17b0723fd757c30157e` |
| `colour_line_iod` | passed | exit 0 | `22024d6cba9ef17b0723fd757c30157e` |
| `colour_layer_iod` | passed | exit 0 | `22024d6cba9ef17b0723fd757c30157e` |
| `colour_text_outofiod` | passed | exit 0 | `22024d6cba9ef17b0723fd757c30157e` |
| `colour_all` | passed | exit 0 | `22024d6cba9ef17b0723fd757c30157e` |

And over the 38 shipped objects: `dcmpschk` **passed 0, failed 38**.

The single cause, verbatim from both tools:

```
presentation state contains a display area selection SQ item with mode 'TRUE SIZE'
but presentationPixelSpacing VM != 2
```

followed, in `dcmp2pgm`, by `F: Can't open input file(s).` and exit code 10.

That is exactly the Type 1C error `dciodvfy` reported in
`results/gsps_conformance_baseline.md`, `PresentationPixelSpacing` absent from the
DisplayedArea module in 38 of 38 objects. So the missing conditional attribute is
not a cosmetic validator complaint. **DCMTK's own reference renderer refuses to
load all 38 shipped objects, and loads all seven conformant variants.** This is
level 1 of `SCORING.md`, refused, with a named cause, measured by a third party
tool, and it is an independent justification for the conformant variant beyond
conformance for its own sake.

Note what `dcmpschk` does not do: it **passes** `colour_text_outofiod`, which
carries the illegal `(0070,0241)`. `dciodvfy` flags that tag and `dcmpschk` does
not. The two validators are complementary and both are needed.

### The trap in dcmp2pgm, measured

All seven rendered PGMs are byte identical to one another. That is unsurprising in
an 8 bit grayscale format, but the important part is stronger. Rendering
`colour_line_iod` and rendering a copy of it with `GraphicAnnotationSequence`
deleted entirely, 18 items removed, gives **the same md5**,
`22024d6cba9ef17b0723fd757c30157e`. Rendering the image with no presentation state
at all gives a different result, md5 `af58b31dba401ced44f10e54b656513a`, differing
in 516,612 of 525,824 pixels, 98.25 percent, spread over the whole frame, which is
a window and level change.

So `dcmp2pgm` applies the grayscale pipeline of a presentation state and **does not
draw graphic annotations at all**. It is a loadability oracle, not a rendering
oracle. `SCORING.md` carries this measurement and the rule that follows: command
line renderers are scored on crash and refusal only.

One practical note: `dcmp2pgm` cannot decode the JPEG lossless source images in
this cohort, transfer syntax `1.2.840.10008.1.2.4.70`, and fails with
`can't change to unencapsulated representation for pixel data`. Run `dcmdjpeg`
first.

## 6. What a human still has to click, and why

### To score the matrix at all

**The entire render and colour half of the matrix.** Eight interactive viewers are
installed and reachable, the objects are loaded, the deep links are printed by
`load_objects.py`, and nobody has looked at a single viewport. Follow
`scripts/viewer_bench/SCORING.md`, which is written so that two scorers agree.
Screenshots go to `results/figures/viewer_<viewer>_<object>_<default|zoom>.png`.

Deep links, printed by the loader and not exercised:

```
stone      http://localhost:8142/stone-webviewer/index.html?study=1.2.826.0.1.3680043.2.174.20250828.5092601867578
ohif plug  http://localhost:8142/ohif/viewer?StudyInstanceUIDs=1.2.826.0.1.3680043.2.174.20250828.5092601867578
ohif alone http://localhost:3110/viewer?StudyInstanceUIDs=1.2.826.0.1.3680043.2.174.20250828.5092601867578
volview    http://localhost:8142/volview/index.html
explorer   http://localhost:8142/ui/app/
```

For Weasis and DICOMscope, launch the executables listed in section 1. Weasis needs
its DICOMweb node adding in preferences, or a `$dicom:rs` command line, because the
`weasis://` protocol handler is registered by a real MSI install and an extracted
copy does not register it. DICOMscope already has the objects in its local index.

### To add the viewers that could not be obtained here

| viewer | what a human must do | why the automated route failed |
|---|---|---|
| **MicroDicom** | download the portable build from a network that can reach microdicom.com | Unreachable from here. TLS handshake fails three independent ways: `curl` on Windows schannel returns `curl: (35) schannel: failed to receive handshake`, python OpenSSL returns `SSLEOFError(8, 'UNEXPECTED_EOF_WHILE_READING')`, and `curlimages/curl` in a Linux container returns `error:0A000126::unexpected eof while reading`. Plain HTTP is also refused, `RemoteDisconnected`. This is network reachability, not a licence or an installer. |
| **RadiAnt free** | run `RadiAnt-2026.1-Setup.exe`, already downloaded to `<path>\tools\viewers\_dl\` | The setup is an 8,218,456 byte PE with no extractable archive, 7-Zip reports `Type = PE` and lists no files. It is a web downloader stub, so there is nothing to extract and no documented silent switch was attempted. |
| **dicompyler** | nothing worth doing | `pip install dicompyler` into the spinelab env fails while getting build requirements: `urllib.error.HTTPError: HTTP Error 403: SSL is required`, raised from its own `setup.py` fetching over plain HTTP. Last release 2018. It is also an RT plan and dose tool, not a presentation state renderer, so it adds little to this matrix. Nothing was installed and the env is unchanged. |
| **Aliza MS** | find the download by hand | `https://www.aliza-dicom-viewer.com/download` returns 200 and 150,037 bytes but a scrape for `.zip .exe .msi .tar.gz .7z` hrefs found none. |

The bench does not include the viewer whose vendor name the shipped objects declare. That vendor's product is commercial and licence gated, no leg of this matrix was ever scored against it, and the conformance and rendering findings do not depend on it. The `_trueid` against `_meddreamid` variant pair is retained because the deployed objects carry those identity tags and reproducing them byte-for-byte is required to reproduce the deployed encoding, not because any viewer from that vendor is under test.

## 7. Honest limits of what is here

- **No visual evidence of any kind exists yet.** Eight viewers, zero scored cells.
- The one archive tested is permissive. A stricter archive, dcm4chee-arc for
  instance, is the obvious next automatable target and would give the refusal level
  a second data point. It was not attempted here: it needs a multi container stack
  with PostgreSQL and that is a separate job.
- The SEG half of the matrix has no objects yet. Slicer is installed and its
  `DICOMSegmentationPlugin` is present, but nothing has been pushed to compare
  against, so GSPS versus SEG is one sided so far.
- All GSPS work is on one study, `1.2.826.0.1.3680043.2.174.20250828.5092601867578`,
  patient `pat_XXXX`, one referenced CT instance `00001589`. The nine variants are
  nine encodings of one annotation set, by design, so viewer differences are
  attributable. Generalisation across studies is untested.
- The source cohort is CT and the model that produced the labels declares
  `channel_names {"0": "MRI"}`. That limitation is unchanged by anything here and
  is stated in `CLAUDE.md`.
- The bench holds private clinical DICOM in a docker volume on this machine.
  Nothing was copied into this repository. `docker compose down -v` wipes it.

## 8. State the bench was left in

Left running with everything loaded, so the human pass can start with no setup.
`GET http://localhost:8142/statistics`, verbatim:

```
CountInstances 87   CountSeries 48   CountStudies 20   CountPatients 20
TotalDiskSizeMB 24
```

87 instances is 38 shipped GSPS plus 40 source CT plus the 9 variants. Both
containers `healthy`. DICOMscope's local index holds 7 variants plus the referenced
image. Slicer has its extensions installed. Weasis is extracted and launchable.

## 9. Reproduce

```
cd scripts/viewer_bench
docker compose down -v && docker compose up -d

python load_objects.py "<path>\test_api\refined_gsps_1" \
    --pattern _GSPS --json <path>\runs\viewer_bench\push_shipped_38.json --no-links
python load_objects.py "<path>\test_api\refined_gsps_1\pat_XXXX\SAGITTAL_BONE_SN007" \
    --pattern .dcm --json <path>\runs\viewer_bench\push_source_series.json --no-links
python load_objects.py <path>\runs\gsps_variants_v2 \
    --pattern .dcm --json <path>\runs\viewer_bench\push_variants.json
python check_dicomweb.py --json <path>\runs\viewer_bench\dicomweb_check.json
```

DCMTK leg, from `<path>\tools\dcmtk\dcmtk-3.7.0-win64-dynamic\bin`:

```
dcmdjpeg <source.dcm> decomp.dcm
dcmpschk <gsps.dcm>
dcmp2pgm -p <gsps.dcm> decomp.dcm out.pgm
storescu -v -aet BENCHSCU -aec SPINEBENCH localhost 4342 <gsps.dcm>
```

Raw records are outside the repository, in `<path>\runs\viewer_bench\`:
`push_shipped_38.json`, `push_source_series.json`, `push_variants.json`,
`dicomweb_check.json`, `dicomweb_check.txt`, `pgm/`, `pgm2/`, and the Slicer
transcripts `slicer_report.txt`, `slicer_install.txt`, `slicer_probe.txt`.
