"""Adayları bekletir; onaydan sonra YOLO veri setine taşır."""

from __future__ import annotations

import json
import os
import threading
import uuid
from pathlib import Path


class CandidateStore:
    def __init__(self, root: Path):
        self.root = root
        self.pending = root / "pending"
        self.dataset = root / "dataset"
        self._lock = threading.Lock()
        self.pending.mkdir(parents=True, exist_ok=True)

    def add(self, jpeg: bytes, detections: list[dict], model: str) -> dict:
        candidate_id = uuid.uuid4().hex
        record = {"id": candidate_id, "model": model, "detections": detections}
        with self._lock:
            (self.pending / f"{candidate_id}.jpg").write_bytes(jpeg)
            (self.pending / f"{candidate_id}.json").write_text(
                json.dumps(record, ensure_ascii=False), encoding="utf-8"
            )
        return record

    def list(self) -> list[dict]:
        with self._lock:
            return [json.loads(path.read_text(encoding="utf-8"))
                    for path in sorted(self.pending.glob("*.json"), reverse=True)]

    def image(self, candidate_id: str) -> bytes:
        self._check_id(candidate_id)
        return (self.pending / f"{candidate_id}.jpg").read_bytes()

    def reject(self, candidate_id: str) -> None:
        self._check_id(candidate_id)
        with self._lock:
            for suffix in (".json", ".jpg"):
                (self.pending / f"{candidate_id}{suffix}").unlink(missing_ok=True)

    def approve(self, candidate_id: str, selected: list[int]) -> dict:
        self._check_id(candidate_id)
        with self._lock:
            record = json.loads((self.pending / f"{candidate_id}.json").read_text(encoding="utf-8"))
            image = (self.pending / f"{candidate_id}.jpg").read_bytes()
            detections = record["detections"]
            if not isinstance(selected, list) or any(type(i) is not int or i < 0 or i >= len(detections) for i in selected):
                raise ValueError("Geçersiz kutu seçimi")
            chosen = [detections[i] for i in dict.fromkeys(selected)]
            image_dir = self.dataset / "images" / "train"
            label_dir = self.dataset / "labels" / "train"
            image_dir.mkdir(parents=True, exist_ok=True)
            label_dir.mkdir(parents=True, exist_ok=True)
            classes_file = self.dataset / "classes.txt"
            classes = classes_file.read_text(encoding="utf-8").splitlines() if classes_file.exists() else []
            labels = []
            for detection in chosen:
                name = detection["class_name"]
                if name not in classes:
                    classes.append(name)
                x, y, w, h = detection["xywhn"]
                if any(not isinstance(v, (int, float)) or not 0 <= v <= 1 for v in (x, y, w, h)):
                    raise ValueError("Geçersiz kutu koordinatı")
                labels.append(f"{classes.index(name)} {x:.6f} {y:.6f} {w:.6f} {h:.6f}")
            image_target = image_dir / f"{candidate_id}.jpg"
            label_target = label_dir / f"{candidate_id}.txt"
            image_temp = image_dir / f".{candidate_id}.jpg.tmp"
            label_temp = label_dir / f".{candidate_id}.txt.tmp"
            image_temp.write_bytes(image)
            label_temp.write_text("\n".join(labels) + ("\n" if labels else ""), encoding="utf-8")
            os.replace(image_temp, image_target)
            os.replace(label_temp, label_target)
            classes_file.write_text("\n".join(classes) + ("\n" if classes else ""), encoding="utf-8")
            data_yaml = (
                f"path: {json.dumps(str(self.dataset.resolve()), ensure_ascii=False)}\n"
                "train: images/train\n"
                f"names: {json.dumps(classes, ensure_ascii=False)}\n"
            )
            (self.dataset / "data.yaml").write_text(data_yaml, encoding="utf-8")
            (self.pending / f"{candidate_id}.jpg").unlink()
            (self.pending / f"{candidate_id}.json").unlink()
            return {"id": candidate_id, "image": str(image_target), "label": str(label_target), "boxes": len(chosen)}

    @staticmethod
    def _check_id(candidate_id: str) -> None:
        if len(candidate_id) != 32 or any(char not in "0123456789abcdef" for char in candidate_id):
            raise ValueError("Geçersiz aday kimliği")
