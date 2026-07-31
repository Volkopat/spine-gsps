"""Emit GSPS variants for the conformance and viewer interoperability experiment.

DICOM offers three places to put a colour in a presentation state, and they are
not equally legal in the Grayscale Softcopy Presentation State IOD:

  LAYER  (0070,0401) Graphic Layer Recommended Display CIELab Value
         Graphic Layer module, Type 3. IN the GSPS IOD.
  LINE   (0070,0251) Pattern On Color CIELab Value, inside Line Style Sequence
         (0070,0232). IN the GSPS IOD. dciodvfy does not flag it.
  TEXT   (0070,0241) Text Color CIELab Value, inside Text Style Sequence
         (0070,0231). dciodvfy reports both as "not present in standard DICOM
         IOD" for a GrayscaleSoftcopyPresentationState.

The deployed pipeline uses TEXT, the one route that is out of IOD, to carry its
per-vertebra quality flag. Whether viewers honour each route is unmeasured, and
no published study compares GSPS against DICOM SEG rendering support across
viewers. This module emits the variants so that question can be answered.

Axes:
  required_attrs   add the seven attributes dciodvfy reports missing
  colour_route     "text" | "line" | "layer" | "all" | "none"
  identity         "true" (this software) | "meddream" (as deployed)

Nothing here invents annotation geometry. Variants are re-emitted from an
existing GSPS object so the comparison holds content fixed.
"""
from __future__ import annotations

import copy
import datetime
from dataclasses import dataclass, field
from pathlib import Path

import pydicom
from pydicom.dataset import Dataset, FileDataset, FileMetaDataset, validate_file_meta
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

GSPS_SOP_CLASS = "1.2.840.10008.5.1.4.1.1.11.1"

TAG_TEXT_STYLE = (0x0070, 0x0231)
TAG_LINE_STYLE = (0x0070, 0x0232)
TAG_TEXT_COLOR = (0x0070, 0x0241)
TAG_PATTERN_ON_COLOR = (0x0070, 0x0251)
TAG_LAYER_COLOR = (0x0070, 0x0401)

# CIELab as DICOM PCS-Values: L* over [0,100] and a*,b* over [-128,127], each
# scaled into a 16 bit unsigned range.
def cielab(L: float, a: float, b: float) -> list[int]:
    return [
        max(0, min(65535, int(round(L / 100.0 * 65535)))),
        max(0, min(65535, int(round((a + 128.0) / 255.0 * 65535)))),
        max(0, min(65535, int(round((b + 128.0) / 255.0 * 65535)))),
    ]


def decode_cielab(triplet) -> tuple[float, float, float]:
    t = list(triplet)
    return (t[0] / 65535.0 * 100.0,
            t[1] / 65535.0 * 255.0 - 128.0,
            t[2] / 65535.0 * 255.0 - 128.0)


YELLOW = cielab(74.9, 23.9, 78.9)     # matches the deployed normal colour
RED = cielab(81.2, 118.1, 72.1)       # matches the deployed flagged colour

COLOUR_ROUTES = ("none", "text", "line", "layer", "all")
IDENTITIES = ("true", "meddream")

TRUE_IDENTITY = {
    "Manufacturer": "spinelab",
    "ManufacturerModelName": "spinelab-gsps",
    "SoftwareVersions": "0.1.0",
    "ImplementationVersionName": "SPINELAB_0_1",
    # pydicom's registered root. Replace with an owned root before any clinical use.
    "ImplementationClassUID": pydicom.uid.PYDICOM_IMPLEMENTATION_UID,
}
DEPLOYED_IDENTITY = {
    "Manufacturer": "Softneta",
    "ManufacturerModelName": "MedDream",
    "SoftwareVersions": None,
    "ImplementationVersionName": "AYCANSTORE3",
    "ImplementationClassUID": "1.2.276.0.16.3.1.3.0.0.0",
}


@dataclass
class Variant:
    required_attrs: bool = True
    colour_route: str = "line"
    identity: str = "true"
    label: str = field(default="")

    def __post_init__(self):
        if self.colour_route not in COLOUR_ROUTES:
            raise ValueError("colour_route must be one of %r" % (COLOUR_ROUTES,))
        if self.identity not in IDENTITIES:
            raise ValueError("identity must be one of %r" % (IDENTITIES,))
        if not self.label:
            self.label = "req-%s_colour-%s_id-%s" % (
                "yes" if self.required_attrs else "no", self.colour_route, self.identity)


