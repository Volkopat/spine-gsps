"""Emit DICOM Segmentation objects carrying one segment per named vertebra.

This is the SEG half of the GSPS versus SEG comparison. `writer.py` re-emits a
Grayscale Softcopy Presentation State, which carries vertebral levels as text
plus a leader line and conveys a per-vertebra quality flag through colour.
This module carries the same information as pixels: one segment per vertebra,
each with a coded anatomical concept and, optionally, its own recommended
display colour.

Why highdicom, and what it cannot do
------------------------------------
Measured against highdicom 0.28.1 on 2026-07-30, not assumed:

  - highdicom CAN write a Grayscale Softcopy Presentation State. The class is
    `highdicom.pr.GrayscaleSoftcopyPresentationState` and SOP class
    1.2.840.10008.5.1.4.1.1.11.1 is in `highdicom.pr.SOP_CLASS_UIDS`. So the
    blanket claim "highdicom cannot write GSPS" is FALSE and must not be made.
  - What highdicom cannot do is per-annotation colour inside a GSPS. The strings
    `TextStyleSequence`, `LineStyleSequence`, `TextColorCIELabValue` and
    `LineColorCIELabValue` do not occur anywhere in the installed package. Its
    only colour route is `GraphicLayer(display_color=...)`, which writes
    (0070,0401) Graphic Layer Recommended Display CIELab Value. That is one of
    the three routes `writer.py` exercises, so two of the three arms of the GSPS
    colour experiment are not expressible with highdicom.
  - For SEG, highdicom is the right tool and is used here directly.

Coded concepts, never invented
------------------------------
Every SNOMED CT code below is read at import time out of pydicom's copy of the
DICOM PS3.16 concept tables (`pydicom.sr.codedict.codes.SCT`). None is typed in
by hand, so none can be fabricated. C1-C7, T1-T12, L1-L5, Sacrum and Coccyx all
resolve and all are members of CID 7151 Segmentation Property Type and CID 7603
Vertebra. Two VerSe levels have NO code in those tables, L6 and T13, and they
therefore fall back to the private coding scheme designator "99SPINELAB". Run
`python -m spinelab.gsps.seg_writer --codes` to print the table and the misses.

Segmentation type
-----------------
BINARY. The labels are a hard argmax: mutually exclusive integer levels from a
mask, with no per-voxel occupancy or probability behind them. FRACTIONAL would
assert a partial-occupancy or probability value that does not exist, and the
confidence signal this project actually has is one number per vertebra, not per
voxel, so it belongs in a segment level attribute rather than in the pixels.
BINARY is also the variant viewers have supported longest, which matters for a
rendering-support comparison. LABELMAP exists in highdicom 0.28.1 but is a
recent addition to the standard and would confound the viewer measurement.
"""
from __future__ import annotations

import argparse
import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import pydicom
from pydicom.dataset import Dataset
from pydicom.sr.codedict import codes
from pydicom.sr.coding import Code

import highdicom as hd

from .writer import RED, YELLOW, cielab

SEG_SOP_CLASS = "1.2.840.10008.5.1.4.1.1.66.4"

# Private coding scheme designator. PS3.3 C.12.1.1.1 requires locally defined
# schemes to start with "99". Used only where PS3.16 has no code.
LOCAL_SCHEME = "99SPINELAB"

# VerSe mask label values ARE the anatomical level. See CLAUDE.md.
VERSE_LEVELS: dict[int, str] = {}
for _i in range(1, 8):
    VERSE_LEVELS[_i] = "C%d" % _i
for _i in range(1, 13):
    VERSE_LEVELS[7 + _i] = "T%d" % _i
for _i in range(1, 7):
    VERSE_LEVELS[19 + _i] = "L%d" % _i
VERSE_LEVELS[26] = "Sacrum"
VERSE_LEVELS[27] = "Coccyx"
VERSE_LEVELS[28] = "T13"

# Which pydicom SCT keyword to look up for each level name.
_SCT_KEYWORD = {"Sacrum": "Sacrum", "Coccyx": "Coccyx"}
for _n in list(VERSE_LEVELS.values()):
    if _n not in _SCT_KEYWORD:
        _SCT_KEYWORD[_n] = "%sVertebra" % _n

