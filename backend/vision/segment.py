"""
Red blood cell segmentation.

    segment(image) -> label_image (int32, 0 = background, 1..N = cells)

Path A: Cellpose (optional, pulls PyTorch). Used only if `cellpose` imports.
Path B: classical fallback, no dependency beyond scikit-image / scipy:
        green channel -> Otsu -> close + FILL HOLES (central pallor would otherwise
        leave rings) -> distance transform -> watershed to split touching cells.

Force a path with the env var CELLLAB_SEGMENTER=A|B, or segment(image, method="A"|"B").
Check the Cellpose version with:  pip show cellpose
"""
from __future__ import annotations

import os
from typing import Optional

import numpy as np
from scipy import ndimage as ndi
from skimage import filters, morphology, segmentation
from skimage.feature import peak_local_max

_CELLPOSE_MODEL = None
_CELLPOSE_FAILED = False            # set after a failure (e.g. weights not downloadable) -> stay on B
LAST_METHOD: Optional[str] = None   # "A" or "B": which path produced the last label image


def _to_gray(image: np.ndarray) -> np.ndarray:
    """Green channel (best RBC / background contrast on Giemsa / Wright stains), float 0..1."""
    img = np.asarray(image)
    if img.ndim == 3:
        g = img[..., 1]
    else:
        g = img
    g = g.astype(np.float32)
    if g.max() > 1.0:
        g /= 255.0
    return g


def cellpose_available() -> bool:
    try:
        import cellpose  # noqa: F401
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Path B: Otsu + fill holes + distance transform + watershed
# ---------------------------------------------------------------------------

