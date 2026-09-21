"""Transparent case-level summaries of independently reviewed video clips."""

from __future__ import annotations

from collections import defaultdict
from statistics import median

from .prototype import relative_opening_band


SUMMARY_METRICS = (
    "tracking_coverage",
    "visible_lip_aperture",
    "mouth_width",
    "lip_aperture_mouth_width_ratio",
    "lip_aperture_eye_span_ratio",
    "relative_head_yaw",
    "relative_head_pitch",
    "relative_head_roll",
)


def summarize_case_measurements(measurements: list[dict], expected_video_ids: list[str]) -> dict:
    """Summarize latest available measurement per clip without making a prediction."""
    latest = {}
    for item in measurements:
        key = (item.get("video_id"), item.get("metric_id"))
        if item.get("video_id") and item.get("metric_id") in SUMMARY_METRICS:
            if key not in latest or str(item.get("revised_at") or "") > str(latest[key].get("revised_at") or ""):
                latest[key] = item
    grouped = defaultdict(list)
    for item in latest.values():
        if item.get("state") == "available" and item.get("value") is not None:
            grouped[item["metric_id"]].append(float(item["value"]))
    metrics = {}
    for metric, values in grouped.items():
        metrics[metric] = {
            "reviewed_clips": len(values),
            "median": float(median(values)),
            "minimum": min(values),
            "maximum": max(values),
            "unit": next(item.get("unit") for item in latest.values() if item.get("metric_id") == metric),
        }
    ratio = (metrics.get("lip_aperture_mouth_width_ratio") or {}).get("median")
    return {
        "clips_expected": len(expected_video_ids),
        "clips_with_reviewed_measurements": len({item["video_id"] for item in latest.values() if item.get("state") == "available"}),
        "metrics": metrics,
        "prototype_relative_opening_band_from_median_ratio": relative_opening_band(ratio),
        "limitation": "Cross-video descriptive summary only. It does not predict difficult intubation or replace a complete airway assessment.",
    }
