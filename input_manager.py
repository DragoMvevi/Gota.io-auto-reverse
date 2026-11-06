import ctypes
from ctypes import wintypes
import time

user32 = ctypes.windll.user32
winmm = ctypes.windll.winmm

# Enable DPI awareness
try:
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
except Exception:
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass

# Initialize 1ms timer resolution
winmm.timeBeginPeriod(1)

KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
INPUT_KEYBOARD = 1

# SendInput structures
class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ('wVk', wintypes.WORD),
        ('wScan', wintypes.WORD),
        ('dwFlags', wintypes.DWORD),
        ('time', wintypes.DWORD),
        ('dwExtraInfo', ctypes.c_ulonglong)
    ]

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [('uMsg', wintypes.DWORD), ('wParamL', wintypes.WORD), ('wParamH', wintypes.WORD)]

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ('dx', wintypes.LONG), ('dy', wintypes.LONG),
        ('mouseData', wintypes.DWORD), ('dwFlags', wintypes.DWORD),
        ('time', wintypes.DWORD), ('dwExtraInfo', ctypes.c_ulonglong)
    ]

class INPUT(ctypes.Structure):
    class _INPUT(ctypes.Union):
        _fields_ = [('ki', KEYBDINPUT), ('mi', MOUSEINPUT), ('hi', HARDWAREINPUT)]
    _anonymous_ = ('_input',)
    _fields_ = [('type', wintypes.DWORD), ('_input', _INPUT)]

# Common VK codes mapping
VK_MAP = {
    "SPACE": 0x20,
    "LBUTTON": 0x01,
    "RBUTTON": 0x02,
    "MBUTTON": 0x04,
    "XBUTTON1": 0x05,
    "XBUTTON2": 0x06,
    "SHIFT": 0x10,
    "CTRL": 0x11,
    "ALT": 0x12,
    "TAB": 0x09,
    "ENTER": 0x0D,
    "ESCAPE": 0x1B,
    "W": 0x57,
    "E": 0x45,
    "R": 0x52,
    "T": 0x54,
    "F": 0x46,
    "V": 0x56,
    "C": 0x43,
    "X": 0x58,
    "Z": 0x5A,
    "Q": 0x51,
    "A": 0x41,
    "S": 0x53,
    "D": 0x44,
}

for i in range(ord('0'), ord('9') + 1):
    VK_MAP[chr(i)] = i
for i in range(ord('A'), ord('Z') + 1):
    VK_MAP[chr(i)] = i

def get_vk(key_name: str) -> int:
    k = key_name.strip().upper()
    return VK_MAP.get(k, 0x20)

def is_key_down(vk_code: int) -> bool:
    return bool(user32.GetAsyncKeyState(vk_code) & 0x8000)

def get_cursor_position() -> tuple[int, int]:
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y

def set_cursor_position(x: int, y: int) -> None:
    user32.SetCursorPos(int(x), int(y))

def send_key_press(vk_code: int, hold_ms: float = 0.0) -> None:
    """
    Fires exactly ONE single hardware key press and release using SendInput.
    """
    scan_code = user32.MapVirtualKeyW(vk_code, 0)
    
    # 1. Key Down
    inp_down = INPUT(type=INPUT_KEYBOARD)
    inp_down.ki.wVk = vk_code
    inp_down.ki.wScan = scan_code
    inp_down.ki.dwFlags = 0
    user32.SendInput(1, ctypes.byref(inp_down), ctypes.sizeof(INPUT))
    
    if hold_ms > 0:
        time.sleep(hold_ms / 1000.0)
        
    # 2. Key Up
    inp_up = INPUT(type=INPUT_KEYBOARD)
    inp_up.ki.wVk = vk_code
    inp_up.ki.wScan = scan_code
    inp_up.ki.dwFlags = KEYEVENTF_KEYUP
    user32.SendInput(1, ctypes.byref(inp_up), ctypes.sizeof(INPUT))

def cleanup_timers() -> None:
    winmm.timeEndPeriod(1)
