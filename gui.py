import tkinter as tk
from tkinter import ttk, messagebox, font
from datetime import datetime
import csv
import zipfile
import sqlite3
import requests
import json
import threading

from config import save_config
from db import DB_FILE, get_all_users
from platform_compat import IS_MAC


SURFACE_BG = "#F3F7FB"
PANEL_BG = "#FFFFFF"
PRIMARY_TEXT = "#17324D"
SECONDARY_TEXT = "#5B7087"
ACCENT_BLUE = "#2F6FED"
ACCENT_BLUE_SOFT = "#E7F0FF"
ACCENT_CORAL = "#F46B5F"
ACCENT_CORAL_SOFT = "#FFE6E2"
SHADOW_COLOR = "#D7E3F4"
HEADER_TOP_BG = "#F2F8FF"
HEADER_BOTTOM_BG = "#E5F0FF"
REGISTER_TOP_BG = "#FFF8F0"
REGISTER_BOTTOM_BG = "#FFEADB"

STATUS_COLORS = {
    "出勤": "#4F7DFF",
    "退勤": "#FF8A7A",
    "外出": "#DDF8EA",
    "戻り": "#EEE1FF",
}

BUTTON_COLORS = {
    "出勤": {"bg": "#4F7DFF", "active": "#3E67D5", "text": "#FFFFFF"},
    "退勤": {"bg": "#FF8A7A", "active": "#E16F60", "text": "#FFFFFF"},
}


def configure_window_for_platform(root):
    root.title("出退勤管理")
    root.geometry("800x480+0+0")
    root.resizable(False, False)

    if IS_MAC:
        return

    def apply_fullscreen():
        try:
            root.update_idletasks()
            root.geometry("800x480+0+0")
            root.overrideredirect(True)
            root.attributes("-fullscreen", True)
            root.lift()
            root.focus_force()
            root.attributes("-topmost", True)
            root.after(250, lambda: root.attributes("-topmost", False))
        except tk.TclError:
            return

    root.after(100, apply_fullscreen)
    root.after(700, apply_fullscreen)
    root.after(1600, apply_fullscreen)


def bind_pressable_label(widget, command, default_bg, hover_bg, fg):
    widget.configure(bg=default_bg, fg=fg, cursor="hand2")
    widget.bind("<Enter>", lambda _e: widget.configure(bg=hover_bg))
    widget.bind("<Leave>", lambda _e: widget.configure(bg=default_bg))
    widget.bind("<Button-1>", lambda _e: command())


def _rounded_polygon_points(x1, y1, x2, y2, radius):
    return [
        x1 + radius, y1,
        x2 - radius, y1,
        x2, y1,
        x2, y1 + radius,
        x2, y2 - radius,
        x2, y2,
        x2 - radius, y2,
        x1 + radius, y2,
        x1, y2,
        x1, y2 - radius,
        x1, y1 + radius,
        x1, y1,
    ]


def create_rounded_button(parent, text, command, bg, hover_bg, fg, width=240, height=84, radius=28):
    canvas = tk.Canvas(
        parent,
        width=width,
        height=height,
        highlightthickness=0,
        bd=0,
        bg=PANEL_BG,
    )

    shadow = canvas.create_polygon(
        _rounded_polygon_points(6, 7, width - 6, height - 3, radius),
        smooth=True,
        fill="#E2E8F2",
        outline="",
    )
    shape = canvas.create_polygon(
        _rounded_polygon_points(4, 4, width - 8, height - 8, radius),
        smooth=True,
        fill=bg,
        outline="",
    )
    label = canvas.create_text(
        width / 2,
        height / 2,
        text=text,
        fill=fg,
        font=("Noto Sans", 18, "bold"),
    )

    def set_fill(color):
        canvas.itemconfigure(shape, fill=color)

    for target in (canvas,):
        target.bind("<Enter>", lambda _e: set_fill(hover_bg))
        target.bind("<Leave>", lambda _e: set_fill(bg))
        target.bind("<Button-1>", lambda _e: command())

    return canvas


def create_shadow_card(parent, bg=PANEL_BG, pad=(14, 14)):
    outer = tk.Frame(parent, bg=SHADOW_COLOR)
    inner = tk.Frame(outer, bg=bg)
    inner.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
    if pad:
        content = tk.Frame(inner, bg=bg, padx=pad[0], pady=pad[1])
        content.pack(fill=tk.BOTH, expand=True)
    else:
        content = inner
    return outer, content