CATEGORY_ANATOMY = codes.SCT.AnatomicalStructure   # CID 7150, SCT 91723000


def level_code(name: str) -> tuple[Code, bool]:
    """Coded concept for a vertebral level name.

    Returns (code, is_snomed). Looks the code up in pydicom's copy of the DICOM
    PS3.16 tables. Falls back to LOCAL_SCHEME when PS3.16 has no code, which is
    the case for L6 and T13. Nothing here hardcodes a SNOMED code value.
    """
    kw = _SCT_KEYWORD.get(name)
    if kw is not None:
        try:
            c = getattr(codes.SCT, kw)
            return Code(c.value, c.scheme_designator, c.meaning), True
        except AttributeError:
            pass
    return Code(name.upper(), LOCAL_SCHEME, "%s vertebra (no PS3.16 code)" % name), False


def code_table() -> list[tuple[int, str, str, str, str, bool]]:
    """(label, name, code value, scheme, meaning, is_snomed) for every VerSe level."""
    out = []
    for lab in sorted(VERSE_LEVELS):
        name = VERSE_LEVELS[lab]
        c, is_sct = level_code(name)
        out.append((lab, name, c.value, c.scheme_designator, c.meaning, is_sct))
    return out


# --------------------------------------------------------------------------
# variants: the colour axis, analogous to writer.COLOUR_ROUTES
# --------------------------------------------------------------------------
# SEG has exactly one place to put a colour: (0062,000D) Recommended Display
# CIELab Value, Type 3 inside each item of (0062,0002) Segment Sequence. There
# is no text-colour versus line-colour choice as there is in GSPS, so the axis
# here is what the colour MEANS, not where it lives.
SEG_COLOUR_ROUTES = ("none", "flag", "uniform")

# Identical L*a*b* to writer.YELLOW and writer.RED so the GSPS and SEG arms of
# the viewer experiment show the same two colours. Cross-checked in _self_check.
LAB_NORMAL = (74.9, 23.9, 78.9)
LAB_FLAGGED = (81.2, 118.1, 72.1)


@dataclass
class SegVariant:
    colour_route: str = "flag"
    segmentation_type: str = "BINARY"
    label: str = field(default="")

    def __post_init__(self):
        if self.colour_route not in SEG_COLOUR_ROUTES:
            raise ValueError("colour_route must be one of %r" % (SEG_COLOUR_ROUTES,))
        if self.segmentation_type not in ("BINARY", "FRACTIONAL"):
            raise ValueError("segmentation_type must be BINARY or FRACTIONAL")
        if not self.label:
            self.label = "seg_colour-%s_%s" % (
                self.colour_route, self.segmentation_type.lower())


DESIGN_SEG_COLOUR = [
    SegVariant("none", "BINARY", "seg_colour_none"),
    SegVariant("uniform", "BINARY", "seg_colour_uniform"),
    SegVariant("flag", "BINARY", "seg_colour_flag"),
]


def _display_colour(name: str, route: str, flagged: set[str]):
    if route == "none":
        return None
    if route == "uniform":
        lab = LAB_NORMAL
    else:
        lab = LAB_FLAGGED if name in flagged else LAB_NORMAL
    return hd.color.CIELabColor(*lab)


IDENTITY = {
    "manufacturer": "spinelab",
    "manufacturer_model_name": "spinelab-seg",
    "software_versions": "0.1.0",
    "device_serial_number": "0",
}

# PN is caret delimited. A bare single component is the retired form and both
# highdicom and dciodvfy flag it, which is exactly the warning the 38 shipped
# GSPS objects carry. A trailing caret disambiguates a deliberate one component
# name, so we use it everywhere we write a PN.
CREATOR_PN = "spinelab^"


# --------------------------------------------------------------------------
# geometry
# --------------------------------------------------------------------------
def sort_series(datasets: Sequence[Dataset]) -> list[Dataset]:
    """Sort image datasets along their own slice normal, most negative first."""
    if not datasets:
        raise ValueError("empty series")
    iop = np.asarray(datasets[0].ImageOrientationPatient, dtype=float)
    normal = np.cross(iop[:3], iop[3:])
    def key(ds):
        return float(np.dot(np.asarray(ds.ImagePositionPatient, dtype=float), normal))
    return sorted(datasets, key=key)


