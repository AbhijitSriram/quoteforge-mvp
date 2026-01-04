# backend/quote_engine.py
import math
from typing import Dict, Any, Optional

# ---- Tunable constants -------------------------------------------------

# Baseline machining rate ($/min) before any multipliers
DEFAULT_MACHINE_RATE = 2.0

# Approximate density in lb / in^3 (for weight estimation)
MATERIAL_DENSITY_LB_PER_IN3 = {
    "aluminum": 0.0975,
    "aluminium": 0.0975,
    "steel": 0.283,
    "mild steel": 0.283,
    "stainless": 0.290,
    "stainless steel": 0.290,
    "titanium": 0.160,
}

# Per-material pricing parameters:
# - material_rate_per_lb: raw stock cost, $/lb
# - machining_multiplier: how much harder it is to machine vs aluminum
MATERIAL_PARAMS = {
    "aluminum": {
        "material_rate_per_lb": 3.0,
        "machining_multiplier": 1.0,
    },
    "aluminium": {
        "material_rate_per_lb": 3.0,
        "machining_multiplier": 1.0,
    },
    "steel": {
        "material_rate_per_lb": 2.8,
        "machining_multiplier": 1.1,
    },
    "mild steel": {
        "material_rate_per_lb": 2.5,
        "machining_multiplier": 1.1,
    },
    "stainless": {
        "material_rate_per_lb": 4.5,
        "machining_multiplier": 1.25,
    },
    "stainless steel": {
        "material_rate_per_lb": 4.5,
        "machining_multiplier": 1.25,
    },
    "titanium": {
        "material_rate_per_lb": 10.0,
        "machining_multiplier": 1.5,
    },
}

# Fallback if material not recognized
DEFAULT_MATERIAL_PARAMS = {
    "material_rate_per_lb": 3.0,
    "machining_multiplier": 1.0,
}

# “Rules of thumb” machining time (per part) by complexity
COMPLEXITY_BASE_TIME_MIN = {
    "simple": 30,
    "moderate": 60,
    "complex": 120,
}

# Size scaling factor
SIZE_FACTOR = {
    "small": 1.0,
    "medium": 1.3,
    "large": 1.8,
}

# Tolerance / difficulty multiplier
TOLERANCE_FACTOR = {
    "normal": 1.0,
    "tight": 1.3,
    "aerospace": 1.7,
}


# ---- Helpers ------------------------------------------------------------