# The four cells of the primary design, plus colour route arms.
DESIGN_2X2 = [
    Variant(True, "line", "true", "conformant_trueid"),
    Variant(True, "line", "meddream", "conformant_meddreamid"),
    Variant(False, "text", "true", "asis_trueid"),
    Variant(False, "text", "meddream", "asis_meddreamid"),
]
DESIGN_COLOUR_ROUTES = [
    Variant(True, "none", "true", "colour_none"),
    Variant(True, "text", "true", "colour_text_outofiod"),
    Variant(True, "line", "true", "colour_line_iod"),
    Variant(True, "layer", "true", "colour_layer_iod"),
    Variant(True, "all", "true", "colour_all"),
]


def _flagged_layers(ds: Dataset) -> set[str]:
    """Which graphic layers carry a flagged (red) annotation in the source object."""
    out: set[str] = set()
    for ga in ds.get("GraphicAnnotationSequence", []):
        layer = str(ga.get("GraphicLayer") or "")
        red = False
        for t in ga.get("TextObjectSequence", []):
            tss = t.get(TAG_TEXT_STYLE)
            if tss is not None and len(tss.value):
                col = tss.value[0].get(TAG_TEXT_COLOR)
                if col is not None and decode_cielab(col.value)[1] > 60:
                    red = True
        for g in ga.get("GraphicObjectSequence", []):
            lss = g.get(TAG_LINE_STYLE)
            if lss is not None and len(lss.value):
                col = lss.value[0].get(TAG_PATTERN_ON_COLOR)
                if col is not None and decode_cielab(col.value)[1] > 60:
                    red = True
        if red and layer:
            out.add(layer)
    return out


def build_variant(src: Dataset, v: Variant, source_image: Dataset | None = None) -> FileDataset:
    """Re-emit `src` under variant `v`. Annotation geometry and text are untouched."""
    ident = TRUE_IDENTITY if v.identity == "true" else DEPLOYED_IDENTITY
    flagged = _flagged_layers(src)

    fm = FileMetaDataset()
    fm.MediaStorageSOPClassUID = GSPS_SOP_CLASS
    fm.MediaStorageSOPInstanceUID = generate_uid()
    fm.TransferSyntaxUID = ExplicitVRLittleEndian
    fm.ImplementationClassUID = ident["ImplementationClassUID"]
    fm.ImplementationVersionName = ident["ImplementationVersionName"]

    ds = FileDataset("", {}, file_meta=fm, preamble=b"\0" * 128)
    for elem in src:
        if elem.tag.group == 0x0002:
            continue
        ds.add(copy.deepcopy(elem))

    ds.SOPClassUID = GSPS_SOP_CLASS
    ds.SOPInstanceUID = fm.MediaStorageSOPInstanceUID
    ds.SeriesInstanceUID = generate_uid()
    ds.Modality = "PR"
    ds.Manufacturer = ident["Manufacturer"]
    ds.ManufacturerModelName = ident["ManufacturerModelName"]
    if ident["SoftwareVersions"]:
        ds.SoftwareVersions = ident["SoftwareVersions"]
    elif "SoftwareVersions" in ds:
        del ds.SoftwareVersions

    now = datetime.datetime.now()
    ds.ContentLabel = "SPINE_QS"
    # ContentDescription has VR LO, maximum 64 characters. pydicom only warns on
    # overrun and writes the long value anyway, producing a non conformant object
    # silently, so truncate explicitly rather than relying on the warning.
    ds.ContentDescription = ("Spine levels, %s" % v.label)[:64]
    ds.PresentationCreationDate = now.strftime("%Y%m%d")
    ds.PresentationCreationTime = now.strftime("%H%M%S")

    # ---- the seven attributes dciodvfy reports missing --------------------
    if v.required_attrs:
        ds.InstanceNumber = 1                       # Type 1, ContentIdentificationMacro
        ds.SeriesNumber = 9001                      # Type 2, GeneralSeries
        ds.StudyID = str(src.get("StudyID") or "")  # Type 2, GeneralStudy
        # Laterality is Type 2C in GeneralSeries, conditional on a paired body
        # part. The spine is not paired, so it is correctly ABSENT. dciodvfy
        # reports it missing because it cannot evaluate the condition, and adding
        # it empty produces a worse diagnostic ("should be absent"). Leave it out.
        if "Laterality" in ds:
            del ds.Laterality
        # PresentationPixelSpacing is Type 1C in DisplayedArea, required when
        # PresentationSizeMode is TRUE SIZE. It and PresentationPixelAspectRatio
        # are alternatives, so setting one means removing the other.
        px = None
        if source_image is not None:
            px = source_image.get("PixelSpacing") or source_image.get("ImagerPixelSpacing")
        for da in ds.get("DisplayedAreaSelectionSequence", []):
            if px is not None:
                da.PresentationPixelSpacing = [float(px[0]), float(px[1])]
                if "PresentationPixelAspectRatio" in da:
                    del da.PresentationPixelAspectRatio
            elif "PresentationPixelAspectRatio" not in da:
                da.PresentationPixelAspectRatio = [1, 1]
        # FileMetaInformationGroupLength and FileMetaInformationVersion are added
        # by validate_file_meta below rather than set by hand.
    else:
        for a in ("InstanceNumber", "SeriesNumber", "StudyID", "Laterality"):
            if a in ds:
                del ds[a]
        for da in ds.get("DisplayedAreaSelectionSequence", []):
            if "PresentationPixelSpacing" in da:
                del da.PresentationPixelSpacing
            if "PresentationPixelAspectRatio" not in da:
                da.PresentationPixelAspectRatio = [1, 1]

    # ---- colour routing ---------------------------------------------------
    want_text = v.colour_route in ("text", "all")
    want_line = v.colour_route in ("line", "all")
    want_layer = v.colour_route in ("layer", "all")

    for ga in ds.get("GraphicAnnotationSequence", []):
        layer = str(ga.get("GraphicLayer") or "")
        red = layer in flagged
        colour = RED if red else YELLOW

        for t in ga.get("TextObjectSequence", []):
            if want_text:
                style = Dataset()
                style.CSSFontName = "Arial"
                style.HorizontalAlignment = "LEFT"
                style.VerticalAlignment = "TOP"
                style.ShadowStyle = "OFF"
                style[TAG_TEXT_COLOR] = pydicom.DataElement(TAG_TEXT_COLOR, "US", colour)
                t[TAG_TEXT_STYLE] = pydicom.DataElement(TAG_TEXT_STYLE, "SQ", [style])
            elif TAG_TEXT_STYLE in t:
                del t[TAG_TEXT_STYLE]

        for g in ga.get("GraphicObjectSequence", []):
            if want_line:
                # The Line Style Sequence macro carries ten Type 1 attributes and
                # dciodvfy enforces every one. The deployed generate_gsps_4.py
                # populates them all; an earlier version of this writer omitted
                # ShadowOffsetX, ShadowOffsetY, ShadowColorCIELabValue and
                # PatternOnOpacity, which dciodvfy caught.
                style = Dataset()
                style.ShadowStyle = "OFF"
                style.ShadowOffsetX = 0.0
                style.ShadowOffsetY = 0.0
                style.ShadowColorCIELabValue = colour
                style.ShadowOpacity = 0.0
                style.LineThickness = 2.0
                style.LineDashingStyle = "DASHED"
                style.LinePattern = 255
                style.PatternOnOpacity = 1.0
                style[TAG_PATTERN_ON_COLOR] = pydicom.DataElement(TAG_PATTERN_ON_COLOR, "US", colour)
                g[TAG_LINE_STYLE] = pydicom.DataElement(TAG_LINE_STYLE, "SQ", [style])
            elif TAG_LINE_STYLE in g:
                del g[TAG_LINE_STYLE]

    for gl in ds.get("GraphicLayerSequence", []):
        name = str(gl.get("GraphicLayer") or "")
        if want_layer:
            gl[TAG_LAYER_COLOR] = pydicom.DataElement(
                TAG_LAYER_COLOR, "US", RED if name in flagged else YELLOW)
        elif TAG_LAYER_COLOR in gl:
            del gl[TAG_LAYER_COLOR]

    validate_file_meta(ds.file_meta, enforce_standard=True)
    return ds


