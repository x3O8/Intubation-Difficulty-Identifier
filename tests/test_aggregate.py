from airway.aggregate import summarize_case_measurements


def test_case_summary_uses_latest_available_value_per_video():
    measurements=[
        {"video_id":"a","metric_id":"lip_aperture_mouth_width_ratio","value":0.18,"unit":"ratio","state":"available","revised_at":"2026-01-01"},
        {"video_id":"a","metric_id":"lip_aperture_mouth_width_ratio","value":0.25,"unit":"ratio","state":"available","revised_at":"2026-01-02"},
        {"video_id":"b","metric_id":"lip_aperture_mouth_width_ratio","value":0.35,"unit":"ratio","state":"available","revised_at":"2026-01-01"},
        {"video_id":"c","metric_id":"lip_aperture_mouth_width_ratio","value":None,"unit":"ratio","state":"unavailable","revised_at":"2026-01-01"},
    ]
    summary=summarize_case_measurements(measurements,["a","b","c"])
    metric=summary["metrics"]["lip_aperture_mouth_width_ratio"]
    assert summary["clips_expected"] == 3
    assert metric == {"reviewed_clips":2,"median":0.3,"minimum":0.25,"maximum":0.35,"unit":"ratio"}
    assert summary["prototype_relative_opening_band_from_median_ratio"] == "mid relative visual opening"
