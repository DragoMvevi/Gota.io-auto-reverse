import threading
import time
from config import AppConfig
from input_manager import (
    is_key_down,
    get_cursor_position,
    set_cursor_position,
    send_key_press,
    get_vk,
)
from detector import CellDetector
from overlay import TrackingOverlay


class TriggerEngine:
    def __init__(self, config: AppConfig, overlay: TrackingOverlay = None):
        self.config = config
        self.overlay = overlay

        self.detector = CellDetector(
            dark_threshold=config.dark_threshold,
            edge_margin_px=config.edge_margin_px,
            max_drift_rate_px=config.max_drift_rate_px,
            search_radius_px=config.search_radius_px,
            tracking_speed=config.tracking_speed,
        )

        self.running = False
        self.worker_thread = None

        # State
        self.mode = "IDLE"  # "IDLE", "FIXED", "MOVABLE", "SMART"
        self.probe_x = 0.0
        self.probe_y = 0.0
        self.locked_color = (0, 0, 0)

        # Key edge tracking (for toggle)
        self.prev_fixed_down = False
        self.prev_smart_down = False

        # Diagnostics
        self.last_latency_us = 0.0
        self.last_rgb = (0, 0, 0)
        self.last_edge_dist = 0.0
        self.trigger_count = 0
        self.status_message = "Ready"

    def start(self):
        if self.running:
            return
        self.running = True
        self.worker_thread = threading.Thread(target=self._run_loop, daemon=True)
        self.worker_thread.start()

    def stop(self):
        self.running = False
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=1.0)
        self.mode = "IDLE"
        if self.overlay:
            self.overlay.update_probe(-100, -100, "IDLE")

    def _fire_trigger(self, t_detected: float = None):
        """
        Executes single-shot key injection, auto-aim redirect, and immediately
        disarms the engine so detection is strictly one-time.
        """
        if t_detected is None:
            t_detected = time.perf_counter()

        target_x, target_y = int(round(self.probe_x)), int(round(self.probe_y))
        orig_mode = self.mode

        # 1. Immediately disarm state and hide overlay (single shot)
        self.mode = "IDLE"
        if self.overlay:
            self.overlay.update_probe(-100, -100, "IDLE")

        self.trigger_count += 1

        # 2. Handle Auto-Aim Cursor Redirection (if enabled)
        orig_x, orig_y = get_cursor_position()
        if self.config.auto_aim_enabled and orig_mode in ("FIXED", "SMART"):
            set_cursor_position(target_x, target_y)
            if self.config.auto_aim_pre_delay_ms > 0:
                time.sleep(self.config.auto_aim_pre_delay_ms / 1000.0)

            # Fire split key instantly (0ms hold)
            send_key_press(self.config.split_action_vk, hold_ms=0.0)

            # Optional cursor restore
            if self.config.auto_aim_restore_pos:
                set_cursor_position(orig_x, orig_y)
        else:
            # Direct key fire at current cursor position (0ms hold)
            send_key_press(self.config.split_action_vk, hold_ms=0.0)

        t_end = time.perf_counter()
        reaction_us = (t_end - t_detected) * 1e6
        self.last_reaction_ms = reaction_us / 1000.0
        self.status_message = f"FIRED in {self.last_reaction_ms:.2f} ms ({int(reaction_us)} µs)"

    def _run_loop(self):
        try:
            while self.running:
                t0 = time.perf_counter()
                sleep_interval = 1.0 / max(100, self.config.sample_rate_hz)

                fixed_vk = self.config.fixed_toggle_vk
                smart_vk = self.config.smart_toggle_vk
                movable_vk = self.config.movable_hold_vk

                fixed_down = is_key_down(fixed_vk)
                smart_down = is_key_down(smart_vk)
                movable_down = is_key_down(movable_vk)

                # Handle Fixed Mode Toggle (Rising edge press)
                if fixed_down and not self.prev_fixed_down:
                    if self.mode == "FIXED":
                        self.mode = "IDLE"
                        self.status_message = "Disarmed"
                        if self.overlay:
                            self.overlay.update_probe(-100, -100, "IDLE")
                    else:
                        cur_x, cur_y = get_cursor_position()
                        self.probe_x, self.probe_y = float(cur_x), float(cur_y)
                        self.mode = "FIXED"
                        self.status_message = f"Locked at ({cur_x}, {cur_y})"
                        if self.overlay:
                            self.overlay.update_probe(cur_x, cur_y, "TRACKING")
                self.prev_fixed_down = fixed_down

                # Handle Smart Mode Toggle (Rising edge press)
                if smart_down and not self.prev_smart_down:
                    if self.mode == "SMART":
                        self.mode = "IDLE"
                        self.status_message = "Smart Disarmed"
                        if self.overlay:
                            self.overlay.update_probe(-100, -100, "IDLE")
                    else:
                        cur_x, cur_y = get_cursor_position()
                        self.locked_color = self.detector.sample_pixel(cur_x, cur_y)
                        self.probe_x, self.probe_y = float(cur_x), float(cur_y)
                        self.mode = "SMART"
                        self.status_message = f"Smart Locked {self.locked_color}"
                        if self.overlay:
                            self.overlay.update_probe(cur_x, cur_y, "SMART")
                self.prev_smart_down = smart_down

                # Handle Movable Mode (Hold)
                if movable_down and self.mode not in ("FIXED", "SMART"):
                    self.mode = "MOVABLE"
                    cur_x, cur_y = get_cursor_position()
                    self.probe_x, self.probe_y = float(cur_x), float(cur_y)
                    self.status_message = f"Holding at ({cur_x}, {cur_y})"
                    if self.overlay:
                        self.overlay.update_probe(cur_x, cur_y, "TRACKING")
                elif not movable_down and self.mode == "MOVABLE":
                    self.mode = "IDLE"
                    self.status_message = "Ready"
                    if self.overlay:
                        self.overlay.update_probe(-100, -100, "IDLE")

                # Active Sampling & Detection
                if self.mode == "SMART":
                    t_detect_start = time.perf_counter()
                    res = self.detector.evaluate_smart_probe(
                        self.probe_x,
                        self.probe_y,
                        self.locked_color,
                        self.config.color_change_tolerance,
                    )
                    self.last_latency_us = res["elapsed_us"]
                    self.last_rgb = res["rgb"]
                    self.last_edge_dist = float(res["edge_dist"])

                    if res["is_split"]:
                        self._fire_trigger(t_detect_start)
                        time.sleep(0.1)
                        continue

                    # Apply 8-directional edge tracking for Smart Mode
                    self.probe_x = float(res["new_x"])
                    self.probe_y = float(res["new_y"])
                    ix, iy = int(round(self.probe_x)), int(round(self.probe_y))
                    if self.overlay:
                        self.overlay.update_probe(ix, iy, "SMART")

                    # Cursor Tether / Stick Cursor to Dot
                    if self.config.cursor_lock_to_dot:
                        set_cursor_position(ix, iy)

                elif self.mode in ("FIXED", "MOVABLE"):
                    t_detect_start = time.perf_counter()
                    res = self.detector.evaluate_probe(self.probe_x, self.probe_y)

                    self.last_latency_us = res["elapsed_us"]
                    self.last_rgb = res["rgb"]
                    self.last_edge_dist = res["edge_dist"]

                    # Check for Black Background touch
                    if res["is_split"]:
                        self._fire_trigger(t_detect_start)
                        time.sleep(0.1)
                        continue

                    # Apply smooth 8-directional edge tracking in Fixed Mode
                    if self.mode == "FIXED":
                        self.probe_x = float(res["new_x"])
                        self.probe_y = float(res["new_y"])
                        ix, iy = int(round(self.probe_x)), int(round(self.probe_y))
                        if self.overlay:
                            self.overlay.update_probe(ix, iy, "TRACKING")

                        # Cursor Tether / Stick Cursor to Dot
                        if self.config.cursor_lock_to_dot:
                            set_cursor_position(ix, iy)
                    elif self.mode == "MOVABLE":
                        if self.overlay:
                            self.overlay.update_probe(
                                int(round(self.probe_x)), int(round(self.probe_y)), "TRACKING"
                            )

                # Intelligent Polling Scheduler (True 1000Hz+ active polling, 0% CPU when idle)
                if self.mode in ("FIXED", "SMART", "MOVABLE"):
                    while (time.perf_counter() - t0) < sleep_interval:
                        time.sleep(0)
                else:
                    # Idle state: relaxed 4ms sleep to conserve CPU
                    time.sleep(0.004)
        finally:
            self.detector.close()

    def reload_config(self, new_config: AppConfig):
        self.config = new_config
        self.detector.dark_threshold = new_config.dark_threshold
        self.detector.edge_margin_px = new_config.edge_margin_px
        self.detector.max_drift_rate_px = new_config.max_drift_rate_px
        self.detector.tracking_speed = new_config.tracking_speed
        if self.overlay:
            self.overlay.set_visibility(new_config.show_overlay)
            self.overlay.dot_size = new_config.overlay_dot_size
