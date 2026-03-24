import json
import threading
import tkinter as tk
from math import ceil
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any

import customtkinter as ctk

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


# ── JSON helpers ──────────────────────────────────────────────────────────────

def flatten_json(data: Any, prefix: str = "") -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if isinstance(data, dict):
        for key, value in data.items():
            path = f"{prefix}.{key}" if prefix else key
            items.extend(flatten_json(value, path))
    elif isinstance(data, list):
        for i, value in enumerate(data):
            items.extend(flatten_json(value, f"{prefix}[{i}]"))
    else:
        items.append({"path": prefix, "value": data})
    return items


def format_item_label(path: str, value: Any, max_length: int = 100) -> str:
    value_text = str(value).replace("\n", "\\n")
    if len(value_text) > max_length:
        value_text = f"{value_text[: max_length - 1]}…"
    return f"{path}  =  {value_text}"


def tokenize_path(path: str) -> list[str | int]:
    tokens: list[str | int] = []
    current = ""
    i = 0
    while i < len(path):
        c = path[i]
        if c == ".":
            if current:
                tokens.append(current)
                current = ""
        elif c == "[":
            if current:
                tokens.append(current)
                current = ""
            j = path.find("]", i)
            tokens.append(int(path[i + 1 : j]))
            i = j
        else:
            current += c
        i += 1
    if current:
        tokens.append(current)
    return tokens


def insert_path(target: dict[str, Any], path: str, value: Any) -> None:
    tokens = tokenize_path(path)
    if not tokens:
        return
    current: Any = target
    for idx, token in enumerate(tokens):
        is_last = idx == len(tokens) - 1
        next_token = tokens[idx + 1] if not is_last else None
        if isinstance(token, str):
            if is_last:
                current[token] = value
                return
            if token not in current or not isinstance(current[token], (dict, list)):
                current[token] = [] if isinstance(next_token, int) else {}
            current = current[token]
        else:
            while len(current) <= token:
                current.append(None)
            if is_last:
                current[token] = value
                return
            if current[token] is None:
                current[token] = [] if isinstance(next_token, int) else {}
            current = current[token]


