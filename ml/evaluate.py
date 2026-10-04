"""
YOLOv8 Evaluation Script.

Evaluates a trained model and saves metrics and confusion matrix.
"""

import argparse
import json
import sys
from pathlib import Path

try:
    from ultralytics import YOLO
except ImportError:
    print("Ultralytics not installed. Please run: pip install ultralytics")
    sys.exit(1)

from ml.config import RESULTS_DIR


def main():
    parser = argparse.ArgumentParser(description="Evaluate YOLOv8 segmentation model.")
    parser.add_argument("--model-path", type=Path, required=True, help="Path to trained .pt or .onnx model")
    parser.add_argument("--data", type=Path, required=True, help="Path to YOLO data.yaml")
    parser.add_argument("--split", type=str, default="test", help="Dataset split to evaluate on")
    
    args = parser.parse_args()
    
    if not args.model_path.exists():
        print(f"Model not found at {args.model_path}. Train a model first.")
        sys.exit(1)
        
    print("These metrics are only valid if evaluated on a real test set.")
    
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    
    model = YOLO(args.model_path)
    metrics = model.val(data=str(args.data), split=args.split)
    
    results_data = {
        "mAP50": getattr(metrics.seg, 'map50', 0.0),
        "mAP50-95": getattr(metrics.seg, 'map', 0.0),
        "precision": getattr(metrics.seg, 'mp', 0.0),
        "recall": getattr(metrics.seg, 'mr', 0.0),
        "f1": getattr(metrics.seg, 'f1', 0.0)
    }
    
    with open(RESULTS_DIR / "metrics.json", "w") as f:
        json.dump(results_data, f, indent=4)
        
    # Note: Ultralytics saves the confusion matrix automatically to its run folder.
    print(f"Evaluation completed. Metrics saved to {RESULTS_DIR}")


if __name__ == "__main__":
    main()
