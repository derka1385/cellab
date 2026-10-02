"""
Label image -> per-cell measurements -> sample.json (contract 4.1, everything MEASURED).

    python -m backend.vision.measure --image external/Chula-RBC-12-Dataset/Dataset/222.jpg

writes backend/data/samples/<sample_id>/{image.png, sample.json, overlay.png}.
For a Chula image the sample id is chula_<image id> and the annotations (if any) fill
shape_class with shape_class_source = "annotation". Areas and diameters are in pixels
(pixel_size_um = null): only ratios matter, the CBC sets the absolute scale.

Central pallor (pallor_ratio):
  1. flat-field the green channel (background ~ 1.0, cells darker);
  2. inside the cell, erode the mask to drop the blurred edge;
  3. normalise each pixel between the cell's own dark rim (10th percentile) and the
     background (1.0): b = (I - rim) / (1 - rim);
  4. pale pixels: b > PALLOR_THRESHOLD; keep the connected pale region that contains the
     centroid (or the one closest to it, within 0.35 radius);
  5. pallor_ratio = equivalent diameter of that region / cell equivalent diameter (0 if none).
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import cv2
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from skimage import filters
from skimage.measure import regionprops

from backend.vision import segment as seg
from backend.vision.chula_loader import (Annotation, CHULA_CLASSES, chula_id_from_path,
                                         load_labels)

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLES_DIR = REPO_ROOT / "backend" / "data" / "samples"

# Pallor parameters. The threshold was chosen on ODD Chula image ids only (dev split:
# 0.2-0.35 all gave AUC 0.95-0.97; 0.3 puts the median normal cell at ~0.38, close to the
# physics anchor PALLOR_RATIO_NORMAL = 0.40). validate_pallor.py reports the EVEN ids.
PALLOR_THRESHOLD = 0.3      # fraction of the way from the cell's dark rim to the background
RIM_PERCENTILE = 10.0
EDGE_ERODE_FRAC = 0.15      # of the cell radius
CENTER_SEARCH_FRAC = 0.35   # pale blob must touch a disc of this radius fraction around centroid

# Exclusion rules (contract 4.1)
MIN_CIRCULARITY = 0.6
MAX_AREA_VS_MEDIAN = 2.0
MIN_AREA_VS_MEDIAN = 0.3    # platelets / debris
WBC_DARK_DROP = 0.15        # pixels this much darker than typical RBC rims -> nucleus
WBC_DARK_FRAC = 0.15
BORDER_MARGIN_PX = 3


@dataclass
class CellRecord:
    cell_id: str
    centroid_px: List[float]
    bbox_px: List[int]
    contour_px: List[List[int]]
    area: float
    diameter: float
    circularity: float
    pallor_ratio: float
    shape_class: Optional[str]
    shape_class_source: str
    excluded: bool
    exclusion_reason: Optional[str]


def _contour(mask: np.ndarray, offset_xy=(0, 0)) -> List[List[int]]:
    m = mask.astype(np.uint8)
    cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cs:
        return []
    c = max(cs, key=cv2.contourArea)
    c = cv2.approxPolyDP(c, 0.8, True)
    ox, oy = offset_xy
    return [[int(p[0][0] + ox), int(p[0][1] + oy)] for p in c]


def pallor_ratio(ff_crop: np.ndarray, mask: np.ndarray, centroid_rc, diameter: float,
                 threshold: float = PALLOR_THRESHOLD) -> float:
    """Central pallor diameter / cell diameter, from a flat-fielded crop and the cell mask."""
    r = diameter / 2.0
    vals = ff_crop[mask]
    if vals.size < 20:
        return 0.0
    rim = float(np.percentile(vals, RIM_PERCENTILE))
    span = 1.0 - rim
    if span <= 1e-3:
        return 0.0
    inner = ndi.binary_erosion(mask, iterations=max(1, int(round(EDGE_ERODE_FRAC * r))))
    if not inner.any():
        return 0.0
    b = (ff_crop - rim) / span
    pale = (b > threshold) & inner
    if not pale.any():
        return 0.0
    lab, n = ndi.label(pale)
    cy, cx = centroid_rc
    yy, xx = np.indices(mask.shape)
    near = (yy - cy) ** 2 + (xx - cx) ** 2 <= (CENTER_SEARCH_FRAC * r) ** 2
    cand = np.unique(lab[near & pale])
    cand = cand[cand > 0]
    if cand.size == 0:
        return 0.0
    sizes = ndi.sum(np.ones_like(lab), lab, index=cand)
    area = float(np.max(sizes))
    return float(min(1.0, 2.0 * math.sqrt(area / math.pi) / diameter))


def measure_cells(image: np.ndarray, labels: np.ndarray,
                  annotations: Optional[Sequence[Annotation]] = None,
                  pallor_threshold: float = PALLOR_THRESHOLD) -> List[CellRecord]:
    H, W = labels.shape
    ff = filters.gaussian(seg.flatfield(image), sigma=0.8)
    props = regionprops(labels)
    if not props:
        return []
    # Annotation -> region (point in mask)
    ann_by_label: Dict[int, List[Annotation]] = {}
    for a in annotations or []:
        x, y = int(round(a.x)), int(round(a.y))
        if 0 <= x < W and 0 <= y < H and labels[y, x] > 0:
            ann_by_label.setdefault(int(labels[y, x]), []).append(a)

    # Border test with a small margin: morphological opening can erode the outermost pixels.
    m = BORDER_MARGIN_PX
    touching = {p.label for p in props
                if p.bbox[0] <= m or p.bbox[1] <= m or p.bbox[2] >= H - m or p.bbox[3] >= W - m}
    inner_areas = [p.area for p in props if p.label not in touching]
    med_area = float(np.median(inner_areas if inner_areas else [p.area for p in props]))
    rims = [float(np.percentile(ff[p.coords[:, 0], p.coords[:, 1]], RIM_PERCENTILE)) for p in props]
    typical_rim = float(np.median(rims))

    out: List[CellRecord] = []
    for k, p in enumerate(props):
        minr, minc, maxr, maxc = p.bbox
        mask = p.image
        area = float(p.area)
        diameter = float(2.0 * math.sqrt(area / math.pi))
        per = float(p.perimeter_crofton) if p.perimeter_crofton > 0 else float(p.perimeter)
        circ = float(min(1.0, 4.0 * math.pi * area / per ** 2)) if per > 0 else 0.0
        cy, cx = p.centroid
        crop = ff[minr:maxr, minc:maxc]
        pr = pallor_ratio(crop, mask, (cy - minr, cx - minc), diameter, pallor_threshold)

        anns = ann_by_label.get(int(p.label), [])
        shape_class, source = None, "none"
        if len(anns) == 1:
            shape_class, source = anns[0].class_name, "annotation"
        elif len(anns) > 1:
            names = sorted({a.class_name for a in anns})
            shape_class, source = (names[0], "annotation") if len(names) == 1 else (None, "none")

        dark_frac = float(np.mean(ff[p.coords[:, 0], p.coords[:, 1]] < typical_rim - WBC_DARK_DROP))
        reason = None
        if p.label in touching:
            reason = "touches_image_border"
        elif area < MIN_AREA_VS_MEDIAN * med_area:
            reason = "too_small_platelet_or_debris"
        elif dark_frac > WBC_DARK_FRAC:
            reason = "dark_nucleus_wbc_or_debris"
        elif area > MAX_AREA_VS_MEDIAN * med_area:
            reason = "overlap_cluster_area_gt_2x_median"
        elif circ < MIN_CIRCULARITY:
            reason = "overlap_or_irregular_circularity_lt_0.6"
        elif len(anns) > 1:
            reason = "overlap_multiple_annotations_in_mask"

        out.append(CellRecord(
            cell_id=f"c{k + 1:03d}",
            centroid_px=[round(float(cx), 1), round(float(cy), 1)],
            bbox_px=[int(minc), int(minr), int(maxc - minc), int(maxr - minr)],
            contour_px=_contour(mask, (minc, minr)),
            area=round(area, 1),
            diameter=round(diameter, 2),
            circularity=round(circ, 3),
            pallor_ratio=round(pr, 3),
            shape_class=shape_class,
            shape_class_source=source,
            excluded=reason is not None,
            exclusion_reason=reason,
        ))
    return out


def build_sample(sample_id: str, label: str, image_rel_path: str, cells: List[CellRecord],
                 source: str, segmenter: str) -> Dict:
    return {
        "sample_id": sample_id,
        "label": label,
        "image_path": image_rel_path,
        "pixel_size_um": None,
        "source": source,
        "provenance": "MEASURED",
        "segmentation_method": segmenter,
        "cells": [asdict(c) for c in cells],
    }


def pallor_color_bgr(pr: float):
    """0 (no pallor, spherocyte-like) -> red ; >= 0.4 (normal pallor) -> green."""
    w = min(max(pr / 0.40, 0.0), 1.0)
    r, g = int(round(230 * (1 - w) + 30 * w)), int(round(40 * (1 - w) + 200 * w))
    return (40, g, r)


def draw_overlay(image: np.ndarray, cells: List[CellRecord]) -> np.ndarray:
    img = cv2.cvtColor(np.asarray(image, dtype=np.uint8), cv2.COLOR_RGB2BGR).copy()
    for c in cells:
        if not c.contour_px:
            continue
        pts = np.array(c.contour_px, dtype=np.int32).reshape(-1, 1, 2)
        color = (110, 110, 110) if c.excluded else pallor_color_bgr(c.pallor_ratio)
        cv2.polylines(img, [pts], True, color, 1 if c.excluded else 2, cv2.LINE_AA)
    # Legend
    h = img.shape[0]
    cv2.rectangle(img, (8, h - 40), (250, h - 6), (255, 255, 255), -1)
    for i in range(120):
        cv2.line(img, (12 + i, h - 20), (12 + i, h - 10), pallor_color_bgr(0.4 * i / 119), 1)
    cv2.putText(img, "pallor 0", (12, h - 26), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 0), 1, cv2.LINE_AA)
    cv2.putText(img, ">=0.4", (110, h - 26), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 0), 1, cv2.LINE_AA)
    cv2.putText(img, "grey: excluded", (140, h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (90, 90, 90), 1, cv2.LINE_AA)
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def process_image(image_path: Path, out_dir: Optional[Path] = None, sample_id: Optional[str] = None,
                  label: Optional[str] = None, labels_path: Optional[Path] = None,
                  method: Optional[str] = None, write_files: bool = True) -> Dict:
    image_path = Path(image_path)
    image = np.asarray(Image.open(image_path).convert("RGB"))
    chula_id = chula_id_from_path(image_path)
    if sample_id is None:
        sample_id = f"chula_{chula_id}" if chula_id else image_path.stem
    if label is None:
        label = f"Chula RBC-12 image {chula_id}" if chula_id else image_path.name
    annotations: List[Annotation] = []
    if labels_path is not None:
        from backend.vision.chula_loader import parse_label_file
        annotations = parse_label_file(Path(labels_path))
    elif chula_id:
        annotations = load_labels(chula_id)

    labels = seg.segment(image, method)
    cells = measure_cells(image, labels, annotations)
    out_dir = Path(out_dir) if out_dir else SAMPLES_DIR / sample_id
    rel = f"data/samples/{sample_id}/image.png"
    sample = build_sample(sample_id, label, rel, cells,
                          "public_dataset" if chula_id else "user_image",
                          seg.method_name(seg.LAST_METHOD))
    if write_files:
        out_dir.mkdir(parents=True, exist_ok=True)
        Image.fromarray(image).save(out_dir / "image.png")
        Image.fromarray(draw_overlay(image, cells)).save(out_dir / "overlay.png")
        with open(out_dir / "sample.json", "w") as f:
            json.dump(sample, f, indent=1)
    return sample


def validate_sample(sample: Dict) -> List[str]:
    """Minimal contract 4.1 check. Returns a list of problems (empty = valid)."""
    errs = []
    for k in ("sample_id", "label", "image_path", "pixel_size_um", "source", "cells"):
        if k not in sample:
            errs.append(f"missing key {k}")
    for c in sample.get("cells", []):
        for k in ("cell_id", "centroid_px", "bbox_px", "contour_px", "area", "diameter",
                  "circularity", "pallor_ratio", "shape_class", "shape_class_source",
                  "excluded", "exclusion_reason"):
            if k not in c:
                errs.append(f"{c.get('cell_id')}: missing {k}")
        if c.get("shape_class_source") not in ("annotation", "classifier", "none"):
            errs.append(f"{c.get('cell_id')}: bad shape_class_source")
        if c.get("excluded") and not c.get("exclusion_reason"):
            errs.append(f"{c.get('cell_id')}: excluded without reason")
        if not (0.0 <= c.get("pallor_ratio", -1) <= 1.0):
            errs.append(f"{c.get('cell_id')}: pallor_ratio out of [0,1]")
    return errs


def main(argv=None):
    ap = argparse.ArgumentParser(description="Segment + measure a smear image -> sample.json")
    ap.add_argument("--image", required=True)
    ap.add_argument("--out-dir", default=None, help="default: backend/data/samples/<sample_id>")
    ap.add_argument("--sample-id", default=None)
    ap.add_argument("--label", default=None)
    ap.add_argument("--labels", default=None, help="optional Chula-format label file (x y class)")
    ap.add_argument("--method", choices=["A", "B"], default=None,
                    help="force segmentation path (A = Cellpose, B = Otsu/watershed)")
    args = ap.parse_args(argv)
    s = process_image(Path(args.image), args.out_dir and Path(args.out_dir), args.sample_id,
                      args.label, args.labels and Path(args.labels), args.method)
    kept = [c for c in s["cells"] if not c["excluded"]]
    errs = validate_sample(s)
    out = Path(args.out_dir) if args.out_dir else SAMPLES_DIR / s["sample_id"]
    pr = [c["pallor_ratio"] for c in kept]
    print(f"[measure] {s['sample_id']}: {len(s['cells'])} regions, {len(kept)} kept, "
          f"segmenter={s['segmentation_method']}, median pallor={np.median(pr) if pr else float('nan'):.3f}")
    print(f"[measure] wrote {out / 'sample.json'} ; contract check: {'OK' if not errs else errs[:5]}")
    return 0 if not errs else 1


if __name__ == "__main__":
    raise SystemExit(main())