def paint_vertical_gradient(canvas, top_color, bottom_color, width, height):
    canvas.delete("gradient")
    r1, g1, b1 = canvas.winfo_rgb(top_color)
    r2, g2, b2 = canvas.winfo_rgb(bottom_color)
    steps = max(height, 1)

    for i in range(steps):
        nr = int(r1 + (r2 - r1) * i / steps) // 256
        ng = int(g1 + (g2 - g1) * i / steps) // 256
        nb = int(b1 + (b2 - b1) * i / steps) // 256
        color = f"#{nr:02x}{ng:02x}{nb:02x}"
        canvas.create_line(0, i, width, i, tags=("gradient",), fill=color)

    canvas.lower("gradient")

# グローバル変数（自動切替の一時停止状態）
auto_switch_suspended = False
touch_notification_active = False  # カードタッチ通知中かどうか

def update_time(label, state_var, info_label, status_colors):
    """
    現在時刻を表示するとともに、auto_switch_suspended および touch_notification_active が False の場合、
    11時前なら「出勤」、11時以降なら「退勤」に自動切り替え、info_label の表示も更新する。
    """
    current_time = datetime.now()
    formatted_time = current_time.strftime("%Y-%m-%d %H:%M:%S")
    spaced_time = " ".join(formatted_time)
    label.config(text=spaced_time)
    
    global auto_switch_suspended, touch_notification_active
    if not auto_switch_suspended and not touch_notification_active:
        new_state = "出勤" if current_time.hour < 11 else "退勤"
        state_var.set(new_state)
        info_label.config(
            text=f"現在のステータス: {new_state}\nカード受付待機中...",
            bg=status_colors[new_state],
            fg="#FFFFFF"
        )
    
    label.after(1000, update_time, label, state_var, info_label, status_colors)


