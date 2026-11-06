import json
import os
from dataclasses import dataclass, asdict

CONFIG_FILE = "config.json"

@dataclass
class AppConfig:
    # Key bindings
    fixed_toggle_key: str = "X"
    fixed_toggle_vk: int = 0x58  # 'X'
    
    smart_toggle_key: str = "Z"
    smart_toggle_vk: int = 0x5A  # 'Z'
    
    movable_hold_key: str = "C"
    movable_hold_vk: int = 0x43   # 'C'
    
    split_action_key: str = "Space"
    split_action_vk: int = 0x20   # VK_SPACE
    
    # Smart Mode parameters
    color_change_tolerance: int = 35   # Total RGB delta required to fire trigger (10-150)
    
    # Auto-Aim & Cursor Tether settings
    auto_aim_enabled: bool = True
    auto_aim_restore_pos: bool = False
    auto_aim_pre_delay_ms: int = 0
    cursor_lock_to_dot: bool = False   # When True, the mouse cursor physically locks to the dot and moves with it!
    
    # Detection & Tracking parameters
    dark_threshold: int = 30           # Max RGB value to be considered black background (0-255)
    edge_margin_px: int = 8            # Distance (px) to maintain inside cell boundary
    max_drift_rate_px: int = 4         # Max shift (px) per tick for drift compensation
    tracking_speed: float = 0.20       # Movement speed factor (0.05 = slow & smooth, 1.0 = instant)
    search_radius_px: int = 20         # Search radius around probe for edge
    
    # Engine & Polling
    sample_rate_hz: int = 1000         # Loop rate (1000 Hz = 1.0 ms polling)
    
    # Overlay & Visuals
    show_overlay: bool = True
    overlay_dot_size: int = 6          # Clean small dot diameter (px)

    def save(self, filepath: str = CONFIG_FILE) -> None:
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(asdict(self), f, indent=4)
        except Exception as e:
            print(f"[Config] Error saving config: {e}")

    @classmethod
    def load(cls, filepath: str = CONFIG_FILE) -> "AppConfig":
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return cls(**data)
            except Exception as e:
                print(f"[Config] Error loading config, using defaults: {e}")
        cfg = cls()
        cfg.save(filepath)
        return cfg