def read_series(dicom_dir: Path, modality_sop: str | None = None) -> list[Dataset]:
    """Read every image instance in a directory, sorted. Skips non-image SOP classes."""
    out = []
    for p in sorted(Path(dicom_dir).glob("*.dcm")):
        ds = pydicom.dcmread(str(p))
        if "ImagePositionPatient" not in ds or "ImageOrientationPatient" not in ds:
            continue          # presentation states and the like
        if modality_sop and str(ds.SOPClassUID) != modality_sop:
            continue
        out.append(ds)
    if not out:
        raise FileNotFoundError("no image instances with a position in %s" % dicom_dir)
    return sort_series(out)


def _lps_affine(nifti_affine: np.ndarray) -> np.ndarray:
    """nibabel affines are RAS. DICOM patient coordinates are LPS."""
    flip = np.diag([-1.0, -1.0, 1.0, 1.0])
    return flip @ np.asarray(nifti_affine, dtype=float)


def resample_labels_to_series(mask: np.ndarray, mask_affine_ras: np.ndarray,
                             series: Sequence[Dataset]) -> np.ndarray:
    """Nearest neighbour sample a label volume onto a sorted DICOM series grid.

    Returns (n_frames, rows, cols) with the same integer label values as `mask`.
    Voxels that fall outside the label volume become 0. When the two grids are
    identical this is exact, because nearest neighbour of an integer index is
    that index.
    """
    inv = np.linalg.inv(_lps_affine(mask_affine_ras))
    rows = int(series[0].Rows)
    cols = int(series[0].Columns)
    row_sp, col_sp = (float(x) for x in series[0].PixelSpacing)
    iop = np.asarray(series[0].ImageOrientationPatient, dtype=float)
    col_dir, row_dir = iop[:3], iop[3:]

    rr, cc = np.meshgrid(np.arange(rows), np.arange(cols), indexing="ij")
    # patient offset of each pixel relative to that frame's ImagePositionPatient
    offs = (cc[..., None] * col_sp * col_dir + rr[..., None] * row_sp * row_dir)

    shape = np.asarray(mask.shape)
    out = np.zeros((len(series), rows, cols), dtype=mask.dtype)
    for f, ds in enumerate(series):
        # Frame 0 supplies the in-plane geometry for every frame, so verify that
        # assumption instead of trusting it.
        if (int(ds.Rows), int(ds.Columns)) != (rows, cols):
            raise ValueError("instance %d is %dx%d but frame 0 is %dx%d"
                             % (f, ds.Rows, ds.Columns, rows, cols))
        if not np.allclose([float(x) for x in ds.PixelSpacing], [row_sp, col_sp]):
            raise ValueError("instance %d has PixelSpacing %s, frame 0 has %s"
                             % (f, list(ds.PixelSpacing), [row_sp, col_sp]))
        if not np.allclose(np.asarray(ds.ImageOrientationPatient, dtype=float), iop,
                           atol=1e-6):
            raise ValueError("instance %d has a different ImageOrientationPatient"
                             " from frame 0, the series is not a single plane stack" % f)
        ipp = np.asarray(ds.ImagePositionPatient, dtype=float)
        pts = offs + ipp                                  # (rows, cols, 3) LPS mm
        idx = pts @ inv[:3, :3].T + inv[:3, 3]            # (rows, cols, 3) voxel
        idx = np.rint(idx).astype(np.int64)
        ok = np.all((idx >= 0) & (idx < shape), axis=-1)
        sel = idx[ok]
        out[f][ok] = mask[sel[:, 0], sel[:, 1], sel[:, 2]]
    return out