def _norm(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    return s.strip().lower() or None


def estimate_weight_lbs(inputs: Dict[str, Any]) -> Optional[float]:
    """
    Try to estimate per-part weight from length/width/height + material.
    Returns None if we don't have enough info.
    """
    if inputs.get("material_weight_lbs") is not None:
        return inputs["material_weight_lbs"]

    material = _norm(inputs.get("material"))
    if not material:
        return None

    length_in = inputs.get("length_in")
    width_in = inputs.get("width_in")
    height_in = inputs.get("height_in")

    if not (length_in and width_in and height_in):
        # Not enough geometry info
        return None

    density = MATERIAL_DENSITY_LB_PER_IN3.get(material)
    if density is None:
        return None

    volume_in3 = float(length_in) * float(width_in) * float(height_in)
    weight = volume_in3 * density
    return round(weight, 2)


def estimate_machining_minutes(inputs: Dict[str, Any]) -> Optional[int]:
    """
    Estimate per-part machining time from complexity + size.
    """
    if inputs.get("machining_minutes") is not None:
        return int(inputs["machining_minutes"])

    complexity = _norm(inputs.get("complexity")) or "moderate"
    size = _norm(inputs.get("size")) or "medium"

    base = COMPLEXITY_BASE_TIME_MIN.get(complexity)
    size_mult = SIZE_FACTOR.get(size, 1.0)

    if base is None:
        return None

    est = base * size_mult
    return int(round(est))


def extract_signals(text: str) -> Dict[str, Any]:
    """
    Very lightweight text-based extraction (Phase 2 still mostly uses
    user inputs, but we keep this for future improvements).
    """
    t = (text or "").lower()
    material = None
    for m in ["aluminum", "aluminium", "stainless", "mild steel", "steel", "titanium"]:
        if m in t:
            material = m
            break

    qty = 1

    return {
        "material": material,
        "qty": qty,
        "raw_text_preview": text[:1200],
        "notes": "",
    }



def extract_signals_from_text(text: str) -> Dict[str, Any]:
    """
    Compatibility wrapper for main.py.

    main.py imports `extract_signals_from_text`, so we keep that name
    and delegate to `extract_signals`.
    """
    return extract_signals(text or "")

def compute_estimate(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Phase-2 estimating engine.

    - Fills in missing machining_minutes and material_weight_lbs using rules.
    - Applies multipliers for complexity, size, tolerance, and MATERIAL TYPE.
    - Returns either:
        { ready: False, missing_inputs: [...], ... }
      or
        { ready: True, cost_usd: ..., breakdown: {...}, ... }
    """
    # Normalize + defaults
    inputs = dict(inputs)  # copy
    inputs["material"] = _norm(inputs.get("material"))
    inputs["complexity"] = _norm(inputs.get("complexity")) or "moderate"
    inputs["size"] = _norm(inputs.get("size")) or "medium"
    inputs["tolerance"] = _norm(inputs.get("tolerance")) or "normal"

    qty = inputs.get("qty") or 1
    try:
        qty = int(qty)
    except Exception:
        qty = 1
    inputs["qty"] = qty

    missing: list[str] = []
    inferred: Dict[str, Any] = {}
    confidence = "high"

    # Material is required (we don't guess it)
    if not inputs["material"]:
        missing.append("material")

    # Try to infer machining_minutes
    mm = inputs.get("machining_minutes")
    if mm is None:
        mm = estimate_machining_minutes(inputs)
        if mm is not None:
            inputs["machining_minutes"] = mm
            inferred["machining_minutes"] = mm
            confidence = "medium"
        else:
            missing.append("machining_minutes")
    else:
        inputs["machining_minutes"] = float(mm)

    # Try to infer material_weight_lbs
    wt = inputs.get("material_weight_lbs")
    if wt is None:
        wt = estimate_weight_lbs(inputs)
        if wt is not None:
            inputs["material_weight_lbs"] = wt
            inferred["material_weight_lbs"] = wt
            confidence = "medium"
        else:
            missing.append("material_weight_lbs")
    else:
        inputs["material_weight_lbs"] = float(wt)

    # If still missing key stuff, return "not ready"
    if missing or not inputs["material"]:
        return {
            "ready": False,
            "missing_inputs": missing,
            "message": "Need a few more details to generate a quote.",
            "confidence": confidence,
            "inferred": inferred,
        }

    # ---- Pricing math ---------------------------------------------------

    machining_minutes_each = float(inputs["machining_minutes"])
    material_weight_lbs_each = float(inputs["material_weight_lbs"])
    material_key = inputs["material"] or ""

    # complexity + tolerance
    complexity_factor = {
        "simple": 1.0,
        "moderate": 1.15,
        "complex": 1.4,
    }.get(inputs["complexity"], 1.15)

    tolerance_factor = TOLERANCE_FACTOR.get(inputs["tolerance"], 1.0)

    # per-material parameters
    mat_params = MATERIAL_PARAMS.get(material_key, DEFAULT_MATERIAL_PARAMS)
    material_rate_per_lb = mat_params["material_rate_per_lb"]
    material_machining_mult = mat_params["machining_multiplier"]

    # Machine rate adjusted for complexity, tolerance AND material
    machine_rate = (
        DEFAULT_MACHINE_RATE
        * complexity_factor
        * tolerance_factor
        * material_machining_mult
    )

    machining_cost_each = machining_minutes_each * machine_rate
    material_cost_each = material_weight_lbs_each * material_rate_per_lb

    subtotal_each = machining_cost_each + material_cost_each

    # Overall multiplier for overhead / profit
    overhead_multiplier = 1.25
    total_each = subtotal_each * overhead_multiplier
    total_all = total_each * qty

    # Simple lead time heuristic:
    #   - base from machining_minutes
    #   - then bump a bit for "hard" materials
    if machining_minutes_each <= 45:
        base_lead = 3
    elif machining_minutes_each <= 90:
        base_lead = 5
    else:
        base_lead = 7

    material_lead_bump = 0
    if "stainless" in material_key:
        material_lead_bump = 1
    if "titanium" in material_key:
        material_lead_bump = 2

    lead_time_days = base_lead + material_lead_bump

    # If we inferred important things, lower confidence
    if inferred and confidence == "high":
        confidence = "medium"
    if "machining_minutes" in inferred and "material_weight_lbs" in inferred:
        confidence = "low"

    return {
        "ready": True,
        "cost_usd": round(total_all, 2),
        "lead_time_days": int(lead_time_days),
        "confidence": confidence,
        "inferred": inferred,
        "breakdown": {
            "qty": qty,
            "material": material_key,
            "machining_minutes_each": round(machining_minutes_each, 2),
            "material_weight_lbs_each": round(material_weight_lbs_each, 2),
            "base_machine_rate_per_min": DEFAULT_MACHINE_RATE,
            "complexity_factor": round(complexity_factor, 3),
            "tolerance_factor": round(tolerance_factor, 3),
            "material_machining_multiplier": round(material_machining_mult, 3),
            "machine_rate_per_min": round(machine_rate, 2),
            "material_rate_per_lb": round(material_rate_per_lb, 2),
            "machining_cost_each": round(machining_cost_each, 2),
            "material_cost_each": round(material_cost_each, 2),
            "subtotal_each": round(subtotal_each, 2),
            "multiplier": overhead_multiplier,
            "total_each": round(total_each, 2),
            "total_all": round(total_all, 2),
        },
    }
