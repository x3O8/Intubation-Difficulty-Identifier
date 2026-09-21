"""Display-only heuristics used by the proof-of-concept interface.

These helpers deliberately do not estimate physical dimensions or clinical risk.
"""

from __future__ import annotations


def relative_opening_band(aperture_over_mouth_width: float | None) -> str | None:
    """Return a readable visual band for a reviewed, dimensionless ratio.

    The breakpoints are presentation-only bins chosen for the prototype.  They
    have not been clinically calibrated and must never be interpreted as cm or
    as an airway-difficulty threshold.
    """
    if aperture_over_mouth_width is None:
        return None
    if aperture_over_mouth_width < 0.20:
        return "lower relative visual opening"
    if aperture_over_mouth_width < 0.40:
        return "mid relative visual opening"
    return "higher relative visual opening"
