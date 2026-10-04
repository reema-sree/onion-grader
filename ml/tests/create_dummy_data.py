"""Create a tiny dummy dataset for testing prepare_dataset.py."""
import numpy as np
import cv2
from pathlib import Path

raw = Path("ml/data/raw")
(raw / "images").mkdir(parents=True, exist_ok=True)
(raw / "labels").mkdir(parents=True, exist_ok=True)

for i in range(10):
    name = f"img_{i:03d}"
    img = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
    cv2.imwrite(str(raw / "images" / f"{name}.jpg"), img)
    (raw / "labels" / f"{name}.txt").write_text("0 0.5 0.5 0.6 0.5 0.6 0.6 0.5 0.6\n")

print(f"Created 10 dummy images+labels in {raw.resolve()}")
