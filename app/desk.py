"""Desktop control on Windows (ctypes only, no packages). Off unless config "desktop_control" is true.
Usage:
  python -I desk.py shot            -> writes %TEMP%\\ekran.png, prints its "WxH" size
  python -I desk.py click X Y [right|double]
  python -I desk.py move X Y
  python -I desk.py type "text"     -> types it as Unicode (does not press Enter)
  python -I desk.py key ctrl+k      -> key / combination (enter, esc, tab, ctrl+w ...)
  python -I desk.py scroll X Y -3   -> negative = down
  python -I desk.py windows         -> visible window titles
  python -I desk.py focus "Notepad" -> brings the window whose title contains it to the front
Coordinates match the image ekran.ps1 takes (DPI-aware, virtual screen).
"""
import ctypes, subprocess, sys, time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import C, T  # noqa: E402

if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
    raise SystemExit(__doc__)
if not C.get("desktop_control"):
    raise SystemExit(T("Masaüstü kontrolü kapalı (ayar: desktop_control).", "Desktop control is off (config: desktop_control)."))

u = ctypes.windll.user32
u.SetProcessDPIAware()
ULONG_PTR = ctypes.c_size_t


class MI(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KI(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class IN(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("mi", MI), ("ki", KI)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def send(*items):
    arr = (IN * len(items))(*items)
    u.SendInput(len(items), arr, ctypes.sizeof(IN))


def mouse(flags, data=0):
    return IN(type=0, mi=MI(0, 0, data, flags, 0, 0))


def kb(vk=0, scan=0, flags=0):
    return IN(type=1, ki=KI(vk, scan, flags, 0, 0))


def move(x, y):
    u.SetCursorPos(int(x), int(y))
    time.sleep(0.15)


def click(x, y, kind=""):
    move(x, y)
    down, up = (0x8, 0x10) if kind in ("sag", "right") else (0x2, 0x4)
    for _ in range(2 if kind in ("cift", "double") else 1):
        send(mouse(down), mouse(up))
        time.sleep(0.08)


def type_text(s):
    for ch in s:
        if ch == "\n":
            press("enter")
            continue
        code = ord(ch)
        send(kb(0, code, 0x4), kb(0, code, 0x4 | 0x2))
        time.sleep(0.02)


KEYS = {"enter": 0x0D, "esc": 0x1B, "tab": 0x09, "backspace": 0x08, "delete": 0x2E, "space": 0x20,
        "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27, "home": 0x24, "end": 0x23,
        "pgup": 0x21, "pgdn": 0x22, "ctrl": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B}


def vk(name):
    name = name.lower()
    if name in KEYS:
        return KEYS[name]
    if len(name) == 1:
        return u.VkKeyScanW(ord(name)) & 0xFF
    if name.startswith("f") and name[1:].isdigit():
        return 0x6F + int(name[1:])
    raise SystemExit(T("bilinmeyen tuş: ", "unknown key: ") + name)


def press(combo):
    codes = [vk(p) for p in combo.split("+")]
    send(*[kb(c) for c in codes], *[kb(c, 0, 0x2) for c in reversed(codes)])
    time.sleep(0.1)


def windows():
    out = []
    cb = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def each(h, _):
        if u.IsWindowVisible(h):
            n = u.GetWindowTextLengthW(h)
            if n:
                b = ctypes.create_unicode_buffer(n + 1)
                u.GetWindowTextW(h, b, n + 1)
                out.append((h, b.value))
        return True
    u.EnumWindows(cb(each), 0)
    return out


def focus(part):
    for h, t in windows():
        if part.lower() in t.lower():
            if u.IsIconic(h):
                u.ShowWindow(h, 9)
            send(kb(0x12), kb(0x12, 0, 0x2))  # an Alt tap loosens the foreground-lock restriction
            u.SetForegroundWindow(h)
            print(T("odak:", "focus:"), t)
            return
    raise SystemExit(T("pencere yok: ", "no window: ") + part)


def main(a):
    c = a[0]
    if c == "shot":
        r = subprocess.run(["powershell", "-NoProfile", "-File", __file__.replace("desk.py", "ekran.ps1")],
                           capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        print(r.stdout.strip() or r.stderr.strip())
    elif c == "click":
        click(a[1], a[2], a[3] if len(a) > 3 else "")
    elif c == "move":
        move(a[1], a[2])
    elif c == "type":
        type_text(a[1])
    elif c == "key":
        press(a[1])
    elif c == "scroll":
        move(a[1], a[2])
        send(mouse(0x800, int(a[3]) * 120 & 0xFFFFFFFF))
    elif c == "windows":
        for _, t in windows():
            print(t)
    elif c == "focus":
        focus(a[1])
    else:
        raise SystemExit(__doc__)


main(sys.argv[1:])
