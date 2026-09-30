"""Yeniden etiketleme kuyruğundaki görselleri ve model tahminlerini gösterir."""

from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from PIL import Image, ImageTk


ROOT = Path(__file__).resolve().parents[1]


class RelabelReviewApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Yeniden Etiketleme Kuyruğu")
        self.minsize(1000, 650)
        self.geometry("1380x860")
        self.relabel_dir = ROOT / "relabel"
        self.images: list[Path] = []
        self.current_index: int | None = None
        self.image: Image.Image | None = None
        self.photo: ImageTk.PhotoImage | None = None
        self.image_rect = (0, 0, 1, 1)
        self._build()
        self.bind_all("<Left>", lambda _event: self.select_relative(-1))
        self.bind_all("<Right>", lambda _event: self.select_relative(1))
        self.refresh_images()

    def _build(self) -> None:
        top = ttk.Frame(self, padding=(10, 10, 10, 0))
        top.pack(fill=tk.X)
        ttk.Label(top, text="Yeniden etiketleme kuyruğu · ← / → görseller arasında geçiş yapar").pack(side=tk.LEFT)
        ttk.Button(top, text="Listeyi yenile", command=self.refresh_images).pack(side=tk.RIGHT)

        body = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        left = ttk.Frame(body, padding=8)
        body.add(left, weight=1)
        ttk.Label(left, text="Görseller (en yeni önce)").pack(anchor=tk.W)
        self.image_list = tk.Listbox(left, exportselection=False, width=34)
        self.image_list.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        self.image_list.bind("<<ListboxSelect>>", self.load_selected)
        self.image_count = ttk.Label(left, text="0 görsel")
        self.image_count.pack(anchor=tk.W, pady=(6, 0))

        center = ttk.Frame(body, padding=8)
        body.add(center, weight=4)
        self.canvas = tk.Canvas(center, background="#10151c", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Configure>", lambda _event: self.draw_image())
        self.image_info = ttk.Label(center, text="Soldan bir görsel seçin.")
        self.image_info.pack(anchor=tk.W, pady=(7, 0))

        right = ttk.Frame(body, padding=8)
        body.add(right, weight=1)
        ttk.Label(right, text="Model tahminleri").pack(anchor=tk.W)
        self.detection_list = tk.Listbox(right, width=30, height=15)
        self.detection_list.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        ttk.Label(right, text="Bu ekran relabel/ içindeki mevcut tahminleri görüntüler.",
                  wraplength=220, justify=tk.LEFT).pack(anchor=tk.W, pady=(10, 0))

    def refresh_images(self) -> None:
        previous = self.images[self.current_index].name if self.current_index is not None and self.images else None
        self.images = sorted(
            self.relabel_dir.glob("*.jpg"),
            key=lambda path: (path.stat().st_mtime_ns, path.name),
            reverse=True,
        ) if self.relabel_dir.is_dir() else []
        self.image_list.delete(0, tk.END)
        for index, path in enumerate(self.images):
            metadata = self.relabel_dir / f"{path.stem}.json"
            suffix = "" if metadata.is_file() else " · tahmin bilgisi yok"
            self.image_list.insert(tk.END, f"{index + 1:04d}  {path.name}{suffix}")
        self.image_count.config(text=f"{len(self.images)} görsel")
        if not self.images:
            self.current_index = None
            self.image = None
            self.photo = None
            self.canvas.delete("all")
            self.detection_list.delete(0, tk.END)
            self.image_info.config(text="relabel/ klasöründe görsel bulunamadı.")
            return
        index = next((i for i, path in enumerate(self.images) if path.name == previous), 0)
        self.select_image(index)

    def load_selected(self, _event=None) -> None:
        selected = self.image_list.curselection()
        if selected:
            self.select_image(selected[0])

    def select_relative(self, offset: int) -> str:
        if self.current_index is None or not self.images:
            return "break"
        index = self.current_index + offset
        if 0 <= index < len(self.images):
            self.select_image(index)
        else:
            self.bell()
        return "break"

    def select_image(self, index: int) -> None:
        path = self.images[index]
        try:
            image = Image.open(path).convert("RGB")
            metadata_path = self.relabel_dir / f"{path.stem}.json"
            record = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.is_file() else {}
            detections = record.get("detections", []) if isinstance(record, dict) else []
            if not isinstance(detections, list):
                detections = []
        except (OSError, ValueError, json.JSONDecodeError) as error:
            messagebox.showerror("Görsel açılamadı", str(error), parent=self)
            return
        self.current_index = index
        self.image = image
        self.image_list.selection_clear(0, tk.END)
        self.image_list.selection_set(index)
        self.image_list.activate(index)
        self.image_list.see(index)
        self.detection_list.delete(0, tk.END)
        for number, detection in enumerate(detections, start=1):
            if not isinstance(detection, dict):
                continue
            name = detection.get("class_name", "tanımsız")
            confidence = detection.get("confidence")
            confidence_text = f" · {float(confidence):.0%}" if isinstance(confidence, (int, float)) else ""
            self.detection_list.insert(tk.END, f"{number}. {name}{confidence_text}")
        self.draw_image(detections)
        model = record.get("model", "model bilgisi yok") if isinstance(record, dict) else "model bilgisi yok"
        self.image_info.config(text=f"{image.width} × {image.height} px · {len(detections)} tahmin · {model} · {path.name}")

    def draw_image(self, detections: list[dict] | None = None) -> None:
        self.canvas.delete("all")
        if self.image is None:
            return
        width = max(1, self.canvas.winfo_width())
        height = max(1, self.canvas.winfo_height())
        scale = min(width / self.image.width, height / self.image.height)
        display_width = max(1, round(self.image.width * scale))
        display_height = max(1, round(self.image.height * scale))
        left = (width - display_width) // 2
        top = (height - display_height) // 2
        self.photo = ImageTk.PhotoImage(self.image.resize((display_width, display_height), Image.Resampling.LANCZOS))
        self.canvas.create_image(left, top, image=self.photo, anchor=tk.NW)
        self.image_rect = (left, top, display_width, display_height)
        if detections is None and self.current_index is not None:
            path = self.images[self.current_index]
            metadata_path = self.relabel_dir / f"{path.stem}.json"
            try:
                record = json.loads(metadata_path.read_text(encoding="utf-8"))
                detections = record.get("detections", [])
            except (OSError, ValueError, json.JSONDecodeError):
                detections = []
        for detection in detections or []:
            if not isinstance(detection, dict):
                continue
            try:
                center_x, center_y, box_width, box_height = detection["xywhn"]
                x1 = left + (center_x - box_width / 2) * display_width
                y1 = top + (center_y - box_height / 2) * display_height
                x2 = left + (center_x + box_width / 2) * display_width
                y2 = top + (center_y + box_height / 2) * display_height
            except (KeyError, TypeError, ValueError):
                continue
            name = str(detection.get("class_name", "tanımsız"))
            confidence = detection.get("confidence")
            label = f"{name} {confidence:.0%}" if isinstance(confidence, (int, float)) else name
            self.canvas.create_rectangle(x1, y1, x2, y2, outline="#36f1b7", width=3)
            self.canvas.create_text(x1 + 4, max(top + 9, y1 + 10), anchor=tk.W, text=label,
                                    fill="#36f1b7", font=("TkDefaultFont", 10, "bold"))


def main() -> None:
    RelabelReviewApp().mainloop()


if __name__ == "__main__":
    main()
