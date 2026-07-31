"""Convert a VerSe CT NIfTI volume into a conformant single frame DICOM CT series.

Why this exists. Every GSPS variant produced so far derives from aycan clinical
CT, so the artifact cannot be released. VerSe is CC BY-SA 4.0 and public, but it
ships as NIfTI while both the pipeline and the GSPS objects need DICOM. This
module closes that gap so every released artifact stands on public data.

The load bearing part is geometry, because a wrong axis mapping is silent: the
series still opens, the pixels still look like a spine, and every downstream
world coordinate is wrong. So the mapping is derived from the affine and nothing
is assumed to be axis aligned or isotropic.

Conventions used here, all from PS3.3 C.7.6.2.1.1:

    world_lps = IPP + i * PixelSpacing[1] * IOP[0:3]
                    + j * PixelSpacing[0] * IOP[3:6]

with i the column index and j the row index. IOP[0:3] is the direction of
increasing column index (the "first row" cosines) and IOP[3:6] the direction of
increasing row index. PixelSpacing is [row spacing, column spacing], that is
[step along IOP[3:6], step along IOP[0:3]]. Getting those two pairs crossed is
the classic silent failure and is why the round trip check below exists.

NIfTI affines are RAS+, DICOM patient coordinates are LPS, so the affine is
premultiplied by diag(-1, -1, 1, 1) once, up front.

Axis choice. The through plane axis defaults to the coarsest spacing, which is
the acquisition's own slice axis for every VerSe case (1.25 mm against 0.3 mm in
plane for the gl series, 3.0 mm against 0.38 mm for the one sagittal case). Ties
fall back to the axis most nearly parallel to the patient superior-inferior axis,
which yields axial slices for a truly isotropic volume. The two in plane axes are
then assigned so that the resulting image follows the usual radiological display
convention: increasing column index runs toward patient Left, or Posterior for a
sagittal plane, and increasing row index runs Posterior, or Inferior when the in
plane axis is the superior-inferior one. Slices advance along
cross(IOP[0:3], IOP[3:6]), so SpacingBetweenSlices is positive and the implied
direction matrix is right handed.

Verify, do not trust. `roundtrip` reads the written series back with a separate
code path, recovers the affine from the DICOM attributes alone, derives the index
permutation between that and the source NIfTI, and reports the worst world
coordinate disagreement in mm over the volume corners together with an exact voxel
value comparison. `crosscheck_simpleitk` runs the same comparison through
SimpleITK and GDCM, because a converter that only agrees with its own reader has
proved nothing. Measured numbers are in `results/public_dicom.md`.

Usage:
    python -m spinelab.io.nifti_to_dicom <case_ct.nii.gz> --out <dir> --roundtrip
    python -m spinelab.io.nifti_to_dicom --demo --out <dir> --roundtrip --simpleitk
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import nibabel as nib
import numpy as np
import pydicom
from pydicom.dataset import FileDataset, FileMetaDataset, validate_file_meta
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from spinelab import paths

CT_SOP_CLASS = "1.2.840.10008.5.1.4.1.1.2"

# VerSe subset staged for this project. Three orientation groups seen so far,
# LPS, LAS and an oblique PSR sagittal group. The directory is still being
# populated, so do not hardcode a case count against it.
VERSE_DIR = paths.DATASETS / "verse_4skx2"

RAS_TO_LPS = np.diag([-1.0, -1.0, 1.0, 1.0])

# Synthetic identity. Nothing here may look like a real patient record.
INSTITUTION_NAME = "PUBLIC_VERSE_DATA"
INSTITUTIONAL_DEPARTMENT = "PUBLIC_VERSE_DATA"
MANUFACTURER = "spinelab"
MANUFACTURER_MODEL = "spinelab-nifti-to-dicom"
SOFTWARE_VERSION = "0.1.0"
PATIENT_NAME_FAMILY = "VERSE"
DEID_METHOD = "PUBLIC VERSE DATA, SYNTHETIC IDENTIFIERS ONLY"
SOURCE_ATTRIBUTION = "VerSe CC BY-SA 4.0, converted from NIfTI by spinelab"

# Two windows so a viewer has something sensible to open with. Type 3, no claim
# attached to either.
WINDOW_CENTER = (40.0, 400.0)
WINDOW_WIDTH = (400.0, 1800.0)
WINDOW_EXPLANATION = ("SOFT_TISSUE", "BONE")


# --------------------------------------------------------------------------
# small numeric helpers
# --------------------------------------------------------------------------
def _ds(x: float) -> str:
    """Format a float as a DS value, keeping the most precision that fits in 16 bytes.

    Written out explicitly rather than left to pydicom so that the precision the
    round trip measures is a property of this module, not of a library default.
    """
    x = float(x)
    s = repr(x)
    if len(s) <= 16:
        return s
    for prec in range(15, 4, -1):
        s = "%.*g" % (prec, x)
        if len(s) <= 16:
            return s
    raise ValueError("cannot represent %r as DS" % x)


def _dsv(vec) -> list[str]:
    return [_ds(v) for v in vec]


def _unit(v: np.ndarray) -> tuple[np.ndarray, float]:
    n = float(np.linalg.norm(v))
    if n == 0.0:
        raise ValueError("degenerate affine, zero length axis vector")
    return v / n, n


def _signed_permutation(m3: np.ndarray, tol: float = 1e-6):
    """If m3 is a signed permutation matrix return (axis per column, sign per column).

    Column d of m3 says which source axis DICOM axis d maps onto, and with which
    sign. Returns None when m3 is anything else, which is the signal that the two
    geometries are not related by a pure permutation and flip.
    """
    axes: list[int] = []
    signs: list[int] = []
    for d in range(3):
        col = m3[:, d]
        big = np.flatnonzero(np.abs(np.abs(col) - 1.0) < tol)
        small = np.flatnonzero(np.abs(col) > tol)
        if len(big) != 1 or len(small) != 1 or big[0] != small[0]:
            return None
        axes.append(int(big[0]))
        signs.append(int(np.sign(col[big[0]])))
    if sorted(axes) != [0, 1, 2]:
        return None
    return axes, signs


# --------------------------------------------------------------------------
# geometry
# --------------------------------------------------------------------------
@dataclass
class SeriesGeometry:
    """Everything needed to write, or to re-derive, the series geometry."""

    row_cosines: np.ndarray      # IOP[0:3], direction of increasing column index
    col_cosines: np.ndarray      # IOP[3:6], direction of increasing row index
    slice_normal: np.ndarray     # direction of increasing instance number
    row_spacing: float           # PixelSpacing[0], step along col_cosines
    col_spacing: float           # PixelSpacing[1], step along row_cosines
    slice_spacing: float         # SpacingBetweenSlices, positive by construction
    origin: np.ndarray           # LPS of voxel (col 0, row 0, slice 0)
    n_rows: int
    n_cols: int
    n_slices: int
    # provenance: which NIfTI axis became which DICOM axis, and which were flipped
    nifti_axis_for: tuple = (0, 0, 0)   # (col axis, row axis, slice axis)
    flipped: tuple = (False, False, False)
    source_axcodes: str = ""
    plane: str = ""
    in_plane_skew: float = 0.0          # |cos| between the two in plane axes
    slice_obliquity_deg: float = 0.0    # angle between slice axis and plane normal

    @property
    def iop(self) -> np.ndarray:
        return np.concatenate([self.row_cosines, self.col_cosines])

    def affine_lps(self) -> np.ndarray:
        """Map DICOM index (i col, j row, k slice) to LPS millimetres."""
        a = np.eye(4)
        a[:3, 0] = self.row_cosines * self.col_spacing
        a[:3, 1] = self.col_cosines * self.row_spacing
        a[:3, 2] = self.slice_normal * self.slice_spacing
        a[:3, 3] = self.origin
        return a

    def ipp(self, k: int) -> np.ndarray:
        return self.origin + k * self.slice_spacing * self.slice_normal


def _display_target(dominant: int) -> np.ndarray:
    """Preferred LPS direction for an in plane axis whose dominant axis is `dominant`.

    Radiological convention: columns run to patient Left, rows run Posterior, and
    a superior-inferior in plane axis runs down the image, that is Inferior.
    """
    if dominant == 0:
        return np.array([1.0, 0.0, 0.0])     # Left
    if dominant == 1:
        return np.array([0.0, 1.0, 0.0])     # Posterior
    return np.array([0.0, 0.0, -1.0])        # Inferior


def _plane_name(normal: np.ndarray) -> str:
    return {0: "SAGITTAL", 1: "CORONAL", 2: "AXIAL"}[int(np.argmax(np.abs(normal)))]


def plan_geometry(affine_ras: np.ndarray, shape, slice_axis: int | None = None,
                  axcodes: str = "") -> SeriesGeometry:
    """Derive the DICOM series geometry from a NIfTI RAS+ affine.

    No assumption of axis alignment or isotropy. The only choices made are which
    axis becomes the slice axis and the display sign convention, both documented
    in the module docstring and both recorded on the returned object.
    """
    a_lps = RAS_TO_LPS @ np.asarray(affine_ras, dtype=np.float64)
    steps = [a_lps[:3, k] for k in range(3)]
    dirs, spacings = [], []
    for s in steps:
        d, n = _unit(s)
        dirs.append(d)
        spacings.append(n)

    if slice_axis is None:
        order = sorted(range(3), key=lambda k: -spacings[k])
        s_ax = order[0]
        # Effectively isotropic: no coarse axis to prefer, so choose the axial plane.
        if spacings[order[1]] > 0.999 * spacings[s_ax]:
            s_ax = max(range(3), key=lambda k: abs(dirs[k][2]))
    else:
        s_ax = int(slice_axis)
        if s_ax not in (0, 1, 2):
            raise ValueError("slice_axis must be 0, 1 or 2")

    rest = [k for k in range(3) if k != s_ax]
    dom = {k: int(np.argmax(np.abs(dirs[k]))) for k in rest}
    a, b = rest
    if dom[a] == 2 and dom[b] != 2:
        in_row, down_col = b, a          # a is the S/I axis so it runs down the image
    elif dom[b] == 2 and dom[a] != 2:
        in_row, down_col = a, b
    elif dom[a] == 0:
        in_row, down_col = a, b
    elif dom[b] == 0:
        in_row, down_col = b, a
    else:
        in_row, down_col = a, b

    # DICOM's Image Orientation Patient carries two direction cosines that every
    # reader treats as orthogonal, so an in plane shear is not representable and
    # must be refused rather than silently squared off. Obliquity of the slice
    # axis relative to the plane IS representable, because each slice carries its
    # own Image Position Patient, so it is allowed.
    in_plane_skew = abs(float(dirs[in_row] @ dirs[down_col]))
    if in_plane_skew > 1e-4:
        raise ValueError(
            "in plane axes are not orthogonal, |cos| = %.3e. DICOM Image "
            "Orientation Patient cannot represent this." % in_plane_skew)

    sign_in_row = 1 if float(dirs[in_row] @ _display_target(dom[in_row])) >= 0 else -1
    sign_down_col = 1 if float(dirs[down_col] @ _display_target(dom[down_col])) >= 0 else -1

    row_cos = sign_in_row * dirs[in_row]
    col_cos = sign_down_col * dirs[down_col]
    normal = np.cross(row_cos, col_cos)
    normal, _ = _unit(normal)
    sign_slice = 1 if float(dirs[s_ax] @ normal) >= 0 else -1
    slice_dir = sign_slice * dirs[s_ax]

    flips = {in_row: sign_in_row < 0, down_col: sign_down_col < 0, s_ax: sign_slice < 0}
    idx0 = np.zeros(4)
    idx0[3] = 1.0
    for ax in range(3):
        if flips[ax]:
            idx0[ax] = shape[ax] - 1
    origin = (a_lps @ idx0)[:3]

    return SeriesGeometry(
        row_cosines=row_cos,
        col_cosines=col_cos,
        slice_normal=slice_dir,
        row_spacing=spacings[down_col],
        col_spacing=spacings[in_row],
        slice_spacing=spacings[s_ax],
        origin=origin,
        n_rows=int(shape[down_col]),
        n_cols=int(shape[in_row]),
        n_slices=int(shape[s_ax]),
        nifti_axis_for=(in_row, down_col, s_ax),
        flipped=(flips[in_row], flips[down_col], flips[s_ax]),
        source_axcodes=axcodes,
        plane=_plane_name(normal),
        in_plane_skew=in_plane_skew,
        slice_obliquity_deg=float(np.degrees(np.arccos(
            min(1.0, max(-1.0, float(slice_dir @ normal)))))),
    )


def reorder_volume(data: np.ndarray, geom: SeriesGeometry) -> np.ndarray:
    """Return the volume as (slice, row, col) following `geom`."""
    in_row, down_col, s_ax = geom.nifti_axis_for
    vol = np.transpose(data, (s_ax, down_col, in_row))
    f_in_row, f_down_col, f_slice = geom.flipped
    slicer = [slice(None)] * 3
    if f_slice:
        slicer[0] = slice(None, None, -1)
    if f_down_col:
        slicer[1] = slice(None, None, -1)
    if f_in_row:
        slicer[2] = slice(None, None, -1)
    return vol[tuple(slicer)]


# --------------------------------------------------------------------------
# pixel scaling
# --------------------------------------------------------------------------
@dataclass
class Rescale:
    slope: float
    intercept: float
    bits_stored: int
    pixel_representation: int
    dtype: np.dtype = field(default_factory=lambda: np.dtype(np.uint16))

    def encode(self, hu: np.ndarray) -> np.ndarray:
        stored = np.rint((hu - self.intercept) / self.slope)
        lo, hi = self._limits()
        if stored.min() < lo or stored.max() > hi:
            raise ValueError(
                "stored values %g..%g outside the %d bit range %d..%d"
                % (stored.min(), stored.max(), self.bits_stored, lo, hi))
        return stored.astype(self.dtype)

    def _limits(self) -> tuple[int, int]:
        if self.pixel_representation == 0:
            return 0, (1 << self.bits_stored) - 1
        return -(1 << (self.bits_stored - 1)), (1 << (self.bits_stored - 1)) - 1

    def decode(self, stored: np.ndarray) -> np.ndarray:
        return stored.astype(np.float64) * self.slope + self.intercept


def plan_rescale(hu: np.ndarray, signed: bool = False) -> Rescale:
    """Choose RescaleSlope, RescaleIntercept, BitsStored and PixelRepresentation.

    VerSe stores integer Hounsfield units, so slope 1 with an integer intercept is
    exact and no quantisation is introduced. The intercept is the conventional
    -1024 unless the volume goes below it, which happens: several cases carry
    -3024 padding, and one carries a metal artifact peak of +10110.
    """
    lo = float(np.min(hu))
    hi = float(np.max(hu))
    integral = bool(np.all(hu == np.rint(hu)))
    slope = 1.0
    if not integral:
        raise ValueError(
            "non integral Hounsfield values %g..%g, a slope other than 1 would be "
            "needed and this converter does not quantise silently" % (lo, hi))
    if signed:
        rs = Rescale(slope, 0.0, 16, 1, np.dtype(np.int16))
    else:
        intercept = min(-1024.0, float(np.floor(lo)))
        rs = Rescale(slope, intercept, 16, 0, np.dtype(np.uint16))
    slo, shi = rs._limits()
    need_lo = (lo - rs.intercept) / slope
    need_hi = (hi - rs.intercept) / slope
    if need_lo < slo or need_hi > shi:
        raise ValueError(
            "Hounsfield range %g..%g does not fit %d bit stored values with "
            "intercept %g" % (lo, hi, rs.bits_stored, rs.intercept))
    return rs


# --------------------------------------------------------------------------
# writing
# --------------------------------------------------------------------------
def _uid(*parts) -> str:
    """Deterministic UID, so a rerun of the same case produces the same series."""
    return generate_uid(entropy_srcs=["spinelab.io.nifti_to_dicom"] + [str(p) for p in parts])


def _subject_of(nifti_path: Path) -> str:
    name = nifti_path.name
    for suffix in ("_ct.nii.gz", "_ct.nii"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name


def _image_type(geom: SeriesGeometry, value3: str | None = None) -> list[str]:
    """ImageType for a CT instance.

    PS3.3 C.8.2.1.1.1 lists AXIAL and LOCALIZER as the Defined Terms for value 3
    of a CT image, and dciodvfy treats an absent value 3 as an error. Defined
    Terms are extensible (PS3.5 Section 6.1), so a non axial plane is labelled
    REFORMATTED, which dciodvfy reports as an unrecognised defined term. That
    warning is preferred over calling a sagittal image AXIAL, which would be a
    factual misstatement inside the object. Override with `value3` if a viewer
    under test refuses the extension.
    """
    if value3 is None:
        value3 = "AXIAL" if geom.plane == "AXIAL" else "REFORMATTED"
    return ["DERIVED", "SECONDARY", value3]


def build_instance(geom: SeriesGeometry, rs: Rescale, stored_slice: np.ndarray,
                   k: int, ids: dict, when: datetime.datetime) -> FileDataset:
    """One CT Image Storage instance for slice index k."""
    sop_instance = _uid(ids["series_key"], "instance", k)

    fm = FileMetaDataset()
    fm.MediaStorageSOPClassUID = CT_SOP_CLASS
    fm.MediaStorageSOPInstanceUID = sop_instance
    fm.TransferSyntaxUID = ExplicitVRLittleEndian
    fm.ImplementationClassUID = pydicom.uid.PYDICOM_IMPLEMENTATION_UID
    fm.ImplementationVersionName = "SPINELAB_0_1"

    ds = FileDataset("", {}, file_meta=fm, preamble=b"\0" * 128)
    ds.SpecificCharacterSet = "ISO_IR 100"

    # --- SOP Common -------------------------------------------------------
    ds.SOPClassUID = CT_SOP_CLASS
    ds.SOPInstanceUID = sop_instance
    ds.InstanceCreationDate = when.strftime("%Y%m%d")
    ds.InstanceCreationTime = when.strftime("%H%M%S")

    # --- Patient. Synthetic, and says so. ---------------------------------
    ds.PatientName = "%s^%s" % (PATIENT_NAME_FAMILY, ids["subject"].upper())
    ds.PatientID = ids["subject"]
    ds.PatientBirthDate = ""     # Type 2, unknown and not invented
    ds.PatientSex = ""           # Type 2, unknown and not invented
    ds.PatientIdentityRemoved = "YES"
    ds.DeidentificationMethod = DEID_METHOD

    # --- Study / Series ---------------------------------------------------
    ds.StudyInstanceUID = ids["study_uid"]
    ds.SeriesInstanceUID = ids["series_uid"]
    ds.StudyID = ids["study_id"]
    ds.AccessionNumber = ""      # Type 2, no order exists
    ds.ReferringPhysicianName = ""   # Type 2
    # Conversion timestamp, not an acquisition time. VerSe publishes no dates.
    ds.StudyDate = when.strftime("%Y%m%d")
    ds.StudyTime = when.strftime("%H%M%S")
    ds.SeriesDate = ds.StudyDate
    ds.SeriesTime = ds.StudyTime
    ds.ContentDate = ds.StudyDate
    ds.ContentTime = ds.StudyTime
    ds.Modality = "CT"
    ds.SeriesNumber = 1
    ds.StudyDescription = "VerSe public CT, converted from NIfTI"
    ds.SeriesDescription = "VerSe %s %s from NIfTI" % (ids["subject"], geom.plane.lower())
    ds.PatientPosition = ids["patient_position"]
    ds.BodyPartExamined = "SPINE"

    # --- Equipment --------------------------------------------------------
    ds.Manufacturer = MANUFACTURER
    ds.ManufacturerModelName = MANUFACTURER_MODEL
    ds.SoftwareVersions = SOFTWARE_VERSION
    ds.InstitutionName = INSTITUTION_NAME
    ds.InstitutionalDepartmentName = INSTITUTIONAL_DEPARTMENT

    # --- Frame of Reference ----------------------------------------------
    ds.FrameOfReferenceUID = ids["for_uid"]
    ds.PositionReferenceIndicator = ""   # Type 2, no reference landmark

    # --- General Image ----------------------------------------------------
    ds.InstanceNumber = k + 1
    ds.ImageType = _image_type(geom, ids.get("image_type_value3"))
    ds.DerivationDescription = SOURCE_ATTRIBUTION
    ds.ImageComments = "Source %s" % ids["source_name"]

    # --- Image Plane. The part that must be right. ------------------------
    ds.PixelSpacing = [_ds(geom.row_spacing), _ds(geom.col_spacing)]
    ds.ImageOrientationPatient = _dsv(geom.iop)
    ds.ImagePositionPatient = _dsv(geom.ipp(k))
    ds.SliceThickness = _ds(geom.slice_spacing)
    ds.SpacingBetweenSlices = _ds(geom.slice_spacing)
    ds.SliceLocation = _ds(float(geom.ipp(k) @ geom.slice_normal))

    # --- Image Pixel ------------------------------------------------------
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.Rows = geom.n_rows
    ds.Columns = geom.n_cols
    ds.BitsAllocated = 16
    ds.BitsStored = rs.bits_stored
    ds.HighBit = rs.bits_stored - 1
    ds.PixelRepresentation = rs.pixel_representation
    ds.PixelData = np.ascontiguousarray(stored_slice).tobytes()

    # --- CT Image ---------------------------------------------------------
    ds.RescaleIntercept = _ds(rs.intercept)
    ds.RescaleSlope = _ds(rs.slope)
    ds.RescaleType = "HU"
    ds.KVP = ""                 # Type 2, not published by VerSe
    ds.AcquisitionNumber = ""   # Type 2, not published by VerSe

    # --- VOI LUT, Type 3 --------------------------------------------------
    ds.WindowCenter = _dsv(WINDOW_CENTER)
    ds.WindowWidth = _dsv(WINDOW_WIDTH)
    ds.WindowCenterWidthExplanation = list(WINDOW_EXPLANATION)

    validate_file_meta(ds.file_meta, enforce_standard=True)
    return ds


def load_nifti(nifti_path: Path):
    """Return (hu volume as float32, RAS+ affine in mm, axcodes)."""
    img = nib.load(str(nifti_path))
    affine = np.asarray(img.affine, dtype=np.float64)
    unit = img.header.get_xyzt_units()[0]
    scale = {"meter": 1000.0, "mm": 1.0, "micron": 0.001}.get(unit, 1.0)
    if scale != 1.0:
        affine[:3, :] = affine[:3, :] * scale
    hu = img.get_fdata(dtype=np.float32)
    img.uncache()
    return hu, affine, "".join(nib.aff2axcodes(affine))


def write_series(nifti_path: Path, out_dir: Path, subject: str | None = None,
                 slice_axis: int | None = None, signed: bool = False,
                 patient_position: str = "HFS", max_slices: int | None = None,
                 study_id: str = "VERSE1", image_type_value3: str | None = None) -> dict:
    """Write one CT Image Storage instance per slice. Returns a provenance record."""
    nifti_path = Path(nifti_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    hu, affine, axcodes = load_nifti(nifti_path)
    geom = plan_geometry(affine, hu.shape, slice_axis=slice_axis, axcodes=axcodes)
    rs = plan_rescale(hu, signed=signed)
    vol = reorder_volume(hu, geom)

    subject = subject or _subject_of(nifti_path)
    series_key = "%s|%s" % (subject, geom.plane)
    ids = {
        "subject": subject,
        "source_name": nifti_path.name,
        "series_key": series_key,
        "study_uid": _uid(subject, "study"),
        "series_uid": _uid(series_key, "series"),
        "for_uid": _uid(series_key, "frame_of_reference"),
        "study_id": study_id,
        "patient_position": patient_position,
        "image_type_value3": image_type_value3,
    }
    when = datetime.datetime.now()

    n = geom.n_slices if max_slices is None else min(geom.n_slices, int(max_slices))
    written = []
    for k in range(n):
        stored = rs.encode(vol[k].astype(np.float64))
        ds = build_instance(geom, rs, stored, k, ids, when)
        p = out_dir / ("%s_%04d.dcm" % (subject, k + 1))
        pydicom.dcmwrite(str(p), ds, enforce_file_format=True)
        written.append(p)

    rec = {
        "source_nifti": str(nifti_path),
        "out_dir": str(out_dir),
        "subject": subject,
        "axcodes": axcodes,
        "plane": geom.plane,
        "image_type": _image_type(geom, image_type_value3),
        "n_instances": len(written),
        "n_slices_total": geom.n_slices,
        "rows": geom.n_rows,
        "columns": geom.n_cols,
        "pixel_spacing": [geom.row_spacing, geom.col_spacing],
        "spacing_between_slices": geom.slice_spacing,
        "image_orientation_patient": [float(v) for v in geom.iop],
        "image_position_patient_first": [float(v) for v in geom.ipp(0)],
        "nifti_axis_for_col_row_slice": list(geom.nifti_axis_for),
        "flipped_col_row_slice": [bool(f) for f in geom.flipped],
        "rescale_slope": rs.slope,
        "rescale_intercept": rs.intercept,
        "bits_stored": rs.bits_stored,
        "pixel_representation": rs.pixel_representation,
        "in_plane_skew_cos": geom.in_plane_skew,
        "slice_obliquity_deg": geom.slice_obliquity_deg,
        "hu_min": float(np.min(hu)),
        "hu_max": float(np.max(hu)),
        "study_instance_uid": ids["study_uid"],
        "series_instance_uid": ids["series_uid"],
        "frame_of_reference_uid": ids["for_uid"],
        "patient_position": patient_position,
    }
    (out_dir / "_conversion.json").write_text(json.dumps(rec, indent=2))
    return rec


# --------------------------------------------------------------------------
# reading back, deliberately independent of the writer
# --------------------------------------------------------------------------
def read_series(series_dir: Path) -> dict:
    """Reconstruct a volume and an affine from a DICOM CT series on disk.

    Uses only the DICOM attributes. Nothing is taken from the conversion record,
    which is what makes the round trip a check rather than a tautology.
    """
    series_dir = Path(series_dir)
    files = sorted(series_dir.glob("*.dcm"))
    if not files:
        raise FileNotFoundError("no *.dcm under %s" % series_dir)

    heads = []
    for f in files:
        ds = pydicom.dcmread(str(f), stop_before_pixels=True)
        if str(ds.SOPClassUID) != CT_SOP_CLASS:
            raise ValueError("%s is not CT Image Storage" % f.name)
        heads.append((f, ds))

    series_uids = {str(ds.SeriesInstanceUID) for _, ds in heads}
    if len(series_uids) != 1:
        raise ValueError("expected one series, found %d" % len(series_uids))

    ref = heads[0][1]
    iop = np.array([float(v) for v in ref.ImageOrientationPatient], dtype=np.float64)
    row_cos, col_cos = iop[:3], iop[3:]
    normal = np.cross(row_cos, col_cos)
    normal = normal / np.linalg.norm(normal)

    # geometry must agree across the series
    max_iop_dev = 0.0
    for _, ds in heads:
        v = np.array([float(x) for x in ds.ImageOrientationPatient], dtype=np.float64)
        max_iop_dev = max(max_iop_dev, float(np.max(np.abs(v - iop))))

    heads.sort(key=lambda fd: float(
        np.array([float(v) for v in fd[1].ImagePositionPatient]) @ normal))

    ipps = np.array([[float(v) for v in ds.ImagePositionPatient] for _, ds in heads])
    if len(heads) > 1:
        # Derive the step from the positions themselves rather than from the plane
        # normal, so a tilted or sheared stack is reconstructed as it was written
        # instead of being projected onto an assumed normal.
        step_vec = (ipps[-1] - ipps[0]) / (len(heads) - 1)
        fitted_ipp = ipps[0] + np.outer(np.arange(len(heads)), step_vec)
        max_ipp_dev = float(np.max(np.abs(ipps - fitted_ipp)))
        proj = ipps @ normal
        gaps = np.diff(proj)
        max_spacing_dev = float(np.max(np.abs(gaps - np.mean(gaps)))) if len(gaps) else 0.0
    else:
        step_vec = normal * float(getattr(ref, "SpacingBetweenSlices", ref.SliceThickness))
        max_spacing_dev = 0.0
        max_ipp_dev = 0.0
    step = float(np.linalg.norm(step_vec))

    ps = [float(v) for v in ref.PixelSpacing]
    rows, cols = int(ref.Rows), int(ref.Columns)
    vol = np.empty((len(heads), rows, cols), dtype=np.float64)
    for k, (f, _) in enumerate(heads):
        ds = pydicom.dcmread(str(f))
        vol[k] = ds.pixel_array.astype(np.float64) * float(ds.RescaleSlope) \
            + float(ds.RescaleIntercept)

    affine = np.eye(4)
    affine[:3, 0] = row_cos * ps[1]      # increasing column index
    affine[:3, 1] = col_cos * ps[0]      # increasing row index
    affine[:3, 2] = step_vec             # increasing slice index
    affine[:3, 3] = ipps[0]

    return {
        "volume": vol,                    # (slice, row, col), Hounsfield units
        "affine_lps": affine,             # (i col, j row, k slice) -> LPS mm
        "n_instances": len(heads),
        "pixel_spacing": ps,
        "step": step,
        "max_iop_deviation": max_iop_dev,
        "max_slice_spacing_deviation_mm": max_spacing_dev,
        "max_ipp_residual_mm": max_ipp_dev,
        "files": [str(f) for f, _ in heads],
    }


def compare_to_source(hu: np.ndarray, a_src: np.ndarray,
                      vol: np.ndarray, a_dcm: np.ndarray) -> dict:
    """Compare a reconstructed volume and affine against the source NIfTI.

    `a_src` maps NIfTI index to LPS, `a_dcm` maps reconstructed index
    (i col, j row, k slice) to LPS, and `vol` is indexed (slice, row, col).

    The permutation between the two index spaces is recovered from the two
    affines, so nothing is taken from the writer. Reported:

      max_world_error_mm   worst disagreement, over the eight volume corners,
                           between the LPS coordinate the reconstruction gives
                           for a voxel and the LPS coordinate the NIfTI affine
                           gives for the same voxel. Both maps are affine, so the
                           maximum over the volume is attained at a corner.
      max_index_residual_voxels
                           how far the recovered index mapping is from an exact
                           signed permutation, in voxels.
      voxels_mismatched    exact Hounsfield comparison over every voxel.
    """
    m = np.linalg.inv(a_src) @ a_dcm
    m_int = np.rint(m)
    max_index_residual = float(np.max(np.abs(m - m_int)))
    perm = _signed_permutation(m_int[:3, :3])
    if perm is None:
        raise ValueError("recovered mapping is not a signed permutation:\n%s" % m_int)
    axes, signs = perm

    n_slices = vol.shape[0]
    corners = np.array([[i, j, k, 1.0]
                        for i in (0, vol.shape[2] - 1)
                        for j in (0, vol.shape[1] - 1)
                        for k in (0, n_slices - 1)], dtype=np.float64).T
    world_dcm = (a_dcm @ corners)[:3]
    world_src = (a_src @ (m_int @ corners))[:3]
    err = np.linalg.norm(world_dcm - world_src, axis=0)

    # value comparison: transpose and flip the source into reconstruction index
    # order using only the recovered permutation
    t = np.transpose(hu, (axes[2], axes[1], axes[0]))    # (slice, row, col)
    slicer = [slice(None)] * 3
    for d in range(3):
        if signs[d] < 0:
            slicer[2 - d] = slice(None, None, -1)
    t = t[tuple(slicer)][:n_slices]
    same_shape = t.shape == vol.shape
    if same_shape:
        diff = np.abs(t.astype(np.float64) - vol)
        n_bad = int(np.count_nonzero(diff))
        max_value_error = float(np.max(diff))
    else:
        n_bad = -1
        max_value_error = float("nan")

    return {
        "n_instances": n_slices,
        "shape_reconstructed": list(vol.shape),
        "shape_source_permuted": list(t.shape),
        "shapes_match": bool(same_shape),
        "max_world_error_mm": float(np.max(err)),
        "mean_world_error_mm": float(np.mean(err)),
        "max_index_residual_voxels": max_index_residual,
        "voxels_compared": int(t.size) if same_shape else 0,
        "voxels_mismatched": n_bad,
        "max_value_error_hu": max_value_error,
        "recovered_axis_map_col_row_slice": axes,
        "recovered_signs_col_row_slice": signs,
    }


def roundtrip(nifti_path: Path, series_dir: Path) -> dict:
    """Read the written series back with this module's own reader and compare."""
    hu, affine, axcodes = load_nifti(Path(nifti_path))
    a_src = RAS_TO_LPS @ affine
    back = read_series(series_dir)
    out = compare_to_source(hu, a_src, back["volume"], back["affine_lps"])
    out.update({
        "reader": "spinelab.io.nifti_to_dicom.read_series",
        "source_nifti": str(nifti_path),
        "series_dir": str(series_dir),
        "axcodes": axcodes,
        "max_iop_deviation": back["max_iop_deviation"],
        "max_slice_spacing_deviation_mm": back["max_slice_spacing_deviation_mm"],
        "max_ipp_residual_mm": back["max_ipp_residual_mm"],
    })
    return out


