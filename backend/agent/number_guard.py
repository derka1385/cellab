"""
number_guard: every number in the agent report must come from a tool result of the run.

Rules (contract section 5):
  - Numbers are extracted by regex from every string of the report, and every numeric
    leaf (findings[].numbers[].value, experiment fields, ...) is checked as well.
  - A number is VERIFIED if it matches at least one number found anywhere in the run's
    tool results (numeric leaves, dict keys like "0.85", and numbers inside strings),
    with a rounding tolerance:
        * equal once both are rounded to 2 significant figures, or
        * equal to the tool value rounded to the precision the report displays
          (e.g. "30.5 %" vs 0.3049);
    and percent <-> fraction conversion ("31 %" matches 0.31, "0.31" matches 31).
  - Numbers declared HYPOTHESIS (findings[].numbers with provenance HYPOTHESIS, or a
    number immediately followed by the word HYPOTHESIS in the text) are exempt.
  - Ignored: digits inside identifiers (c012, tc_04, x5000, 3D), and bare integers 0, 1, 2
    used as counts/ordinals ("two samples", "step 1").
"""
from __future__ import annotations

import math
import re
from typing import Any, Dict, Iterable, List, Set, Tuple

# A number not glued to an identifier on the left (letters, digits, '_', '.') and not
# glued to an ASCII letter / '_' on the right ("3D", "2nd" are not quantities),
# except a multiplier suffix: "2x" is a quantity.
NUM_RE = re.compile(
    r"(?<![\w.])([-+−]?)(\d+(?:[.,]\d+)?(?:[eE][-+]?\d+)?)(?!(?!x\b)[A-Za-z_\d])(\s*%)?"
)
HYP_WINDOW = 40
IGNORED_INTS = {0, 1, 2}
SKIP_KEYS = {"number_guard", "tool_call_id", "provenance", "unit"}


# ---------------------------------------------------------------------------
# extraction
# ---------------------------------------------------------------------------

def _parse(sign: str, body: str) -> float:
    body = body.replace(",", ".")
    v = float(body)
    return -v if sign in ("-", "−") else v


def _decimals(body: str) -> int:
    body = body.replace(",", ".")
    if "e" in body.lower():
        return 6
    return len(body.split(".")[1]) if "." in body else 0


def numbers_in_text(text: str) -> List[Dict]:
    """All numbers in a string: value, displayed decimals, percent flag, hypothesis flag."""
    out = []
    for m in NUM_RE.finditer(text):
        sign, body, pct = m.group(1), m.group(2), m.group(3)
        try:
            v = _parse(sign, body)
        except ValueError:
            continue
        after = text[m.end(): m.end() + HYP_WINDOW]
        out.append({"value": v, "decimals": _decimals(body), "pct": bool(pct),
                    "raw": m.group(0).strip(), "hypothesis": "HYPOTHESIS" in after,
                    "context": text[max(0, m.start() - 40): m.end() + 30]})
    return out


def _walk(obj: Any, path: str = "") -> Iterable[Tuple[str, Any]]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk_key(k, path)
            yield from _walk(v, f"{path}.{k}" if path else str(k))
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            yield from _walk(v, f"{path}[{i}]")
    else:
        yield path, obj


def _walk_key(k: Any, path: str) -> Iterable[Tuple[str, Any]]:
    # dict keys such as "3.1" or "0.85" (predicted_pass_fraction, fraction_si_above) carry data
    if isinstance(k, str) and NUM_RE.fullmatch(k.strip()):
        yield f"{path}<key>", k


def tool_number_pool(tool_results: Dict[str, Any]) -> List[float]:
    """Every number that appears in any tool result of the run."""
    pool: Set[float] = set()
    for out in tool_results.values():
        for _, leaf in _walk(out):
            if isinstance(leaf, bool) or leaf is None:
                continue
            if isinstance(leaf, (int, float)):
                if math.isfinite(float(leaf)):
                    pool.add(float(leaf))
            elif isinstance(leaf, str):
                for n in numbers_in_text(leaf):
                    pool.add(abs(n["value"]))
                    if n["pct"]:
                        pool.add(abs(n["value"]) / 100.0)
    return sorted(abs(v) for v in pool)