def background_estimate(gray: np.ndarray, cell_scale_px: int = 100) -> np.ndarray:
    """
    Smooth bright-background estimate (corrects vignetting / uneven illumination).
    Grey closing with an element larger than a cell removes the (darker) cells; done on a
    4x downsampled image for speed.
    """
    f = 4
    small = gray[::f, ::f]
    size = max(5, cell_scale_px // f)
    bg = ndi.grey_closing(small, size=(size, size))
    bg = ndi.uniform_filter(bg, size=size)
    bg = ndi.zoom(bg, (gray.shape[0] / bg.shape[0], gray.shape[1] / bg.shape[1]), order=1)
    bg = bg[:gray.shape[0], :gray.shape[1]]
    if bg.shape != gray.shape:  # zoom rounding
        pad = [(0, gray.shape[0] - bg.shape[0]), (0, gray.shape[1] - bg.shape[1])]
        bg = np.pad(bg, pad, mode="edge")
    return np.maximum(bg, 1e-3)


def flatfield(image: np.ndarray) -> np.ndarray:
    """Green channel divided by its background estimate: background ~1, cells < 1."""
    g = _to_gray(image)
    return np.clip(g / background_estimate(g), 0.0, 1.5)


def fill_small_holes(fg: np.ndarray, max_frac: float = 0.4) -> np.ndarray:
    """
    Fill holes (central pallor) but NOT background pockets enclosed by a ring of touching
    cells: only holes smaller than max_frac x the typical object area are filled.
    """
    cc, n = ndi.label(fg)
    if n == 0:
        return fg
    sizes = np.bincount(cc.ravel())[1:]
    typical = float(np.median(sizes[sizes >= 40])) if np.any(sizes >= 40) else float(sizes.max())
    holes = ndi.binary_fill_holes(fg) & ~fg
    hl, nh = ndi.label(holes)
    if nh == 0:
        return fg
    hsizes = np.bincount(hl.ravel())
    small = hsizes <= max_frac * typical
    small[0] = False
    return fg | small[hl]


def foreground_mask(image: np.ndarray) -> np.ndarray:
    """Binary cell mask with holes filled (cells are darker than the background)."""
    g = filters.gaussian(flatfield(image), sigma=1.0)
    t = filters.threshold_otsu(g)
    fg = g < t
    disk2 = morphology.disk(2).astype(bool)
    fg = ndi.binary_closing(fg, structure=disk2, border_value=0)
    fg = fill_small_holes(fg)               # BEFORE watershed: pallor makes rings otherwise
    fg = ndi.binary_opening(fg, structure=disk2)
    # Remove tiny specks (version-independent replacement for remove_small_objects).
    cc, n = ndi.label(fg)
    if n:
        sizes = np.bincount(cc.ravel())
        keep = sizes >= 40
        keep[0] = False
        fg = keep[cc]
    return fg


def segment_classical(image: np.ndarray) -> np.ndarray:
    fg = foreground_mask(image)
    if not fg.any():
        return np.zeros(fg.shape, dtype=np.int32)
    dist = ndi.distance_transform_edt(fg)
    cc, n_cc = ndi.label(fg)
    # Typical cell radius: median of the max distance in each connected component.
    maxima = ndi.maximum(dist, cc, index=np.arange(1, n_cc + 1))
    r_typ = float(np.median(maxima)) if n_cc else 10.0
    dist_s = filters.gaussian(dist, sigma=max(1.0, 0.1 * r_typ))
    peaks = peak_local_max(dist_s, min_distance=max(3, int(0.6 * r_typ)),
                           threshold_abs=0.35 * r_typ, labels=cc, exclude_border=False)
    markers = np.zeros(fg.shape, dtype=np.int32)
    markers[tuple(peaks.T)] = np.arange(1, len(peaks) + 1)
    # Components without any peak (small blobs) still get one marker.
    has_marker = np.zeros(n_cc + 1, dtype=bool)
    has_marker[np.unique(cc[markers > 0])] = True
    next_id = len(peaks) + 1
    for lab in range(1, n_cc + 1):
        if not has_marker[lab]:
            ys, xs = np.nonzero(cc == lab)
            k = int(np.argmax(dist[ys, xs]))
            markers[ys[k], xs[k]] = next_id
            next_id += 1
    labels = segmentation.watershed(-dist_s, markers, mask=fg)
    return merge_oversplit(labels.astype(np.int32))


def _circularity(mask: np.ndarray) -> float:
    from skimage.measure import regionprops
    p = regionprops(mask.astype(np.uint8))[0]
    per = p.perimeter_crofton
    return float(4 * np.pi * p.area / per ** 2) if per > 0 else 0.0


def merge_oversplit(labels: np.ndarray, max_area_vs_median: float = 1.5,
                    min_union_circularity: float = 0.88) -> np.ndarray:
    """
    Undo watershed over-segmentation: merge two touching regions when their union is a
    round, single-cell-sized object (a half cell would otherwise look like a cell without
    central pallor, i.e. a false spherocyte).
    """
    from skimage.measure import regionprops
    labels = labels.copy()
    props = {p.label: p for p in regionprops(labels)}
    if len(props) < 2:
        return labels
    med = float(np.median([p.area for p in props.values()]))
    # Adjacent pairs: compare each pixel with its right and lower neighbour.
    pairs = set()
    for a, b in ((labels[:, :-1], labels[:, 1:]), (labels[:-1, :], labels[1:, :])):
        m = (a != b) & (a > 0) & (b > 0)
        for u, v in zip(a[m].ravel(), b[m].ravel()):
            pairs.add((int(min(u, v)), int(max(u, v))))
    cand = []
    for u, v in pairs:
        area = props[u].area + props[v].area
        if area > max_area_vs_median * med:
            continue
        r0 = min(props[u].bbox[0], props[v].bbox[0]); c0 = min(props[u].bbox[1], props[v].bbox[1])
        r1 = max(props[u].bbox[2], props[v].bbox[2]); c1 = max(props[u].bbox[3], props[v].bbox[3])
        sub = labels[r0:r1, c0:c1]
        circ = _circularity((sub == u) | (sub == v))
        if circ >= min_union_circularity:
            cand.append((circ, u, v))
    used = set()
    for circ, u, v in sorted(cand, reverse=True):
        if u in used or v in used:
            continue
        labels[labels == v] = u
        used.update((u, v))
    return labels


# ---------------------------------------------------------------------------
# Path A: Cellpose (defensive across v3 / v4 APIs)
# ---------------------------------------------------------------------------

def segment_cellpose(image: np.ndarray, diameter: Optional[float] = None) -> np.ndarray:
    global _CELLPOSE_MODEL
    from cellpose import models  # type: ignore
    if _CELLPOSE_MODEL is None:
        if hasattr(models, "CellposeModel"):
            try:
                # Cellpose 4: CellposeModel defaults to the 'cpsam' model.
                _CELLPOSE_MODEL = models.CellposeModel(gpu=False)
            except TypeError:
                _CELLPOSE_MODEL = models.CellposeModel(gpu=False, model_type="cyto3")
        else:  # very old API
            _CELLPOSE_MODEL = models.Cellpose(gpu=False, model_type="cyto")
    img = np.asarray(image)
    out = _CELLPOSE_MODEL.eval(img, diameter=diameter)
    masks = out[0]
    return np.asarray(masks, dtype=np.int32)


def segment(image: np.ndarray, method: Optional[str] = None) -> np.ndarray:
    """Return an int32 label image. Chooses Cellpose (A) if available, else the fallback (B)."""
    global LAST_METHOD
    method = (method or os.environ.get("CELLLAB_SEGMENTER", "auto")).upper()
    global _CELLPOSE_FAILED
    if method == "A" or (method == "AUTO" and not _CELLPOSE_FAILED and cellpose_available()):
        try:
            labels = segment_cellpose(image)
            LAST_METHOD = "A"
            return labels
        except Exception as exc:  # fall back rather than break the demo
            if method == "A":
                raise
            _CELLPOSE_FAILED = True
            print(f"[segment] Cellpose unavailable ({type(exc).__name__}: {str(exc)[:120]}), "
                  f"using fallback B for this process")
    labels = segment_classical(image)
    LAST_METHOD = "B"
    return labels


def method_name(code: Optional[str]) -> str:
    return {"A": "cellpose", "B": "otsu_fill_watershed"}.get(code or "", "unknown")