# --------------------------------------------------------------------------
# the writer
# --------------------------------------------------------------------------
def segment_descriptions(present: Sequence[int], variant: SegVariant,
                        flagged: Iterable[str] = ()) -> tuple[list, dict[int, int]]:
    """One SegmentDescription per present VerSe label value.

    Returns (descriptions, {verse_label: segment_number}). Segment numbers are
    consecutive from 1, which is what the SEG IOD requires.
    """
    flagged = {str(f).strip() for f in flagged if str(f).strip()}
    unknown = sorted(set(flagged) - set(VERSE_LEVELS.values()))
    if unknown:
        raise ValueError("flagged names are not vertebral levels: %r" % unknown)

    algo = hd.AlgorithmIdentificationSequence(
        name="spinelab-verse-mask-import",
        version=IDENTITY["software_versions"],
        family=codes.DCM.ArtificialIntelligence,
    )
    descs, mapping = [], {}
    for n, lab in enumerate(sorted(present), start=1):
        name = VERSE_LEVELS[lab]
        code, _ = level_code(name)
        descs.append(hd.seg.SegmentDescription(
            segment_number=n,
            segment_label=name,
            segmented_property_category=CATEGORY_ANATOMY,
            segmented_property_type=code,
            algorithm_type=hd.seg.SegmentAlgorithmTypeValues.AUTOMATIC,
            algorithm_identification=algo,
            tracking_id="spinelab-%s" % name,
            tracking_uid=hd.UID(),
            display_color=_display_colour(name, variant.colour_route, flagged),
        ))
        mapping[lab] = n
    return descs, mapping


def build_segmentation(series: Sequence[Dataset], label_frames: np.ndarray,
                      variant: SegVariant | None = None,
                      flagged: Iterable[str] = (),
                      series_number: int = 9002,
                      instance_number: int = 1,
                      content_label: str = "SPINE_SEG",
                      content_description: str | None = None) -> hd.seg.Segmentation:
    """Build a Segmentation from a sorted series and a (frames, rows, cols) label array.

    `label_frames` carries VerSe label values. They are remapped to consecutive
    segment numbers here; the original level is preserved in SegmentLabel and in
    the coded concept, not in the pixel value.
    """
    variant = variant or SegVariant()
    if label_frames.shape[0] != len(series):
        raise ValueError("label_frames has %d frames but the series has %d instances"
                         % (label_frames.shape[0], len(series)))
    present = sorted(int(v) for v in np.unique(label_frames) if v)
    bad = [v for v in present if v not in VERSE_LEVELS]
    if bad:
        raise ValueError("label values with no VerSe level meaning: %r" % bad)
    if not present:
        raise ValueError("label volume is empty on this series grid")

    descs, mapping = segment_descriptions(present, variant, flagged)
    remap = np.zeros(max(present) + 1, dtype=np.uint8)
    for lab, n in mapping.items():
        remap[lab] = n
    pixels = remap[label_frames.astype(np.int64)]

    if content_description is None:
        content_description = "Vertebral level segmentation, variant %s" % variant.label

    seg = hd.seg.Segmentation(
        source_images=list(series),
        pixel_array=pixels,
        segmentation_type=variant.segmentation_type,
        segment_descriptions=descs,
        series_instance_uid=hd.UID(),
        series_number=series_number,
        sop_instance_uid=hd.UID(),
        instance_number=instance_number,
        manufacturer=IDENTITY["manufacturer"],
        manufacturer_model_name=IDENTITY["manufacturer_model_name"],
        software_versions=IDENTITY["software_versions"],
        device_serial_number=IDENTITY["device_serial_number"],
        content_label=content_label,
        content_description=content_description,
        content_creator_name=CREATOR_PN,
        omit_empty_frames=True,
    )
    if str(seg.SOPClassUID) != SEG_SOP_CLASS:
        raise RuntimeError("highdicom wrote SOP class %s, expected %s"
                           % (seg.SOPClassUID, SEG_SOP_CLASS))
    _declare_local_scheme(seg, descs)
    return seg


def _declare_local_scheme(seg: Dataset, descs) -> None:
    """Add a Coding Scheme Identification item if any segment used LOCAL_SCHEME.

    PS3.3 C.12.1.1.1: when a private coding scheme is used, the object should
    identify it. highdicom does not do this for us.
    """
    used = any(str(getattr(d.SegmentedPropertyTypeCodeSequence[0],
                           "CodingSchemeDesignator", "")) == LOCAL_SCHEME
               for d in descs)
    if not used:
        return
    item = Dataset()
    item.CodingSchemeDesignator = LOCAL_SCHEME
    item.CodingSchemeName = "spinelab local vertebral levels"
    item.CodingSchemeResponsibleOrganization = (
        "spinelab. Used only for levels with no code in DICOM PS3.16.")
    seg.CodingSchemeIdentificationSequence = [item]


