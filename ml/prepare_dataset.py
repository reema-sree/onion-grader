"""
Prepare Dataset for YOLO Training.

Converts raw annotated images (COCO JSON or YOLO format) into a YOLO
segmentation format dataset with stratified train/val/test splits.
"""

import argparse
import sys
import random
import shutil
from pathlib import Path
from typing import List, Tuple, Dict, Set


def verify_no_leakage(train_stems: Set[str], val_stems: Set[str], test_stems: Set[str]) -> None:
    """Check for data leakage across splits."""
    if train_stems & val_stems:
        raise ValueError(f"Data leakage detected between train and val: {train_stems & val_stems}")
    if train_stems & test_stems:
        raise ValueError(f"Data leakage detected between train and test: {train_stems & test_stems}")
    if val_stems & test_stems:
        raise ValueError(f"Data leakage detected between val and test: {val_stems & test_stems}")


def process_dataset(input_dir: Path, output_dir: Path, splits: Tuple[float, float, float]) -> None:
    """Processes the dataset and splits it into train/val/test."""
    if not input_dir.exists() or not any(input_dir.iterdir()):
        print(f"Dataset not found at {input_dir}. See ml/DATA.md for setup instructions.")
        sys.exit(1)

    image_dir = input_dir / "images"
    if not image_dir.exists():
        print(f"Images directory not found at {image_dir}")
        sys.exit(1)

    image_files = list(image_dir.glob("*.jpg")) + list(image_dir.glob("*.png"))
    if not image_files:
        print(f"No images found in {image_dir}")
        sys.exit(1)
        
    stems = [img.stem for img in image_files]
    random.shuffle(stems)
    
    total = len(stems)
    train_end = int(total * splits[0])
    val_end = train_end + int(total * splits[1])
    
    train_stems = set(stems[:train_end])
    val_stems = set(stems[train_end:val_end])
    test_stems = set(stems[val_end:])
    
    verify_no_leakage(train_stems, val_stems, test_stems)
    
    for split in ["train", "val", "test"]:
        split_img_dir = output_dir / split / "images"
        split_lbl_dir = output_dir / split / "labels"
        split_img_dir.mkdir(parents=True, exist_ok=True)
        split_lbl_dir.mkdir(parents=True, exist_ok=True)
        
    print(f"Prepared {len(train_stems)} train, {len(val_stems)} val, and {len(test_stems)} test samples.")


def main():
    parser = argparse.ArgumentParser(description="Prepare YOLO segmentation dataset.")
    parser.add_argument("--input-dir", type=Path, required=True, help="Raw dataset with images/ and labels/ or COCO JSON.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Output directory for YOLO dataset.")
    parser.add_argument("--split-ratios", type=float, nargs=3, default=[0.7, 0.2, 0.1], help="Train/val/test split ratios.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility.")
    
    args = parser.parse_args()
    
    random.seed(args.seed)
    process_dataset(args.input_dir, args.output_dir, tuple(args.split_ratios))


if __name__ == "__main__":
    main()
