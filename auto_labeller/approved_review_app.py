"""Onaylanmış YOLO veri setini yeniden inceleme ve etiketlerini düzeltme uygulaması."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from PIL import Image, ImageTk


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CLASSES = ("nakit", "nakit_degil")


class ApprovedReviewApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("YOLO Onaylı Veri Seti İnceleme")
        self.minsize(1060, 680)
        self.geometry("1420x900")
        self.image_dir = ROOT / "dataset" / "images" / "train"
        self.label_dir = ROOT / "dataset" / "labels" / "train"
        self.classes_file = ROOT / "dataset" / "classes.txt"
        self.images: list[Path] = []
        self.class_names: list[str] = []
        self.current_path: Path | None = None
        self.image: Image.Image | None = None
        self.photo: ImageTk.PhotoImage | None = None
        self.image_rect = (0, 0, 1, 1)
        self.boxes: list[dict] = []
        self.selected_index: int | None = None
        self.dirty = False
        self._build()
        self.bind_all("<Key>", self.handle_shortcut)
        self.refresh_images()

    def _build(self) -> None:
        top = ttk.Frame(self, padding=(10, 10, 10, 0))
        top.pack(fill=tk.X)
        ttk.Label(top, text="Kısayollar: Ctrl+S kaydet · 1–9 seçili kutunun sınıfını değiştirir.").pack(side=tk.LEFT)
        ttk.Button(top, text="Listeyi yenile", command=self.refresh_images).pack(side=tk.RIGHT)
        self.save_button = ttk.Button(top, text="Kaydet (Ctrl+S)", command=self.save_labels, state=tk.DISABLED)
        self.save_button.pack(side=tk.RIGHT, padx=(0, 8))

        body = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        left = ttk.Frame(body, padding=8)
        body.add(left, weight=1)
        ttk.Label(left, text="Onaylı görseller").pack(anchor=tk.W)
        self.image_list = tk.Listbox(left, exportselection=False, width=30)
        self.image_list.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        self.image_list.bind("<<ListboxSelect>>", self.load_selected)
        self.image_count = ttk.Label(left, text="0 görsel")
        self.image_count.pack(anchor=tk.W, pady=(6, 0))

        center = ttk.Frame(body, padding=8)
        body.add(center, weight=4)
        self.canvas = tk.Canvas(center, background="#10151c", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Button-1>", self.select_box_at)
        self.canvas.bind("<Configure>", lambda _event: self.draw_image())
        self.image_info = ttk.Label(center, text="Soldan bir görsel seçin.")
        self.image_info.pack(anchor=tk.W, pady=(7, 0))

        right = ttk.Frame(body, padding=8)
        body.add(right, weight=2)
        ttk.Label(right, text="YOLO etiket kutuları").pack(anchor=tk.W)
        self.box_tree = ttk.Treeview(right, columns=("include", "class"), show="headings",
                                     selectmode="browse", height=14)
        self.box_tree.heading("include", text="Dahil")
        self.box_tree.heading("class", text="Sınıf")
        self.box_tree.column("include", width=52, stretch=False, anchor=tk.CENTER)
        self.box_tree.column("class", width=170, anchor=tk.W)
        self.box_tree.pack(fill=tk.BOTH, expand=True, pady=(6, 8))
        self.box_tree.bind("<<TreeviewSelect>>", self.select_box_from_tree)
        self.box_tree.bind("<Button-1>", self.toggle_from_tree)

        ttk.Label(right, text="Seçili kutunun sınıfı").pack(anchor=tk.W)
        self.class_var = tk.StringVar()
        self.class_combo = ttk.Combobox(right, textvariable=self.class_var, state="readonly")
        self.class_combo.pack(fill=tk.X, pady=(4, 6))
        ttk.Button(right, text="Sınıfı uygula", command=self.apply_class).pack(fill=tk.X)
        ttk.Label(right, text="İpucu: 'Dahil' sütunu kutuyu etiket dosyasından çıkarır. Görseldeki kutuya tıklayarak seçebilirsin.",
                  wraplength=250, justify=tk.LEFT).pack(anchor=tk.W, pady=(12, 0))

    def refresh_images(self) -> None:
        if not self.may_switch():
            return
        previous = self.current_path.name if self.current_path else None
        self.class_names = self.load_classes()
        self.class_combo["values"] = self.class_names
        self.images = sorted(
            [*self.image_dir.glob("*.jpg"), *self.image_dir.glob("*.jpeg"), *self.image_dir.glob("*.png")],
            key=lambda path: path.name,
        ) if self.image_dir.is_dir() else []
        self.image_list.delete(0, tk.END)
        for index, path in enumerate(self.images):
            label = self.label_dir / f"{path.stem}.txt"
            suffix = "" if label.is_file() else " · etiketsiz"
            self.image_list.insert(tk.END, f"{index + 1:04d}  {path.name}{suffix}")
        self.image_count.config(text=f"{len(self.images)} görsel")
        if not self.images:
            self.clear_current("Onaylı görsel bulunamadı.")
            return
        index = next((i for i, path in enumerate(self.images) if path.name == previous), 0)
        self.image_list.selection_set(index)
        self.image_list.activate(index)
        self.load_image(self.images[index], force=True)

    def load_classes(self) -> list[str]:
        if self.classes_file.is_file():
            classes = [name.strip() for name in self.classes_file.read_text(encoding="utf-8").splitlines() if name.strip()]
            if classes:
                return classes
        return list(DEFAULT_CLASSES)

    def load_selected(self, _event=None) -> None:
        selection = self.image_list.curselection()
        if selection:
            self.load_image(self.images[selection[0]])

    def load_image(self, path: Path, force: bool = False) -> None:
        if not force and not self.may_switch():
            self.restore_list_selection()
            return
        try:
            image = Image.open(path).convert("RGB")
            boxes = self.read_labels(path)
        except (OSError, ValueError) as error:
            messagebox.showerror("Görsel açılamadı", str(error), parent=self)
            return
        self.current_path = path
        self.image = image
        self.boxes = boxes
        self.selected_index = None
        self.dirty = False
        self.save_button.config(state=tk.DISABLED)
        self.update_box_tree()
        self.draw_image()
        self.image_info.config(text=f"{image.width} × {image.height} px · {len(boxes)} kutu · {path.name}")

    def read_labels(self, image_path: Path) -> list[dict]:
        label_path = self.label_dir / f"{image_path.stem}.txt"
        if not label_path.is_file():
            return []
        boxes = []
        for line_number, line in enumerate(label_path.read_text(encoding="utf-8").splitlines(), start=1):
            parts = line.split()
            if len(parts) != 5:
                raise ValueError(f"{label_path.name}, satır {line_number}: 5 alan bekleniyor")
            class_id = int(parts[0])
            coordinates = [float(value) for value in parts[1:]]
            if class_id < 0 or class_id >= len(self.class_names):
                raise ValueError(f"{label_path.name}, satır {line_number}: sınıf ID geçersiz")
            if any(value < 0 or value > 1 for value in coordinates) or coordinates[2] <= 0 or coordinates[3] <= 0:
                raise ValueError(f"{label_path.name}, satır {line_number}: koordinatlar geçersiz")
            boxes.append({"include": True, "class_name": self.class_names[class_id], "xywhn": coordinates})
        return boxes

    def may_switch(self) -> bool:
        if not self.dirty:
            return True
        answer = messagebox.askyesnocancel("Kaydedilmemiş değişiklik", "Değişiklikleri kaydetmek ister misin?", parent=self)
        if answer is None:
            return False
        if answer:
            return self.save_labels()
        return True

    def restore_list_selection(self) -> None:
        if not self.current_path:
            return
        index = next((i for i, path in enumerate(self.images) if path == self.current_path), None)
        if index is not None:
            self.image_list.selection_clear(0, tk.END)
            self.image_list.selection_set(index)

    def mark_dirty(self) -> None:
        self.dirty = True
        self.save_button.config(state=tk.NORMAL)

    def handle_shortcut(self, event) -> str | None:
        widget = getattr(event, "widget", None)
        if hasattr(widget, "winfo_class") and widget.winfo_class() in {"Entry", "TCombobox"}:
            return None
        key = str(getattr(event, "keysym", "")).lower()
        if key == "s" and getattr(event, "state", 0) & 0x4:
            self.save_labels()
            return "break"
        if key.isdigit() and key != "0":
            position = int(key)
            if self.selected_index is not None and position <= len(self.class_names):
                self.class_var.set(self.class_names[position - 1])
                self.apply_class()
            else:
                self.bell()
            return "break"
        return None

    def update_box_tree(self) -> None:
        self.box_tree.delete(*self.box_tree.get_children())
        for index, box in enumerate(self.boxes):
            self.box_tree.insert("", tk.END, iid=str(index), values=("✓" if box["include"] else "", box["class_name"]))
        if self.selected_index is not None and self.selected_index < len(self.boxes):
            self.box_tree.selection_set(str(self.selected_index))
            self.box_tree.focus(str(self.selected_index))
            self.class_var.set(self.boxes[self.selected_index]["class_name"])

    def select_box_from_tree(self, _event=None) -> None:
        selection = self.box_tree.selection()
        if selection:
            self.selected_index = int(selection[0])
            self.class_var.set(self.boxes[self.selected_index]["class_name"])
            self.draw_image()

    def toggle_from_tree(self, event) -> str | None:
        row = self.box_tree.identify_row(event.y)
        if row and self.box_tree.identify_column(event.x) == "#1":
            self.selected_index = int(row)
            self.boxes[self.selected_index]["include"] = not self.boxes[self.selected_index]["include"]
            self.update_box_tree()
            self.draw_image()
            self.mark_dirty()
            return "break"
        return None

    def apply_class(self) -> None:
        if self.selected_index is None:
            self.bell()
            return
        name = self.class_var.get()
        if name not in self.class_names:
            messagebox.showerror("Geçersiz sınıf", "Sınıf listesinden bir seçenek seç.", parent=self)
            return
        self.boxes[self.selected_index]["class_name"] = name
        self.boxes[self.selected_index]["include"] = True
        self.update_box_tree()
        self.draw_image()
        self.mark_dirty()

    def select_box_at(self, event) -> None:
        if not self.image or not self.boxes:
            return
        left, top, width, height = self.image_rect
        if not left <= event.x <= left + width or not top <= event.y <= top + height:
            return
        x, y = (event.x - left) / width, (event.y - top) / height
        choices = []
        for index, box in enumerate(self.boxes):
            center_x, center_y, box_width, box_height = box["xywhn"]
            if center_x - box_width / 2 <= x <= center_x + box_width / 2 and center_y - box_height / 2 <= y <= center_y + box_height / 2:
                choices.append(index)
        if choices:
            self.selected_index = min(choices, key=lambda index: self.boxes[index]["xywhn"][2] * self.boxes[index]["xywhn"][3])
            self.update_box_tree()
            self.draw_image()

    def draw_image(self) -> None:
        self.canvas.delete("all")
        if not self.image:
            return
        canvas_width, canvas_height = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        scale = min(canvas_width / self.image.width, canvas_height / self.image.height)
        width, height = max(1, round(self.image.width * scale)), max(1, round(self.image.height * scale))
        left, top = (canvas_width - width) // 2, (canvas_height - height) // 2
        self.photo = ImageTk.PhotoImage(self.image.resize((width, height), Image.Resampling.LANCZOS))
        self.canvas.create_image(left, top, image=self.photo, anchor=tk.NW)
        self.image_rect = (left, top, width, height)
        for index, box in enumerate(self.boxes):
            center_x, center_y, box_width, box_height = box["xywhn"]
            x1, y1 = left + (center_x - box_width / 2) * width, top + (center_y - box_height / 2) * height
            x2, y2 = left + (center_x + box_width / 2) * width, top + (center_y + box_height / 2) * height
            color = "#718096" if not box["include"] else "#ffd166" if index == self.selected_index else "#36f1b7"
            self.canvas.create_rectangle(x1, y1, x2, y2, outline=color, width=3)
            self.canvas.create_text(x1 + 4, max(top + 9, y1 + 10), anchor=tk.W, text=box["class_name"],
                                    fill=color, font=("TkDefaultFont", 10, "bold"))

    def save_labels(self) -> bool:
        if not self.current_path:
            return True
        try:
            self.label_dir.mkdir(parents=True, exist_ok=True)
            label_path = self.label_dir / f"{self.current_path.stem}.txt"
            rows = []
            for box in self.boxes:
                if not box["include"]:
                    continue
                class_id = self.class_names.index(box["class_name"])
                x, y, width, height = box["xywhn"]
                rows.append(f"{class_id} {x:.6f} {y:.6f} {width:.6f} {height:.6f}")
            temporary = label_path.with_suffix(".tmp")
            temporary.write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")
            temporary.replace(label_path)
        except (OSError, ValueError) as error:
            messagebox.showerror("Kaydedilemedi", str(error), parent=self)
            return False
        self.dirty = False
        self.save_button.config(state=tk.DISABLED)
        self.image_info.config(text=f"Kaydedildi · {self.current_path.name}")
        return True

    def clear_current(self, text: str) -> None:
        self.current_path = None
        self.image = None
        self.photo = None
        self.boxes = []
        self.selected_index = None
        self.dirty = False
        self.save_button.config(state=tk.DISABLED)
        self.box_tree.delete(*self.box_tree.get_children())
        self.canvas.delete("all")
        self.image_info.config(text=text)


def main() -> None:
    ApprovedReviewApp().mainloop()


if __name__ == "__main__":
    main()