def create_gui(root, config, open_registration_window_callback, close_callback=None):
    """
    メインのGUIを作成して返す。
    ・ウィンドウサイズは WVGA (800x480) に固定し、全画面で起動
    ・自動切替機能：11時前は「出勤」、11時以降は「退勤」
    ・ステータスボタン押下時は、30秒間自動切替を停止
    """
    compact_mode = True
    noto_sans_font = font.Font(family="Noto Sans", size=14 if compact_mode else 16)
    title_font = font.Font(family="Noto Sans", size=13 if compact_mode else 15, weight="bold")
    status_font = font.Font(family="Noto Sans", size=18 if compact_mode else 22, weight="bold")
    helper_font = font.Font(family="Noto Sans", size=9 if compact_mode else 11)
    digital_font = font.Font(family="Digital-7", size=28 if compact_mode else 34)

    style = ttk.Style()
    style.theme_use("clam")
    style.configure("Worktime.Treeview", rowheight=30 if compact_mode else 34, font=("Noto Sans", 10 if compact_mode else 12))
    style.configure("Worktime.Treeview.Heading", font=("Noto Sans", 11, "bold"))

    root.configure(bg=SURFACE_BG)

    configure_window_for_platform(root)

    main_frame = tk.Frame(root, bg=SURFACE_BG, padx=10 if compact_mode else 20, pady=8 if compact_mode else 18)
    main_frame.pack(expand=True, fill=tk.BOTH)
    root._attendance_container = main_frame
    root._registration_mode_visible = False

    top_bar = tk.Frame(main_frame, bg=SURFACE_BG)
    top_bar.pack(fill=tk.X, pady=(0, 6))

    action_wrap = tk.Frame(top_bar, bg=SURFACE_BG)
    action_wrap.pack(side=tk.RIGHT)

    registration_button = tk.Label(
        action_wrap,
        text="カード登録",
        font=("Noto Sans", 10 if compact_mode else 12, "bold"),
        padx=14 if compact_mode else 18,
        pady=7 if compact_mode else 10,
        bd=1,
        relief="solid",
    )
    registration_button.pack(side=tk.LEFT, padx=(0, 8))
    bind_pressable_label(
        registration_button,
        open_registration_window_callback,
        "#FFFFFF",
        "#EEF5FF",
        PRIMARY_TEXT,
    )

    settings_button = tk.Label(
        action_wrap,
        text="設定",
        font=("Noto Sans", 10 if compact_mode else 12, "bold"),
        padx=14 if compact_mode else 18,
        pady=7 if compact_mode else 10,
        bd=1,
        relief="solid",
    )
    settings_button.pack(side=tk.LEFT)
    bind_pressable_label(
        settings_button,
        lambda: open_settings_window(root, config),
        "#FFFFFF",
        "#EEF5FF",
        PRIMARY_TEXT,
    )

    if close_callback is not None:
        close_button = tk.Label(
            action_wrap,
            text="閉じる",
            font=("Noto Sans", 10 if compact_mode else 12, "bold"),
            padx=14 if compact_mode else 18,
            pady=7 if compact_mode else 10,
            bd=1,
            relief="solid",
        )
        close_button.pack(side=tk.LEFT, padx=(8, 0))
        bind_pressable_label(
            close_button,
            close_callback,
            "#FFFFFF",
            "#EEF5FF",
            PRIMARY_TEXT,
        )

    body_frame = tk.Frame(main_frame, bg=SURFACE_BG)
    body_frame.pack(fill=tk.BOTH, expand=True)
    left_card, left_inner = create_shadow_card(body_frame, pad=(10, 10) if compact_mode else (14, 14))
    left_card.pack(fill=tk.BOTH, expand=True)

    tk.Label(
        left_inner,
        text="現在時刻",
        font=title_font,
        bg=PANEL_BG,
        fg=PRIMARY_TEXT,
    ).pack(anchor=tk.W)

    tk.Label(
        left_inner,
        text="自動切替は 11:00 を境に出勤 / 退勤を更新します",
        font=helper_font,
        bg=PANEL_BG,
        fg=SECONDARY_TEXT,
    ).pack(anchor=tk.W, pady=(2, 6 if compact_mode else 12))

    time_frame = tk.Frame(left_inner, bg="#F6FAFF", padx=12 if compact_mode else 18, pady=8 if compact_mode else 18)
    time_frame.pack(fill=tk.X, pady=(0, 6 if compact_mode else 14))
    time_label = tk.Label(
        time_frame,
        text="2 0 2 5 - 0 1 - 2 9   1 6 : 5 9 : 5 5",
        font=digital_font,
        fg=PRIMARY_TEXT,
        bg="#F6FAFF",
    )
    time_label.pack(anchor=tk.CENTER)

    state_var = tk.StringVar(value="出勤")

    info_label = tk.Label(
        left_inner,
        text="現在のステータス: 出勤\nカード受付待機中...",
        font=status_font,
        fg="#FFFFFF",
        bg=STATUS_COLORS["出勤"],
        anchor="center",
        height=2,
        wraplength=720 if compact_mode else 640,
        padx=12 if compact_mode else 18,
        pady=10 if compact_mode else 18,
    )
    info_label.pack(fill=tk.X, pady=(0, 6 if compact_mode else 14))

    def suspend_auto_switch():
        global auto_switch_suspended
        auto_switch_suspended = True
        root.after(30000, reset_auto_switch)

    def reset_auto_switch():
        global auto_switch_suspended
        auto_switch_suspended = False

    tk.Label(
        left_inner,
        text="打刻モード",
        font=title_font,
        bg=PANEL_BG,
        fg=PRIMARY_TEXT,
    ).pack(anchor=tk.W)

    tk.Label(
        left_inner,
        text="出勤または退勤を選んで、そのままカードをタッチします",
        font=helper_font,
        bg=PANEL_BG,
        fg=SECONDARY_TEXT,
    ).pack(anchor=tk.W, pady=(2, 6 if compact_mode else 12))

    button_frame = tk.Frame(left_inner, bg=PANEL_BG)
    button_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 0))
    button_frame.grid_columnconfigure(0, weight=1)
    button_frame.grid_columnconfigure(1, weight=1)
    button_frame.grid_columnconfigure(2, weight=1)
    button_frame.grid_columnconfigure(3, weight=1)
    button_frame.grid_rowconfigure(0, weight=1)

    filtered_states = ["出勤", "退勤"]

    for i, state in enumerate(filtered_states):
        colors = BUTTON_COLORS[state]
        button = create_rounded_button(
            button_frame,
            state,
            lambda s=state: [
                state_var.set(s),
                update_status_label(s, info_label, STATUS_COLORS[s]),
                suspend_auto_switch(),
            ],
            colors["bg"],
            colors["active"],
            colors["text"],
            width=220 if compact_mode else 240,
            height=84 if compact_mode else 84,
            radius=22 if compact_mode else 28,
        )
        target_column = 1 if i == 0 else 2
        button.grid(row=0, column=target_column, pady=(0, 0))

    update_time(time_label, state_var, info_label, STATUS_COLORS)

    return state_var, time_label, info_label


