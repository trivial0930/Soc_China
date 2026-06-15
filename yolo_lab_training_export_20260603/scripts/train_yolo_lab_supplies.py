from __future__ import annotations

import argparse
from pathlib import Path

from ultralytics import YOLO


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train YOLO on the public lab supplies dataset.")
    parser.add_argument("--data", default="data.yaml", help="Path to Ultralytics data.yaml.")
    parser.add_argument("--model", default="yolo11s.pt", help="Base model, e.g. yolo11n.pt/yolo11s.pt/yolo11m.pt.")
    parser.add_argument("--epochs", type=int, default=150)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", default="-1", help="Batch size. Use -1 for Ultralytics auto-batch.")
    parser.add_argument("--device", default="0", help="GPU id, comma-separated GPU ids, cpu, or mps.")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--patience", type=int, default=30)
    parser.add_argument("--project", default="runs/lab_supplies_public")
    parser.add_argument("--name", default=None, help="Run name. Defaults to <model>_<imgsz>.")
    parser.add_argument("--no-cache", action="store_true", help="Disable image caching.")
    parser.add_argument("--resume", default=None, help="Resume from a previous last.pt checkpoint.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--optimizer", default="auto", help="Ultralytics optimizer: auto, SGD, Adam, AdamW, etc.")
    parser.add_argument("--lr0", type=float, default=None, help="Initial learning rate. Leave unset for Ultralytics default.")
    parser.add_argument("--lrf", type=float, default=None, help="Final LR fraction. Leave unset for Ultralytics default.")
    parser.add_argument("--weight-decay", type=float, default=None, help="Weight decay. Leave unset for Ultralytics default.")
    parser.add_argument("--warmup-epochs", type=float, default=None, help="Warmup epochs. Leave unset for Ultralytics default.")
    parser.add_argument("--close-mosaic", type=int, default=20, help="Disable mosaic for the final N epochs.")
    parser.add_argument("--mosaic", type=float, default=None, help="Mosaic augmentation probability.")
    parser.add_argument("--mixup", type=float, default=None, help="MixUp augmentation probability.")
    parser.add_argument("--copy-paste", type=float, default=None, help="Copy-paste augmentation probability.")
    parser.add_argument("--degrees", type=float, default=None, help="Image rotation augmentation range in degrees.")
    parser.add_argument("--translate", type=float, default=None, help="Image translation augmentation fraction.")
    parser.add_argument("--scale", type=float, default=None, help="Image scale augmentation range.")
    parser.add_argument("--multi-scale", action="store_true", help="Train with varying image sizes.")
    parser.add_argument(
        "--extra",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Pass an additional Ultralytics train argument. May be used multiple times.",
    )
    return parser.parse_args()


def parse_batch(value: str) -> int | float:
    if value == "-1":
        return -1
    if "." in value:
        return float(value)
    return int(value)


def parse_extra_value(value: str) -> object:
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"none", "null"}:
        return None
    try:
        if "." in value or "e" in lowered:
            return float(value)
        return int(value)
    except ValueError:
        return value


def parse_extra_args(values: list[str]) -> dict[str, object]:
    parsed: dict[str, object] = {}
    for item in values:
        if "=" not in item:
            raise ValueError(f"--extra must use KEY=VALUE format, got: {item}")
        key, value = item.split("=", 1)
        parsed[key.replace("-", "_")] = parse_extra_value(value)
    return parsed


def main() -> None:
    args = parse_args()
    model_name = Path(args.model).stem
    run_name = args.name or f"{model_name}_{args.imgsz}"

    model = YOLO(args.resume or args.model)
    train_kwargs = dict(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=parse_batch(args.batch),
        device=args.device,
        workers=args.workers,
        patience=args.patience,
        project=args.project,
        name=run_name,
        pretrained=args.resume is None,
        cache=not args.no_cache,
        cos_lr=True,
        close_mosaic=args.close_mosaic,
        seed=args.seed,
        deterministic=True,
        plots=True,
        optimizer=args.optimizer,
    )
    optional_kwargs = {
        "lr0": args.lr0,
        "lrf": args.lrf,
        "weight_decay": args.weight_decay,
        "warmup_epochs": args.warmup_epochs,
        "mosaic": args.mosaic,
        "mixup": args.mixup,
        "copy_paste": args.copy_paste,
        "degrees": args.degrees,
        "translate": args.translate,
        "scale": args.scale,
    }
    train_kwargs.update({key: value for key, value in optional_kwargs.items() if value is not None})
    if args.multi_scale:
        train_kwargs["multi_scale"] = True
    train_kwargs.update(parse_extra_args(args.extra))
    if args.resume:
        train_kwargs["resume"] = True

    model.train(**train_kwargs)


if __name__ == "__main__":
    main()
