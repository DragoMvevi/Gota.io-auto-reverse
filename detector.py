import ctypes
from ctypes import wintypes
import math
import threading
import time

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

SRCCOPY = 0x00CC0020
BI_RGB = 0

# Sentinel 24-bit RGB value (0x010203 -> R=1, G=2, B=3) used by the black overlay crosshair
OVERLAY_SIGNATURE = 0x010203

SQRT2 = 1.4142135623730951
INV_SQRT2 = 0.7071067811865475


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


# Configure 64-bit safe GDI signatures
gdi32.CreateDIBSection.argtypes = [
    wintypes.HDC,
    ctypes.c_void_p,
    wintypes.UINT,
    ctypes.POINTER(ctypes.c_void_p),
    wintypes.HANDLE,
    wintypes.DWORD,
]
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wintypes.HDC]


class _DIBSurface:
    """Direct-memory Win32 DIBSection surface for zero-GetPixel RAM reads."""

    def __init__(self, hdc_screen: int, size: int):
        self.size = size
        self.half = size // 2
        self.hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
        bmi = BITMAPINFOHEADER(
            ctypes.sizeof(BITMAPINFOHEADER),
            size,
            -size,  # Top-down DIB (row 0 is top)
            1,
            32,
            BI_RGB,
            0,
            0,
            0,
            0,
            0,
        )
        self.bits_ptr = ctypes.c_void_p()
        self.hbm = gdi32.CreateDIBSection(
            hdc_screen, ctypes.byref(bmi), 0, ctypes.byref(self.bits_ptr), None, 0
        )
        self.old_bm = gdi32.SelectObject(self.hdc_mem, self.hbm)
        self.buf = (ctypes.c_uint32 * (size * size)).from_address(self.bits_ptr.value)

    def capture(self, hdc_screen: int, center_x: int, center_y: int) -> None:
        gdi32.BitBlt(
            self.hdc_mem,
            0,
            0,
            self.size,
            self.size,
            hdc_screen,
            int(center_x - self.half),
            int(center_y - self.half),
            SRCCOPY,
        )

    def close(self) -> None:
        if self.hdc_mem:
            gdi32.SelectObject(self.hdc_mem, self.old_bm)
            gdi32.DeleteObject(self.hbm)
            gdi32.DeleteDC(self.hdc_mem)
            self.hdc_mem = None