def open_registration_window(
    root,
    registration_session,
    sync_users_callback,
    on_registration_selected,
    on_registration_cleared,
):
    """カード登録用の同一画面ビューへ切り替える"""
    existing_view = getattr(root, "_registration_view", None)
    if existing_view is not None:
        if hasattr(root, "_attendance_container"):
            root._attendance_container.pack_forget()
        existing_view.pack(fill=tk.BOTH, expand=True)
        root._registration_mode_visible = True
        if hasattr(root, "_registration_clear_selection"):
            root._registration_clear_selection()
        if hasattr(root, "_registration_refresh"):
            root._registration_refresh()
        if hasattr(root, "_registration_focus_search"):
            root._registration_focus_search()
        return

    compact_mode = True
    if hasattr(root, "_attendance_container"):
        root._attendance_container.pack_forget()
    root._registration_mode_visible = True
    status_var = tk.StringVar(value="ユーザーを選択するとカード登録モードになります")
    selected_user_var = tk.StringVar(value="未選択")
    search_var = tk.StringVar()
    summary_var = tk.StringVar(value="ユーザー 0 件")

    shell = tk.Frame(root, bg=SURFACE_BG, padx=10 if compact_mode else 18, pady=8 if compact_mode else 18)
    shell.pack(fill=tk.BOTH, expand=True)
    root._registration_view = shell

    top_bar = tk.Frame(shell, bg=SURFACE_BG)
    top_bar.pack(fill=tk.X, pady=(0, 6))

    tk.Label(
        top_bar,
        text="カード登録",
        font=("Noto Sans", 14 if compact_mode else 16, "bold"),
        bg=SURFACE_BG,
        fg=PRIMARY_TEXT,
    ).pack(side=tk.LEFT)

    body = tk.Frame(shell, bg=SURFACE_BG)
    body.pack(fill=tk.BOTH, expand=True)
    if compact_mode:
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=6)
        body.grid_rowconfigure(1, weight=1)
        list_card, list_inner = create_shadow_card(body, pad=(10, 10))
        list_card.grid(row=0, column=0, sticky="nsew", pady=(0, 6))
        side_card, side_inner = create_shadow_card(body, pad=(8, 7))
        side_card.grid(row=1, column=0, sticky="nsew")
    else:
        body.grid_columnconfigure(0, weight=5)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)
        list_card, list_inner = create_shadow_card(body)
        list_card.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        side_card, side_inner = create_shadow_card(body)
        side_card.grid(row=0, column=1, sticky="nsew")

    toolbar = tk.Frame(list_inner, bg=PANEL_BG)
    toolbar.pack(fill=tk.X, pady=(0, 8))

    tk.Label(toolbar, text="ユーザー検索", font=("Noto Sans", 11 if compact_mode else 12, "bold"), bg=PANEL_BG, fg=PRIMARY_TEXT).pack(side=tk.LEFT)

    search_entry = tk.Entry(
        toolbar,
        textvariable=search_var,
        font=("Noto Sans", 11 if compact_mode else 12),
        relief="flat",
        bg="#F4F8FC",
        fg=PRIMARY_TEXT,
        insertbackground=PRIMARY_TEXT,
        width=14 if compact_mode else 24,
    )
    search_entry.pack(side=tk.RIGHT, padx=(10, 0), ipady=6 if compact_mode else 8)

    tk.Label(toolbar, textvariable=summary_var, font=("Noto Sans", 10 if compact_mode else 11), bg=PANEL_BG, fg=SECONDARY_TEXT).pack(side=tk.RIGHT)

    columns = ("ID", "名前", "ログインID", "カード")
    tree_area = tk.Frame(list_inner, bg=PANEL_BG)
    tree_area.pack(fill=tk.BOTH, expand=True)

    tree_frame = tk.Frame(tree_area, bg=PANEL_BG)
    tree_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    scroll_tools = tk.Frame(tree_area, bg=PANEL_BG, padx=8)
    scroll_tools.pack(side=tk.RIGHT, fill=tk.Y)

    user_tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=7 if compact_mode else 14, style="Worktime.Treeview")
    for col in columns:
        user_tree.heading(col, text=col)
    user_tree.column("ID", width=105 if compact_mode else 130, anchor=tk.W)
    user_tree.column("名前", width=140 if compact_mode else 180, anchor=tk.W)
    user_tree.column("ログインID", width=120 if compact_mode else 180, anchor=tk.W)
    user_tree.column("カード", width=120 if compact_mode else 180, anchor=tk.W)
    tree_scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=user_tree.yview)
    user_tree.configure(yscrollcommand=tree_scrollbar.set)
    user_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    tree_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    if compact_mode:
        selected_panel = tk.Frame(side_inner, bg=ACCENT_BLUE_SOFT, padx=10, pady=8)
        selected_panel.pack(fill=tk.BOTH, expand=True)
        tk.Label(selected_panel, text="登録対象", font=("Noto Sans", 11, "bold"), bg=ACCENT_BLUE_SOFT, fg=PRIMARY_TEXT).pack(anchor=tk.W)
        tk.Label(selected_panel, textvariable=selected_user_var, font=("Noto Sans", 11), bg=ACCENT_BLUE_SOFT, fg=PRIMARY_TEXT, wraplength=680, justify="left").pack(anchor=tk.W, pady=(4, 0))
        tk.Label(selected_panel, textvariable=status_var, font=("Noto Sans", 10), bg=ACCENT_BLUE_SOFT, fg=SECONDARY_TEXT, wraplength=680, justify="left").pack(anchor=tk.W, pady=(2, 0))
    else:
        right_sections = [
            ("1. ユーザーを選択", "一覧から対象者を選ぶと、登録待機モードに切り替わります。"),
            ("2. カードをタッチ", "選択中のユーザーへカード番号を紐付けます。"),
            ("3. 必要なら最新化", "サーバー側でユーザーが増えた場合は「最新化」で再取得します。"),
        ]
        for title, desc in right_sections:
            section = tk.Frame(side_inner, bg="#F7FAFE", padx=14, pady=12)
            section.pack(fill=tk.X, pady=(0, 10))
            tk.Label(section, text=title, font=("Noto Sans", 12, "bold"), bg="#F7FAFE", fg=PRIMARY_TEXT).pack(anchor=tk.W)
            tk.Label(section, text=desc, font=("Noto Sans", 11), bg="#F7FAFE", fg=SECONDARY_TEXT, justify="left", wraplength=220).pack(anchor=tk.W, pady=(4, 0))

        selected_panel = tk.Frame(side_inner, bg=ACCENT_BLUE_SOFT, padx=14, pady=14)
        selected_panel.pack(fill=tk.X, pady=(4, 0))
        tk.Label(selected_panel, text="登録対象", font=("Noto Sans", 12, "bold"), bg=ACCENT_BLUE_SOFT, fg=PRIMARY_TEXT).pack(anchor=tk.W)
        tk.Label(selected_panel, textvariable=selected_user_var, font=("Noto Sans", 12), bg=ACCENT_BLUE_SOFT, fg=PRIMARY_TEXT, wraplength=220, justify="left").pack(anchor=tk.W, pady=(6, 0))
        tk.Label(selected_panel, textvariable=status_var, font=("Noto Sans", 11), bg=ACCENT_BLUE_SOFT, fg=SECONDARY_TEXT, wraplength=220, justify="left").pack(anchor=tk.W, pady=(6, 0))

    def load_users():
        for item in user_tree.get_children():
            user_tree.delete(item)
        keyword = search_var.get().strip().lower()
        users = get_all_users()
        visible_count = 0
        for user in users:
            haystack = " ".join(
                [
                    str(user["res_user_id"] or ""),
                    str(user["name"] or ""),
                    str(user["login_id"] or ""),
                    str(user["id_serial"] or ""),
                ]
            ).lower()
            if keyword and keyword not in haystack:
                continue
            serial_text = user["id_serial"] if user["id_serial"] else "未登録"
            user_tree.insert(
                "",
                tk.END,
                values=(user["res_user_id"], user["name"], user["login_id"], serial_text),
            )
            visible_count += 1
        summary_var.set(f"ユーザー {visible_count} 件")

    touch_scroll_state = {"y": None}

    def scroll_tree(units):
        user_tree.yview_scroll(units, "units")

    def start_touch_scroll(event):
        touch_scroll_state["y"] = event.y_root

    def drag_touch_scroll(event):
        previous_y = touch_scroll_state["y"]
        if previous_y is None:
            touch_scroll_state["y"] = event.y_root
            return

        delta = previous_y - event.y_root
        if abs(delta) >= 18:
            steps = int(delta / 18)
            user_tree.yview_scroll(steps, "units")
            touch_scroll_state["y"] = event.y_root
            return "break"

    def end_touch_scroll(_event=None):
        touch_scroll_state["y"] = None

    def clear_selection():
        selected_items = user_tree.selection()
        if selected_items:
            user_tree.selection_remove(selected_items)
        registration_session.clear()
        selected_user_var.set("未選択")
        status_var.set("ユーザーを選択するとカード登録モードになります")
        on_registration_cleared()

    def handle_user_selected(_event=None):
        selection = user_tree.selection()
        if not selection:
            clear_selection()
            return
        values = user_tree.item(selection[0])["values"]
        user_id = values[0]
        user_name = values[1]
        registration_session.select_user(user_id, user_name)
        selected_user_var.set(f"選択中: {user_name} ({user_id})")
        status_var.set("カードをタッチしてください")
        on_registration_selected(user_name)

    def refresh_users():
        status_var.set("ユーザー一覧を更新中...")

        def worker():
            success = sync_users_callback()

            def finish():
                load_users()
                clear_selection()
                status_var.set(
                    "ユーザー一覧を更新しました" if success else "更新に失敗しました"
                )

            root.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    def close_window():
        clear_selection()
        root._registration_mode_visible = False
        shell.pack_forget()
        if hasattr(root, "_attendance_container"):
            root._attendance_container.pack(expand=True, fill=tk.BOTH)
        search_var.set("")

    action_wrap = tk.Frame(top_bar, bg=SURFACE_BG)
    action_wrap.pack(side=tk.RIGHT)

    back_button = tk.Label(
        action_wrap,
        text="戻る",
        font=("Noto Sans", 10 if compact_mode else 12, "bold"),
        padx=14 if compact_mode else 18,
        pady=7 if compact_mode else 10,
        bd=1,
        relief="solid",
    )
    back_button.pack(side=tk.RIGHT)
    bind_pressable_label(
        back_button,
        close_window,
        "#FFFFFF",
        "#EEF5FF",
        PRIMARY_TEXT,
    )

    clear_button = tk.Label(
        action_wrap,
        text="選択解除",
        font=("Noto Sans", 10 if compact_mode else 12, "bold"),
        padx=14 if compact_mode else 18,
        pady=7 if compact_mode else 10,
        bd=1,
        relief="solid",
    )
    clear_button.pack(side=tk.RIGHT, padx=(0, 8))
    bind_pressable_label(
        clear_button,
        clear_selection,
        "#FFFFFF",
        "#EEF5FF",
        PRIMARY_TEXT,
    )

    refresh_button = tk.Label(
        action_wrap,
        text="最新化",
        font=("Noto Sans", 10 if compact_mode else 12, "bold"),
        padx=14 if compact_mode else 18,
        pady=7 if compact_mode else 10,
        bd=1,
        relief="solid",
    )
    refresh_button.pack(side=tk.RIGHT, padx=(0, 8))
    bind_pressable_label(
        refresh_button,
        refresh_users,
        "#FFFFFF",
        "#EEF5FF",
        PRIMARY_TEXT,
    )

    scroll_up_button = tk.Label(
        scroll_tools,
        text="▲",
        font=("Noto Sans", 14, "bold"),
        padx=12,
        pady=10,
        bd=1,
        relief="solid",
    )
    scroll_up_button.pack(fill=tk.X)
    bind_pressable_label(scroll_up_button, lambda: scroll_tree(-3), "#FFFFFF", "#EEF5FF", PRIMARY_TEXT)

    scroll_hint = tk.Label(
        scroll_tools,
        text="一覧\n移動",
        font=("Noto Sans", 9, "bold"),
        bg=SURFACE_BG,
        fg=SECONDARY_TEXT,
        justify="center",
    )
    scroll_hint.pack(fill=tk.X, pady=8)

    scroll_down_button = tk.Label(
        scroll_tools,
        text="▼",
        font=("Noto Sans", 14, "bold"),
        padx=12,
        pady=10,
        bd=1,
        relief="solid",
    )
    scroll_down_button.pack(fill=tk.X)
    bind_pressable_label(scroll_down_button, lambda: scroll_tree(3), "#FFFFFF", "#EEF5FF", PRIMARY_TEXT)

    user_tree.bind("<<TreeviewSelect>>", handle_user_selected)
    user_tree.bind("<ButtonPress-1>", start_touch_scroll, add="+")
    user_tree.bind("<B1-Motion>", drag_touch_scroll, add="+")
    user_tree.bind("<ButtonRelease-1>", end_touch_scroll, add="+")
    search_var.trace_add("write", lambda *_args: load_users())
    load_users()
    search_entry.focus_set()
    root._registration_refresh = load_users
    root._registration_focus_search = search_entry.focus_set
    root._registration_clear_selection = clear_selection
    root._close_registration_view = close_window