def crosscheck_simpleitk(nifti_path: Path, series_dir: Path) -> dict:
    """Same comparison, but the series is read by SimpleITK and GDCM.

    A converter that only agrees with its own reader has proved nothing. This
    routes the same check through a third party DICOM stack, which is what any
    downstream consumer of these series will actually use.
    """
    import SimpleITK as sitk    # lazy: the module must import without SimpleITK

    reader = sitk.ImageSeriesReader()
    names = reader.GetGDCMSeriesFileNames(str(series_dir))
    if not names:
        raise FileNotFoundError("GDCM found no series under %s" % series_dir)
    reader.SetFileNames(names)
    img = reader.Execute()

    spacing = np.array(img.GetSpacing(), dtype=np.float64)          # (col, row, slice)
    direction = np.array(img.GetDirection(), dtype=np.float64).reshape(3, 3)
    a_dcm = np.eye(4)
    a_dcm[:3, :3] = direction * spacing        # columns scaled by their own spacing
    a_dcm[:3, 3] = np.array(img.GetOrigin(), dtype=np.float64)
    vol = sitk.GetArrayFromImage(img).astype(np.float64)            # (slice, row, col)

    hu, affine, axcodes = load_nifti(Path(nifti_path))
    a_src = RAS_TO_LPS @ affine
    out = compare_to_source(hu, a_src, vol, a_dcm)
    out.update({
        "reader": "SimpleITK %s ImageSeriesReader, GDCM" % sitk.Version_VersionString(),
        "source_nifti": str(nifti_path),
        "series_dir": str(series_dir),
        "axcodes": axcodes,
        "sitk_spacing_col_row_slice": [float(v) for v in spacing],
        "sitk_origin": [float(v) for v in img.GetOrigin()],
        "sitk_direction_det": float(np.linalg.det(direction)),
        "sitk_files": len(names),
    })
    return out


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
# Two cases with different orientation codes, plus the one oblique sagittal case.
DEMO_CASES = (
    "sub-gl003_dir-ax_ct.nii.gz",       # LPS, axial, 0.291 x 0.291 x 1.25 mm
    "sub-verse505_ct.nii.gz",           # LAS, axial, 0.977 x 0.977 x 0.9 mm
    "sub-verse525_dir-sag_ct.nii.gz",   # PSR, oblique sagittal, 0.381 x 0.381 x 3.0 mm
)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("nifti", nargs="*", help="VerSe *_ct.nii.gz files")
    ap.add_argument("--demo", action="store_true",
                    help="convert the three staged demo cases from %s" % VERSE_DIR)
    ap.add_argument("--out", required=True, help="output root, one subdirectory per case")
    ap.add_argument("--slice-axis", type=int, default=None, choices=(0, 1, 2))
    ap.add_argument("--signed", action="store_true",
                    help="PixelRepresentation 1 with intercept 0 instead of unsigned")
    ap.add_argument("--patient-position", default="HFS")
    ap.add_argument("--max-slices", type=int, default=None,
                    help="write only the first N instances, for fast validator loops")
    ap.add_argument("--image-type-value3", default=None,
                    help="override ImageType value 3, default AXIAL or REFORMATTED")
    ap.add_argument("--roundtrip", action="store_true", help="read back and compare")
    ap.add_argument("--simpleitk", action="store_true",
                    help="also read the series back with SimpleITK and GDCM")
    ap.add_argument("--json", dest="out_json", default=None)
    args = ap.parse_args(argv)

    targets = [Path(p) for p in args.nifti]
    if args.demo:
        targets += [VERSE_DIR / n for n in DEMO_CASES]
    if not targets:
        print("nothing to do, pass a NIfTI path or --demo")
        return 1

    out_root = Path(args.out)
    records = []
    for src in targets:
        if not src.exists():
            print("MISSING %s" % src)
            return 2
        subject = _subject_of(src)
        out_dir = out_root / subject
        print("=" * 78)
        print("%s -> %s" % (src.name, out_dir))
        rec = write_series(src, out_dir, subject=subject, slice_axis=args.slice_axis,
                           signed=args.signed, patient_position=args.patient_position,
                           max_slices=args.max_slices,
                           image_type_value3=args.image_type_value3)
        print("  %s axcodes, %s plane, %d instances of %dx%d, ImageType %s" % (
            rec["axcodes"], rec["plane"], rec["n_instances"],
            rec["rows"], rec["columns"], "\\".join(rec["image_type"])))
        print("  PixelSpacing %s  SpacingBetweenSlices %s  SliceThickness %s" % (
            rec["pixel_spacing"], rec["spacing_between_slices"],
            rec["spacing_between_slices"]))
        print("  IOP %s" % rec["image_orientation_patient"])
        print("  IPP(1) %s" % rec["image_position_patient_first"])
        print("  slope %g intercept %g bits %d pixelrep %d, HU %g..%g" % (
            rec["rescale_slope"], rec["rescale_intercept"], rec["bits_stored"],
            rec["pixel_representation"], rec["hu_min"], rec["hu_max"]))
        print("  in plane skew |cos| %.3e, slice obliquity %.4f deg" % (
            rec["in_plane_skew_cos"], rec["slice_obliquity_deg"]))
        entry = {"conversion": rec}
        if args.roundtrip:
            rt = roundtrip(src, out_dir)
            entry["roundtrip"] = rt
            print("  ROUND TRIP (pydicom) max world error %.3e mm, mean %.3e mm" % (
                rt["max_world_error_mm"], rt["mean_world_error_mm"]))
            print("    index residual %.3e voxels, IOP spread %.3e, "
                  "slice spacing spread %.3e mm" % (
                      rt["max_index_residual_voxels"], rt["max_iop_deviation"],
                      rt["max_slice_spacing_deviation_mm"]))
            print("    voxels %d compared, %d mismatched, max value error %g HU" % (
                rt["voxels_compared"], rt["voxels_mismatched"],
                rt["max_value_error_hu"]))
        if args.simpleitk:
            ck = crosscheck_simpleitk(src, out_dir)
            entry["simpleitk"] = ck
            print("  CROSSCHECK %s" % ck["reader"])
            print("    max world error %.3e mm, mean %.3e mm, det %g" % (
                ck["max_world_error_mm"], ck["mean_world_error_mm"],
                ck["sitk_direction_det"]))
            print("    voxels %d compared, %d mismatched, max value error %g HU" % (
                ck["voxels_compared"], ck["voxels_mismatched"],
                ck["max_value_error_hu"]))
        records.append(entry)

    if args.out_json:
        Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_json).write_text(json.dumps(records, indent=2))
        print("wrote %s" % args.out_json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
