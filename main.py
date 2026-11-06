import ctypes
import sys
import tkinter as tk
import customtkinter as ctk
from PIL import Image, ImageDraw, ImageTk

from config import AppConfig
from input_manager import get_vk, cleanup_timers
from overlay import TrackingOverlay
from engine import TriggerEngine

# Set explicit Windows AppUserModelID so taskbar displays our custom icon
try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Drago.GotaAutoReverse.v2")
except Exception:
    pass

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


def create_app_icon_image(size: int = 256) -> Image.Image:
    """Generates the custom Gota.io Auto Reverse icon in memory."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = max(2, size // 16)
    r = size // 4

    # Obsidian rounded badge with cyan border
    d.rounded_rectangle(
        [pad, pad, size - pad - 1, size - pad - 1],
        radius=r,
        fill=(11, 15, 25, 255),
        outline=(56, 189, 248, 255),
        width=max(2, size // 26),
    )

    # Secondary cell (violet)
    c1_r = int(size * 0.22)
    c1_x, c1_y = int(size * 0.36), int(size * 0.62)
    d.ellipse(
        [c1_x - c1_r, c1_y - c1_r, c1_x + c1_r, c1_y + c1_r],
        fill=(168, 85, 247, 235),
        outline=(233, 213, 255, 255),
        width=max(2, size // 42),
    )

    # Primary reverse-split cell (electric cyan)
    c2_r = int(size * 0.27)
    c2_x, c2_y = int(size * 0.63), int(size * 0.38)
    d.ellipse(
        [c2_x - c2_r, c2_y - c2_r, c2_x + c2_r, c2_y + c2_r],
        fill=(6, 182, 212, 245),
        outline=(165, 243, 252, 255),
        width=max(2, size // 36),
    )

    # Precision black crosshair locked on the cell rim
    ch_x, ch_y = int(size * 0.45), int(size * 0.53)
    cr = max(4, size // 11)
    w = max(2, size // 30)
    d.ellipse([ch_x - cr, ch_y - cr, ch_x + cr, ch_y + cr], outline=(10, 14, 23, 255), width=w)
    arm = cr + max(3, size // 22)
    d.line([ch_x - arm, ch_y, ch_x + arm, ch_y], fill=(10, 14, 23, 255), width=w)
    d.line([ch_x, ch_y - arm, ch_x, ch_y + arm], fill=(10, 14, 23, 255), width=w)
    return img


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Gota.io Auto Reverse • Made by Drago")
        self.geometry("680x840")
        self.resizable(False, False)
        self.configure(fg_color="#090d16")

        # Apply custom window & taskbar icon (override CTk's delayed default icon)
        self._icon_photos = []
        self._apply_custom_icon()
        self.after(250, self._apply_custom_icon)

        self.config = AppConfig.load()

        # Initialize Overlay
        self.overlay = TrackingOverlay(master=self, dot_size=self.config.overlay_dot_size)
        self.overlay.set_visibility(self.config.show_overlay)

        # Initialize Engine
        self.engine = TriggerEngine(self.config, self.overlay)

        self._build_ui()

        # Start Engine immediately
        self.engine.start()

        # UI update timer
        self._update_diagnostics()

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _apply_custom_icon(self):
        try:
            img_256 = create_app_icon_image(256)
            img_64 = create_app_icon_image(64)
            img_32 = create_app_icon_image(32)
            img_16 = create_app_icon_image(16)
            self._icon_photos = [
                ImageTk.PhotoImage(img_256),
                ImageTk.PhotoImage(img_64),
                ImageTk.PhotoImage(img_32),
                ImageTk.PhotoImage(img_16),
            ]
            self.wm_iconphoto(True, *self._icon_photos)
        except Exception:
            pass

    def _build_ui(self):
        # ── TOP HEADER BANNER ──
        header_frame = ctk.CTkFrame(
            self,
            corner_radius=14,
            fg_color="#111827",
            border_width=1,
            border_color="#1e293b",
        )
        header_frame.pack(fill="x", padx=18, pady=(16, 8))

        header_inner = ctk.CTkFrame(header_frame, fg_color="transparent")
        header_inner.pack(fill="x", padx=16, pady=12)

        # Left side: Logo + Title
        left_hdr = ctk.CTkFrame(header_inner, fg_color="transparent")
        left_hdr.pack(side="left", fill="y")

        try:
            logo_ctk = ctk.CTkImage(
                light_image=create_app_icon_image(128),
                dark_image=create_app_icon_image(128),
                size=(46, 46),
            )
            logo_lbl = ctk.CTkLabel(left_hdr, image=logo_ctk, text="")
            logo_lbl.pack(side="left", padx=(0, 12))
        except Exception:
            pass

        title_stack = ctk.CTkFrame(left_hdr, fg_color="transparent")
        title_stack.pack(side="left")

        title_label = ctk.CTkLabel(
            title_stack,
            text="GOTA.IO AUTO REVERSE",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color="#38bdf8",
        )
        title_label.pack(anchor="w")

        subtitle = ctk.CTkLabel(
            title_stack,
            text="Sub-1ms Optical Reverse Engine • 8-Axis Edge Lock • Auto-Aim Snap",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#94a3b8",
        )
        subtitle.pack(anchor="w")

        # Right side: Author badge
        right_hdr = ctk.CTkFrame(header_inner, fg_color="transparent")
        right_hdr.pack(side="right")

        author_badge = ctk.CTkLabel(
            right_hdr,
            text=" ★ Made by Drago ",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#e9d5ff",
            fg_color="#3b0764",
            corner_radius=8,
            padx=10,
            pady=4,
        )
        author_badge.pack(anchor="e")

        # ── LIVE TELEMETRY BAR (3 CARDS) ──
        telemetry_row = ctk.CTkFrame(self, fg_color="transparent")
        telemetry_row.pack(fill="x", padx=18, pady=(0, 8))
        telemetry_row.grid_columnconfigure((0, 1, 2), weight=1, uniform="tele")

        # Card 1: Engine Status
        c_status = ctk.CTkFrame(
            telemetry_row, corner_radius=12, fg_color="#0f172a", border_width=1, border_color="#1e293b"
        )
        c_status.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        ctk.CTkLabel(
            c_status,
            text="ENGINE STATUS",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#64748b",
        ).pack(anchor="w", padx=12, pady=(8, 0))
        self.lbl_status = ctk.CTkLabel(
            c_status,
            text="READY (IDLE)",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#38bdf8",
        )
        self.lbl_status.pack(anchor="w", padx=12, pady=(2, 8))

        # Card 2: Scan Latency
        c_lat = ctk.CTkFrame(
            telemetry_row, corner_radius=12, fg_color="#0f172a", border_width=1, border_color="#1e293b"
        )
        c_lat.grid(row=0, column=1, sticky="nsew", padx=5)
        ctk.CTkLabel(
            c_lat,
            text="SCAN LATENCY",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#64748b",
        ).pack(anchor="w", padx=12, pady=(8, 0))
        self.lbl_latency = ctk.CTkLabel(
            c_lat,
            text="0.0 µs (0.000 ms)",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#34d399",
        )
        self.lbl_latency.pack(anchor="w", padx=12, pady=(2, 8))

        # Card 3: Probe Telemetry & Reverses
        c_probe = ctk.CTkFrame(
            telemetry_row, corner_radius=12, fg_color="#0f172a", border_width=1, border_color="#1e293b"
        )
        c_probe.grid(row=0, column=2, sticky="nsew", padx=(5, 0))
        top_probe = ctk.CTkFrame(c_probe, fg_color="transparent")
        top_probe.pack(fill="x", padx=12, pady=(8, 0))
        ctk.CTkLabel(
            top_probe,
            text="PROBE TELEMETRY",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#64748b",
        ).pack(side="left")
        self.lbl_triggers = ctk.CTkLabel(
            top_probe,
            text="Fired: 0",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#c084fc",
        )
        self.lbl_triggers.pack(side="right")

        self.lbl_probe_info = ctk.CTkLabel(
            c_probe,
            text="Edge: N/A | RGB: [0,0,0]",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#e2e8f0",
        )
        self.lbl_probe_info.pack(anchor="w", padx=12, pady=(2, 8))

        # ── SCROLLABLE SETTINGS CONTAINER ──
        scroll = ctk.CTkScrollableFrame(
            self,
            corner_radius=14,
            fg_color="#0f172a",
            border_width=1,
            border_color="#1e293b",
        )
        scroll.pack(fill="both", expand=True, padx=18, pady=4)

        # ── SECTION 1: KEY BINDINGS & MODES (2x2 GRID) ──
        self._create_section_header(scroll, "KEY BINDINGS & TRIGGER MODES", "Configure hotkeys for each tracking mode")

        kb_grid = ctk.CTkFrame(scroll, fg_color="transparent")
        kb_grid.pack(fill="x", pady=(2, 10))
        kb_grid.grid_columnconfigure((0, 1), weight=1, uniform="kb")

        self.ent_fixed_key = self._create_keybind_card(
            kb_grid,
            row=0,
            col=0,
            title="Fixed Mode (Toggle)",
            desc="Glides to edge & triggers on black bg",
            default_val=self.config.fixed_toggle_key,
            accent="#34d399",
        )
        self.ent_smart_key = self._create_keybind_card(
            kb_grid,
            row=0,
            col=1,
            title="Smart Mode (Toggle)",
            desc="Locks cell color & fires on change",
            default_val=self.config.smart_toggle_key,
            accent="#c084fc",
        )
        self.ent_movable_key = self._create_keybind_card(
            kb_grid,
            row=1,
            col=0,
            title="Movable Mode (Hold)",
            desc="Samples live under your cursor",
            default_val=self.config.movable_hold_key,
            accent="#f59e0b",
        )
        self.ent_split_key = self._create_keybind_card(
            kb_grid,
            row=1,
            col=1,
            title="Reverse / Split Action Key",
            desc="Key injected when trigger fires",
            default_val=self.config.split_action_key,
            accent="#38bdf8",
        )

        # ── SECTION 2: AUTO-AIM, CURSOR & OVERLAY ──
        self._create_section_header(scroll, "AUTO-AIM & OVERLAY CONTROLS", "Cursor redirection and visual crosshair settings")

        aim_card = ctk.CTkFrame(scroll, corner_radius=10, fg_color="#111827", border_width=1, border_color="#1e293b")
        aim_card.pack(fill="x", pady=(2, 10))

        self.sw_auto_aim = ctk.CTkSwitch(
            aim_card,
            text="Enable Auto-Aim Snap (Snaps cursor to target cell before splitting)",
            font=ctk.CTkFont(size=12, weight="bold"),
            progress_color="#0284c7",
            onvalue=True,
            offvalue=False,
        )
        if self.config.auto_aim_enabled:
            self.sw_auto_aim.select()
        self.sw_auto_aim.pack(anchor="w", padx=14, pady=(10, 5))

        self.sw_restore_pos = ctk.CTkSwitch(
            aim_card,
            text="Restore Original Cursor Position After Reverse Split",
            font=ctk.CTkFont(size=12),
            progress_color="#0284c7",
            onvalue=True,
            offvalue=False,
        )
        if self.config.auto_aim_restore_pos:
            self.sw_restore_pos.select()
        self.sw_restore_pos.pack(anchor="w", padx=14, pady=5)

        self.sw_cursor_lock = ctk.CTkSwitch(
            aim_card,
            text="Cursor Tether (Mouse physically locks onto crosshair & glides with it)",
            font=ctk.CTkFont(size=12),
            progress_color="#0284c7",
            onvalue=True,
            offvalue=False,
        )
        if self.config.cursor_lock_to_dot:
            self.sw_cursor_lock.select()
        self.sw_cursor_lock.pack(anchor="w", padx=14, pady=5)

        self.sw_overlay = ctk.CTkSwitch(
            aim_card,
            text="Show Black Crosshair Overlay (Click-through target reticle)",
            font=ctk.CTkFont(size=12),
            progress_color="#0284c7",
            onvalue=True,
            offvalue=False,
        )
        if self.config.show_overlay:
            self.sw_overlay.select()
        self.sw_overlay.pack(anchor="w", padx=14, pady=5)

        # Pre-Delay Slider inside aim_card
        self.lbl_predelay, self.sl_predelay = self._create_slider_row(
            aim_card,
            label_text="Auto-Aim Snap Pre-Delay",
            value_text=f"{self.config.auto_aim_pre_delay_ms} ms",
            from_=0,
            to=10,
            steps=10,
            initial=self.config.auto_aim_pre_delay_ms,
            command=self._on_predelay_change,
            padx=14,
        )

        # ── SECTION 3: EDGE TRACKING & SENSITIVITY ──
        self._create_section_header(scroll, "EDGE TRACKING & SENSITIVITY", "Fine-tune crosshair glide speed and detection thresholds")

        tune_card = ctk.CTkFrame(scroll, corner_radius=10, fg_color="#111827", border_width=1, border_color="#1e293b")
        tune_card.pack(fill="x", pady=(2, 6))

        self.lbl_speed, self.sl_speed = self._create_slider_row(
            tune_card,
            label_text="Crosshair Glide Speed",
            value_text=f"{int(round(self.config.tracking_speed * 100))}%",
            from_=0.05,
            to=1.0,
            steps=19,
            initial=self.config.tracking_speed,
            command=self._on_speed_change,
            padx=14,
        )

        self.lbl_margin, self.sl_margin = self._create_slider_row(
            tune_card,
            label_text="Edge Safety Margin (Distance inside rim)",
            value_text=f"{self.config.edge_margin_px} px",
            from_=2,
            to=20,
            steps=18,
            initial=self.config.edge_margin_px,
            command=self._on_margin_change,
            padx=14,
        )

        self.lbl_drift, self.sl_drift = self._create_slider_row(
            tune_card,
            label_text="Max Drift Step Cap",
            value_text=f"{self.config.max_drift_rate_px} px/tick",
            from_=2,
            to=15,
            steps=13,
            initial=self.config.max_drift_rate_px,
            command=self._on_drift_change,
            padx=14,
        )

        self.lbl_dark, self.sl_dark = self._create_slider_row(
            tune_card,
            label_text="Dark Background RGB Threshold",
            value_text=f"{self.config.dark_threshold}",
            from_=10,
            to=80,
            steps=70,
            initial=self.config.dark_threshold,
            command=self._on_dark_change,
            padx=14,
        )

        self.lbl_tol, self.sl_tol = self._create_slider_row(
            tune_card,
            label_text="Smart Mode Color Sensitivity",
            value_text=f"{self.config.color_change_tolerance}",
            from_=10,
            to=120,
            steps=110,
            initial=self.config.color_change_tolerance,
            command=self._on_tol_change,
            padx=14,
        )

        self.lbl_hz, self.sl_hz = self._create_slider_row(
            tune_card,
            label_text="Engine Polling Rate",
            value_text=f"{self.config.sample_rate_hz} Hz ({1000/self.config.sample_rate_hz:.1f} ms)",
            from_=500,
            to=2000,
            steps=15,
            initial=self.config.sample_rate_hz,
            command=self._on_hz_change,
            padx=14,
        )

        # ── FOOTER ACTIONS ──
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=18, pady=(8, 6))

        self.btn_save = ctk.CTkButton(
            footer,
            text="APPLY & SAVE SETTINGS",
            height=40,
            corner_radius=10,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color="#0284c7",
            hover_color="#0369a1",
            command=self._apply_settings,
        )
        self.btn_save.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.btn_toggle_engine = ctk.CTkButton(
            footer,
            text="STOP ENGINE",
            height=40,
            width=155,
            corner_radius=10,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color="#dc2626",
            hover_color="#b91c1c",
            command=self._toggle_engine,
        )
        self.btn_toggle_engine.pack(side="right")

        credit_lbl = ctk.CTkLabel(
            self,
            text="Gota.io Auto Reverse • Built by Drago",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#475569",
        )
        credit_lbl.pack(pady=(0, 8))

    def _create_section_header(self, parent, title: str, subtitle: str):
        hdr = ctk.CTkFrame(parent, fg_color="transparent")
        hdr.pack(fill="x", pady=(6, 2))
        ctk.CTkLabel(
            hdr,
            text=title,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#38bdf8",
        ).pack(side="left")
        ctk.CTkLabel(
            hdr,
            text=subtitle,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#64748b",
        ).pack(side="right")

    def _create_keybind_card(self, parent, row: int, col: int, title: str, desc: str, default_val: str, accent: str):
        padx = (0, 5) if col == 0 else (5, 0)
        card = ctk.CTkFrame(
            parent,
            corner_radius=10,
            fg_color="#111827",
            border_width=1,
            border_color="#1e293b",
        )
        card.grid(row=row, column=col, sticky="nsew", padx=padx, pady=4)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=8)

        txt_col = ctk.CTkFrame(inner, fg_color="transparent")
        txt_col.pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(
            txt_col,
            text=title,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=accent,
        ).pack(anchor="w")
        ctk.CTkLabel(
            txt_col,
            text=desc,
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color="#94a3b8",
        ).pack(anchor="w")

        entry = ctk.CTkEntry(
            inner,
            width=68,
            height=32,
            corner_radius=8,
            justify="center",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color="#090d16",
            border_color="#334155",
        )
        entry.insert(0, default_val)
        entry.pack(side="right", padx=(8, 0))
        return entry

    def _create_slider_row(self, parent, label_text: str, value_text: str, from_: float, to: float, steps: int, initial: float, command, padx: int = 10):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=padx, pady=5)

        top = ctk.CTkFrame(row, fg_color="transparent")
        top.pack(fill="x")

        ctk.CTkLabel(
            top,
            text=label_text,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#cbd5e1",
        ).pack(side="left")

        val_lbl = ctk.CTkLabel(
            top,
            text=value_text,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#38bdf8",
            fg_color="#090d16",
            corner_radius=6,
            padx=8,
            pady=1,
        )
        val_lbl.pack(side="right")

        slider = ctk.CTkSlider(
            row,
            from_=from_,
            to=to,
            number_of_steps=steps,
            height=16,
            button_color="#38bdf8",
            button_hover_color="#0284c7",
            progress_color="#0284c7",
            command=command,
        )
        slider.set(initial)
        slider.pack(fill="x", pady=(3, 2))
        return val_lbl, slider

    def _on_predelay_change(self, val):
        self.lbl_predelay.configure(text=f"{int(val)} ms")

    def _on_margin_change(self, val):
        self.lbl_margin.configure(text=f"{int(val)} px")

    def _on_drift_change(self, val):
        self.lbl_drift.configure(text=f"{int(val)} px/tick")

    def _on_dark_change(self, val):
        self.lbl_dark.configure(text=f"{int(val)}")

    def _on_tol_change(self, val):
        self.lbl_tol.configure(text=f"{int(val)}")

    def _on_speed_change(self, val):
        self.lbl_speed.configure(text=f"{int(round(val * 100))}%")

    def _on_hz_change(self, val):
        hz = int(val)
        self.lbl_hz.configure(text=f"{hz} Hz ({1000/hz:.1f} ms)")

    def _apply_settings(self):
        self.config.fixed_toggle_key = self.ent_fixed_key.get().strip().upper()
        self.config.fixed_toggle_vk = get_vk(self.config.fixed_toggle_key)

        self.config.smart_toggle_key = self.ent_smart_key.get().strip().upper()
        self.config.smart_toggle_vk = get_vk(self.config.smart_toggle_key)

        self.config.movable_hold_key = self.ent_movable_key.get().strip().upper()
        self.config.movable_hold_vk = get_vk(self.config.movable_hold_key)

        self.config.split_action_key = self.ent_split_key.get().strip()
        self.config.split_action_vk = get_vk(self.config.split_action_key)

        self.config.auto_aim_enabled = bool(self.sw_auto_aim.get())
        self.config.auto_aim_restore_pos = bool(self.sw_restore_pos.get())
        self.config.auto_aim_pre_delay_ms = int(self.sl_predelay.get())
        self.config.cursor_lock_to_dot = bool(self.sw_cursor_lock.get())

        self.config.edge_margin_px = int(self.sl_margin.get())
        self.config.max_drift_rate_px = int(self.sl_drift.get())
        self.config.tracking_speed = float(self.sl_speed.get())
        self.config.dark_threshold = int(self.sl_dark.get())
        self.config.color_change_tolerance = int(self.sl_tol.get())
        self.config.sample_rate_hz = int(self.sl_hz.get())

        self.config.show_overlay = bool(self.sw_overlay.get())

        self.config.save()
        self.engine.reload_config(self.config)
        self.btn_save.configure(text="✓ SETTINGS SAVED", fg_color="#059669")
        self.after(
            1400,
            lambda: self.btn_save.configure(text="APPLY & SAVE SETTINGS", fg_color="#0284c7"),
        )

    def _toggle_engine(self):
        if self.engine.running:
            self.engine.stop()
            self.btn_toggle_engine.configure(
                text="START ENGINE", fg_color="#10b981", hover_color="#059669"
            )
            self.lbl_status.configure(text="STOPPED", text_color="#ef4444")
        else:
            self.engine.start()
            self.btn_toggle_engine.configure(
                text="STOP ENGINE", fg_color="#dc2626", hover_color="#b91c1c"
            )
            self.lbl_status.configure(text="READY (IDLE)", text_color="#38bdf8")

    def _update_diagnostics(self):
        if self.engine.running:
            mode_text = self.engine.mode
            if mode_text == "FIXED":
                self.lbl_status.configure(text="LOCKED [FIXED]", text_color="#34d399")
            elif mode_text == "SMART":
                self.lbl_status.configure(
                    text=f"SMART {self.engine.locked_color}", text_color="#c084fc"
                )
            elif mode_text == "MOVABLE":
                self.lbl_status.configure(text="ACTIVE [HOLD]", text_color="#f59e0b")
            else:
                self.lbl_status.configure(text=f"{self.engine.status_message}", text_color="#38bdf8")

            lat_us = self.engine.last_latency_us
            lat_ms = lat_us / 1000.0
            self.lbl_latency.configure(text=f"{lat_us:.1f} µs ({lat_ms:.3f} ms)")

            r, g, b = self.engine.last_rgb
            self.lbl_probe_info.configure(
                text=f"Edge: {self.engine.last_edge_dist:.1f}px | RGB: [{r},{g},{b}]"
            )
            self.lbl_triggers.configure(text=f"Fired: {self.engine.trigger_count}")

        self.after(50, self._update_diagnostics)

    def on_close(self):
        self.engine.stop()
        if self.overlay:
            self.overlay.close()
        cleanup_timers()
        try:
            self.quit()
        except Exception:
            pass
        self.destroy()
        sys.exit(0)


if __name__ == "__main__":
    app = App()
    app.mainloop()