def update_status_label(state, info_label, bg_color=None):
    """
    ステータス変更時にラベルの背景色とテキストを更新
    """
    if bg_color is None:
        bg_color = info_label["bg"]  # 現在の背景色を取得

    info_label.config(
        text=f"現在のステータス: {state}\nカード受付待機中...",
        bg=bg_color,
        fg="#FFFFFF"
    )


def update_user_label(info_label, info, state, status_color, text_color="#1E3A8A", font_weight="normal", change_bg=True):
    """
    ユーザー情報や状態をラベルに通知表示する。
    ・change_bg が True なら背景色も status_color に設定、False なら現状の背景色を維持する。
    ・通知表示後、1500ms 後にデフォルトの「カード受付待機中...」表示に戻す。
    """
    global touch_notification_active
    touch_notification_active = True  # 通知中フラグをオン

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    text = f"現在のステータス: {state}\n{info}\n[{timestamp}]" if info else f"現在のステータス: {state}\nカード受付待機中..."
    
    current_bg = info_label.cget("bg")
    bg_to_use = status_color if change_bg else current_bg

    # info_label の現在のフォントから新たなフォントオブジェクトを生成
    custom_font = font.Font(font=info_label.cget("font"))
    custom_font.configure(weight=font_weight)
    
    info_label.config(text=text, bg=bg_to_use, fg=text_color, font=custom_font)
    
    # 1500ms 後にデフォルトの状態に戻す
    def reset_label():
        global touch_notification_active
        default_fg = "#1E3A8A"
        default_weight = "normal"
        # フォントサイズを20に固定
        default_font = font.Font(family="Noto Sans", size=20, weight=default_weight)
        # 背景色は change_bg により status_color か現状の背景色
        reset_bg = status_color if change_bg else current_bg
        info_label.config(
            text=f"現在のステータス: {state}\nカード受付待機中...",
            bg=reset_bg,
            fg=PRIMARY_TEXT,
            font=default_font
        )
        touch_notification_active = False  # 通知終了
    info_label.after(2000, reset_label)


