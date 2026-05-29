# -*- coding: utf-8 -*-
"""
桌面待办事项小工具

运行方式：
    python desktop_todo.py

特点：
    - 纯标准库实现，无需额外安装依赖
    - 自动保存到 desktop_todo_data.json
    - 编辑器负责管理内容，透明文字浮层负责常驻桌面
    - 支持搜索、筛选、优先级、到期提醒
"""

from __future__ import annotations

import json
import sys
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import tkinter as tk
from tkinter import colorchooser, filedialog, font as tkfont, messagebox, ttk


def runtime_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


BASE_DIR = runtime_base_dir()
DATA_FILE = BASE_DIR / "desktop_todo_data.json"

APP_BG = "#f4efe6"
PANEL_BG = "#fffaf0"
CARD_BG = "#fffdf7"
CARD_DONE_BG = "#ece4d5"
TEXT = "#2b251c"
MUTED = "#776f61"
ACCENT = "#c26a3d"
ACCENT_DARK = "#8c4328"
DANGER = "#b24b43"
SUCCESS = "#4d7c59"
BORDER = "#dfd2bf"
OVERLAY_TRANSPARENT = "#010203"
OVERLAY_TEXT = "#fff2d2"
OVERLAY_SHADOW = "#24180f"
DEFAULT_OVERLAY_FONT = "Microsoft YaHei UI"
DEFAULT_OVERLAY_FONT_SIZE = 16
BLOCKED_OVERLAY_COLORS = {OVERLAY_TRANSPARENT.lower(), "#ff00ff", "#f0f"}

PRIORITIES = ("普通", "重要", "紧急")
FILTERS = ("全部", "未完成", "已完成", "今天", "逾期")


def iso_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def make_id() -> str:
    return uuid.uuid4().hex[:12]


def shifted_transparent_color(text_color: str) -> str:
    """生成接近文字色的透明抠图色，减少 Tk 抗锯齿混色造成的彩边。"""
    if not text_color.startswith("#") or len(text_color) != 7:
        return OVERLAY_TRANSPARENT

    channels = [int(text_color[i:i + 2], 16) for i in (1, 3, 5)]
    shifted = []
    for value in channels:
        shifted.append(max(0, value - 18) if value > 127 else min(255, value + 18))
    key = f"#{shifted[0]:02x}{shifted[1]:02x}{shifted[2]:02x}"
    return key if key.lower() != text_color.lower() else OVERLAY_TRANSPARENT


def parse_due_text(raw: str) -> datetime | None:
    """支持几种常用输入：YYYY-MM-DD HH:MM、MM-DD HH:MM、HH:MM。"""
    text = raw.strip()
    if not text:
        return None

    formats = ("%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M", "%Y-%m-%d", "%Y/%m/%d")
    for fmt in formats:
        try:
            parsed = datetime.strptime(text, fmt)
            if fmt in ("%Y-%m-%d", "%Y/%m/%d"):
                parsed = parsed.replace(hour=23, minute=59)
            return parsed
        except ValueError:
            pass

    current_year = datetime.now().year
    for fmt in ("%m-%d %H:%M", "%m/%d %H:%M", "%m-%d", "%m/%d"):
        try:
            parsed = datetime.strptime(f"{current_year}-{text}", f"%Y-{fmt}")
            if fmt in ("%m-%d", "%m/%d"):
                parsed = parsed.replace(hour=23, minute=59)
            return parsed
        except ValueError:
            pass

    try:
        parsed_time = datetime.strptime(text, "%H:%M").time()
        return datetime.combine(date.today(), parsed_time)
    except ValueError:
        return None


def format_due(due_at: str) -> str:
    if not due_at:
        return "无截止时间"
    try:
        due = datetime.fromisoformat(due_at)
        return due.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return due_at


def due_for_logic(due_at: str) -> datetime | None:
    """尽量把截止时间文本解析成日期；解析不了就只当作普通文字。"""
    if not due_at:
        return None
    try:
        return datetime.fromisoformat(due_at)
    except ValueError:
        return parse_due_text(due_at)


def is_today(due_at: str) -> bool:
    due = due_for_logic(due_at)
    return due is not None and due.date() == date.today()


def is_overdue(due_at: str, done: bool) -> bool:
    if done:
        return False
    due = due_for_logic(due_at)
    return due is not None and due < datetime.now()


