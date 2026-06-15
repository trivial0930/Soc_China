from __future__ import annotations

import argparse
from pathlib import Path

import yaml


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check YOLO image/label pairs and label values.")
    parser.add_argument("--root", default=".", help="Dataset root containing data.yaml, images/, labels/.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = Path(args.root)
    data = yaml.safe_load((root / "data.yaml").read_text())
    names = data["names"]
    class_count = len(names)
    errors: list[str] = []

    for split in ("train", "val", "test"):
        image_dir = root / "images" / split
        label_dir = root / "labels" / split
        images = sorted(p for p in image_dir.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
        labels = sorted(label_dir.glob("*.txt"))

        image_stems = {p.stem for p in images}
        label_stems = {p.stem for p in labels}
        missing_labels = image_stems - label_stems
        missing_images = label_stems - image_stems
        if missing_labels:
            errors.append(f"{split}: {len(missing_labels)} images have no label file")
        if missing_images:
            errors.append(f"{split}: {len(missing_images)} labels have no image file")

        box_count = 0
        for label in labels:
            for line_number, line in enumerate(label.read_text().splitlines(), 1):
                parts = line.split()
                if len(parts) != 5:
                    errors.append(f"{label}:{line_number}: expected 5 fields, got {len(parts)}")
                    continue
                class_id = int(float(parts[0]))
                coords = [float(value) for value in parts[1:]]
                if not 0 <= class_id < class_count:
                    errors.append(f"{label}:{line_number}: class id {class_id} outside 0..{class_count - 1}")
                if any(value < 0 or value > 1 for value in coords):
                    errors.append(f"{label}:{line_number}: coordinate outside 0..1")
                box_count += 1

        print(f"{split}: images={len(images)} labels={len(labels)} boxes={box_count}")

    if errors:
        print("\nErrors:")
        for error in errors[:50]:
            print(f"- {error}")
        raise SystemExit(1)

    print("\nDataset check passed.")


if __name__ == "__main__":
    main()
