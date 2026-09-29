"""Bekleyen YOLO adaylarını insan onayıyla veri setine ekleyen masaüstü uygulaması."""

from __future__ import annotations

import io
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from PIL import Image, ImageTk

from .storage import CandidateStore


ROOT = Path(__file__).resolve().parents[1]
CLASS_NAMES = ("nakit", "nakit_degil")


class ReviewApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("YOLO Aday İnceleme")
        self.minsize(1060, 680)
        self.geometry("1420x900")
        self.store = CandidateStore(ROOT)
        self.candidates: list[dict] = []
        self.current: dict | None = None
        self.boxes: list[dict] = []
        self.class_names: list[str] = []
        self.image: Image.Image | None = None
        self.photo: ImageTk.PhotoImage | None = None
        self.image_rect = (0, 0, 1, 1)
        self.selected_index: int | None = None
        self.undo_action: dict | None = None
        self._build()
        self.bind_all("<Key>", self.handle_shortcut)
        self.refresh_candidates()

    def _build(self) -> None:
        top = ttk.Frame(self, padding=(10, 10, 10, 0))
        top.pack(fill=tk.X)
        ttk.Label(top, text="Kısayollar: A onayla · R reddet · E yeniden etiketle · Ctrl+Z geri al · 1–9 sınıf değiştir.").pack(side=tk.LEFT)
        self.undo_button = ttk.Button(top, text="Geri al (Ctrl+Z)", command=self.undo_last_action, state=tk.DISABLED)
        self.undo_button.pack(side=tk.RIGHT, padx=(0, 8))
        ttk.Button(top, text="Listeyi yenile", command=self.refresh_candidates).pack(side=tk.RIGHT)

        body = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        left = ttk.Frame(body, padding=8)
        body.add(left, weight=1)
        ttk.Label(left, text="Bekleyen adaylar").pack(anchor=tk.W)
        self.candidate_list = tk.Listbox(left, exportselection=False, width=27)
        self.candidate_list.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        self.candidate_list.bind("<<ListboxSelect>>", self.load_selected)
        self.candidate_count = ttk.Label(left, text="0 aday")
        self.candidate_count.pack(anchor=tk.W, pady=(6, 0))

        center = ttk.Frame(body, padding=8)
        body.add(center, weight=4)
        self.canvas = tk.Canvas(center, background="#10151c", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Button-1>", self.select_box_at)
        self.canvas.bind("<Configure>", lambda _event: self.draw_image())
        self.image_info = ttk.Label(center, text="Soldan bir aday seçin.")
        self.image_info.pack(anchor=tk.W, pady=(7, 0))

        right = ttk.Frame(body, padding=8)
        body.add(right, weight=2)
        ttk.Label(right, text="Tespit edilen kutular").pack(anchor=tk.W)
        self.box_tree = ttk.Treeview(right, columns=("include", "class", "confidence"),
                                     show="headings", selectmode="browse", height=14)
        self.box_tree.heading("include", text="Dahil")
        self.box_tree.heading("class", text="Sınıf")
        self.box_tree.heading("confidence", text="Güven")
        self.box_tree.column("include", width=52, stretch=False, anchor=tk.CENTER)
        self.box_tree.column("class", width=150, anchor=tk.W)
        self.box_tree.column("confidence", width=60, stretch=False, anchor=tk.E)
        self.box_tree.pack(fill=tk.BOTH, expand=True, pady=(6, 8))
        self.box_tree.bind("<<TreeviewSelect>>", self.select_box_from_tree)
        self.box_tree.bind("<Button-1>", self.toggle_from_tree)

        ttk.Label(right, text="Seçili kutunun sınıfı").pack(anchor=tk.W)
        self.class_var = tk.StringVar()
        self.class_combo = ttk.Combobox(right, textvariable=self.class_var, state="readonly")
        self.class_combo.pack(fill=tk.X, pady=(4, 6))
        ttk.Button(right, text="Sınıfı uygula", command=self.apply_class).pack(fill=tk.X)
        ttk.Label(right, text="İpucu: 'Dahil' sütununa tıklayarak kutuyu çıkarabilir, görselde kutuya tıklayarak seçebilirsin. 1–9, listedeki sınıf sırasını kullanır.",
                  wraplength=250, justify=tk.LEFT).pack(anchor=tk.W, pady=(12, 0))

        actions = ttk.Frame(right)
        actions.pack(fill=tk.X, side=tk.BOTTOM, pady=(20, 0))
        ttk.Button(actions, text="Yeniden etiketlemeye gönder", command=self.send_for_relabel).pack(fill=tk.X)
        ttk.Button(actions, text="Reddet", command=self.reject, style="Danger.TButton").pack(fill=tk.X)
        ttk.Button(actions, text="Onayla ve veri setine ekle", command=self.approve).pack(fill=tk.X, pady=(8, 0))

        style = ttk.Style(self)
        style.configure("Danger.TButton", foreground="#9b1c1c")

    def refresh_candidates(self) -> None:
        self.candidates = []
        page = 0
        while True:
            result = self.store.page(page, page_size=100)
            self.candidates.extend(result["items"])
            if (page + 1) * result["page_size"] >= result["total"]:
                break
            page += 1
        previous = self.current["id"] if self.current else None
        self.candidate_list.delete(0, tk.END)
        for index, candidate in enumerate(self.candidates):
            self.candidate_list.insert(tk.END, f"{index + 1:04d}  {candidate['id'][:10]}  ({len(candidate['detections'])} kutu)")
        self.candidate_count.config(text=f"{len(self.candidates)} aday")
        if not self.candidates:
            self.clear_current("Bekleyen aday yok.")
            return
        index = next((i for i, item in enumerate(self.candidates) if item["id"] == previous), 0)
        self.candidate_list.selection_clear(0, tk.END)
        self.candidate_list.selection_set(index)
        self.candidate_list.activate(index)
        self.load_candidate(self.candidates[index])

    def load_selected(self, _event=None) -> None:
        selection = self.candidate_list.curselection()
        if selection:
            self.load_candidate(self.candidates[selection[0]])

    def load_candidate(self, candidate: dict) -> None:
        try:
            record = self.store.record(candidate["id"])
            image = Image.open(io.BytesIO(self.store.image(candidate["id"]))).convert("RGB")
        except (FileNotFoundError, OSError, ValueError) as error:
            messagebox.showerror("Aday açılamadı", str(error), parent=self)
            self.refresh_candidates()
            return
        self.current = record
        self.image = image
        self.boxes = [
            {"include": True, "class_name": str(box["class_name"]),
             "confidence": float(box.get("confidence", 0)), "xywhn": list(box["xywhn"])}
            for box in record["detections"]
        ]
        self.class_names = list(CLASS_NAMES)
        self.class_combo["values"] = self.class_names
        self.selected_index = None
        self.update_box_tree()
        self.draw_image()
        self.image_info.config(text=f"{image.width} × {image.height} px · {len(self.boxes)} kutu · {candidate['id']}")

    def handle_shortcut(self, event) -> str | None:
        """Text entry fields keep their own keystrokes; the review surface gets shortcuts."""
        widget = getattr(event, "widget", None)
        widget_class = widget.winfo_class() if hasattr(widget, "winfo_class") else ""
        if widget_class in {"Entry", "TCombobox"}:
            return None
        key = str(getattr(event, "keysym", "")).lower()
        if key == "z" and getattr(event, "state", 0) & 0x4:
            self.undo_last_action()
            return "break"
        if key == "a":
            self.approve(announce=False)
            return "break"
        if key == "r":
            self.reject(confirm=False)
            return "break"
        if key == "e":
            self.send_for_relabel()
            return "break"
        if key.isdigit() and key != "0":
            self.apply_shortcut_class(int(key))
            return "break"
        return None

    def apply_shortcut_class(self, position: int) -> None:
        if self.selected_index is None:
            self.bell()
            return
        if position > len(self.class_names):
            self.bell()
            return
        self.class_var.set(self.class_names[position - 1])
        self.apply_class()

    def update_box_tree(self) -> None:
        self.box_tree.delete(*self.box_tree.get_children())
        for index, box in enumerate(self.boxes):
            self.box_tree.insert("", tk.END, iid=str(index), values=("✓" if box["include"] else "", box["class_name"],
                                                                  f"{box['confidence']:.0%}"))
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

    def toggle_from_tree(self, event) -> None:
        row = self.box_tree.identify_row(event.y)
        column = self.box_tree.identify_column(event.x)
        if row and column == "#1":
            index = int(row)
            self.boxes[index]["include"] = not self.boxes[index]["include"]
            self.selected_index = index
            self.update_box_tree()
            self.draw_image()
            return "break"
        return None

    def apply_class(self) -> None:
        if self.selected_index is None:
            messagebox.showinfo("Kutu seç", "Önce listeden veya görselden bir kutu seç.", parent=self)
            return
        name = self.class_var.get().strip()
        if name not in CLASS_NAMES:
            messagebox.showerror("Geçersiz sınıf", "Yalnızca nakit veya nakit_degil seçilebilir.", parent=self)
            return
        self.boxes[self.selected_index]["class_name"] = name
        self.boxes[self.selected_index]["include"] = True
        self.update_box_tree()
        self.draw_image()

    def select_box_at(self, event) -> None:
        if not self.image or not self.boxes:
            return
        left, top, display_width, display_height = self.image_rect
        x, y = event.x, event.y
        if not left <= x <= left + display_width or not top <= y <= top + display_height:
            return
        normalized_x = (x - left) / display_width
        normalized_y = (y - top) / display_height
        matches = []
        for index, box in enumerate(self.boxes):
            center_x, center_y, width, height = box["xywhn"]
            if center_x - width / 2 <= normalized_x <= center_x + width / 2 and center_y - height / 2 <= normalized_y <= center_y + height / 2:
                matches.append(index)
        if matches:
            self.selected_index = min(matches, key=lambda index: self.boxes[index]["xywhn"][2] * self.boxes[index]["xywhn"][3])
            self.update_box_tree()
            self.draw_image()

    def draw_image(self) -> None:
        self.canvas.delete("all")
        if not self.image:
            return
        canvas_width = max(1, self.canvas.winfo_width())
        canvas_height = max(1, self.canvas.winfo_height())
        scale = min(canvas_width / self.image.width, canvas_height / self.image.height)
        display_width = max(1, round(self.image.width * scale))
        display_height = max(1, round(self.image.height * scale))
        left = (canvas_width - display_width) // 2
        top = (canvas_height - display_height) // 2
        display = self.image.resize((display_width, display_height), Image.Resampling.LANCZOS)
        self.photo = ImageTk.PhotoImage(display)
        self.canvas.create_image(left, top, image=self.photo, anchor=tk.NW)
        self.image_rect = (left, top, display_width, display_height)
        for index, box in enumerate(self.boxes):
            center_x, center_y, width, height = box["xywhn"]
            x1 = left + (center_x - width / 2) * display_width
            y1 = top + (center_y - height / 2) * display_height
            x2 = left + (center_x + width / 2) * display_width
            y2 = top + (center_y + height / 2) * display_height
            if not box["include"]:
                color = "#718096"
            elif index == self.selected_index:
                color = "#ffd166"
            else:
                color = "#36f1b7"
            self.canvas.create_rectangle(x1, y1, x2, y2, outline=color, width=3)
            self.canvas.create_text(x1 + 4, max(top + 9, y1 + 10), anchor=tk.W,
                                    text=box["class_name"], fill=color, font=("TkDefaultFont", 10, "bold"))

    def approve(self, announce: bool = True) -> None:
        if not self.current:
            return
        snapshot = self.snapshot_current()
        if snapshot is None:
            return
        chosen = [{"class_name": box["class_name"], "xywhn": box["xywhn"]}
                  for box in self.boxes if box["include"]]
        try:
            result = self.store.approve_detections(self.current["id"], chosen)
        except (OSError, ValueError) as error:
            messagebox.showerror("Onaylanamadı", str(error), parent=self)
            return
        self.set_undo_action({"kind": "approve", "record": snapshot[0], "image": snapshot[1]})
        if announce:
            messagebox.showinfo("Veri setine eklendi", f"{result['boxes']} kutu onaylandı.", parent=self)
        self.current = None
        self.refresh_candidates()

    def reject(self, confirm: bool = True) -> None:
        if not self.current:
            return
        if confirm and not messagebox.askyesno("Adayı reddet", "Bu aday ve tahminleri silinsin mi?", parent=self):
            return
        snapshot = self.snapshot_current()
        if snapshot is None:
            return
        try:
            self.store.reject(self.current["id"])
        except (OSError, ValueError) as error:
            messagebox.showerror("Reddedilemedi", str(error), parent=self)
            return
        self.set_undo_action({"kind": "reject", "record": snapshot[0], "image": snapshot[1]})
        self.current = None
        self.refresh_candidates()

    def send_for_relabel(self) -> None:
        if not self.current:
            return
        try:
            candidate_id = self.current["id"]
            self.store.send_for_relabel(candidate_id)
        except (OSError, ValueError) as error:
            messagebox.showerror("Taşınamadı", str(error), parent=self)
            return
        self.set_undo_action({"kind": "relabel", "candidate_id": candidate_id})
        self.current = None
        self.refresh_candidates()

    def snapshot_current(self) -> tuple[dict, bytes] | None:
        if not self.current:
            return None
        try:
            return self.current.copy(), self.store.image(self.current["id"])
        except (OSError, ValueError) as error:
            messagebox.showerror("Aday okunamadı", str(error), parent=self)
            return None

    def set_undo_action(self, action: dict) -> None:
        self.undo_action = action
        self.undo_button.config(state=tk.NORMAL)

    def undo_last_action(self) -> None:
        action = self.undo_action
        if action is None:
            self.bell()
            return
        try:
            if action["kind"] == "approve":
                self.store.undo_approval(action["record"]["id"], action["record"], action["image"])
            elif action["kind"] == "reject":
                self.store.restore_pending(action["record"], action["image"])
            elif action["kind"] == "relabel":
                self.store.undo_relabel(action["candidate_id"])
            else:
                raise ValueError("Bilinmeyen geri alma işlemi")
        except (OSError, ValueError) as error:
            messagebox.showerror("Geri alınamadı", str(error), parent=self)
            return
        self.undo_action = None
        self.undo_button.config(state=tk.DISABLED)
        self.current = None
        self.refresh_candidates()

    def clear_current(self, text: str) -> None:
        self.current = None
        self.boxes = []
        self.image = None
        self.photo = None
        self.selected_index = None
        self.box_tree.delete(*self.box_tree.get_children())
        self.canvas.delete("all")
        self.image_info.config(text=text)


def main() -> None:
    ReviewApp().mainloop()


if __name__ == "__main__":
    main()