def seg_from_nifti(mask_nifti: Path, dicom_dir: Path, out_path: Path,
                  variant: SegVariant | None = None,
                  flagged: Iterable[str] = ()) -> tuple[Path, dict]:
    """Convert a NIfTI label volume plus a DICOM series into one SEG file."""
    import nibabel as nib

    series = read_series(Path(dicom_dir))
    img = nib.load(str(mask_nifti))
    mask = np.asanyarray(img.dataobj).astype(np.int16)
    frames = resample_labels_to_series(mask, img.affine, series)

    seg = build_segmentation(series, frames, variant=variant, flagged=flagged)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    seg.save_as(str(out_path), enforce_file_format=True)

    src_labels = sorted(int(v) for v in np.unique(mask) if v)
    got_labels = sorted(int(v) for v in np.unique(frames) if v)
    stats = {
        "mask": str(mask_nifti),
        "series": str(dicom_dir),
        "n_source_instances": len(series),
        "rows": int(series[0].Rows), "columns": int(series[0].Columns),
        "labels_in_nifti": src_labels,
        "labels_on_series_grid": got_labels,
        "levels": [VERSE_LEVELS[v] for v in got_labels],
        "n_segments": len(got_labels),
        "n_frames_written": int(getattr(seg, "NumberOfFrames", 0)),
        "sop_class_uid": str(seg.SOPClassUID),
        "sop_instance_uid": str(seg.SOPInstanceUID),
        "voxels_in_nifti": int((mask > 0).sum()),
        "voxels_on_series_grid": int((frames > 0).sum()),
        "bytes": out_path.stat().st_size,
        "variant": (variant or SegVariant()).label,
        "flagged": sorted(flagged),
    }
    return out_path, stats


# --------------------------------------------------------------------------
# SUPERSEDED: a DICOM series to reference, built from the VerSe CT itself
# --------------------------------------------------------------------------
# Use `spinelab.io.nifti_to_dicom` instead. It is the canonical converter, it
# handles LAS and oblique affines and anisotropic in plane spacing, and its
# instances score zero dciodvfy errors where these score one (the unevaluable
# Laterality conditional).
#
# This is kept only so `seg_writer` can be exercised without a second module, for
# example in a test that needs a throwaway series. It writes a minimal but
# geometrically faithful CT series from a VerSe CT volume.
def _fmt_ds(x: float) -> str:
    """Format a float as a DS string of at most 16 characters.

    pydicom will happily write repr(float) into a DS, which for a value like
    0.29101601243019104 is 19 characters. dciodvfy reports that as an invalid
    value length, and it is: PS3.5 caps DS at 16 bytes.
    """
    v = float(x)
    for prec in range(12, 0, -1):
        s = "%.*g" % (prec, v)
        if len(s) <= 16:
            return s
    return "0"


def _plane_term(col_dir: np.ndarray, row_dir: np.ndarray) -> str:
    """ImageType value 3 for the CT Image module, from the slice normal.

    PS3.3 C.8.2.1.1.1 lists AXIAL and LOCALIZER as Defined Terms, which are
    extensible, and has no term for a reformatted plane. We report the plane we
    actually wrote rather than claiming AXIAL for a sagittal stack.
    """
    n = np.abs(np.cross(col_dir, row_dir))
    return ("SAGITTAL", "CORONAL", "AXIAL")[int(np.argmax(n))]