def on_state_button_click(state, state_var, state_label):
    """
    ステートボタンをクリックしたときに呼ばれる
    """
    state_var.set(state)
    state_label.config(text=state)


# def update_user_label(label, info, state):
#     """
#     ユーザー情報や状態をラベルに表示
#     """
#     timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#     text = f"{info}\n[{state}] {timestamp}" if info else ""
#     label.config(text=text)


# def update_time(label):
#     """
#     現在時刻を更新し続ける（文字間にスペースを追加）
#     """
#     # 現在時刻を取得
#     current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

#     # 各文字間にスペースを追加
#     spaced_time = " ".join(current_time)

#     # ラベルを更新
#     label.config(text=spaced_time)

#     # 1秒ごとに再実行
#     label.after(1000, update_time, label)


def open_settings_window(root, config):
    """
    設定画面を表示
    """
    settings_window = tk.Toplevel(root)
    settings_window.title("設定")

    # ラベルとエントリーの作成
    labels = [
        ("サーバーヘルスチェックAPI:", "server_helth_api"),
        ("ユーザーリストAPI:", "user_list_api"),
        ("タイムスタンプ送信API:", "set_timestamp_api"),
        ("マージAPI:", "marge_api"),
        ("ユーザーデータファイル:", "user_data_file"),
        ("ユーザーシリアル登録API:", "set_user_serial"),
        ("サーバーURL:", "server_url"),
        ("ユーザーID:", "user_id"),
    ]

    entries = {}

    for i, (label_text, key) in enumerate(labels):
        tk.Label(settings_window, text=label_text).grid(row=i, column=0, sticky=tk.W, padx=10, pady=5)
        entry = tk.Entry(settings_window, width=40)
        entry.grid(row=i, column=1, padx=10, pady=5)
        entry.insert(0, config.get(key, ""))  # デフォルトで値を取得
        entries[key] = entry

    # 自動同期オプション
    auto_sync_var = tk.BooleanVar(value=config.get("auto_sync", False))
    tk.Checkbutton(settings_window, text="自動同期を有効にする", variable=auto_sync_var).grid(
        row=len(labels), column=0, columnspan=2, pady=5
    )

    def save_settings():
        """
        設定を保存
        """
        for key, entry in entries.items():
            config[key] = entry.get()

        config["auto_sync"] = auto_sync_var.get()

        # 設定を保存（仮の保存処理）
        with open("config.json", "w") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)

        settings_window.destroy()

    def merge_records():
        """
        未連携データをマージAPIに送信
        """
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, serial_number, timestamp, state, back_user_id, user_name, login_id
                FROM attendance
                WHERE marge IS NULL OR marge = 0
            """)
            records = cursor.fetchall()

            if not records:
                messagebox.showinfo("マージ", "未連携のデータはありません。")
                return

            payload = []
            for record in records:
                payload.append({
                    "marge_id": record[0],
                    "serial_no": record[1],
                    "timestamp": record[2],
                    "state": record[3],
                    "user_id": record[4],
                    "user_name": record[5],
                    "login_id": record[6],
                })

            response = requests.post(config["marge_api"], json=payload)
            if response.status_code == 200:
                # 成功 -> margeを1に更新
                record_ids = [rec[0] for rec in records]
                placeholders = ",".join("?" for _ in record_ids)
                cursor.execute(f"UPDATE attendance SET marge = 1 WHERE id IN ({placeholders})", record_ids)
                conn.commit()
                messagebox.showinfo("マージ", "データの連携に成功しました。")
            else:
                messagebox.showerror("エラー", f"データ連携に失敗: {response.status_code}")

        except Exception as e:
            messagebox.showerror("エラー", f"データ連携中にエラーが発生しました。\n{e}")
        finally:
            conn.close()

    def export_to_csv():
        """
        未連携データをCSV出力
        """
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, serial_number, timestamp, state, back_user_id, user_name, login_id
                FROM attendance
                WHERE marge IS NULL OR marge = 0
            """)
            records = cursor.fetchall()

            if not records:
                messagebox.showinfo("CSV出力", "未連携のデータはありません。")
                return

            csv_file = f"attendance_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            zip_file = f"attendance_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"

            # CSV書き込み
            with open(csv_file, "w", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow(["ID", "Serial Number", "Timestamp", "State", "Back User ID", "User Name", "Login ID"])
                writer.writerows(records)

            # ZIP圧縮
            with zipfile.ZipFile(zip_file, "w", zipfile.ZIP_DEFLATED) as zipf:
                zipf.write(csv_file, arcname=csv_file)

            # marge を 1 に更新
            record_ids = [rec[0] for rec in records]
            placeholders = ",".join("?" for _ in record_ids)
            cursor.execute(f"UPDATE attendance SET marge = 1 WHERE id IN ({placeholders})", record_ids)
            conn.commit()

            messagebox.showinfo("CSV出力", f"CSV出力が完了しました。\nZIPファイル: {zip_file}")
            print(f"ZIPファイルが生成されました: {zip_file}")

        except Exception as e:
            messagebox.showerror("エラー", f"CSV出力中にエラーが発生しました。\n{e}")
        finally:
            conn.close()

    # 設定画面のボタン
    button_frame = tk.Frame(settings_window)
    button_frame.grid(row=len(labels) + 1, columnspan=2, pady=10)

    tk.Button(button_frame, text="保存", command=save_settings).pack(side=tk.LEFT, padx=5)
    tk.Button(button_frame, text="マージ", command=merge_records).pack(side=tk.LEFT, padx=5)
    tk.Button(button_frame, text="CSV出力", command=export_to_csv).pack(side=tk.LEFT, padx=5)
