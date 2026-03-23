import json
import tkinter as tk
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
    selected_paths: list[str], flat_items: list[dict[str, Any]]
) -> dict[str, Any]:
    value_map = {item["path"]: item["value"] for item in flat_items}
    result: dict[str, Any] = {}
    for path in selected_paths:
        if path in value_map:
            insert_path(result, path, value_map[path])
    return result


def make_output_filename(name: str) -> str:
    p = Path(name)
    return f"{p.stem}+custom.json" if p.suffix.lower() == ".json" else f"{p.name}+custom.json"


# ── App ───────────────────────────────────────────────────────────────────────

class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Custom i18n Key Builder")
        self.geometry("1200x720")
        self.minsize(900, 580)

        self._source_file: str = ""
        self._flat_items: list[dict[str, Any]] = []
        # each entry: (checkbox_widget, bool_var, key_path)
        self._check_items: list[tuple[ctk.CTkCheckBox, tk.BooleanVar, str]] = []

        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # File row
        file_row = ctk.CTkFrame(self)
        file_row.grid(row=0, column=0, padx=16, pady=(16, 4), sticky="ew")
        file_row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(file_row, text="File:", width=50).grid(
            row=0, column=0, padx=(12, 6), pady=10
        )
        self._file_label = ctk.CTkLabel(
            file_row, text="ยังไม่ได้เลือกไฟล์", anchor="w", text_color="gray"
        )
        self._file_label.grid(row=0, column=1, padx=6, pady=10, sticky="ew")
        ctk.CTkButton(file_row, text="Browse…", width=90, command=self._browse).grid(
            row=0, column=2, padx=12, pady=10
        )

        # Search + bulk-select row
        ctrl_row = ctk.CTkFrame(self)
        ctrl_row.grid(row=1, column=0, padx=16, pady=4, sticky="ew")
        ctrl_row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(ctrl_row, text="Search:", width=50).grid(
            row=0, column=0, padx=(12, 6), pady=10
        )
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._apply_filter())
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
        pane.grid(row=2, column=0, padx=16, pady=4, sticky="nsew")
        pane.grid_columnconfigure(0, weight=2)
        pane.grid_columnconfigure(1, weight=3)
        pane.grid_rowconfigure(0, weight=1)

        # Left: scrollable checkbox list
        left = ctk.CTkFrame(pane)
        left.grid(row=0, column=0, padx=(0, 6), sticky="nsew")
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        self._count_label = ctk.CTkLabel(left, text="Keys: –")
        self._count_label.grid(row=0, column=0, padx=12, pady=(10, 4), sticky="w")

        self._scroll = ctk.CTkScrollableFrame(left)
        self._scroll.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="nsew")
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
        bottom.grid(row=3, column=0, padx=16, pady=(4, 16), sticky="ew")
        bottom.grid_columnconfigure(0, weight=1)

        self._status = ctk.CTkLabel(bottom, text="", text_color="gray")
        self._status.grid(row=0, column=0, padx=12, sticky="w")
        ctk.CTkButton(
            bottom, text="Convert & Save", width=160, height=40, command=self._convert
        ).grid(row=0, column=1, padx=12)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _browse(self) -> None:
        path = filedialog.askopenfilename(
            title="เลือกไฟล์ i18n JSON",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception as exc:
            messagebox.showerror("Error", f"ไม่สามารถอ่านไฟล์ได้:\n{exc}")
            return
        if not isinstance(data, dict):
            messagebox.showerror("Error", "JSON หลักต้องเป็น object")
            return
        self._source_file = path
        self._flat_items = flatten_json(data)
        self._file_label.configure(text=path, text_color="white")
        self._search_var.set("")
        self._apply_filter()
        self._set_status("")

    def _apply_filter(self) -> None:
        query = self._search_var.get().strip().lower()
        previously_checked = {path for _, var, path in self._check_items if var.get()}

        for cb, _, _ in self._check_items:
            cb.destroy()
        self._check_items.clear()

        matches = [
            item
            for item in self._flat_items
            if not query
            or query in item["path"].lower()
            or query in str(item["value"]).lower()
        ]

        for item in matches:
            path = item["path"]
            var = tk.BooleanVar(value=path in previously_checked)
            var.trace_add("write", lambda *_: self._on_check())
            label = f"{path}  =  {item['value']}"
            cb = ctk.CTkCheckBox(
                self._scroll,
                text=label,
                variable=var,
                onvalue=True,
                offvalue=False,
            )
            cb.grid(sticky="w", padx=4, pady=2)
            self._check_items.append((cb, var, path))

        self._update_count()
        self._update_preview()

    def _on_check(self) -> None:
        self._update_count()
        self._update_preview()

    def _select_all(self) -> None:
        for _, var, _ in self._check_items:
            var.set(True)

    def _clear_all(self) -> None:
        for _, var, _ in self._check_items:
            var.set(False)

    def _update_count(self) -> None:
        matched = len(self._check_items)
        selected = sum(1 for _, var, _ in self._check_items if var.get())
        self._count_label.configure(
            text=f"Keys: {matched} matched  •  {selected} selected"
        )

    def _update_preview(self) -> None:
        selected = [path for _, var, path in self._check_items if var.get()]
        if not selected:
            self._set_preview("เลือก key เพื่อดู preview…")
            return
        data = build_custom_json(selected, self._flat_items)
        self._set_preview(json.dumps(data, ensure_ascii=False, indent=2))

    def _set_preview(self, text: str) -> None:
        self._preview.configure(state="normal")
        self._preview.delete("1.0", "end")
        self._preview.insert("1.0", text)
        self._preview.configure(state="disabled")

    def _set_status(self, text: str, color: str = "gray") -> None:
        self._status.configure(text=text, text_color=color)

    def _convert(self) -> None:
        if not self._source_file:
            messagebox.showwarning("Warning", "กรุณาเลือกไฟล์ก่อน")
            return
        selected = [path for _, var, path in self._check_items if var.get()]
        if not selected:
            messagebox.showwarning("Warning", "กรุณาเลือก key อย่างน้อย 1 รายการ")
            return
        default_name = make_output_filename(Path(self._source_file).name)
        save_path = filedialog.asksaveasfilename(
            title="บันทึก custom JSON",
            defaultextension=".json",
            initialfile=default_name,
            filetypes=[("JSON files", "*.json")],
        )
        if not save_path:
            return
        data = build_custom_json(selected, self._flat_items)
        with open(save_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        self._set_status(f"✓ บันทึกแล้ว: {save_path}", "#4CAF50")
        messagebox.showinfo("Done", f"บันทึกไฟล์แล้วที่:\n{save_path}")


if __name__ == "__main__":
    app = App()
    app.mainloop()
