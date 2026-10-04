#!/usr/bin/env python3
"""Download the onion instance‑segmentation dataset from Roboflow Universe.

Usage:
    python ml/download_dataset.py --api-key YOUR_ROBOFLOW_API_KEY
    python ml/download_dataset.py --api-key YOUR_KEY --format yolov8 --version 1

The downloaded data is placed into ml/data/raw/ by default.  Run
prepare_dataset.py afterwards to create the train/val/test split.

Environment variable ROBOFLOW_API_KEY can also be used instead of --api-key.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

# Roboflow project coordinates
WORKSPACE = "yolo-custom-object-detection"
PROJECT = "instance-segmentation-wagk9"

ML_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ML_DIR / "data" / "raw"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download the onion segmentation dataset from Roboflow.",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("ROBOFLOW_API_KEY"),
        help="Roboflow API key (or set ROBOFLOW_API_KEY env var).",
    )
    parser.add_argument(
        "--format",
        default="yolov8",
        choices=["yolov8", "coco", "voc", "yolov5"],
        help="Annotation format to download (default: yolov8).",
    )
    parser.add_argument(
        "--version",
        type=int,
        default=None,
        help="Dataset version number. Omit to use the latest version.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Directory to save downloaded data (default: {DEFAULT_OUTPUT}).",
    )
    args = parser.parse_args()

    if not args.api_key:
        print(
            "ERROR: No Roboflow API key provided.\n"
            "  Pass --api-key YOUR_KEY  or  set the ROBOFLOW_API_KEY env var.\n"
            "  Get your free key at https://app.roboflow.com/settings/api",
            file=sys.stderr,
        )
        sys.exit(1)

    # ------- lazy import so the rest of the repo doesn't depend on roboflow -------
    try:
        from roboflow import Roboflow  # type: ignore[import-untyped]
    except ImportError:
        print(
            "ERROR: The 'roboflow' package is not installed.\n"
            "  Install it with:  pip install roboflow",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Connecting to Roboflow workspace '{WORKSPACE}', project '{PROJECT}' ...")
    rf = Roboflow(api_key=args.api_key)
    project = rf.workspace(WORKSPACE).project(PROJECT)

    if args.version is not None:
        version = project.version(args.version)
    else:
        versions = project.versions()
        if not versions:
            print("ERROR: No versions found for this project.", file=sys.stderr)
            sys.exit(1)
        version = versions[0]
        print(f"Using latest version: {version.version}")

    print(f"Downloading in '{args.format}' format …")
    dataset = version.download(args.format)

    # Move into our canonical output directory
    src = Path(dataset.location)
    dst = args.output_dir
    dst.mkdir(parents=True, exist_ok=True)

    for item in src.iterdir():
        target = dst / item.name
        if target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
        shutil.move(str(item), str(target))

    print(f"\n✓ Dataset saved to {dst.resolve()}")
    print("Next steps:")
    print(f"  python -m ml.prepare_dataset --input-dir {dst} --output-dir ml/data/processed")


if __name__ == "__main__":
    main()
