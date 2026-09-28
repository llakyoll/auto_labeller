"""GStreamer komut satırından JPEG kareleri okur."""

from __future__ import annotations

import json
import subprocess
import threading
import time
from dataclasses import dataclass


def detect_codec(url: str) -> str:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-rtsp_transport", "tcp", "-select_streams", "v:0",
             "-show_entries", "stream=codec_name", "-of", "json", url],
            capture_output=True, text=True, timeout=20, check=True,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ValueError("RTSP akışına bağlanılamadı veya codec okunamadı") from exc
    streams = json.loads(result.stdout).get("streams", [])
    codec = streams[0].get("codec_name") if streams else None
    if codec not in {"h264", "hevc", "h265"}:
        raise ValueError(f"Desteklenmeyen video codec'i: {codec or 'bulunamadı'}")
    return "h265" if codec in {"hevc", "h265"} else "h264"


def pipeline(url: str, codec: str, latency: int = 200) -> list[str]:
    if codec not in {"h264", "h265"}:
        raise ValueError("Yalnızca H.264 ve H.265 destekleniyor")
    return [
        "gst-launch-1.0", "-q", "rtspsrc", f"location={url}", "protocols=tcp",
        f"latency={latency}", "!", f"rtp{codec}depay", "!", f"{codec}parse", "!",
        f"avdec_{codec}", "!", "videoconvert", "!", "video/x-raw,format=I420", "!",
        "jpegenc", "quality=85", "!", "fdsink", "fd=1", "sync=false",
    ]


@dataclass(frozen=True)
class Frame:
    sequence: int
    jpeg: bytes
    captured_at: float


class RtspCapture:
    def __init__(self, url: str, codec: str):
        self.url = url
        self.codec = codec
        self._lock = threading.Lock()
        self._latest: Frame | None = None
        self._sequence = 0
        self._error = ""
        self._stop = threading.Event()
        self._process: subprocess.Popen | None = None
        self._thread = threading.Thread(target=self._run, daemon=True, name="rtsp-capture")

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._process and self._process.poll() is None:
            self._process.terminate()
        self._thread.join(timeout=3)

    def latest(self) -> Frame | None:
        with self._lock:
            return self._latest

    @property
    def error(self) -> str:
        with self._lock:
            return self._error

    def _run(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                self._process = subprocess.Popen(
                    pipeline(self.url, self.codec), stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL, bufsize=0,
                )
                data = bytearray()
                assert self._process.stdout is not None
                while not self._stop.is_set():
                    chunk = self._process.stdout.read(65536)
                    if not chunk:
                        break
                    data.extend(chunk)
                    while True:
                        begin = data.find(b"\xff\xd8")
                        if begin < 0:
                            data.clear()
                            break
                        if begin:
                            del data[:begin]
                        end = data.find(b"\xff\xd9", 2)
                        if end < 0:
                            break
                        jpeg = bytes(data[:end + 2])
                        del data[:end + 2]
                        with self._lock:
                            self._sequence += 1
                            self._latest = Frame(self._sequence, jpeg, time.time())
                            self._error = ""
                        backoff = 1.0
                    if len(data) > 20_000_000:
                        data.clear()
                if not self._stop.is_set():
                    with self._lock:
                        self._error = "RTSP akışı kesildi; yeniden bağlanılıyor"
            except OSError as exc:
                with self._lock:
                    self._error = f"GStreamer başlatılamadı: {exc}"
            finally:
                if self._process and self._process.poll() is None:
                    self._process.terminate()
                    try:
                        self._process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        self._process.kill()
                self._process = None
            if self._stop.wait(backoff):
                break
            backoff = min(backoff * 2, 10.0)