class CellDetector:
    # 8 directions: (grid_dx, grid_dy, unit_x, unit_y, step_euclidean_scale)
    DIRECTIONS_8 = (
        (-1, 0, -1.0, 0.0, 1.0),
        (1, 0, 1.0, 0.0, 1.0),
        (0, -1, 0.0, -1.0, 1.0),
        (0, 1, 0.0, 1.0, 1.0),
        (-1, -1, -INV_SQRT2, -INV_SQRT2, SQRT2),
        (1, -1, INV_SQRT2, -INV_SQRT2, SQRT2),
        (-1, 1, -INV_SQRT2, INV_SQRT2, SQRT2),
        (1, 1, INV_SQRT2, INV_SQRT2, SQRT2),
    )

    # Fallback offsets around center in case moving probe lands on a 2px crosshair arm
    CENTER_FALLBACK_OFFSETS = ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1), (2, 2), (-2, -2))

    # Adaptive steps for wide 512x512 radar (up to 252px radius in 48 checks/ray)
    WIDE_STEPS = (
        tuple(range(2, 34, 2))
        + tuple(range(36, 100, 4))
        + tuple(range(104, 254, 8))
    )

    def __init__(
        self,
        dark_threshold: int = 35,
        edge_margin_px: int = 8,
        max_drift_rate_px: int = 4,
        patch_size: int = 64,
        search_radius_px: int = 20,
        tracking_speed: float = 0.20,
    ):
        self.dark_threshold = dark_threshold
        self.edge_margin_px = edge_margin_px
        self.max_drift_rate_px = max_drift_rate_px
        self.micro_size = max(64, patch_size)
        self.wide_size = 512
        self.search_radius_px = search_radius_px
        self.tracking_speed = max(0.01, min(1.0, tracking_speed))

        # Thread-isolated GDI resources (created lazily on the calling thread)
        self._owner_tid = None
        self.hdc_screen = None
        self.micro_dib: _DIBSurface | None = None
        self.wide_dib: _DIBSurface | None = None

        # Remember last valid outward edge unit vector for deep-cell escaping
        self._last_norm_x = 1.0
        self._last_norm_y = 0.0
        self._last_move_time = time.perf_counter()

    def _ensure_thread_gdi(self) -> None:
        tid = threading.get_ident()
        if self._owner_tid == tid and self.hdc_screen and self.micro_dib and self.wide_dib:
            return
        self.close()
        self._owner_tid = tid
        self.hdc_screen = user32.GetDC(0)
        self.micro_dib = _DIBSurface(self.hdc_screen, self.micro_size)
        self.wide_dib = _DIBSurface(self.hdc_screen, self.wide_size)

    def close(self) -> None:
        if self.micro_dib:
            self.micro_dib.close()
            self.micro_dib = None
        if self.wide_dib:
            self.wide_dib.close()
            self.wide_dib = None
        if self.hdc_screen:
            user32.ReleaseDC(0, self.hdc_screen)
            self.hdc_screen = None
        self._owner_tid = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def is_dark(self, r: int, g: int, b: int) -> bool:
        """Determines if pixel is the dark/black background."""
        return max(r, g, b) <= self.dark_threshold

    def _read_unoccluded_center(self, buf, size: int, half: int) -> tuple[int, int, int]:
        """Reads center pixel, bypassing the overlay crosshair signature (0x010203) if overlapped."""
        for ox, oy in self.CENTER_FALLBACK_OFFSETS:
            raw = buf[(half + oy) * size + (half + ox)] & 0xFFFFFF
            if raw != OVERLAY_SIGNATURE:
                return (raw >> 16) & 0xFF, (raw >> 8) & 0xFF, raw & 0xFF
        raw = buf[half * size + half] & 0xFFFFFF
        return (raw >> 16) & 0xFF, (raw >> 8) & 0xFF, raw & 0xFF

    def _scan_8dir_dark(self, surface: _DIBSurface, use_wide_steps: bool = False) -> tuple[float, float, float]:
        """
        Scans 8 directions in memory for dark background pixels.
        Returns (min_edge_dist, norm_x, norm_y) pointing toward the closest cell edge.
        """
        buf = surface.buf
        size = surface.size
        half = surface.half
        thresh = self.dark_threshold

        steps = self.WIDE_STEPS if use_wide_steps else range(1, half - 1)

        ray_hits = []
        min_dist = 9999.0
        best_ux = 0.0
        best_uy = 0.0

        for dx, dy, ux, uy, scale in self.DIRECTIONS_8:
            prev_step = 1
            for step in steps:
                raw = buf[(half + dy * step) * size + (half + dx * step)] & 0xFFFFFF
                if raw == OVERLAY_SIGNATURE:
                    prev_step = step
                    continue
                r = (raw >> 16) & 0xFF
                g = (raw >> 8) & 0xFF
                b = raw & 0xFF
                if r <= thresh and g <= thresh and b <= thresh:
                    # Fine 1-pixel refinement if coarse step was used
                    exact_step = step
                    if step - prev_step > 1:
                        for fine in range(prev_step + 1, step):
                            fraw = buf[(half + dy * fine) * size + (half + dx * fine)] & 0xFFFFFF
                            if fraw == OVERLAY_SIGNATURE:
                                continue
                            if ((fraw >> 16) & 0xFF) <= thresh and ((fraw >> 8) & 0xFF) <= thresh and (fraw & 0xFF) <= thresh:
                                exact_step = fine
                                break
                    dist = exact_step * scale
                    ray_hits.append((dist, ux, uy))
                    if dist < min_dist:
                        min_dist = dist
                        best_ux = ux
                        best_uy = uy
                    break
                prev_step = step

        if min_dist >= 9000.0:
            return 9999.0, 0.0, 0.0

        # Blend closest ray with adjacent 45-degree rays for continuous 360-degree circle normal
        vx = 0.0
        vy = 0.0
        cutoff = min_dist * 1.35 + 4.0
        for dist, ux, uy in ray_hits:
            if dist <= cutoff and (ux * best_ux + uy * best_uy) > 0.2:
                w = 1.0 / (dist * dist + 1.0)
                vx += ux * w
                vy += uy * w

        mag = math.hypot(vx, vy)
        if mag > 1e-6:
            norm_x = vx / mag
            norm_y = vy / mag
        else:
            norm_x = best_ux
            norm_y = best_uy

        self._last_norm_x = norm_x
        self._last_norm_y = norm_y
        return min_dist, norm_x, norm_y

    def _scan_8dir_smart(
        self, surface: _DIBSurface, ref_rgb: tuple[int, int, int], tolerance: int, use_wide_steps: bool = False
    ) -> tuple[float, float, float]:
        """
        Scans 8 directions in memory for pixels differing from ref_rgb by more than tolerance.
        Returns (min_edge_dist, norm_x, norm_y) pointing toward the closest boundary.
        """
        buf = surface.buf
        size = surface.size
        half = surface.half
        ref_r, ref_g, ref_b = ref_rgb

        steps = self.WIDE_STEPS if use_wide_steps else range(1, half - 1)

        ray_hits = []
        min_dist = 9999.0
        best_ux = 0.0
        best_uy = 0.0

        for dx, dy, ux, uy, scale in self.DIRECTIONS_8:
            prev_step = 1
            for step in steps:
                raw = buf[(half + dy * step) * size + (half + dx * step)] & 0xFFFFFF
                if raw == OVERLAY_SIGNATURE:
                    prev_step = step
                    continue
                sr = (raw >> 16) & 0xFF
                sg = (raw >> 8) & 0xFF
                sb = raw & 0xFF
                if (abs(sr - ref_r) + abs(sg - ref_g) + abs(sb - ref_b)) > tolerance:
                    exact_step = step
                    if step - prev_step > 1:
                        for fine in range(prev_step + 1, step):
                            fraw = buf[(half + dy * fine) * size + (half + dx * fine)] & 0xFFFFFF
                            if fraw == OVERLAY_SIGNATURE:
                                continue
                            fr = (fraw >> 16) & 0xFF
                            fg = (fraw >> 8) & 0xFF
                            fb = fraw & 0xFF
                            if (abs(fr - ref_r) + abs(fg - ref_g) + abs(fb - ref_b)) > tolerance:
                                exact_step = fine
                                break
                    dist = exact_step * scale
                    ray_hits.append((dist, ux, uy))
                    if dist < min_dist:
                        min_dist = dist
                        best_ux = ux
                        best_uy = uy
                    break
                prev_step = step

        if min_dist >= 9000.0:
            return 9999.0, 0.0, 0.0

        vx = 0.0
        vy = 0.0
        cutoff = min_dist * 1.35 + 4.0
        for dist, ux, uy in ray_hits:
            if dist <= cutoff and (ux * best_ux + uy * best_uy) > 0.2:
                w = 1.0 / (dist * dist + 1.0)
                vx += ux * w
                vy += uy * w

        mag = math.hypot(vx, vy)
        if mag > 1e-6:
            norm_x = vx / mag
            norm_y = vy / mag
        else:
            norm_x = best_ux
            norm_y = best_uy

        self._last_norm_x = norm_x
        self._last_norm_y = norm_y
        return min_dist, norm_x, norm_y

    def _compute_edge_locked_pos(
        self, probe_x: float, probe_y: float, min_dist: float, norm_x: float, norm_y: float
    ) -> tuple[float, float]:
        """
        Computes updated (new_x, new_y) with frame-rate-independent (60Hz normalized) movement:
        - Detection still runs at full 1000Hz+, while crosshair movement is smooth and controlled.
        - Inward movement (error < 0, when cell shrinks/reduces size) is kept slow so a shrinking
          or splitting cell edge easily overtakes the crosshair and fires.
        - Outward movement (error > 0, when aiming inside a cell) steadily glides out to the edge.
        """
        now = time.perf_counter()
        dt = min(0.05, max(0.0002, now - self._last_move_time))
        self._last_move_time = now
        dt_scale = dt * 60.0  # Normalized to 60 FPS ticks

        if min_dist >= 9000.0:
            # Deep inside a massive cell (>254px from border): steady glide outward toward border
            seek_step = max(1.2, float(self.max_drift_rate_px) * self.tracking_speed * 1.5) * dt_scale
            return (
                float(probe_x) + self._last_norm_x * seek_step,
                float(probe_y) + self._last_norm_y * seek_step,
            )

        error = min_dist - float(self.edge_margin_px)
        if abs(error) < 0.35:
            return float(probe_x), float(probe_y)

        # Base drift step normalized by dt_scale so 1000Hz polling doesn't multiply movement speed
        base_step = min(float(self.max_drift_rate_px), abs(error)) * self.tracking_speed * dt_scale

        if error < 0.0:
            # Cell edge is moving inward / cell is reducing size:
            # Move slowly inward (0.55x base_step) so size reduction / split overtakes the crosshair!
            step = base_step * 0.55
        elif error > 12.0:
            # Deep inside the cell: smooth, moderate outward glide to reach the edge
            glide_speed = max(self.tracking_speed * 1.2, 0.08)
            step = min(float(self.max_drift_rate_px), abs(error)) * glide_speed * dt_scale
        else:
            # Near the edge moving outward (0 < error <= 12): normal controlled drift
            step = base_step

        # Clamp so we never overshoot past the target edge_margin_px
        step = min(step, abs(error))

        if error < 0:
            # Too close to boundary -> slow inward drift (-norm)
            new_x = float(probe_x) - norm_x * step
            new_y = float(probe_y) - norm_y * step
        else:
            # Inside cell -> glide outward toward boundary (+norm)
            new_x = float(probe_x) + norm_x * step
            new_y = float(probe_y) + norm_y * step

        return new_x, new_y

    def snap_to_edge(
        self,
        probe_x: float,
        probe_y: float,
        smart_mode: bool = False,
        ref_rgb: tuple[int, int, int] = (0, 0, 0),
        tolerance: int = 35,
    ) -> tuple[float, float]:
        """
        Immediately locates the nearest cell boundary (up to 254px away) when first locking
        inside a cell and snaps the probe right to edge_margin_px inside the rim.
        """
        self._ensure_thread_gdi()
        ix, iy = int(round(probe_x)), int(round(probe_y))
        self.wide_dib.capture(self.hdc_screen, ix, iy)

        if smart_mode:
            min_dist, norm_x, norm_y = self._scan_8dir_smart(
                self.wide_dib, ref_rgb, tolerance, use_wide_steps=True
            )
        else:
            cr, cg, cb = self._read_unoccluded_center(
                self.wide_dib.buf, self.wide_dib.size, self.wide_dib.half
            )
            if self.is_dark(cr, cg, cb):
                return float(probe_x), float(probe_y)
            min_dist, norm_x, norm_y = self._scan_8dir_dark(self.wide_dib, use_wide_steps=True)

        if min_dist < 9000.0:
            shift = min_dist - float(self.edge_margin_px)
            return float(probe_x) + norm_x * shift, float(probe_y) + norm_y * shift

        return float(probe_x), float(probe_y)

    def evaluate_probe(self, probe_x: float, probe_y: float) -> dict:
        """
        Evaluates Fixed/Movable probe using direct RAM DIBSection buffers and 8-way normal tracking.
        """
        self._ensure_thread_gdi()
        t0 = time.perf_counter()

        ix, iy = int(round(probe_x)), int(round(probe_y))
        self.micro_dib.capture(self.hdc_screen, ix, iy)

        t_scan0 = time.perf_counter()
        center_r, center_g, center_b = self._read_unoccluded_center(
            self.micro_dib.buf, self.micro_dib.size, self.micro_dib.half
        )

        # 1. CORE TRIGGER: If center touches the dark/black background -> SPLIT DETECTED!
        if self.is_dark(center_r, center_g, center_b):
            t_end = time.perf_counter()
            return {
                "is_split": True,
                "is_on_cell": False,
                "new_x": probe_x,
                "new_y": probe_y,
                "rgb": (center_r, center_g, center_b),
                "edge_dist": 0.0,
                "elapsed_us": (t_end - t_scan0) * 1e6,
            }

        # 2. 8-Directional Edge Scan (Micro 64x64 first, auto-escalating to Wide 512x512 if deep inside cell)
        min_black_dist, norm_x, norm_y = self._scan_8dir_dark(self.micro_dib, use_wide_steps=False)
        if min_black_dist >= 9000.0:
            self.wide_dib.capture(self.hdc_screen, ix, iy)
            t_scan0 = time.perf_counter()
            min_black_dist, norm_x, norm_y = self._scan_8dir_dark(self.wide_dib, use_wide_steps=True)

        new_x, new_y = self._compute_edge_locked_pos(
            probe_x, probe_y, min_black_dist, norm_x, norm_y
        )

        t_end = time.perf_counter()
        return {
            "is_split": False,
            "is_on_cell": True,
            "new_x": new_x,
            "new_y": new_y,
            "rgb": (center_r, center_g, center_b),
            "edge_dist": min_black_dist if min_black_dist < 9000.0 else -1.0,
            "elapsed_us": (t_end - t_scan0) * 1e6,
        }

    def sample_pixel(self, x: int, y: int) -> tuple[int, int, int]:
        """Samples the exact physical screen pixel color at (x, y), ignoring overlay pixels."""
        self._ensure_thread_gdi()
        self.micro_dib.capture(self.hdc_screen, int(x), int(y))
        return self._read_unoccluded_center(
            self.micro_dib.buf, self.micro_dib.size, self.micro_dib.half
        )

    def evaluate_smart_probe(
        self,
        probe_x: float,
        probe_y: float,
        ref_rgb: tuple[int, int, int],
        tolerance: int = 35,
    ) -> dict:
        """
        Smart Mode with 8-Directional Edge Seeking & Tracking:
        - Monitors the color at (probe_x, probe_y).
        - If center changes past tolerance -> FIRES!
        - Always seeks and locks onto the cell boundary (even if activated deep inside the cell).
        """
        self._ensure_thread_gdi()
        ix, iy = int(round(probe_x)), int(round(probe_y))
        self.micro_dib.capture(self.hdc_screen, ix, iy)

        t_scan0 = time.perf_counter()
        cr, cg, cb = self._read_unoccluded_center(
            self.micro_dib.buf, self.micro_dib.size, self.micro_dib.half
        )

        ref_r, ref_g, ref_b = ref_rgb
        diff = abs(cr - ref_r) + abs(cg - ref_g) + abs(cb - ref_b)

        # 1. Trigger Check: Did color change past tolerance?
        if diff > tolerance:
            t_end = time.perf_counter()
            return {
                "is_split": True,
                "color_diff": diff,
                "rgb": (cr, cg, cb),
                "new_x": probe_x,
                "new_y": probe_y,
                "edge_dist": 0.0,
                "elapsed_us": (t_end - t_scan0) * 1e6,
            }

        # 2. 8-Directional Smart Edge Scan (Micro 64x64 first, auto-escalating to Wide 512x512 if deep inside cell)
        min_edge_dist, norm_x, norm_y = self._scan_8dir_smart(
            self.micro_dib, ref_rgb, tolerance, use_wide_steps=False
        )
        if min_edge_dist >= 9000.0:
            self.wide_dib.capture(self.hdc_screen, ix, iy)
            t_scan0 = time.perf_counter()
            min_edge_dist, norm_x, norm_y = self._scan_8dir_smart(
                self.wide_dib, ref_rgb, tolerance, use_wide_steps=True
            )

        new_x, new_y = self._compute_edge_locked_pos(
            probe_x, probe_y, min_edge_dist, norm_x, norm_y
        )

        t_end = time.perf_counter()
        return {
            "is_split": False,
            "color_diff": diff,
            "rgb": (cr, cg, cb),
            "new_x": new_x,
            "new_y": new_y,
            "edge_dist": min_edge_dist if min_edge_dist < 9000.0 else -1.0,
            "elapsed_us": (t_end - t_scan0) * 1e6,
        }
