"""
YOLOv8 ONNX Export Script.

Exports a trained PyTorch model to ONNX format for production inference.
"""

import argparse
import sys
from pathlib import Path

try:
    from ultralytics import YOLO
except ImportError:
    print("Ultralytics not installed. Please run: pip install ultralytics")
    sys.exit(1)

from ml.config import DEFAULT_IMG_SIZE


def main():
    parser = argparse.ArgumentParser(description="Export YOLOv8 model to ONNX.")
    parser.add_argument("--model-path", type=Path, required=True, help="Path to trained .pt model")
    parser.add_argument("--output-path", type=Path, default=None, help="Output path for ONNX model")
    parser.add_argument("--imgsz", type=int, default=DEFAULT_IMG_SIZE, help="Image size")
    parser.add_argument("--simplify", action="store_true", help="Simplify ONNX model")
    
    args = parser.parse_args()
    
    if not args.model_path.exists():
        print(f"Model not found at {args.model_path}. Please provide a valid model path.")
        sys.exit(1)
        
    model = YOLO(args.model_path)
    exported_path = model.export(
        format="onnx",
        imgsz=args.imgsz,
        simplify=args.simplify
    )
    
    print(f"Export successful. Model saved to: {exported_path}")


if __name__ == "__main__":
    main()
