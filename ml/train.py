"""
YOLOv8 Training Script.

Thin wrapper to train a YOLOv8 segmentation model for onion grading.
"""

import argparse
import sys
from pathlib import Path

try:
    from ultralytics import YOLO
except ImportError:
    print("Ultralytics not installed. Please run: pip install ultralytics")
    sys.exit(1)

from ml.config import DEFAULT_IMG_SIZE, RUNS_DIR


def main():
    parser = argparse.ArgumentParser(description="Train YOLOv8 segmentation model.")
    parser.add_argument("--data", type=Path, required=True, help="Path to YOLO data.yaml")
    parser.add_argument("--model", type=str, default="yolov8n-seg.pt", help="Base model to use")
    parser.add_argument("--epochs", type=int, default=100, help="Number of training epochs")
    parser.add_argument("--imgsz", type=int, default=DEFAULT_IMG_SIZE, help="Image size")
    parser.add_argument("--batch", type=int, default=16, help="Batch size")
    parser.add_argument("--name", type=str, default="onion_seg", help="Experiment name")
    
    args = parser.parse_args()
    
    if not args.data.exists():
        print("Data config not found. Run prepare_dataset.py first.")
        sys.exit(1)
        
    print("Do NOT report metrics from this run unless trained on real labelled data.")
    
    model = YOLO(args.model)
    results = model.train(
        data=str(args.data),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        name=args.name,
        project=str(RUNS_DIR)
    )
    print(f"Training completed. Results saved to {RUNS_DIR / args.name}")


if __name__ == "__main__":
    main()
