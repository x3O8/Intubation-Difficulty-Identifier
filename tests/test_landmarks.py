import pytest
from airway.landmarks import FaceLandmarkerAdapter

def test_missing_model_clear_recovery(tmp_path):
    with pytest.raises(FileNotFoundError,match="Missing local model"):
        FaceLandmarkerAdapter(tmp_path/"missing.task")