def nifti_to_ct_series(ct_nifti: Path, out_dir: Path, patient_id: str,
                      series_description: str = "VERSE CT",
                      study_uid: str | None = None) -> list[Path]:
    import nibabel as nib

    img = nib.load(str(ct_nifti))
    arr = np.asanyarray(img.dataobj)
    # Keep the native voxel axes. Frames run along nibabel axis 2, a frame's
    # columns along axis 0 and its rows along axis 1. Reorienting to LPS first
    # would turn a sagittal acquisition into a 1200 frame axial stack for no
    # gain, and the geometry is exact either way.
    aff = _lps_affine(img.affine)
    col_dir, row_dir, slc_dir = aff[:3, 0], aff[:3, 1], aff[:3, 2]
    gram = np.array([[float(np.dot(u, v)) for v in (col_dir, row_dir, slc_dir)]
                     for u in (col_dir, row_dir, slc_dir)])
    off_diag = np.abs(gram - np.diag(np.diag(gram))).max()
    if off_diag > 1e-3 * np.abs(np.diag(gram)).max():
        raise ValueError("affine is not orthogonal, max off diagonal %.4g" % off_diag)
    col_sp = float(np.linalg.norm(col_dir))
    row_sp = float(np.linalg.norm(row_dir))
    slc_sp = float(np.linalg.norm(slc_dir))
    unit_col, unit_row = col_dir / col_sp, row_dir / row_sp
    iop = [_fmt_ds(v) for v in np.concatenate([unit_col, unit_row])]
    plane = _plane_term(unit_col, unit_row)
    origin = aff[:3, 3]

    arr = np.clip(arr, -32768, 32767).astype(np.int16)
    n_cols, n_rows, n_frames = arr.shape

    study_uid = study_uid or hd.UID()
    series_uid = hd.UID()
    frame_uid = hd.UID()
    now = datetime.datetime.now()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for k in range(n_frames):
        fm = pydicom.dataset.FileMetaDataset()
        fm.MediaStorageSOPClassUID = pydicom.uid.CTImageStorage
        fm.MediaStorageSOPInstanceUID = hd.UID()
        fm.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
        fm.ImplementationClassUID = pydicom.uid.PYDICOM_IMPLEMENTATION_UID
        ds = pydicom.dataset.FileDataset("", {}, file_meta=fm, preamble=b"\0" * 128)
        ds.SpecificCharacterSet = "ISO_IR 100"
        ds.SOPClassUID = pydicom.uid.CTImageStorage
        ds.SOPInstanceUID = fm.MediaStorageSOPInstanceUID
        ds.PatientName = patient_id + "^"
        ds.PatientID = patient_id
        ds.PatientBirthDate = ""
        ds.PatientSex = ""
        ds.StudyInstanceUID = study_uid
        ds.StudyDate = now.strftime("%Y%m%d")
        ds.StudyTime = now.strftime("%H%M%S")
        ds.StudyID = "1"
        ds.AccessionNumber = ""
        ds.ReferringPhysicianName = ""
        ds.SeriesInstanceUID = series_uid
        ds.SeriesNumber = 1
        ds.SeriesDescription = series_description
        ds.Modality = "CT"
        ds.Manufacturer = IDENTITY["manufacturer"]
        ds.ManufacturerModelName = "verse-nifti-to-dicom"
        ds.SoftwareVersions = IDENTITY["software_versions"]
        ds.DeviceSerialNumber = IDENTITY["device_serial_number"]
        ds.FrameOfReferenceUID = frame_uid
        ds.PositionReferenceIndicator = ""
        ds.ImageType = ["DERIVED", "SECONDARY", plane]
        ds.InstanceNumber = k + 1
        ds.ContentDate = ds.StudyDate
        ds.ContentTime = ds.StudyTime
        ds.AcquisitionNumber = 1
        ds.KVP = ""
        ds.PatientPosition = "HFS"
        ds.ImageOrientationPatient = iop
        ds.ImagePositionPatient = [_fmt_ds(v) for v in (origin + k * slc_dir)]
        ds.PixelSpacing = [_fmt_ds(row_sp), _fmt_ds(col_sp)]
        ds.SliceThickness = _fmt_ds(slc_sp)
        ds.SamplesPerPixel = 1
        ds.PhotometricInterpretation = "MONOCHROME2"
        ds.Rows = n_rows
        ds.Columns = n_cols
        ds.BitsAllocated = 16
        ds.BitsStored = 16
        ds.HighBit = 15
        ds.PixelRepresentation = 1
        ds.RescaleIntercept = 0
        ds.RescaleSlope = 1
        ds.RescaleType = "HU"
        ds.WindowCenter = 300
        ds.WindowWidth = 1500
        # arr is indexed [col, row, frame]; a DICOM frame is (Rows, Columns).
        ds.PixelData = np.ascontiguousarray(arr[:, :, k].T).tobytes()
        p = out_dir / ("%04d.dcm" % (k + 1))
        pydicom.dcmwrite(str(p), ds, enforce_file_format=True)
        written.append(p)
    return written


