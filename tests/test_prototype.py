from airway.prototype import relative_opening_band


def test_relative_opening_band_is_display_only_and_deterministic():
    assert relative_opening_band(None) is None
    assert relative_opening_band(0.19) == "lower relative visual opening"
    assert relative_opening_band(0.20) == "mid relative visual opening"
    assert relative_opening_band(0.40) == "higher relative visual opening"
