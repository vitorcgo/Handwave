import ctypes
import sys

WCA_ACCENT_POLICY = 19
ACCENT_ENABLE_ACRYLICBLURBEHIND = 4
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_DONOTROUND = 1


class _AccentPolicy(ctypes.Structure):
    _fields_ = [
        ("AccentState", ctypes.c_int),
        ("AccentFlags", ctypes.c_int),
        ("GradientColor", ctypes.c_uint),
        ("AnimationId", ctypes.c_int),
    ]


class _CompositionData(ctypes.Structure):
    _fields_ = [
        ("Attribute", ctypes.c_int),
        ("Data", ctypes.c_void_p),
        ("SizeOfData", ctypes.c_size_t),
    ]


def enable_blur(hwnd: int, tint: int = 0x30281410) -> bool:
    """Aplica acrylic atrás da janela no Windows. tint usa o formato AABBGGRR."""
    if sys.platform != "win32":
        return False
    try:
        accent = _AccentPolicy(ACCENT_ENABLE_ACRYLICBLURBEHIND, 2, tint, 0)
        data = _CompositionData(
            WCA_ACCENT_POLICY,
            ctypes.cast(ctypes.pointer(accent), ctypes.c_void_p),
            ctypes.sizeof(accent),
        )
        if not ctypes.windll.user32.SetWindowCompositionAttribute(hwnd, ctypes.byref(data)):
            return False
        value = ctypes.c_int(DWMWCP_DONOTROUND)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(value), ctypes.sizeof(value)
        )
        return True
    except (AttributeError, OSError):
        return False


def set_round_region(hwnd: int, width: int, height: int, radius: int):
    """Recorta a janela (e o blur junto) com cantos arredondados. radius 0 remove o recorte."""
    if sys.platform != "win32":
        return
    gdi32 = ctypes.windll.gdi32
    user32 = ctypes.windll.user32
    gdi32.CreateRoundRectRgn.restype = ctypes.c_void_p
    user32.SetWindowRgn.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool]
    region = gdi32.CreateRoundRectRgn(0, 0, width + 1, height + 1, radius * 2, radius * 2) if radius else None
    user32.SetWindowRgn(hwnd, region, True)