def build_custom_json(
    selected_paths: set[str], value_map: dict[str, Any], ordered_paths: list[str]
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for path in ordered_paths:
        if path in value_map:
            if path in selected_paths:
                insert_path(result, path, value_map[path])
    return result


def make_output_filename(name: str) -> str:
    p = Path(name)
    return f"{p.stem}+custom.json" if p.suffix.lower() == ".json" else f"{p.name}+custom.json"


def load_json_file(path: str) -> Any:
    # utf-8-sig transparently handles UTF-8 BOM and normal UTF-8.
    with open(path, encoding="utf-8-sig") as fh:
        return json.load(fh)


# ── App ───────────────────────────────────────────────────────────────────────

class App(ctk.CTk):
    _BATCH_SIZE = 40
    _PAGE_SIZE = 200

    def __init__(self) -> None:
        super().__init__()
        self.title("Custom i18n Key Builder")
        self.geometry("1200x720")
        self.minsize(900, 580)

        self._source_file: str = ""
        self._flat_items: list[dict[str, Any]] = []
        self._flat_item_order: list[str] = []
        self._value_map: dict[str, Any] = {}
        self._filtered_items: list[dict[str, Any]] = []
        self._selected_paths: set[str] = set()
        self._page_index: int = 0
        self._existing_file: str = ""
        self._existing_data: dict[str, Any] | None = None
        # each entry: (checkbox_widget, bool_var, key_path)
        self._check_items: list[tuple[ctk.CTkCheckBox, tk.BooleanVar, str]] = []
        # debounce handles
        self._search_debounce_id: str | None = None
        self._preview_debounce_id: str | None = None
        # track batch build so stale batches can be cancelled
        self._build_generation: int = 0
        self._preview_generation: int = 0
        # spinner state
        self._spinner_id: str | None = None
        self._is_loading: bool = False

        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)  # row 4 = main pane

        # File row
        file_row = ctk.CTkFrame(self)
        file_row.grid(row=0, column=0, padx=16, pady=(16, 0), sticky="ew")
        file_row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(file_row, text="File:", width=50).grid(
            row=0, column=0, padx=(12, 6), pady=10
        )
        self._file_label = ctk.CTkLabel(
            file_row, text="ยังไม่ได้เลือกไฟล์", anchor="w", text_color="gray"
        )
        self._file_label.grid(row=0, column=1, padx=6, pady=10, sticky="ew")
        self._browse_btn = ctk.CTkButton(
            file_row, text="Browse…", width=90, command=self._browse
        )
        self._browse_btn.grid(row=0, column=2, padx=12, pady=10)

        # Existing-file row
        existing_row = ctk.CTkFrame(self)
        existing_row.grid(row=1, column=0, padx=16, pady=(4, 0), sticky="ew")
        existing_row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(existing_row, text="Update:", width=50).grid(
            row=0, column=0, padx=(12, 6), pady=10
        )

        self._existing_file_label = ctk.CTkLabel(
            existing_row,
            text="update จากไฟล์เก่า",
            text_color="gray",
            anchor="w",
        )
        self._existing_file_label.grid(row=0, column=1, padx=6, pady=10, sticky="ew")

        self._choose_existing_btn = ctk.CTkButton(
            existing_row,
            text="Browse…",
            width=90,
            command=self._choose_existing_file,
            state="disabled",
        )
        self._choose_existing_btn.grid(row=0, column=2, padx=12, pady=10)

        # Progress bar (indeterminate spinner) — hidden by default
        self._progress_bar = ctk.CTkProgressBar(self, mode="indeterminate", height=6)
        self._progress_bar.grid(row=2, column=0, padx=16, pady=0, sticky="ew")
        self._progress_bar.grid_remove()  # hidden until loading

        # Search + bulk-select row
        ctrl_row = ctk.CTkFrame(self)
        ctrl_row.grid(row=3, column=0, padx=16, pady=4, sticky="ew")
        ctrl_row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(ctrl_row, text="Search:", width=50).grid(
            row=0, column=0, padx=(12, 6), pady=10
        )
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._schedule_filter())
        ctk.CTkEntry(
            ctrl_row,
            textvariable=self._search_var,
            placeholder_text="ค้นหา key หรือ value…",
        ).grid(row=0, column=1, padx=6, pady=10, sticky="ew")
        ctk.CTkButton(
            ctrl_row, text="Select All", width=110, command=self._select_all
        ).grid(row=0, column=2, padx=6, pady=10)
        ctk.CTkButton(
            ctrl_row,
            text="Clear",
            width=80,
            fg_color="#555",
            hover_color="#444",
            command=self._clear_all,
        ).grid(row=0, column=3, padx=(0, 12), pady=10)

        # Main pane: key list (left) | preview (right)
        pane = ctk.CTkFrame(self, fg_color="transparent")
        pane.grid(row=4, column=0, padx=16, pady=4, sticky="nsew")
        pane.grid_columnconfigure(0, weight=2)
        pane.grid_columnconfigure(1, weight=3)
        pane.grid_rowconfigure(0, weight=1)

        # Left: scrollable checkbox list
        left = ctk.CTkFrame(pane)
        left.grid(row=0, column=0, padx=(0, 6), sticky="nsew")
        left.grid_rowconfigure(2, weight=1)
        left.grid_columnconfigure(0, weight=1)

        self._count_label = ctk.CTkLabel(left, text="Keys: –")
        self._count_label.grid(row=0, column=0, padx=12, pady=(10, 4), sticky="w")

        nav = ctk.CTkFrame(left, fg_color="transparent")
        nav.grid(row=1, column=0, padx=8, pady=(0, 4), sticky="ew")
        nav.grid_columnconfigure(1, weight=1)

        self._prev_btn = ctk.CTkButton(
            nav, text="< Prev", width=70, command=lambda: self._change_page(-1)
        )
        self._prev_btn.grid(row=0, column=0, padx=(4, 6), pady=2, sticky="w")

        self._page_label = ctk.CTkLabel(nav, text="Page 0/0", anchor="center")
        self._page_label.grid(row=0, column=1, padx=6, pady=2, sticky="ew")

        self._next_btn = ctk.CTkButton(
            nav, text="Next >", width=70, command=lambda: self._change_page(1)
        )
        self._next_btn.grid(row=0, column=2, padx=(6, 4), pady=2, sticky="e")

        self._scroll = ctk.CTkScrollableFrame(left)
        self._scroll.grid(row=2, column=0, padx=8, pady=(0, 8), sticky="nsew")
        self._scroll.grid_columnconfigure(0, weight=1)

        # Right: JSON preview
        right = ctk.CTkFrame(pane)
        right.grid(row=0, column=1, padx=(6, 0), sticky="nsew")
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(right, text="Preview (JSON)").grid(
            row=0, column=0, padx=12, pady=(10, 4), sticky="w"
        )
        self._preview = ctk.CTkTextbox(
            right, font=("Consolas", 12), wrap="none", state="disabled"
        )
        self._preview.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="nsew")

        # Bottom: status + Convert button
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.grid(row=5, column=0, padx=16, pady=(4, 16), sticky="ew")
        bottom.grid_columnconfigure(0, weight=1)

        self._status = ctk.CTkLabel(bottom, text="", text_color="gray")
        self._status.grid(row=0, column=0, padx=12, sticky="w")

        ctk.CTkButton(
            bottom, text="Convert & Save", width=160, height=40, command=self._convert
        ).grid(row=0, column=1, padx=12)

    # ── Actions ───────────────────────────────────────────────────────────────

    # ── Spinner helpers ───────────────────────────────────────────────────────

    def _start_loading(self, message: str = "กำลังโหลด…") -> None:
        self._is_loading = True
        self._browse_btn.configure(state="disabled")
        self._progress_bar.grid()          # show
        self._progress_bar.start()         # animate
        self._set_status(message, "#FFA500")

    def _stop_loading(self) -> None:
        self._is_loading = False
        self._progress_bar.stop()
        self._progress_bar.grid_remove()   # hide
        self._browse_btn.configure(state="normal")
        self._set_status("")

    def _browse(self) -> None:
        path = filedialog.askopenfilename(
            title="เลือกไฟล์ i18n JSON",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        self._start_loading("กำลังอ่านไฟล์…")
        self._file_label.configure(text=path, text_color="gray")
        threading.Thread(target=self._load_file, args=(path,), daemon=True).start()

    def _load_file(self, path: str) -> None:
        """Runs in background thread — parse JSON then hand off to main thread."""
        try:
            data = load_json_file(path)
        except Exception as exc:
            self.after(0, lambda: (
                self._stop_loading(),
                messagebox.showerror("Error", f"ไม่สามารถอ่านไฟล์ได้:\n{exc}"),
            ))
            return
        if not isinstance(data, dict):
            self.after(0, lambda: (
                self._stop_loading(),
                messagebox.showerror("Error", "JSON หลักต้องเป็น object"),
            ))
            return
        flat = flatten_json(data)
        self.after(0, lambda: self._on_file_loaded(path, flat))

    def _on_file_loaded(self, path: str, flat_items: list[dict[str, Any]]) -> None:
        self._source_file = path
        self._flat_items = flat_items
        self._flat_item_order = [item["path"] for item in flat_items]
        self._value_map = {item["path"]: item["value"] for item in flat_items}
        self._selected_paths.clear()
        self._file_label.configure(text=path, text_color="white")
        self._choose_existing_btn.configure(state="normal")
        self._search_var.set("")
        self._set_status("กำลังสร้างรายการ…", "#FFA500")
        self._apply_filter()

    # ── Debounce helpers ──────────────────────────────────────────────────────

    def _schedule_filter(self) -> None:
        if self._search_debounce_id:
            self.after_cancel(self._search_debounce_id)
        self._search_debounce_id = self.after(300, self._apply_filter)

    def _schedule_preview(self) -> None:
        if self._preview_debounce_id:
            self.after_cancel(self._preview_debounce_id)
        self._preview_debounce_id = self.after(200, self._update_preview)

    # ── Filter & render ───────────────────────────────────────────────────────

    def _apply_filter(self) -> None:
        query = self._search_var.get().strip().lower()
        self._filtered_items = [
            item
            for item in self._flat_items
            if not query
            or query in item["path"].lower()
            or query in str(item["value"]).lower()
        ]
        self._page_index = 0

        # bump generation so any stale batch stops
        self._build_generation += 1
        self._preview_generation += 1
        self._count_label.configure(
            text=f"Keys: {len(self._filtered_items)} matched  •  กำลังโหลด…"
        )
        if not self._is_loading:
            self._start_loading("กำลังสร้างรายการ…")
        self._render_current_page()

    def _render_current_page(self) -> None:
        for cb, _, _ in self._check_items:
            cb.destroy()
        self._check_items.clear()

        gen = self._build_generation
        start = self._page_index * self._PAGE_SIZE
        end = min(start + self._PAGE_SIZE, len(self._filtered_items))
        current_items = self._filtered_items[start:end]
        self._update_page_controls()
        self._build_batch(current_items, 0, gen)

    def _build_batch(
        self,
        items: list[dict[str, Any]],
        start: int,
        generation: int,
    ) -> None:
        """Create checkboxes in small batches, yielding to the event loop between each."""
        if generation != self._build_generation:
            return  # stale — a newer filter was triggered

        end = min(start + self._BATCH_SIZE, len(items))
        for item in items[start:end]:
            path = item["path"]
            var = tk.BooleanVar(value=path in self._selected_paths)
            cb = ctk.CTkCheckBox(
                self._scroll,
                text=format_item_label(path, item["value"]),
                variable=var,
                onvalue=True,
                offvalue=False,
                command=lambda selected_path=path, selected_var=var: self._on_check(
                    selected_path, selected_var
                ),
            )
            cb.grid(sticky="w", padx=4, pady=2)
            self._check_items.append((cb, var, path))

        self._update_count()

        if end < len(items):
            total = len(items)
            page_no = self._page_index + 1 if self._filtered_items else 0
            self._set_status(
                f"กำลังสร้างรายการหน้า {page_no}… {end}/{total}", "#FFA500"
            )
            # schedule next batch — gives event loop a chance to breathe
            self.after(0, lambda: self._build_batch(items, end, generation))
        else:
            # all done
            self._stop_loading()
            self._schedule_preview()

    def _on_check(self, path: str, var: tk.BooleanVar) -> None:
        if var.get():
            self._selected_paths.add(path)
        else:
            self._selected_paths.discard(path)
        self._update_count()
        self._schedule_preview()

    def _select_all(self) -> None:
        for item in self._filtered_items:
            self._selected_paths.add(item["path"])
        for _, var, _ in self._check_items:
            var.set(True)
        self._update_count()
        self._schedule_preview()

    def _clear_all(self) -> None:
        for item in self._filtered_items:
            self._selected_paths.discard(item["path"])
        for _, var, _ in self._check_items:
            var.set(False)
        self._update_count()
        self._schedule_preview()

    def _update_count(self) -> None:
        matched = len(self._filtered_items)
        selected = sum(1 for item in self._filtered_items if item["path"] in self._selected_paths)
        page_count = ceil(matched / self._PAGE_SIZE) if matched else 0
        page_text = f"Page {self._page_index + 1}/{page_count}" if page_count else "Page 0/0"
        self._page_label.configure(text=page_text)
        self._count_label.configure(
            text=f"Keys: {matched} matched  •  {selected} selected"
        )

    def _update_preview(self) -> None:
        self._preview_generation += 1
        generation = self._preview_generation
        selected = set(self._selected_paths)
        if not selected:
            if self._existing_data is not None:
                self._set_preview(json.dumps(self._existing_data, ensure_ascii=False, indent=2))
                return
            self._set_preview("เลือก key เพื่อดู preview…")
            return
        self._set_preview("กำลังสร้าง preview…")
        threading.Thread(
            target=self._build_preview,
            args=(selected, generation),
            daemon=True,
        ).start()

    def _build_preview(self, selected_paths: set[str], generation: int) -> None:
        if self._existing_data is not None:
            data = self._build_updated_json(selected_paths, self._existing_data)
        else:
            data = build_custom_json(selected_paths, self._value_map, self._flat_item_order)
        preview_text = json.dumps(data, ensure_ascii=False, indent=2)
        self.after(0, lambda: self._finish_preview(preview_text, generation))

    def _finish_preview(self, preview_text: str, generation: int) -> None:
        if generation != self._preview_generation:
            return
        self._set_preview(preview_text)

    def _change_page(self, delta: int) -> None:
        total_pages = ceil(len(self._filtered_items) / self._PAGE_SIZE) if self._filtered_items else 0
        if total_pages == 0:
            return
        next_page = self._page_index + delta
        if next_page < 0 or next_page >= total_pages:
            return
        self._page_index = next_page
        self._build_generation += 1
        if not self._is_loading:
            self._start_loading("กำลังเปลี่ยนหน้า…")
        self._render_current_page()

    def _update_page_controls(self) -> None:
        total_pages = ceil(len(self._filtered_items) / self._PAGE_SIZE) if self._filtered_items else 0
        current_page = self._page_index + 1 if total_pages else 0
        self._page_label.configure(text=f"Page {current_page}/{total_pages}" if total_pages else "Page 0/0")
        self._prev_btn.configure(state="normal" if self._page_index > 0 else "disabled")
        self._next_btn.configure(
            state="normal" if total_pages and self._page_index < total_pages - 1 else "disabled"
        )

    def _set_preview(self, text: str) -> None:
        self._preview.configure(state="normal")
        self._preview.delete("1.0", "end")
        self._preview.insert("1.0", text)

    def _set_status(self, text: str, color: str = "gray") -> None:
        self._status.configure(text=text, text_color=color)

    def _choose_existing_file(self) -> None:
        if not self._source_file:
            messagebox.showwarning("Warning", "กรุณาเลือกไฟล์หลักก่อน")
            return
        path = filedialog.askopenfilename(
            title="เลือกไฟล์ custom เดิม",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            data = load_json_file(path)
        except Exception as exc:
            messagebox.showerror("Error", f"ไม่สามารถอ่านไฟล์เดิมได้:\n{exc}")
            return
        if not isinstance(data, dict):
            messagebox.showerror("Error", "ไฟล์เดิมต้องเป็น JSON object")
            return
        self._existing_file = path
        self._existing_data = data
        self._existing_file_label.configure(text=path, text_color="white")
        self._set_preview(json.dumps(data, ensure_ascii=False, indent=2))

    def _build_updated_json(self, selected_paths: set[str], base_data: dict[str, Any]) -> dict[str, Any]:
        result = json.loads(json.dumps(base_data))
        for path in self._flat_item_order:
            if path in selected_paths and path in self._value_map:
                insert_path(result, path, self._value_map[path])
        return result

    def _convert(self) -> None:
        if not self._source_file:
            messagebox.showwarning("Warning", "กรุณาเลือกไฟล์ก่อน")
            return
        selected = set(self._selected_paths)
        if not selected:
            messagebox.showwarning("Warning", "กรุณาเลือก key อย่างน้อย 1 รายการ")
            return

        try:
            preview_text = self._preview.get("1.0", "end-1c")
            data = json.loads(preview_text)
        except json.JSONDecodeError:
            messagebox.showerror("Error", "Preview JSON ไม่ถูกต้อง กรุณาตรวจสอบ syntax")
            return
        
        if self._existing_file:
            if not messagebox.askyesno(
                "ยืนยันการอัปเดต",
                f"ต้องการอัปเดตไฟล์เดิมนี้หรือไม่?\n{self._existing_file}",
            ):
                return
            save_path = self._existing_file
        else:
            default_name = make_output_filename(Path(self._source_file).name)
            save_path = filedialog.asksaveasfilename(
                title="บันทึก custom JSON",
                defaultextension=".json",
                initialfile=default_name,
                filetypes=[("JSON files", "*.json")],
            )
            if not save_path:
                return

        with open(save_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        self._set_status(f"✓ บันทึกแล้ว: {save_path}", "#4CAF50")
        messagebox.showinfo("Done", f"บันทึกไฟล์แล้วที่:\n{save_path}")


if __name__ == "__main__":
    app = App()
    app.mainloop()
