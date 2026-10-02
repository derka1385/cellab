"""
Chula RBC-12 dataset reader.

Dataset: https://github.com/Chula-PIC-Lab/Chula-RBC-12-Dataset (MIT License, Chula PIC Lab 2021).
Fetch it with `bash scripts/get_chula.sh` (clones into external/, git-ignored).

Layout:
    Dataset/<id>.jpg   640x480 RGB smear images
    Label/<id>.txt     one line per annotated cell: "x y class" (space separated)

Not every image has a label file, and not every cell in an image is annotated.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CHULA_ROOT = Path(os.environ.get(
    "CHULA_ROOT", REPO_ROOT / "external" / "Chula-RBC-12-Dataset"))

# Class ids as documented in the dataset README (0..12; 10 is "uncategorised").
CHULA_CLASSES: Dict[int, str] = {
    0: "normal",
    1: "macrocyte",
    2: "microcyte",
    3: "spherocyte",
    4: "target_cell",
    5: "stomatocyte",
    6: "ovalocyte",
    7: "teardrop",
    8: "burr_cell",
    9: "schistocyte",
    10: "uncategorised",
    11: "hypochromia",
    12: "elliptocyte",
}


@dataclass
class Annotation:
    x: float
    y: float
    class_id: int

    @property
    def class_name(self) -> str:
        return CHULA_CLASSES.get(self.class_id, "unknown")


def image_path(image_id: str, root: Path = DEFAULT_CHULA_ROOT) -> Path:
    for ext in (".jpg", ".JPG", ".jpeg", ".png"):
        p = Path(root) / "Dataset" / f"{image_id}{ext}"
        if p.exists():
            return p
    raise FileNotFoundError(f"Chula image {image_id} not found under {root}/Dataset "
                            f"(run: bash scripts/get_chula.sh)")


def label_path(image_id: str, root: Path = DEFAULT_CHULA_ROOT) -> Path:
    return Path(root) / "Label" / f"{image_id}.txt"


def load_image(image_id: str, root: Path = DEFAULT_CHULA_ROOT) -> np.ndarray:
    """RGB uint8 array (H, W, 3)."""
    return np.asarray(Image.open(image_path(image_id, root)).convert("RGB"))


def parse_label_file(path: Path) -> List[Annotation]:
    """Parse 'x y class' lines. Some files contain stray bytes, so decode as latin-1."""
    out: List[Annotation] = []
    with open(path, encoding="latin-1") as f:
        for line in f:
            parts = line.replace(",", " ").split()
            if len(parts) < 3:
                continue
            try:
                out.append(Annotation(float(parts[0]), float(parts[1]), int(float(parts[2]))))
            except ValueError:
                continue
    return out


def load_labels(image_id: str, root: Path = DEFAULT_CHULA_ROOT) -> List[Annotation]:
    p = label_path(image_id, root)
    return parse_label_file(p) if p.exists() else []


def list_image_ids(root: Path = DEFAULT_CHULA_ROOT, labelled_only: bool = True) -> List[str]:
    """Image ids sorted numerically. With labelled_only, only ids with both image and labels."""
    root = Path(root)
    imgs = {p.stem for p in (root / "Dataset").iterdir()
            if p.suffix.lower() in (".jpg", ".jpeg", ".png")}
    if labelled_only:
        labs = {p.stem for p in (root / "Label").glob("*.txt")}
        imgs &= labs
    return sorted(imgs, key=lambda s: (not s.isdigit(), int(s) if s.isdigit() else 0, s))


def chula_id_from_path(path: str | Path, root: Path = DEFAULT_CHULA_ROOT) -> Optional[str]:
    """Return the Chula image id if `path` is an image of the Dataset folder, else None."""
    p = Path(path).resolve()
    try:
        if p.parent == (Path(root) / "Dataset").resolve():
            return p.stem
    except OSError:
        pass
    return None


def class_counts(image_id: str, root: Path = DEFAULT_CHULA_ROOT) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for a in load_labels(image_id, root):
        counts[a.class_name] = counts.get(a.class_name, 0) + 1
    return counts


if __name__ == "__main__":
    ids = list_image_ids()
    print(f"{len(ids)} labelled images in {DEFAULT_CHULA_ROOT}")
    total: Dict[str, int] = {}
    for i in ids:
        for k, v in class_counts(i).items():
            total[k] = total.get(k, 0) + v
    for k, v in sorted(total.items(), key=lambda kv: -kv[1]):
        print(f"  {k:14s} {v}")
