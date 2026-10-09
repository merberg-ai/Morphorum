from __future__ import annotations
import pytest
from morphorum.animation_hybrid_extract import validate_extraction
from morphorum.animation_hybrid_source import HybridSourceError

def test_extract_normal_range():
    result=validate_extraction(0, 3, 12, 10)
    assert result["estimated_frames"]==36

@pytest.mark.parametrize("start,end,fps,duration", [
    (-1,1,12,2),(1,1,12,2),(0,4,12,3),(0,10,121,10),(0,100,120,100),
    (0,float("nan"),12,10),
])
def test_extract_bounds(start,end,fps,duration):
    with pytest.raises(HybridSourceError):
        validate_extraction(start,end,fps,duration)