@dataclass
class Task:
    title: str
    note: str = ""
    due_at: str = ""
    priority: str = "普通"
    done: bool = False
    reminded: bool = False
    task_id: str = field(default_factory=make_id)
    created_at: str = field(default_factory=iso_now)
    updated_at: str = field(default_factory=iso_now)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        return cls(
            task_id=str(data.get("task_id") or data.get("id") or make_id()),
            title=str(data.get("title") or "未命名待办"),
            note=str(data.get("note") or ""),
            due_at=str(data.get("due_at") or ""),
            priority=str(data.get("priority") or "普通"),
            done=bool(data.get("done", False)),
            reminded=bool(data.get("reminded", False)),
            created_at=str(data.get("created_at") or iso_now()),
            updated_at=str(data.get("updated_at") or iso_now()),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "note": self.note,
            "due_at": self.due_at,
            "priority": self.priority,
            "done": self.done,
            "reminded": self.reminded,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class ScrollFrame(ttk.Frame):
    def __init__(self, master: tk.Widget) -> None:
        super().__init__(master)
        self.canvas = tk.Canvas(self, bg=APP_BG, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.canvas.yview)
        self.body = ttk.Frame(self.canvas, style="Body.TFrame")
        self.body_id = self.canvas.create_window((0, 0), window=self.body, anchor="nw")

        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.body.bind("<Configure>", self._sync_scroll_region)
        self.canvas.bind("<Configure>", self._sync_body_width)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _sync_scroll_region(self, _event: tk.Event[Any] | None = None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _sync_body_width(self, event: tk.Event[Any]) -> None:
        self.canvas.itemconfigure(self.body_id, width=event.width)

    def _on_mousewheel(self, event: tk.Event[Any]) -> None:
        if self.winfo_ismapped():
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


class FloatingTodoOverlay:
    """只显示待办文字的透明桌面浮层。"""

    def __init__(self, app: "DesktopTodoApp") -> None:
        self.app = app
        self.locked = False
        self.transparent_color = app.overlay_transparent_color()
        self.uses_color_key = True
        self.window = tk.Toplevel(app.root)
        self.window.title("待办文字浮层")
        self.window.overrideredirect(True)
        self.window.configure(bg=self.transparent_color)
        self.window.attributes("-topmost", app.topmost_var.get())

        try:
            self.window.attributes("-transparentcolor", self.transparent_color)
        except tk.TclError:
            self.uses_color_key = False
            self.window.attributes("-alpha", 0.88)
            self.window.configure(bg="#1f1b16")

        self.container = tk.Frame(self.window, bg=self._bg_color(), padx=10, pady=8)
        self.container.pack(fill=tk.BOTH, expand=True)

        self.menu = tk.Menu(self.window, tearoff=False)
        self.menu.add_command(label="打开编辑器", command=self.app.show_editor)
        self.menu.add_command(label="隐藏桌面文字", command=self.app.hide_overlay)
        self.menu.add_separator()
        self.menu.add_command(label="退出程序", command=self.app.quit_app)

        self._drag_dx = 0
        self._drag_dy = 0
        self._bind_overlay_events(self.window)
        self._bind_overlay_events(self.container)
        self.move_to(app.overlay_x, app.overlay_y)
        self.set_locked(app.overlay_locked_var.get())

        if not app.overlay_visible_var.get():
            self.window.withdraw()

    def set_topmost(self, enabled: bool) -> None:
        self.window.attributes("-topmost", enabled)

    def set_locked(self, enabled: bool) -> None:
        self.locked = enabled

    def show(self) -> None:
        self.window.deiconify()
        self.window.lift()

    def hide(self) -> None:
        self.window.withdraw()

    def destroy(self) -> None:
        try:
            self.window.destroy()
        except tk.TclError:
            pass

    def move_to(self, x: int, y: int) -> None:
        self.window.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _bg_color(self) -> str:
        return self.transparent_color if self.uses_color_key else "#1f1b16"

    def _sync_transparent_color(self) -> None:
        if not self.uses_color_key:
            return

        new_color = self.app.overlay_transparent_color()
        if new_color == self.transparent_color:
            return

        self.transparent_color = new_color
        self.window.configure(bg=self.transparent_color)
        self.window.attributes("-transparentcolor", self.transparent_color)
        self.container.configure(bg=self.transparent_color)

    def update(self, tasks: list[Task]) -> None:
        self._sync_transparent_color()
        for child in self.container.winfo_children():
            child.destroy()

        pending = [task for task in tasks if not task.done]
        if not pending:
            self._add_line("没有未完成待办", self._font(2, "bold"), self._text_color())
            hint = "文字已锁定，请在编辑器中解锁" if self.locked else "双击这里打开编辑器"
            self._add_line(hint, self._font(-5), self._text_color())
        else:
            self._add_line("待办", self._font(-2, "bold"), self._text_color())
            for index, task in enumerate(pending[:8], start=1):
                self._add_task_line(index, task)
            if len(pending) > 8:
                self._add_line(f"还有 {len(pending) - 8} 条未显示...", self._font(-5), self._text_color())

        self._bind_children()
        if self.app.overlay_visible_var.get():
            self.show()

    def _font(self, offset: int = 0, weight: str = "") -> tuple[str, int] | tuple[str, int, str]:
        size = max(8, self.app.overlay_font_size() + offset)
        family = self.app.overlay_font_family()
        if weight:
            return family, size, weight
        return family, size

    def _text_color(self) -> str:
        return self.app.overlay_font_color()

    def _add_task_line(self, index: int, task: Task) -> None:
        overdue = is_overdue(task.due_at, task.done)
        marker = "!!" if task.priority == "紧急" else "!" if task.priority == "重要" else "-"
        self._add_line(
            f"{marker} {index}. {task.title}",
            self._font(0, "bold"),
            self._text_color(),
            pady=(7, 0),
        )

        meta_parts = []
        if task.due_at:
            prefix = "已逾期" if overdue else "截止"
            meta_parts.append(f"{prefix} {format_due(task.due_at)}")
        if task.priority != "普通":
            meta_parts.append(task.priority)
        if meta_parts:
            self._add_line(" / ".join(meta_parts), self._font(-5), self._text_color(), padx=22)

        if task.note:
            note = task.note.replace("\n", " ")
            if len(note) > 38:
                note = f"{note[:38]}..."
            self._add_line(note, self._font(-5), self._text_color(), padx=22)

    def _add_line(
        self,
        text: str,
        font: tuple[str, int] | tuple[str, int, str],
        color: str,
        padx: int = 0,
        pady: tuple[int, int] = (2, 0),
    ) -> None:
        bg = self._bg_color()
        row = tk.Frame(self.container, bg=bg)
        row.pack(anchor=tk.W, fill=tk.X, pady=pady)

        label = tk.Label(
            row,
            text=text,
            bg=bg,
            fg=color,
            font=font,
            justify=tk.LEFT,
            wraplength=390,
        )
        label.pack(anchor=tk.W, padx=(padx, 0))

        self._bind_overlay_events(row)
        self._bind_overlay_events(label)

    def _bind_children(self) -> None:
        for child in self.container.winfo_children():
            self._bind_overlay_events(child)
            for grandchild in child.winfo_children():
                self._bind_overlay_events(grandchild)

    def _bind_overlay_events(self, widget: tk.Widget) -> None:
        widget.bind("<ButtonPress-1>", self._start_drag)
        widget.bind("<B1-Motion>", self._drag)
        widget.bind("<ButtonRelease-1>", self._finish_drag)
        widget.bind("<Double-Button-1>", self._open_editor_from_overlay)
        widget.bind("<Button-3>", self._show_menu)

    def _start_drag(self, event: tk.Event[Any]) -> None:
        if self.locked:
            return
        self._drag_dx = event.x_root - self.window.winfo_x()
        self._drag_dy = event.y_root - self.window.winfo_y()

    def _drag(self, event: tk.Event[Any]) -> None:
        if self.locked:
            return
        x = event.x_root - self._drag_dx
        y = event.y_root - self._drag_dy
        self.move_to(x, y)

    def _finish_drag(self, _event: tk.Event[Any]) -> None:
        if self.locked:
            return
        self.app.overlay_x = self.window.winfo_x()
        self.app.overlay_y = self.window.winfo_y()
        self.app.save_overlay_state()

    def _open_editor_from_overlay(self, _event: tk.Event[Any]) -> None:
        if not self.locked:
            self.app.show_editor()

    def _show_menu(self, event: tk.Event[Any]) -> None:
        if self.locked:
            return
        self.menu.tk_popup(event.x_root, event.y_root)


class DesktopTodoApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("待办编辑器")
        self.root.minsize(420, 640)

        self.tasks: list[Task] = []
        self.editing_id: str | None = None
        self.closing = False
        self.reminder_after_id: str | None = None
        self.overlay_x = 72
        self.overlay_y = 88
        self.font_families = self._available_font_families()

        self.title_var = tk.StringVar()
        self.due_var = tk.StringVar()
        self.priority_var = tk.StringVar(value="普通")
        self.search_var = tk.StringVar()
        self.filter_var = tk.StringVar(value="全部")
        self.topmost_var = tk.BooleanVar(value=True)
        self.overlay_visible_var = tk.BooleanVar(value=True)
        self.overlay_locked_var = tk.BooleanVar(value=False)
        self.overlay_font_family_var = tk.StringVar(value=DEFAULT_OVERLAY_FONT)
        self.overlay_font_size_var = tk.StringVar(value=str(DEFAULT_OVERLAY_FONT_SIZE))
        self.overlay_font_color_var = tk.StringVar(value=OVERLAY_TEXT)
        self.status_var = tk.StringVar(value="准备好了")

        self._setup_window()
        self._setup_style()
        self._build_ui()
        self._load_tasks()
        self._sync_style_controls()
        self.overlay = FloatingTodoOverlay(self)
        self._refresh_tasks()
        self._schedule_reminder_check()

        self.root.protocol("WM_DELETE_WINDOW", self.quit_app)

    def run(self) -> None:
        self.root.mainloop()

    def _available_font_families(self) -> list[str]:
        try:
            names = sorted({name for name in tkfont.families(self.root) if not name.startswith("@")})
        except tk.TclError:
            names = []

        preferred = ["Microsoft YaHei UI", "Microsoft YaHei", "SimHei", "SimSun", "KaiTi", "Arial"]
        ordered = [name for name in preferred if name in names]
        ordered.extend(name for name in names if name not in ordered)
        return ordered or preferred

    def _setup_window(self) -> None:
        width = 460
        height = 720
        screen_width = self.root.winfo_screenwidth()
        x = max(20, screen_width - width - 36)
        y = 48
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.configure(bg=APP_BG)

    def _setup_style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(".", font=("Microsoft YaHei UI", 10), foreground=TEXT)
        style.configure("Body.TFrame", background=APP_BG)
        style.configure("Panel.TFrame", background=PANEL_BG)
        style.configure("Card.TFrame", background=CARD_BG)
        style.configure("Muted.TLabel", background=PANEL_BG, foreground=MUTED)
        style.configure("Title.TLabel", background=PANEL_BG, foreground=TEXT, font=("Microsoft YaHei UI", 20, "bold"))
        style.configure("SubTitle.TLabel", background=PANEL_BG, foreground=MUTED, font=("Microsoft YaHei UI", 9))
        style.configure("CardTitle.TLabel", background=CARD_BG, foreground=TEXT, font=("Microsoft YaHei UI", 11, "bold"))
        style.configure("CardMeta.TLabel", background=CARD_BG, foreground=MUTED, font=("Microsoft YaHei UI", 9))
        style.configure("Done.TLabel", background=CARD_DONE_BG, foreground=MUTED, font=("Microsoft YaHei UI", 11, "overstrike"))
        style.configure("TEntry", padding=8)
        style.configure("TCombobox", padding=6)
        style.configure("Accent.TButton", foreground="#ffffff", background=ACCENT, padding=(12, 7))
        style.map("Accent.TButton", background=[("active", ACCENT_DARK), ("pressed", ACCENT_DARK)])
        style.configure("Soft.TButton", background="#eadfcd", padding=(10, 6))
        style.map("Soft.TButton", background=[("active", "#dfcfb7")])
        style.configure("Danger.TButton", foreground="#ffffff", background=DANGER, padding=(10, 6))
        style.map("Danger.TButton", background=[("active", "#953931")])
        style.configure("TCheckbutton", background=PANEL_BG)

    def _build_ui(self) -> None:
        shell = ttk.Frame(self.root, style="Body.TFrame", padding=14)
        shell.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(shell, style="Panel.TFrame", padding=(16, 14))
        header.pack(fill=tk.X)
        self._paint_panel(header)

        title_row = ttk.Frame(header, style="Panel.TFrame")
        title_row.pack(fill=tk.X)
        ttk.Label(title_row, text="待办编辑器", style="Title.TLabel").pack(side=tk.LEFT)
        ttk.Checkbutton(
            title_row,
            text="文字置顶",
            variable=self.topmost_var,
            command=self._toggle_topmost,
            style="TCheckbutton",
        ).pack(side=tk.RIGHT)
        ttk.Checkbutton(
            title_row,
            text="锁定文字",
            variable=self.overlay_locked_var,
            command=self._toggle_overlay_locked,
            style="TCheckbutton",
        ).pack(side=tk.RIGHT, padx=(0, 12))
        ttk.Checkbutton(
            title_row,
            text="显示桌面文字",
            variable=self.overlay_visible_var,
            command=self._toggle_overlay_visible,
            style="TCheckbutton",
        ).pack(side=tk.RIGHT, padx=(0, 12))

        ttk.Label(
            header,
            text="这里负责编辑；桌面上只悬浮待办文字。锁定后文字不可拖动、双击或右键。",
            style="SubTitle.TLabel",
        ).pack(anchor=tk.W, pady=(3, 0))

        form = ttk.Frame(shell, style="Panel.TFrame", padding=(16, 14))
        form.pack(fill=tk.X, pady=(12, 0))
        self._paint_panel(form)

        ttk.Label(form, text="待办内容", style="Muted.TLabel").grid(row=0, column=0, sticky=tk.W)
        title_entry = ttk.Entry(form, textvariable=self.title_var)
        title_entry.grid(row=1, column=0, columnspan=3, sticky=tk.EW, pady=(4, 10))
        title_entry.bind("<Return>", lambda _event: self._save_from_form())

        ttk.Label(form, text="截止时间（可随便写）", style="Muted.TLabel").grid(row=2, column=0, sticky=tk.W)
        ttk.Label(form, text="优先级", style="Muted.TLabel").grid(row=2, column=2, sticky=tk.W, padx=(10, 0))

        due_entry = ttk.Entry(form, textvariable=self.due_var)
        due_entry.grid(row=3, column=0, columnspan=2, sticky=tk.EW, pady=(4, 10))
        due_entry.insert(0, "")

        priority = ttk.Combobox(form, textvariable=self.priority_var, values=PRIORITIES, state="readonly", width=8)
        priority.grid(row=3, column=2, sticky=tk.EW, padx=(10, 0), pady=(4, 10))

        ttk.Label(form, text="备注", style="Muted.TLabel").grid(row=4, column=0, sticky=tk.W)
        self.note_text = tk.Text(
            form,
            height=3,
            wrap=tk.WORD,
            bg="#fffdf8",
            fg=TEXT,
            insertbackground=TEXT,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=ACCENT,
            font=("Microsoft YaHei UI", 10),
        )
        self.note_text.grid(row=5, column=0, columnspan=3, sticky=tk.EW, pady=(4, 10))

        button_row = ttk.Frame(form, style="Panel.TFrame")
        button_row.grid(row=6, column=0, columnspan=3, sticky=tk.EW)
        self.save_button = ttk.Button(button_row, text="添加待办", style="Accent.TButton", command=self._save_from_form)
        self.save_button.pack(side=tk.LEFT)
        ttk.Button(button_row, text="清空输入", style="Soft.TButton", command=self._clear_form).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(
            button_row,
            text="可写：18:30 / 明天上午 / 有空再做 / 任意文字",
            style="Muted.TLabel",
        ).pack(side=tk.RIGHT)

        form.columnconfigure(0, weight=1)
        form.columnconfigure(1, weight=1)
        form.columnconfigure(2, weight=0)

        style_panel = ttk.Frame(shell, style="Panel.TFrame", padding=(16, 12))
        style_panel.pack(fill=tk.X, pady=(12, 0))
        self._paint_panel(style_panel)

        ttk.Label(style_panel, text="桌面文字样式", style="Muted.TLabel").grid(row=0, column=0, sticky=tk.W)
        ttk.Label(style_panel, text="字体", style="Muted.TLabel").grid(row=1, column=0, sticky=tk.W, pady=(8, 0))
        ttk.Label(style_panel, text="字号", style="Muted.TLabel").grid(row=1, column=1, sticky=tk.W, padx=(10, 0), pady=(8, 0))
        ttk.Label(style_panel, text="颜色", style="Muted.TLabel").grid(row=1, column=2, sticky=tk.W, padx=(10, 0), pady=(8, 0))

        self.font_combo = ttk.Combobox(
            style_panel,
            textvariable=self.overlay_font_family_var,
            values=self.font_families,
            state="readonly",
            width=20,
        )
        self.font_combo.grid(row=2, column=0, sticky=tk.EW, pady=(4, 0))
        self.font_combo.bind("<<ComboboxSelected>>", lambda _event: self._apply_overlay_style())

        size_spin = tk.Spinbox(
            style_panel,
            from_=8,
            to=72,
            textvariable=self.overlay_font_size_var,
            command=self._apply_overlay_style,
            width=6,
            relief=tk.FLAT,
            bg="#fffdf8",
            fg=TEXT,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=ACCENT,
        )
        size_spin.grid(row=2, column=1, sticky=tk.EW, padx=(10, 0), pady=(4, 0))
        size_spin.bind("<KeyRelease>", lambda _event: self._apply_overlay_style())
        size_spin.bind("<FocusOut>", lambda _event: self._apply_overlay_style())

        color_row = ttk.Frame(style_panel, style="Panel.TFrame")
        color_row.grid(row=2, column=2, sticky=tk.EW, padx=(10, 0), pady=(4, 0))
        self.color_preview = tk.Label(color_row, text="    ", bg=OVERLAY_TEXT, relief=tk.FLAT)
        self.color_preview.pack(side=tk.LEFT, ipady=7)
        ttk.Entry(color_row, textvariable=self.overlay_font_color_var, width=10).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(color_row, text="选择", style="Soft.TButton", command=self._choose_overlay_color).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(color_row, text="应用", style="Accent.TButton", command=self._apply_overlay_style).pack(side=tk.LEFT, padx=(6, 0))

        style_panel.columnconfigure(0, weight=1)
        style_panel.columnconfigure(1, weight=0)
        style_panel.columnconfigure(2, weight=1)

        tools = ttk.Frame(shell, style="Panel.TFrame", padding=(16, 12))
        tools.pack(fill=tk.X, pady=(12, 0))
        self._paint_panel(tools)

        ttk.Entry(tools, textvariable=self.search_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.search_var.trace_add("write", lambda *_args: self._refresh_tasks())

        filter_box = ttk.Combobox(tools, textvariable=self.filter_var, values=FILTERS, state="readonly", width=9)
        filter_box.pack(side=tk.LEFT, padx=(8, 0))
        filter_box.bind("<<ComboboxSelected>>", lambda _event: self._refresh_tasks())

        ttk.Button(tools, text="导出", style="Soft.TButton", command=self._export_tasks).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(tools, text="清理完成", style="Danger.TButton", command=self._delete_done).pack(side=tk.LEFT, padx=(8, 0))

        self.summary_label = ttk.Label(shell, text="", background=APP_BG, foreground=MUTED)
        self.summary_label.pack(anchor=tk.W, pady=(10, 6))

        self.scroll = ScrollFrame(shell)
        self.scroll.pack(fill=tk.BOTH, expand=True)

        footer = ttk.Frame(shell, style="Body.TFrame")
        footer.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(footer, textvariable=self.status_var, background=APP_BG, foreground=MUTED).pack(side=tk.LEFT)
        ttk.Button(footer, text="退出程序", style="Danger.TButton", command=self.quit_app).pack(side=tk.RIGHT)
        ttk.Button(footer, text="只显示桌面文字", style="Accent.TButton", command=self.hide_editor).pack(side=tk.RIGHT, padx=(0, 8))
        ttk.Button(footer, text="保存", style="Soft.TButton", command=self._save_tasks).pack(side=tk.RIGHT)

        self.root.bind("<Control-s>", lambda _event: self._save_tasks())

    def overlay_font_family(self) -> str:
        family = self.overlay_font_family_var.get().strip() or DEFAULT_OVERLAY_FONT
        if family.startswith("@"):
            family = family[1:]
        if family not in self.font_families:
            return DEFAULT_OVERLAY_FONT if DEFAULT_OVERLAY_FONT in self.font_families else self.font_families[0]
        return family

    def overlay_font_size(self) -> int:
        try:
            size = int(self.overlay_font_size_var.get())
        except ValueError:
            size = DEFAULT_OVERLAY_FONT_SIZE
        return max(8, min(72, size))

    def overlay_font_color(self) -> str:
        color = self.overlay_font_color_var.get().strip() or OVERLAY_TEXT
        try:
            red, green, blue = self.root.winfo_rgb(color)
        except tk.TclError:
            return OVERLAY_TEXT
        normalized = f"#{red // 256:02x}{green // 256:02x}{blue // 256:02x}"
        if normalized.lower() in BLOCKED_OVERLAY_COLORS:
            return OVERLAY_TEXT
        return normalized

    def overlay_transparent_color(self) -> str:
        return shifted_transparent_color(self.overlay_font_color())

    def _sync_style_controls(self) -> None:
        size = self.overlay_font_size()
        if self.overlay_font_size_var.get() != str(size):
            self.overlay_font_size_var.set(str(size))

        family = self.overlay_font_family()
        if self.overlay_font_family_var.get().strip() != family:
            self.overlay_font_family_var.set(family)
        if hasattr(self, "font_combo"):
            self.font_combo.configure(values=self.font_families)

        color = self.overlay_font_color()
        if self.overlay_font_color_var.get().strip() != color:
            self.overlay_font_color_var.set(color)
        if hasattr(self, "color_preview"):
            self.color_preview.configure(bg=color)

    def _apply_overlay_style(self) -> None:
        self._sync_style_controls()
        if hasattr(self, "overlay"):
            self.overlay.update(self._sorted_tasks())
        self._save_tasks()
        self.status_var.set("桌面文字样式已应用")

    def _choose_overlay_color(self) -> None:
        _rgb, color = colorchooser.askcolor(
            color=self.overlay_font_color(),
            parent=self.root,
            title="选择桌面文字颜色",
        )
        if color:
            self.overlay_font_color_var.set(color)
            self._apply_overlay_style()

    def _paint_panel(self, widget: ttk.Frame) -> None:
        widget.configure(style="Panel.TFrame")

    def _load_tasks(self) -> None:
        if not DATA_FILE.exists():
            self.tasks = []
            return

        try:
            raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                raw_tasks = raw.get("tasks", [])
                overlay = raw.get("overlay", {})
                if isinstance(overlay, dict):
                    self.overlay_x = int(overlay.get("x", self.overlay_x))
                    self.overlay_y = int(overlay.get("y", self.overlay_y))
                    self.overlay_visible_var.set(bool(overlay.get("visible", True)))
                    self.topmost_var.set(bool(overlay.get("topmost", True)))
                    self.overlay_locked_var.set(bool(overlay.get("locked", False)))
                    self.overlay_font_family_var.set(str(overlay.get("font_family") or self.overlay_font_family()))
                    self.overlay_font_size_var.set(str(overlay.get("font_size") or self.overlay_font_size()))
                    self.overlay_font_color_var.set(str(overlay.get("font_color") or self.overlay_font_color()))
            else:
                raw_tasks = raw
            self.tasks = [Task.from_dict(item) for item in raw_tasks if isinstance(item, dict)]
            self.status_var.set(f"已加载 {len(self.tasks)} 条待办")
        except Exception as exc:
            messagebox.showwarning("读取失败", f"读取待办数据失败，将从空列表开始。\n\n{exc}")
            self.tasks = []

    def _save_tasks(self) -> None:
        payload = {
            "app": "desktop_todo",
            "saved_at": iso_now(),
            "overlay": {
                "x": self.overlay_x,
                "y": self.overlay_y,
                "visible": self.overlay_visible_var.get(),
                "topmost": self.topmost_var.get(),
                "locked": self.overlay_locked_var.get(),
                "font_family": self.overlay_font_family(),
                "font_size": self.overlay_font_size(),
                "font_color": self.overlay_font_color(),
            },
            "tasks": [task.to_dict() for task in self.tasks],
        }
        DATA_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self.status_var.set(f"已保存：{DATA_FILE.name}")

    def save_overlay_state(self) -> None:
        self._save_tasks()

    def _save_from_form(self) -> None:
        title = self.title_var.get().strip()
        if not title:
            messagebox.showinfo("还差一点", "先写一条待办内容吧。")
            return

        note = self.note_text.get("1.0", tk.END).strip()
        due_at = self.due_var.get().strip()
        priority = self.priority_var.get() if self.priority_var.get() in PRIORITIES else "普通"

        if self.editing_id:
            task = self._find_task(self.editing_id)
            if not task:
                self.editing_id = None
                messagebox.showwarning("没有找到", "这条待办可能已经被删除。")
                return
            task.title = title
            task.note = note
            task.due_at = due_at
            task.priority = priority
            task.updated_at = iso_now()
            task.reminded = False
            self.status_var.set("已更新待办")
        else:
            self.tasks.append(Task(title=title, note=note, due_at=due_at, priority=priority))
            self.status_var.set("已添加待办")

        self._clear_form()
        self._save_tasks()
        self._refresh_tasks()

    def _clear_form(self) -> None:
        self.editing_id = None
        self.title_var.set("")
        self.due_var.set("")
        self.priority_var.set("普通")
        self.note_text.delete("1.0", tk.END)
        self.save_button.configure(text="添加待办")

    def _find_task(self, task_id: str) -> Task | None:
        return next((task for task in self.tasks if task.task_id == task_id), None)

    def _filtered_tasks(self) -> list[Task]:
        keyword = self.search_var.get().strip().lower()
        selected_filter = self.filter_var.get()

        def matches(task: Task) -> bool:
            if keyword and keyword not in f"{task.title} {task.note}".lower():
                return False
            if selected_filter == "未完成":
                return not task.done
            if selected_filter == "已完成":
                return task.done
            if selected_filter == "今天":
                return is_today(task.due_at)
            if selected_filter == "逾期":
                return is_overdue(task.due_at, task.done)
            return True

        return [task for task in self._sorted_tasks() if matches(task)]

    def _sorted_tasks(self) -> list[Task]:
        priority_weight = {"紧急": 0, "重要": 1, "普通": 2}

        def due_key(task: Task) -> tuple[int, str]:
            if not task.due_at:
                return 1, "9999-12-31T23:59"
            return 0, task.due_at

        return sorted(
            self.tasks,
            key=lambda task: (
                task.done,
                not is_overdue(task.due_at, task.done),
                priority_weight.get(task.priority, 2),
                *due_key(task),
                task.created_at,
            ),
        )

    def _refresh_tasks(self) -> None:
        for child in self.scroll.body.winfo_children():
            child.destroy()

        visible = self._filtered_tasks()
        total = len(self.tasks)
        done = sum(1 for task in self.tasks if task.done)
        overdue = sum(1 for task in self.tasks if is_overdue(task.due_at, task.done))
        self.summary_label.configure(text=f"共 {total} 条，完成 {done} 条，逾期 {overdue} 条；当前显示 {len(visible)} 条")

        if hasattr(self, "overlay"):
            self.overlay.update(self._sorted_tasks())

        if not visible:
            empty = tk.Frame(self.scroll.body, bg=APP_BG)
            empty.pack(fill=tk.BOTH, expand=True, pady=42)
            tk.Label(
                empty,
                text="这里还很清爽。\n添加一条待办，让它先替你惦记着。",
                bg=APP_BG,
                fg=MUTED,
                font=("Microsoft YaHei UI", 12),
                justify=tk.CENTER,
            ).pack()
            return

        for task in visible:
            self._add_task_card(task)

    def _add_task_card(self, task: Task) -> None:
        bg = CARD_DONE_BG if task.done else CARD_BG
        overdue = is_overdue(task.due_at, task.done)

        card = tk.Frame(self.scroll.body, bg=bg, highlightthickness=1, highlightbackground=BORDER)
        card.pack(fill=tk.X, padx=(0, 4), pady=(0, 10))

        inner = tk.Frame(card, bg=bg, padx=12, pady=10)
        inner.pack(fill=tk.X)

        done_var = tk.BooleanVar(value=task.done)
        check = tk.Checkbutton(
            inner,
            variable=done_var,
            command=lambda task_id=task.task_id, var=done_var: self._toggle_done(task_id, var.get()),
            bg=bg,
            activebackground=bg,
            selectcolor=bg,
            relief=tk.FLAT,
        )
        check.grid(row=0, column=0, rowspan=3, sticky=tk.NW, padx=(0, 8))

        title_fg = MUTED if task.done else TEXT
        title_font = ("Microsoft YaHei UI", 11, "overstrike") if task.done else ("Microsoft YaHei UI", 11, "bold")
        title = tk.Label(inner, text=task.title, bg=bg, fg=title_fg, font=title_font, anchor="w", justify=tk.LEFT)
        title.grid(row=0, column=1, sticky=tk.EW)

        badge_text = task.priority
        badge_bg = {"紧急": "#f3c6bf", "重要": "#f5dfb6", "普通": "#dce8d5"}.get(task.priority, "#dce8d5")
        badge_fg = {"紧急": "#8d2d25", "重要": "#805618", "普通": "#42634c"}.get(task.priority, "#42634c")
        tk.Label(
            inner,
            text=badge_text,
            bg=badge_bg,
            fg=badge_fg,
            font=("Microsoft YaHei UI", 9, "bold"),
            padx=8,
            pady=2,
        ).grid(row=0, column=2, sticky=tk.NE, padx=(8, 0))

        due_text = format_due(task.due_at)
        due_fg = DANGER if overdue else MUTED
        due_prefix = "已逾期 " if overdue else "截止 "
        tk.Label(
            inner,
            text=f"{due_prefix}{due_text}",
            bg=bg,
            fg=due_fg,
            font=("Microsoft YaHei UI", 9),
            anchor="w",
        ).grid(row=1, column=1, columnspan=2, sticky=tk.EW, pady=(4, 0))

        if task.note:
            tk.Label(
                inner,
                text=task.note,
                bg=bg,
                fg=MUTED,
                font=("Microsoft YaHei UI", 9),
                anchor="w",
                justify=tk.LEFT,
                wraplength=320,
            ).grid(row=2, column=1, columnspan=2, sticky=tk.EW, pady=(5, 0))

        actions = tk.Frame(inner, bg=bg)
        actions.grid(row=3, column=1, columnspan=2, sticky=tk.EW, pady=(8, 0))

        tk.Button(
            actions,
            text="编辑",
            command=lambda task_id=task.task_id: self._edit_task(task_id),
            bg="#eadfcd",
            fg=TEXT,
            relief=tk.FLAT,
            padx=10,
            pady=4,
            cursor="hand2",
        ).pack(side=tk.LEFT)
        tk.Button(
            actions,
            text="删除",
            command=lambda task_id=task.task_id: self._delete_task(task_id),
            bg="#f0d0ca",
            fg=DANGER,
            relief=tk.FLAT,
            padx=10,
            pady=4,
            cursor="hand2",
        ).pack(side=tk.LEFT, padx=(8, 0))

        inner.columnconfigure(1, weight=1)

    def _toggle_done(self, task_id: str, done: bool) -> None:
        task = self._find_task(task_id)
        if not task:
            return
        task.done = done
        task.updated_at = iso_now()
        if not done:
            task.reminded = False
        self._save_tasks()
        self._refresh_tasks()

    def _edit_task(self, task_id: str) -> None:
        task = self._find_task(task_id)
        if not task:
            return
        self.editing_id = task.task_id
        self.title_var.set(task.title)
        self.due_var.set(format_due(task.due_at) if task.due_at else "")
        self.priority_var.set(task.priority if task.priority in PRIORITIES else "普通")
        self.note_text.delete("1.0", tk.END)
        self.note_text.insert("1.0", task.note)
        self.save_button.configure(text="保存修改")
        self.status_var.set("正在编辑一条待办")

    def _delete_task(self, task_id: str) -> None:
        task = self._find_task(task_id)
        if not task:
            return
        if not messagebox.askyesno("确认删除", f"删除这条待办？\n\n{task.title}"):
            return
        self.tasks = [item for item in self.tasks if item.task_id != task_id]
        if self.editing_id == task_id:
            self._clear_form()
        self._save_tasks()
        self._refresh_tasks()

    def _delete_done(self) -> None:
        done_count = sum(1 for task in self.tasks if task.done)
        if done_count == 0:
            messagebox.showinfo("没有可清理项", "目前没有已完成的待办。")
            return
        if not messagebox.askyesno("清理完成项", f"确定删除 {done_count} 条已完成待办？"):
            return
        self.tasks = [task for task in self.tasks if not task.done]
        self._clear_form()
        self._save_tasks()
        self._refresh_tasks()

    def _export_tasks(self) -> None:
        path = filedialog.asksaveasfilename(
            title="导出待办",
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("JSON 文件", "*.json"), ("所有文件", "*.*")],
        )
        if not path:
            return

        target = Path(path)
        if target.suffix.lower() == ".json":
            target.write_text(
                json.dumps([task.to_dict() for task in self._sorted_tasks()], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        else:
            lines = ["桌面待办事项", "=" * 20, ""]
            for task in self._sorted_tasks():
                mark = "x" if task.done else " "
                lines.append(f"[{mark}] {task.title}")
                lines.append(f"    优先级：{task.priority}")
                lines.append(f"    截止：{format_due(task.due_at)}")
                if task.note:
                    lines.append(f"    备注：{task.note}")
                lines.append("")
            target.write_text("\n".join(lines), encoding="utf-8")

        self.status_var.set(f"已导出：{target.name}")
        messagebox.showinfo("导出成功", f"待办已导出到：\n{target}")

    def _toggle_topmost(self) -> None:
        if hasattr(self, "overlay"):
            self.overlay.set_topmost(self.topmost_var.get())
        self._save_tasks()

    def _toggle_overlay_locked(self) -> None:
        locked = self.overlay_locked_var.get()
        if hasattr(self, "overlay"):
            self.overlay.set_locked(locked)
        self._save_tasks()
        self.status_var.set("桌面文字已锁定" if locked else "桌面文字已解锁")

    def _toggle_overlay_visible(self) -> None:
        if self.overlay_visible_var.get():
            self.show_overlay()
        else:
            self.hide_overlay()

    def show_overlay(self) -> None:
        if self.closing:
            return
        self.overlay_visible_var.set(True)
        if hasattr(self, "overlay"):
            self.overlay.show()
        self._save_tasks()

    def hide_overlay(self) -> None:
        if self.closing:
            return
        self.overlay_visible_var.set(False)
        if hasattr(self, "overlay"):
            self.overlay.hide()
        self._save_tasks()

    def show_editor(self) -> None:
        if self.closing:
            return
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self.status_var.set("编辑器已打开")

    def hide_editor(self) -> None:
        if self.closing:
            return
        self._save_tasks()
        self.show_overlay()
        self.root.withdraw()

    def quit_app(self) -> None:
        if self.closing:
            return
        self.closing = True

        if self.reminder_after_id:
            try:
                self.root.after_cancel(self.reminder_after_id)
            except tk.TclError:
                pass
            self.reminder_after_id = None

        try:
            self._save_tasks()
        except Exception:
            pass

        if hasattr(self, "overlay"):
            self.overlay.destroy()

        try:
            self.root.quit()
            self.root.destroy()
        except tk.TclError:
            pass

    def _schedule_reminder_check(self) -> None:
        if self.closing:
            return
        self._check_reminders()
        if not self.closing:
            self.reminder_after_id = self.root.after(30_000, self._schedule_reminder_check)

    def _check_reminders(self) -> None:
        if self.closing:
            return
        changed = False
        due_tasks: list[Task] = []

        for task in self.tasks:
            if task.done or task.reminded or not task.due_at:
                continue
            try:
                due = due_for_logic(task.due_at)
            except ValueError:
                continue
            if due is not None and due <= datetime.now():
                task.reminded = True
                due_tasks.append(task)
                changed = True

        if changed:
            self._save_tasks()
            self._refresh_tasks()

        if due_tasks:
            preview = "\n".join(f"- {task.title}" for task in due_tasks[:5])
            more = "" if len(due_tasks) <= 5 else f"\n还有 {len(due_tasks) - 5} 条..."
            self.root.bell()
            messagebox.showinfo("待办提醒", f"这些待办到时间了：\n\n{preview}{more}")

    def _on_close(self) -> None:
        self.quit_app()


if __name__ == "__main__":
    DesktopTodoApp().run()