# --------------------------------------------------------------------------
def _self_check() -> int:
    """Cross-check the CIELab encoding and print the code table."""
    bad = 0
    for name, lab in (("normal", LAB_NORMAL), ("flagged", LAB_FLAGGED)):
        hi = tuple(hd.color.CIELabColor(*lab).value)
        ours = tuple(cielab(*lab))
        ok = hi == ours
        bad += 0 if ok else 1
        print("  CIELab %-8s L*a*b*=%-22s highdicom=%s writer.cielab=%s %s"
              % (name, lab, hi, ours, "match" if ok else "MISMATCH"))
    ref = {"normal": tuple(YELLOW), "flagged": tuple(RED)}
    for name, lab in (("normal", LAB_NORMAL), ("flagged", LAB_FLAGGED)):
        if tuple(cielab(*lab)) != ref[name]:
            print("  WARNING %s does not equal writer's constant" % name)
            bad += 1
    print()
    print("  %-5s %-7s %-12s %-11s %s" % ("label", "level", "code", "scheme", "meaning"))
    n_sct = 0
    for lab, nm, val, scheme, meaning, is_sct in code_table():
        n_sct += int(is_sct)
        print("  %-5d %-7s %-12s %-11s %s" % (lab, nm, val, scheme, meaning))
    print("\n  %d of %d levels have a PS3.16 SNOMED CT code, %d use %s"
          % (n_sct, len(VERSE_LEVELS), len(VERSE_LEVELS) - n_sct, LOCAL_SCHEME))
    print("  category: (%s, %s, %r)" % (CATEGORY_ANATOMY.value,
                                        CATEGORY_ANATOMY.scheme_designator,
                                        CATEGORY_ANATOMY.meaning))
    return bad


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Write a DICOM SEG of vertebral levels")
    ap.add_argument("--codes", action="store_true",
                    help="print the coded concept table and the CIELab cross check, then exit")
    ap.add_argument("--mask", help="*_seg-vert_msk.nii.gz")
    ap.add_argument("--series", help="directory of DICOM image instances to reference")
    ap.add_argument("--out", help="output .dcm, or output directory when --design is given")
    ap.add_argument("--flag", default="", help="comma separated levels to colour as flagged")
    ap.add_argument("--colour", choices=SEG_COLOUR_ROUTES, default="flag")
    ap.add_argument("--design", action="store_true",
                    help="emit every colour route variant into --out as a directory")
    ap.add_argument("--make-series-from", metavar="CT_NIFTI",
                    help="stopgap: build a CT series from a NIfTI into --series first")
    ap.add_argument("--patient-id", default="VERSE_PUBLIC")
    a = ap.parse_args(argv)

    if a.codes:
        return 1 if _self_check() else 0
    if not (a.mask and a.series and a.out):
        ap.error("--mask, --series and --out are required unless --codes is given")

    if a.make_series_from:
        paths = nifti_to_ct_series(Path(a.make_series_from), Path(a.series), a.patient_id)
        print("wrote %d CT instances to %s" % (len(paths), a.series))

    flagged = [s for s in a.flag.split(",") if s.strip()]
    variants = DESIGN_SEG_COLOUR if a.design else [SegVariant(a.colour)]
    for v in variants:
        out = (Path(a.out) / ("%s.dcm" % v.label)) if a.design else Path(a.out)
        p, st = seg_from_nifti(Path(a.mask), Path(a.series), out, v, flagged)
        print("%-22s %-38s %d segments, %d frames, %.1f MB"
              % (v.label, p.name, st["n_segments"], st["n_frames_written"],
                 st["bytes"] / 1e6))
        print("   levels: %s" % ", ".join(st["levels"]))
        print("   voxels nifti=%d on series grid=%d" %
              (st["voxels_in_nifti"], st["voxels_on_series_grid"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
