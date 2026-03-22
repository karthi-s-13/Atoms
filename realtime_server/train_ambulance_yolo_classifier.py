"""Train a YOLO classification model for ambulance-vs-nonambulance crops."""

from __future__ import annotations

import random
import shutil
from pathlib import Path

from ultralytics import YOLO

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE_DATASET = PROJECT_ROOT / "ambulance_dataset"
WORK_DATASET = PROJECT_ROOT / "datasets" / "ambulance_cls"
OUTPUT_DIR = PROJECT_ROOT / "models"
OUTPUT_MODEL = OUTPUT_DIR / "ambulance_yolo_cls.pt"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
SPLIT_RATIO = 0.85
SEED = 42


def gather_images(folder: Path) -> list[Path]:
    return [path for path in sorted(folder.iterdir()) if path.suffix.lower() in IMAGE_EXTENSIONS]


def reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def prepare_dataset() -> Path:
    random.seed(SEED)
    train_dir = WORK_DATASET / "train"
    val_dir = WORK_DATASET / "val"
    for split_dir in (train_dir, val_dir):
        reset_dir(split_dir)

    classes = [("ambulance", "ambulance"), ("noambulance", "noambulance")]
    for source_name, target_name in classes:
        source_dir = SOURCE_DATASET / source_name
        if not source_dir.exists():
            raise FileNotFoundError(f"Missing dataset folder: {source_dir}")

        images = gather_images(source_dir)
        random.shuffle(images)
        split_index = max(1, int(len(images) * SPLIT_RATIO))
        split_index = min(split_index, max(len(images) - 1, 1))
        train_images = images[:split_index]
        val_images = images[split_index:]

        for split_name, split_images in (("train", train_images), ("val", val_images)):
            target_dir = WORK_DATASET / split_name / target_name
            target_dir.mkdir(parents=True, exist_ok=True)
            for image_path in split_images:
                shutil.copy2(image_path, target_dir / image_path.name)

    return WORK_DATASET


def train() -> None:
    dataset_dir = prepare_dataset()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    base_model = "yolov8n-cls.pt" if Path("yolov8n-cls.pt").exists() else "yolov8n-cls.yaml"
    model = YOLO(base_model)
    model.train(
        data=str(dataset_dir),
        epochs=20,
        imgsz=224,
        batch=32,
        patience=6,
        project=str(OUTPUT_DIR),
        name="ambulance_yolo_cls_run",
        exist_ok=True,
    )

    best_model = OUTPUT_DIR / "ambulance_yolo_cls_run" / "weights" / "best.pt"
    if not best_model.exists():
        raise FileNotFoundError(f"Training finished but best model was not found at {best_model}")
    shutil.copy2(best_model, OUTPUT_MODEL)
    print(f"Saved trained classifier to {OUTPUT_MODEL}")


if __name__ == "__main__":
    train()
