"""
Validate the pallor -> sphericity inference on Chula RBC-12.

For annotated "normal" and "spherocyte" cells (annotation point inside a kept segmented
cell), compare pallor_ratio (MEASURED) and SI = si_from_pallor(pallor_ratio) (INFERRED).
Reports counts, medians, AUC of SI for spherocyte vs normal, a 95 % CI from an
IMAGE-LEVEL bootstrap (cells of one image are not independent), and the AUC restricted
to images that contain both classes (controls part of the image/patient confound).

The pallor threshold was tuned on odd image ids; the default here is the even ids
(held-out split).

    python -m backend.vision.validate_pallor                 # even ids (held-out)
    python -m backend.vision.validate_pallor --split all --max-images 60

Outputs: backend/data/validation/{validation.json, pallor_validation.png, cells.csv}
"""
from __future__ import annotations

import argparse
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import numpy as np
from scipy.stats import rankdata

from backend.physics.celllab_physics import (PALLOR_RATIO_NORMAL, SI_DISCOCYTE, SI_SPHEROCYTE,
                                             si_from_pallor)
from backend.vision import chula_loader as cl
from backend.vision import measure as ms
from backend.vision import segment as sg

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "backend" / "data" / "validation"
SI_HIGH = 0.85   # HYPOTHESIS threshold used for "spherical" fractions in the summary


