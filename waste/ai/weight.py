"""Waste weight estimates based on declared quantities."""

# Valeurs indicatives à valider par pesée.
WEIGHT_REFERENCE = {
    "organic": {"liter": (0.3, 0.7), "item": (0.1, 0.5), "bag": (1.0, 3.0)},
    "plastic": {"liter": (0.05, 0.15), "item": (0.02, 0.2), "bag": (0.2, 1.0)},
    "mixed": {"liter": (0.2, 0.5), "item": (0.1, 0.5), "bag": (0.8, 2.5)},
    "not_accepted": {"liter": (0.2, 0.8), "item": (0.1, 1.0), "bag": (1.0, 5.0)},
}


def estimate_weight(waste_type, quantity):
    """Return a conservative min/max kilogram range for a quantity."""
    if not isinstance(quantity, dict):
        return None
    value = quantity.get("value")
    unit = quantity.get("unit")
    if value is None or unit is None:
        return None
    if unit == "kg":
        return (float(value), float(value))
    reference = WEIGHT_REFERENCE.get(waste_type, {}).get(unit)
    if reference is None:
        return None
    return (float(value) * reference[0], float(value) * reference[1])
