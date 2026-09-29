"""Yalnızca localhost üzerinde çalışan veri toplama arayüzü."""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from .capture import RtspCapture, detect_codec
from .storage import CandidateStore


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static" / "index.html"


class Labeller:
    def __init__(self) -> None:
        self.store = CandidateStore(ROOT)
        self.lock = threading.Lock()
        self.capture: RtspCapture | None = None
        self.worker: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.model = None
        self.model_path = ""
        self.selected_classes: list[int] = []
        self.interval = 2.0
        self.confidence = 0.35
        self.collect_interval = 10.0
        self.last_saved_at = 0.0
        self.result: dict | None = None
        self.error = ""

    @staticmethod
    def load_model(model_path: str):
        model_file = Path(model_path).expanduser().resolve()
        if model_file.suffix.lower() != ".pt" or not model_file.is_file():
            raise ValueError("Var olan bir .pt model dosyası seç")
        from ultralytics import YOLO

        model = YOLO(str(model_file))
        if model.task != "detect":
            raise ValueError("Modelin object detection modeli olması gerekiyor")
        return model_file, model

    @staticmethod
    def class_options(model_path: str) -> list[dict]:
        _, model = Labeller.load_model(model_path)
        return [{"id": int(class_id), "name": name}
                for class_id, name in sorted(model.names.items())]

    def start(self, url: str, model_path: str, confidence: float, interval: float,
              collect_interval: float, selected_classes: list[int]) -> dict:
        parsed = urlsplit(url)
        if parsed.scheme not in {"rtsp", "rtsps"} or not parsed.hostname:
            raise ValueError("Geçerli bir RTSP adresi gir")
        if not 0.01 <= confidence <= 1 or not 0.2 <= interval <= 60 or not 1 <= collect_interval <= 3600:
            raise ValueError("Eşik veya aralık geçersiz")
        model_file, model = self.load_model(model_path)
        if not isinstance(selected_classes, list) or not selected_classes:
            raise ValueError("En az bir model sınıfı seç")
        if any(type(class_id) is not int or class_id not in model.names for class_id in selected_classes):
            raise ValueError("Modelde bulunmayan sınıf seçildi")
        selected_classes = list(dict.fromkeys(selected_classes))
        self.stop()
        codec = detect_codec(url)
        capture = RtspCapture(url, codec)
        with self.lock:
            self.model = model
            self.model_path = str(model_file)
            self.selected_classes = selected_classes
            self.confidence = confidence
            self.interval = interval
            self.collect_interval = collect_interval
            self.last_saved_at = 0.0
            self.result = None
            self.error = ""
            self.capture = capture
            self.stop_event = threading.Event()
            self.worker = threading.Thread(target=self._infer_loop, args=(self.stop_event,),
                                           daemon=True, name="yolo-inference")
        capture.start()
        self.worker.start()
        return {"codec": codec, "classes": {class_id: model.names[class_id]
                                            for class_id in selected_classes}}

    def stop(self) -> None:
        self.stop_event.set()
        if self.capture:
            self.capture.stop()
        if self.worker and self.worker.is_alive():
            self.worker.join(timeout=3)
        with self.lock:
            self.capture = None
            self.worker = None
            self.model = None
            self.result = None

    def status(self) -> dict:
        with self.lock:
            capture = self.capture
            result = self.result
            return {
                "running": capture is not None,
                "model": self.model_path if capture else "",
                "frame_sequence": capture.latest().sequence if capture and capture.latest() else 0,
                "camera_error": capture.error if capture else "",
                "inference_error": self.error,
                "result": {k: v for k, v in result.items() if k != "jpeg"} if result else None,
            }

    def preview(self) -> bytes | None:
        with self.lock:
            return self.result["jpeg"] if self.result else None

    def capture_candidate(self) -> dict:
        with self.lock:
            result = self.result
            model_path = self.model_path
        if not result:
            raise ValueError("Henüz işlenmiş kamera karesi yok")
        return self.store.add(result["jpeg"], result["detections"], model_path)

    def _infer_loop(self, stop_event: threading.Event) -> None:
        import cv2
        import numpy as np

        last_sequence = 0
        while not stop_event.is_set():
            capture = self.capture
            frame = capture.latest() if capture else None
            if not frame or frame.sequence == last_sequence:
                stop_event.wait(0.1)
                continue
            last_sequence = frame.sequence
            try:
                image = cv2.imdecode(np.frombuffer(frame.jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
                if image is None:
                    raise ValueError("JPEG kare çözülemedi")
                prediction = self.model.predict(
                    image, conf=self.confidence, classes=self.selected_classes,
                    device="cpu", verbose=False,
                )[0]
                detections = []
                for box in prediction.boxes:
                    class_id = int(box.cls[0].item())
                    detections.append({
                        "class_name": prediction.names[class_id],
                        "confidence": round(float(box.conf[0].item()), 4),
                        "xywhn": [round(float(v), 6) for v in box.xywhn[0].tolist()],
                    })
                result = {
                    "jpeg": frame.jpeg,
                    "sequence": frame.sequence,
                    "captured_at": frame.captured_at,
                    "detections": detections,
                }
                with self.lock:
                    self.result = result
                    self.error = ""
                now = time.monotonic()
                if detections and now - self.last_saved_at >= self.collect_interval:
                    self.store.add(frame.jpeg, detections, self.model_path)
                    self.last_saved_at = now
            except Exception as exc:
                with self.lock:
                    self.error = str(exc)
            stop_event.wait(self.interval)


LABELLER = Labeller()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:
        # RTSP kimlik bilgilerini ve gereksiz tekrarları günlükte tutma.
        pass

    def _send(self, data: bytes, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, value: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        self._send(json.dumps(value, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", status)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length < 0 or length > 65536:
            raise ValueError("İstek çok büyük")
        value = json.loads(self.rfile.read(length))
        if not isinstance(value, dict):
            raise ValueError("JSON nesnesi bekleniyor")
        return value

    def _upload_model(self) -> dict:
        encoded_name = self.headers.get("X-Model-Name", "")
        name = unquote(encoded_name).replace("\\", "/").split("/")[-1]
        if not name.lower().endswith(".pt"):
            raise ValueError("Yalnızca .pt model dosyası seçilebilir")
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 < length <= 2 * 1024 * 1024 * 1024:
            raise ValueError("Model dosyası boş veya 2 GB sınırını aşıyor")
        safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", name)[:100]
        models_dir = ROOT / "models"
        models_dir.mkdir(parents=True, exist_ok=True)
        target = models_dir / f"{uuid.uuid4().hex}_{safe_name}"
        temp = target.with_suffix(".upload")
        try:
            remaining = length
            with temp.open("wb") as output:
                while remaining:
                    chunk = self.rfile.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ValueError("Model aktarımı tamamlanmadı")
                    output.write(chunk)
                    remaining -= len(chunk)
            os.replace(temp, target)
        finally:
            temp.unlink(missing_ok=True)
        return {"path": str(target), "name": name, "size": length}

    def do_GET(self) -> None:
        request_url = urlsplit(self.path)
        path = request_url.path
        try:
            if path == "/":
                self._send(STATIC.read_bytes(), "text/html; charset=utf-8")
            elif path == "/api/status":
                self._json(LABELLER.status())
            elif path == "/api/candidates":
                page = int(parse_qs(request_url.query).get("page", ["0"])[0])
                self._json(LABELLER.store.page(page))
            elif path == "/api/frame.jpg":
                image = LABELLER.preview()
                if image is None:
                    self._json({"error": "Henüz kare yok"}, HTTPStatus.NOT_FOUND)
                else:
                    self._send(image, "image/jpeg")
            elif path.startswith("/api/candidates/") and path.endswith(".jpg"):
                candidate_id = path.split("/")[-1][:-4]
                self._send(LABELLER.store.image(candidate_id), "image/jpeg")
            else:
                self._json({"error": "Bulunamadı"}, HTTPStatus.NOT_FOUND)
        except (ValueError, FileNotFoundError) as exc:
            self._json({"error": str(exc)}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        try:
            if path == "/api/models/upload":
                self._json(self._upload_model())
                return
            body = self._body()
            if path == "/api/models/classes":
                response = LABELLER.class_options(str(body.get("model_path", "")))
            elif path == "/api/start":
                response = LABELLER.start(
                    str(body.get("url", "")), str(body.get("model_path", "")),
                    float(body.get("confidence", 0.35)), float(body.get("interval", 2)),
                    float(body.get("collect_interval", 10)), body.get("selected_classes", []),
                )
            elif path == "/api/stop":
                LABELLER.stop()
                response = {"stopped": True}
            elif path == "/api/capture":
                response = LABELLER.capture_candidate()
            elif path.startswith("/api/candidates/"):
                parts = path.split("/")
                if len(parts) != 5:
                    raise ValueError("Geçersiz adres")
                candidate_id, action = parts[3], parts[4]
                if action == "approve":
                    response = LABELLER.store.approve(candidate_id, body.get("selected", []))
                elif action == "reject":
                    LABELLER.store.reject(candidate_id)
                    response = {"rejected": candidate_id}
                else:
                    raise ValueError("Geçersiz işlem")
            else:
                self._json({"error": "Bulunamadı"}, HTTPStatus.NOT_FOUND)
                return
            self._json(response)
        except (ValueError, FileNotFoundError, IndexError, KeyError, json.JSONDecodeError) as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
    print("Yerel arayüz: http://127.0.0.1:8765", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        LABELLER.stop()
        server.server_close()


if __name__ == "__main__":
    main()
