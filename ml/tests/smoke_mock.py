"""Quick smoke test for mock inference."""
import os
os.environ["MOCK_MODEL"] = "true"

import numpy as np
from ml.inference.interface import infer

image = np.zeros((480, 640, 3), dtype=np.uint8)
result = infer(image)

print("=== Mock Inference Smoke Test ===")
print(f"  Detections: {result['total_detections']}")
print(f"  Mock flag:  {result['mock']}")
print(f"  Marker:     {result['marker_status']}")
print(f"  Classes:    {[d['class'] for d in result['detections']]}")
all_mock = all(d.get("mock") for d in result["detections"])
print(f"  All dets mock=True: {all_mock}")
assert result["mock"] is True, "Top-level mock flag should be True"
assert all_mock, "Every detection should have mock=True"
assert 5 <= result["total_detections"] <= 15
print("\nPASS: Mock inference works correctly!")
