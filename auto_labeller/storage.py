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
        self.relabel_dir = root / "relabel"
        self.dataset = root / "dataset"
        self._lock = threading.Lock()
        self.pending.mkdir(parents=True, exist_ok=True)
        self.relabel_dir.mkdir(parents=True, exist_ok=True)

    def add(self, jpeg: bytes, detections: list[dict], model: str) -> dict:
        candidate_id = uuid.uuid4().hex
        record = {"id": candidate_id, "model": model, "detections": detections}
        with self._lock:
            (self.pending / f"{candidate_id}.jpg").write_bytes(jpeg)
            (self.pending / f"{candidate_id}.json").write_text(
                json.dumps(record, ensure_ascii=False), encoding="utf-8"
            )
        return record

    def page(self, page: int, page_size: int = 40) -> dict:
        if page < 0 or page_size < 1:
            raise ValueError("Geçersiz aday sayfası")
        with self._lock:
            paths = sorted(self.pending.glob("*.json"),
                           key=lambda path: (path.stat().st_mtime_ns, path.name), reverse=True)
            total = len(paths)
            page = min(page, max(0, (total - 1) // page_size))
            selected = paths[page * page_size:(page + 1) * page_size]
            return {
                "items": [json.loads(path.read_text(encoding="utf-8")) for path in selected],
                "page": page,
                "page_size": page_size,
                "total": total,
            }

    def image(self, candidate_id: str) -> bytes:
        self._check_id(candidate_id)
        return (self.pending / f"{candidate_id}.jpg").read_bytes()

    def record(self, candidate_id: str) -> dict:
        self._check_id(candidate_id)
        with self._lock:
            return json.loads((self.pending / f"{candidate_id}.json").read_text(encoding="utf-8"))

    def reject(self, candidate_id: str) -> None:
        self._check_id(candidate_id)
        with self._lock:
            for suffix in (".json", ".jpg"):
                (self.pending / f"{candidate_id}{suffix}").unlink(missing_ok=True)

    def send_for_relabel(self, candidate_id: str) -> dict:
        """Adayı veri setine almadan yeniden etiketleme kuyruğuna taşır."""
        self._check_id(candidate_id)
        with self._lock:
            source_image = self.pending / f"{candidate_id}.jpg"
            source_record = self.pending / f"{candidate_id}.json"
            if not source_image.is_file() or not source_record.is_file():
                raise FileNotFoundError("Aday görseli veya tahmini bulunamadı")
            target_image = self.relabel_dir / source_image.name
            target_record = self.relabel_dir / source_record.name
            if target_image.exists() or target_record.exists():
                raise FileExistsError("Aday yeniden etiketleme klasöründe zaten var")
            os.replace(source_image, target_image)
            try:
                os.replace(source_record, target_record)
            except OSError:
                os.replace(target_image, source_image)
                raise
            return {"id": candidate_id, "image": str(target_image), "record": str(target_record)}

    def approve(self, candidate_id: str, selected: list[int]) -> dict:
        self._check_id(candidate_id)
        with self._lock:
            record = json.loads((self.pending / f"{candidate_id}.json").read_text(encoding="utf-8"))
            detections = record["detections"]
            if not isinstance(selected, list) or any(type(i) is not int or i < 0 or i >= len(detections) for i in selected):
                raise ValueError("Geçersiz kutu seçimi")
            chosen = [detections[i] for i in dict.fromkeys(selected)]
            return self._approve_locked(candidate_id, chosen)

    def approve_detections(self, candidate_id: str, detections: list[dict]) -> dict:
        self._check_id(candidate_id)
        if not isinstance(detections, list):
            raise ValueError("Kutular liste biçiminde olmalı")
        with self._lock:
            return self._approve_locked(candidate_id, detections)

    def _approve_locked(self, candidate_id: str, chosen: list[dict]) -> dict:
        image = (self.pending / f"{candidate_id}.jpg").read_bytes()
        image_dir = self.dataset / "images" / "train"
        label_dir = self.dataset / "labels" / "train"
        image_dir.mkdir(parents=True, exist_ok=True)
        label_dir.mkdir(parents=True, exist_ok=True)
        classes_file = self.dataset / "classes.txt"
        classes = classes_file.read_text(encoding="utf-8").splitlines() if classes_file.exists() else []
        labels = []
        for detection in chosen:
            if not isinstance(detection, dict):
                raise ValueError("Geçersiz kutu")
            name = detection.get("class_name")
            if not isinstance(name, str) or not name.strip():
                raise ValueError("Kutu sınıfı boş olamaz")
            name = name.strip()
            if name not in classes:
                classes.append(name)
            coordinates = detection.get("xywhn")
            if not isinstance(coordinates, list) or len(coordinates) != 4:
                raise ValueError("Geçersiz kutu koordinatı")
            x, y, w, h = coordinates
            if any(not isinstance(v, (int, float)) or not 0 <= v <= 1 for v in (x, y, w, h)):
                raise ValueError("Geçersiz kutu koordinatı")
            if w <= 0 or h <= 0:
                raise ValueError("Kutu genişliği ve yüksekliği pozitif olmalı")
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