def emit_all(src_path: Path, out_dir: Path, variants=None,
             source_image: Path | None = None) -> list[tuple[str, Path]]:
    """Write every variant of one source object. Returns (label, path) pairs."""
    variants = variants or DESIGN_2X2
    src = pydicom.dcmread(str(src_path))
    img = pydicom.dcmread(str(source_image), stop_before_pixels=True) if source_image else None
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for v in variants:
        ds = build_variant(src, v, img)
        p = out_dir / ("%s__%s.dcm" % (src_path.stem, v.label))
        pydicom.dcmwrite(str(p), ds, enforce_file_format=True)
        written.append((v.label, p))
    return written


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Emit GSPS variants from an existing object")
    ap.add_argument("source", help="an existing *_GSPS.dcm")
    ap.add_argument("--out", required=True)
    ap.add_argument("--source-image", default=None,
                    help="a referenced source image, for PresentationPixelSpacing")
    ap.add_argument("--design", choices=("2x2", "colour", "both"), default="both")
    a = ap.parse_args()

    sets = {"2x2": DESIGN_2X2, "colour": DESIGN_COLOUR_ROUTES,
            "both": DESIGN_2X2 + DESIGN_COLOUR_ROUTES}[a.design]
    seen, uniq = set(), []
    for v in sets:
        if v.label not in seen:
            seen.add(v.label)
            uniq.append(v)
    for label, p in emit_all(Path(a.source), Path(a.out), uniq,
                             Path(a.source_image) if a.source_image else None):
        print("%-28s %s" % (label, p.name))