# ---------------------------------------------------------------------------
# matching
# ---------------------------------------------------------------------------

def _sig(x: float, s: int = 2) -> float:
    if x == 0 or not math.isfinite(x):
        return x
    return round(x, s - 1 - int(math.floor(math.log10(abs(x)))))


def _close(x: float, v: float, decimals: int | None) -> bool:
    x, v = abs(x), abs(v)
    if math.isclose(x, v, rel_tol=1e-9, abs_tol=1e-12):
        return True
    if _sig(x) == _sig(v):
        return True
    if decimals is not None:
        # tool value rounded to the precision the report displays
        if abs(x - v) <= 0.5 * 10 ** (-decimals) + 1e-12:
            return True
    return False


def is_verified(value: float, pool: List[float], pct: bool = False,
                decimals: int | None = None) -> bool:
    cands = [(abs(value), decimals)]
    if pct:
        cands.append((abs(value) / 100.0, None if decimals is None else decimals + 2))
    elif abs(value) <= 1.0:
        cands.append((abs(value) * 100.0, None if decimals is None else max(0, decimals - 2)))
    for x, d in cands:
        for v in pool:
            if _close(x, v, d):
                return True
    return False


# ---------------------------------------------------------------------------
# report check
# ---------------------------------------------------------------------------

def _hypothesis_values(report: Dict) -> List[float]:
    vals = []
    for f in report.get("findings") or []:
        for n in (f.get("numbers") or []) if isinstance(f, dict) else []:
            if isinstance(n, dict) and n.get("provenance") == "HYPOTHESIS":
                try:
                    vals.append(abs(float(n.get("value"))))
                except (TypeError, ValueError):
                    pass
    return vals


def check_report(report: Dict, tool_results: Dict[str, Any]) -> Dict:
    """
    Returns {"checked": int, "unverified": int, "unverified_items": [...], "hypothesis": int}.
    tool_results: tool_call_id -> tool output (only successful, non-report tool calls).
    """
    pool = tool_number_pool({k: v for k, v in tool_results.items()})
    hyp = _hypothesis_values(report)
    checked = 0
    n_hyp = 0
    bad: List[Dict] = []

    def is_hyp(v: float, dec: int | None, pct: bool) -> bool:
        return any(_close(v, h, dec) or (pct and _close(v / 100.0, h, None)) for h in hyp)

    for path, leaf in _walk(report):
        top = path.split(".")[0].split("[")[0]
        last = path.split(".")[-1].split("[")[0]
        if top in SKIP_KEYS or last in SKIP_KEYS:
            continue
        if isinstance(leaf, bool) or leaf is None:
            continue
        if isinstance(leaf, (int, float)):
            v = float(leaf)
            if not math.isfinite(v):
                continue
            # declared HYPOTHESIS entry in findings[].numbers
            if last == "value" and ".numbers[" in path:
                idx_f, idx_n = re.findall(r"\[(\d+)\]", path)[:2]
                ent = report["findings"][int(idx_f)]["numbers"][int(idx_n)]
                if ent.get("provenance") == "HYPOTHESIS":
                    n_hyp += 1
                    continue
            checked += 1
            if not is_verified(v, pool):
                bad.append({"value": v, "where": path, "context": f"{path} = {leaf}"})
        elif isinstance(leaf, str):
            for n in numbers_in_text(leaf):
                v = n["value"]
                if (n["decimals"] == 0 and not n["pct"] and float(v).is_integer()
                        and int(abs(v)) in IGNORED_INTS):
                    continue
                if n["hypothesis"] or is_hyp(v, n["decimals"], n["pct"]):
                    n_hyp += 1
                    continue
                checked += 1
                if not is_verified(v, pool, pct=n["pct"], decimals=n["decimals"]):
                    bad.append({"value": n["raw"], "where": path, "context": n["context"]})
    return {"checked": checked, "unverified": len(bad), "unverified_items": bad,
            "hypothesis": n_hyp}