def auc(pos: np.ndarray, neg: np.ndarray) -> float:
    """P(score_pos > score_neg) + 0.5 P(tie)  (Mann-Whitney)."""
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    r = rankdata(np.concatenate([pos, neg]))
    return float((r[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def roc_curve(pos, neg):
    scores = np.unique(np.concatenate([pos, neg]))[::-1]
    tpr = [0.0] + [float(np.mean(pos >= s)) for s in scores] + [1.0]
    fpr = [0.0] + [float(np.mean(neg >= s)) for s in scores] + [1.0]
    return np.array(fpr), np.array(tpr)


def bootstrap_auc_by_image(rows: List[Dict], n_boot: int = 1000, seed: int = 0):
    rng = np.random.default_rng(seed)
    by_img: Dict[str, List[Dict]] = {}
    for r in rows:
        by_img.setdefault(r["image_id"], []).append(r)
    imgs = list(by_img)
    vals = []
    for _ in range(n_boot):
        pick = rng.choice(len(imgs), size=len(imgs), replace=True)
        sel = [r for k in pick for r in by_img[imgs[k]]]
        pos = np.array([r["si"] for r in sel if r["cls"] == "spherocyte"])
        neg = np.array([r["si"] for r in sel if r["cls"] == "normal"])
        if len(pos) and len(neg):
            vals.append(auc(pos, neg))
    return [round(float(np.percentile(vals, 2.5)), 4), round(float(np.percentile(vals, 97.5)), 4)]


def q(x, p):
    return round(float(np.percentile(x, p)), 4) if len(x) else None


def class_summary(vals_pr, vals_si):
    pr, si = np.asarray(vals_pr), np.asarray(vals_si)
    return {
        "n_cells": int(len(pr)),
        "pallor_ratio_median": q(pr, 50), "pallor_ratio_iqr": [q(pr, 25), q(pr, 75)],
        "pallor_zero_fraction": round(float(np.mean(pr == 0)), 4) if len(pr) else None,
        "si_median": q(si, 50), "si_iqr": [q(si, 25), q(si, 75)],
        f"fraction_si_gt_{SI_HIGH}": round(float(np.mean(si > SI_HIGH)), 4) if len(si) else None,
    }


def run(split: str = "even", max_images: int = 0, n_boot: int = 1000) -> Dict:
    ids = cl.list_image_ids()
    if split == "even":
        ids = [i for i in ids if i.isdigit() and int(i) % 2 == 0]
    elif split == "odd":
        ids = [i for i in ids if i.isdigit() and int(i) % 2 == 1]
    ids = [i for i in ids if any(a.class_id in (0, 3) for a in cl.load_labels(i))]
    if max_images:
        ids = ids[:max_images]

    rows: List[Dict] = []           # one per kept, annotated cell (all classes)
    n_ann = {"normal": 0, "spherocyte": 0}
    n_matched_any = {"normal": 0, "spherocyte": 0}
    methods = set()
    t0 = time.time()
    for k, i in enumerate(ids):
        img = cl.load_image(i)
        anns = cl.load_labels(i)
        for a in anns:
            if a.class_name in n_ann:
                n_ann[a.class_name] += 1
        labels = sg.segment(img)
        methods.add(sg.method_name(sg.LAST_METHOD))
        cells = ms.measure_cells(img, labels, anns)
        n_norm = sum(a.class_id == 0 for a in anns)
        n_sph = sum(a.class_id == 3 for a in anns)
        for c in cells:
            if c.shape_class in n_matched_any:
                n_matched_any[c.shape_class] += 1
            if c.excluded or c.shape_class_source != "annotation":
                continue
            rows.append({"image_id": i, "cell_id": c.cell_id, "cls": c.shape_class,
                         "pallor_ratio": c.pallor_ratio, "si": round(si_from_pallor(c.pallor_ratio), 4),
                         "area_px": c.area, "circularity": c.circularity,
                         "mixed_image": n_norm >= 3 and n_sph >= 3})
        if (k + 1) % 25 == 0:
            print(f"[validate] {k + 1}/{len(ids)} images, {time.time() - t0:.0f}s")

    def sel(cls, mixed_only=False):
        return [r for r in rows if r["cls"] == cls and (r["mixed_image"] or not mixed_only)]

    nor, sph = sel("normal"), sel("spherocyte")
    si_n = np.array([r["si"] for r in nor]); si_s = np.array([r["si"] for r in sph])
    pr_n = np.array([r["pallor_ratio"] for r in nor]); pr_s = np.array([r["pallor_ratio"] for r in sph])
    mn, msp = sel("normal", True), sel("spherocyte", True)
    auc_si = auc(si_s, si_n)
    per_class = {}
    for name in sorted({r["cls"] for r in rows}):
        rr = [r for r in rows if r["cls"] == name]
        per_class[name] = class_summary([r["pallor_ratio"] for r in rr], [r["si"] for r in rr])

    result = {
        "what": "Does measured central pallor separate annotated spherocytes from normal RBCs?",
        "dataset": "Chula RBC-12 (MIT License), github.com/Chula-PIC-Lab/Chula-RBC-12-Dataset",
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "split": split,
        "split_note": ("pallor threshold tuned on odd image ids; this run uses held-out even ids"
                       if split == "even" else "includes images used to tune the pallor threshold"),
        "segmentation_method": sorted(methods),
        "pallor_threshold": ms.PALLOR_THRESHOLD,
        "si_mapping": {"function": "celllab_physics.si_from_pallor", "si_discocyte": SI_DISCOCYTE,
                       "si_spherocyte": SI_SPHEROCYTE, "pallor_ratio_normal": PALLOR_RATIO_NORMAL},
        "n_images": len(ids),
        "annotations": {
            "normal": n_ann["normal"], "spherocyte": n_ann["spherocyte"],
            "matched_to_a_segmented_region": n_matched_any,
            "kept_after_exclusions": {"normal": len(nor), "spherocyte": len(sph)},
        },
        "normal": class_summary(pr_n, si_n),
        "spherocyte": class_summary(pr_s, si_s),
        "auc_si_spherocyte_vs_normal": round(auc_si, 4),
        "auc_ci95_image_bootstrap": bootstrap_auc_by_image(nor + sph, n_boot) if n_boot else None,
        "auc_si_mixed_images_only": {
            "auc": round(auc(np.array([r["si"] for r in msp]), np.array([r["si"] for r in mn])), 4),
            "n_images": len({r["image_id"] for r in mn + msp}),
            "n_normal": len(mn), "n_spherocyte": len(msp),
            "note": "images with >= 3 annotated normal AND >= 3 spherocytes: limits the "
                    "between-image (staining / magnification / patient) confound",
        },
        "per_class_all_annotations": per_class,
        "provenance": {"pallor_ratio": "MEASURED", "si": "INFERRED", "auc": "COMPUTED"},
        "caveats": [
            "Spherocyte-rich images come from few patients/slides: part of the separation may "
            "reflect slide-level differences; see auc_si_mixed_images_only.",
            "Labels are single expert point annotations; not every cell in an image is annotated.",
            "SI is inferred by a linear map of pallor; the AUC validates the ranking, not the "
            "absolute SI values.",
        ],
        "runtime_s": round(time.time() - t0, 1),
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_DIR / "validation.json", "w") as f:
        json.dump(result, f, indent=1)
    with open(OUT_DIR / "cells.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["image_id"])
        w.writeheader()
        w.writerows(rows)
    plot(result, pr_n, pr_s, si_n, si_s, OUT_DIR / "pallor_validation.png")
    return result


def plot(res, pr_n, pr_s, si_n, si_s, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    c_norm, c_sph = "#2a78b5", "#d1495b"
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.4))
    bins = np.linspace(0, 0.8, 33)
    ax[0].hist(pr_n, bins=bins, density=True, alpha=0.6, color=c_norm, label=f"normal (n={len(pr_n)})")
    ax[0].hist(pr_s, bins=bins, density=True, alpha=0.6, color=c_sph, label=f"spherocyte (n={len(pr_s)})")
    ax[0].set_xlabel("central pallor ratio (MEASURED)")
    ax[0].set_ylabel("density")
    ax[0].set_title("Central pallor by annotated class")
    ax[0].legend(frameon=False)

    sib = np.linspace(SI_DISCOCYTE - 0.01, SI_SPHEROCYTE + 0.01, 30)
    ax[1].hist(si_n, bins=sib, density=True, alpha=0.6, color=c_norm, label="normal")
    ax[1].hist(si_s, bins=sib, density=True, alpha=0.6, color=c_sph, label="spherocyte")
    ax[1].set_xlabel("sphericity index SI (INFERRED from pallor)")
    ax[1].set_title("Inferred sphericity")
    ax[1].legend(frameon=False)

    fpr, tpr = roc_curve(si_s, si_n)
    ci = res.get("auc_ci95_image_bootstrap")
    ax[2].plot(fpr, tpr, color=c_sph, lw=2,
               label=f"AUC {res['auc_si_spherocyte_vs_normal']:.3f}"
                     + (f" [{ci[0]:.3f}-{ci[1]:.3f}]" if ci else ""))
    ax[2].plot([0, 1], [0, 1], color="#999", lw=1, ls="--")
    mx = res["auc_si_mixed_images_only"]
    ax[2].set_title(f"SI: spherocyte vs normal (mixed images: AUC {mx['auc']:.3f})")
    ax[2].set_xlabel("false positive rate (normal)")
    ax[2].set_ylabel("true positive rate (spherocyte)")
    ax[2].legend(frameon=False, loc="lower right")
    for a in ax:
        a.spines[["top", "right"]].set_visible(False)
    fig.suptitle(f"Chula RBC-12, {res['n_images']} images ({res['split']} ids), "
                 f"segmentation: {', '.join(res['segmentation_method'])}", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["even", "odd", "all"], default="even")
    ap.add_argument("--max-images", type=int, default=0)
    ap.add_argument("--n-boot", type=int, default=1000)
    a = ap.parse_args(argv)
    r = run(a.split, a.max_images, a.n_boot)
    print(json.dumps({k: r[k] for k in ("n_images", "annotations", "normal", "spherocyte",
                                        "auc_si_spherocyte_vs_normal", "auc_ci95_image_bootstrap",
                                        "auc_si_mixed_images_only")}, indent=1))
    print(f"[validate] wrote {OUT_DIR / 'validation.json'} and {OUT_DIR / 'pallor_validation.png'}")


if __name__ == "__main__":
    main()
