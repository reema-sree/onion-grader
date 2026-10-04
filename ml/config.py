"""
ML Configuration Module.

Contains configuration constants, paths, and environment variable toggles
for the ML pipeline.
"""

import os
from pathlib import Path

# Load MOCK_MODEL from environment (default False)
MOCK_MODEL = os.getenv("MOCK_MODEL", "False").lower() in ("true", "1", "yes")

# Grading defect classes as per config/grading_rules.yaml
DEFECT_CLASSES = ['good', 'damaged', 'rotten', 'sprouted', 'undersized']

# Segmentation stage classes
YOLO_CLASSES = ['onion', 'marker']

# Paths relative to the ml directory
ML_DIR = Path(__file__).parent.absolute()
DATASET_DIR = ML_DIR / "dataset"
MODELS_DIR = ML_DIR / "models"
EXPORTS_DIR = ML_DIR / "exports"
RUNS_DIR = ML_DIR / "runs"
RESULTS_DIR = ML_DIR / "results"

# Image size
DEFAULT_IMG_SIZE = 640
