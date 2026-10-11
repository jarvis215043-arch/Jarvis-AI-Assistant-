from __future__ import annotations

import json
import math
import os
import platform
import random
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np
import psutil

if platform.system() == "Windows":
    _WIN_HIDE: dict = {"creationflags": subprocess.CREATE_NO_WINDOW}
else:
    _WIN_HIDE: dict = {}

from PyQt6.QtCore import (
    QEasingCurve, QLineF, QMimeData, QObject, QParallelAnimationGroup, QPointF,
    QPropertyAnimation, QRect, QRectF, QSize, Qt, QTimer, QUrl, pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush, QColor, QConicalGradient, QDragEnterEvent, QDropEvent, QFont,
    QFontDatabase, QImage, QKeySequence, QLinearGradient, QPainter, QPainterPath,
    QPen, QPixmap, QPolygonF, QRadialGradient, QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QPushButton, QScrollArea, QSizePolicy, QSplitter,
    QStackedLayout, QStackedWidget, QTextEdit, QVBoxLayout, QWidget, QProgressBar,
)

# ── Which Mark this is ───────────────────────────────────────────────────────
# One constant, read by the window title, the header badge and the PROTOCOL
# panel. It used to be typed separately in each of those places, and they drifted:
# Mark 52 and 53 shipped showing "PROTOCOL XLIX" — the number from Mark 49 — and
# Mark 55 shipped titled "MARK 54". Deriving the protocol from the name means a
# release bump is this one line.
APP_VERSION  = "MARK LIII"
APP_PROTOCOL = APP_VERSION.split()[-1]

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent

BASE_DIR   = _base_dir()
CONFIG_DIR = BASE_DIR / "config"
API_FILE   = CONFIG_DIR / "api_keys.json"


def _read_full_config() -> dict:
    """Read api_keys.json config dict. Returns {} on any error."""
    try:
        return json.loads(API_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


# Default assistant name — used when config/api_keys.json has no
# "assistant_name". Can still be changed any time in ⚙ → CUSTOMISE ASSISTANT.
DEFAULT_ASSISTANT_NAME = "JARVIS"


def _assistant_display_name() -> str:
    return ((_read_full_config().get("assistant_name") or DEFAULT_ASSISTANT_NAME)
            .strip().upper() or DEFAULT_ASSISTANT_NAME)


_DEFAULT_W, _DEFAULT_H = 980, 700
_MIN_W,     _MIN_H     = 760, 560
_LEFT_W  = 148
_RIGHT_W = 340

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"


class C:
    BG        = "#00060a"
    PANEL     = "#010d14"
    PANEL2    = "#010f18"
    BORDER    = "#0d3347"
    BORDER_B  = "#1a5c7a"
    BORDER_A  = "#0f4060"
    PRI       = "#00d4ff"
    PRI_DIM   = "#007a99"
    PRI_GHO   = "#001f2e"
    ACC       = "#ff6b00"
    ACC2      = "#ffcc00"
    GREEN     = "#00ff88"
    GREEN_D   = "#00aa55"
    RED       = "#ff3355"
    MUTED_C   = "#ff3366"
    TEXT      = "#8ffcff"
    TEXT_DIM  = "#3a8a9a"
    TEXT_MED  = "#5ab8cc"
    WHITE     = "#d8f8ff"
    DARK      = "#000d14"
    BAR_BG    = "#011520"


# Keys tied to the accent colour — status colours (ACC, GREEN, RED…) stay fixed
_HUE_LINKED = (
    "BG", "PANEL", "PANEL2", "BORDER", "BORDER_B", "BORDER_A",
    "PRI", "PRI_DIM", "PRI_GHO", "TEXT", "TEXT_DIM", "TEXT_MED",
    "WHITE", "DARK", "BAR_BG",
)
_PALETTE_DEFAULTS: dict[str, str] = {k: getattr(C, k) for k in _HUE_LINKED}

# The whole interface is orange by default now (like the orange JARVIS orb).
# A colour picked in ⚙ → CUSTOMISE ASSISTANT still overrides it.
DEFAULT_UI_COLOR = "#ff7a1a"


def apply_ui_accent(accent_hex: str) -> bool:
    """
    Re-derives the whole teal-family palette from the chosen accent colour
    (hue shift — brightness/saturation ratios are preserved, design stays intact).
    Painted elements (HUD, waveform, metrics) pick up the new colour on the next
    frame; stylesheet-based panels pick it up when they are rebuilt.
    """
    import colorsys

    accent_hex = (accent_hex or "").strip().lower()
    if not (accent_hex.startswith("#") and len(accent_hex) == 7):
        return False
    try:
        int(accent_hex[1:], 16)
    except ValueError:
        return False

    def _hsv(h: str) -> tuple[float, float, float]:
        r = int(h[1:3], 16) / 255
        g = int(h[3:5], 16) / 255
        b = int(h[5:7], 16) / 255
        return colorsys.rgb_to_hsv(r, g, b)

    base_h            = _hsv(_PALETTE_DEFAULTS["PRI"])[0]
    acc_h, acc_s, _av = _hsv(accent_hex)
    dh   = acc_h - base_h
    grey = acc_s < 0.08   # near-grey accent → the whole theme is desaturated

    for key, hex0 in _PALETTE_DEFAULTS.items():
        h, s, v = _hsv(hex0)
        if grey:
            s *= 0.15
        r, g, b = colorsys.hsv_to_rgb((h + dh) % 1.0, s, v)
        setattr(C, key, "#{:02x}{:02x}{:02x}".format(
            int(r * 255 + 0.5), int(g * 255 + 0.5), int(b * 255 + 0.5)))
    return True


def current_palette() -> dict[str, str]:
    """A snapshot of the accent-linked colours currently on class C."""
    return {k: getattr(C, k) for k in _HUE_LINKED}


def retheme_all_widgets(old: dict[str, str], new: dict[str, str]) -> None:
    """
    LIVE full theme change. Replaces the old palette colours with the new ones
    in EVERY widget's stylesheet across the app and repaints them. This way the
    colour change applies INSTANTLY across the whole interface — panels, buttons,
    borders included — not just the painted elements. No restart needed.
    """
    mapping = {old[k].lower(): new[k].lower()
               for k in old if old[k].lower() != new.get(k, old[k]).lower()}
    if not mapping:
        return
    app = QApplication.instance()
    if app is None:
        return
    for w in app.allWidgets():
        try:
            ss = w.styleSheet()
            if ss:
                s2 = ss
                for o, n in mapping.items():
                    if o in s2:
                        s2 = s2.replace(o, n)
                if s2 != ss:
                    w.setStyleSheet(s2)
            w.update()
        except Exception:
            pass


def qcol(h: str, a: int = 255) -> QColor:
    c = QColor(h); c.setAlpha(a); return c


# ── Windows GPU via NVML DLL (no subprocess, no console window) ──────────────
_nvml_lib: object = None   # cached ctypes DLL
_nvml_ok:  object = None   # None=untested, True=works, False=unavailable


def _nvml_gpu_windows() -> float:
    """Return NVIDIA GPU utilisation % using nvml.dll directly — zero subprocess."""
    global _nvml_lib, _nvml_ok
    if _nvml_ok is False:
        return -1.0
    try:
        import ctypes

        class _Util(ctypes.Structure):
            _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]

        if _nvml_lib is None:
            for dll_name in ("nvml", r"C:\Windows\System32\nvml.dll"):
                try:
                    lib = ctypes.WinDLL(dll_name)
                    lib.nvmlInit_v2()
                    _nvml_lib = lib
                    break
                except Exception:
                    continue

        if _nvml_lib is None:
            import pynvml  # type: ignore
            pynvml.nvmlInit()
            h = pynvml.nvmlDeviceGetHandleByIndex(0)
            _nvml_ok = True
            return float(pynvml.nvmlDeviceGetUtilizationRates(h).gpu)

        dev = ctypes.c_void_p()
        _nvml_lib.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(dev))
        util = _Util()
        _nvml_lib.nvmlDeviceGetUtilizationRates(dev, ctypes.byref(util))
        _nvml_ok = True
        return float(util.gpu)
    except Exception:
        _nvml_ok = False
        return -1.0


class _SysMetrics:
    def __init__(self):
        self.cpu  = 0.0
        self.mem  = 0.0
        self.net  = 0.0   
        self.gpu  = -1.0  
        self.tmp  = -1.0  
        self._lock = threading.Lock()
        self._last_net = psutil.net_io_counters()
        self._last_net_t = time.time()
        self._running = True
        # Probe caches — GPU (NVML) and temperature (WMI) are the expensive
        # queries; initialise their handles once and reuse them instead of
        # rebuilding a connection on every poll.
        self._slow_tick = 0            # gpu/temp refreshed every 3rd cycle
        self._pynvml    = None         # cached pynvml module + device handle
        self._pynvml_h  = None
        self._pynvml_ok = None         # None=untested, False=unavailable here
        self._nv_unix   = None         # cached (lib, dev) for Linux/macOS NVML
        self._wmi_conn  = None         # cached WMI connection (creating one is slow)
        self._wmi_ok    = None         # None=untested, False=unavailable here
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def _loop(self):
        while self._running:
            try:
                self._update()
            except Exception:
                pass
            time.sleep(2.0)

    def _update(self):
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent

        nc  = psutil.net_io_counters()
        now = time.time()
        dt  = now - self._last_net_t
        if dt > 0:
            sent = (nc.bytes_sent - self._last_net.bytes_sent) / dt
            recv = (nc.bytes_recv - self._last_net.bytes_recv) / dt
            net  = (sent + recv) / (1024 * 1024)
        else:
            net = 0.0
        self._last_net   = nc
        self._last_net_t = now

        # GPU and temperature change slowly and are the most expensive probes
        # (NVML / WMI) — refresh them every 3rd cycle (~6 s) instead of every
        # cycle, reusing the previous reading in between.
        self._slow_tick = (self._slow_tick + 1) % 3
        if self._slow_tick == 1:
            gpu = self._get_gpu()
            tmp = self._get_temp()
        else:
            gpu = self.gpu
            tmp = self.tmp

        with self._lock:
            self.cpu = cpu
            self.mem = mem
            self.net = net
            self.gpu = gpu
            self.tmp = tmp

    def _get_gpu(self) -> float:
        # pynvml — subprocess-free; initialise once and reuse the handle.
        # Re-initialising NVML on every poll is slow, so cache it and stop
        # retrying pynvml entirely once it proves unavailable here.
        if self._pynvml_ok is not False:
            try:
                if self._pynvml_h is None:
                    import pynvml  # type: ignore
                    pynvml.nvmlInit()
                    self._pynvml    = pynvml
                    self._pynvml_h  = pynvml.nvmlDeviceGetHandleByIndex(0)
                    self._pynvml_ok = True
                return float(self._pynvml.nvmlDeviceGetUtilizationRates(self._pynvml_h).gpu)
            except Exception:
                self._pynvml_ok = False

        # Windows: nvml.dll via ctypes (already cached in _nvml_gpu_windows)
        if _OS == "Windows":
            return _nvml_gpu_windows()

        # Linux / macOS: libnvidia-ml shared lib via ctypes — init once, reuse
        try:
            import ctypes

            class _Util(ctypes.Structure):
                _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]

            if self._nv_unix is None:
                _lib = "libnvidia-ml.so.1" if _OS == "Linux" else "libnvidia-ml.dylib"
                nv = ctypes.CDLL(_lib)
                nv.nvmlInit_v2()
                dev = ctypes.c_void_p()
                nv.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(dev))
                self._nv_unix = (nv, dev)

            nv, dev = self._nv_unix
            u = _Util()
            nv.nvmlDeviceGetUtilizationRates(dev, ctypes.byref(u))
            return float(u.gpu)
        except Exception:
            pass

        return -1.0   # N/A — zero subprocess on all platforms

    def _get_temp(self) -> float:
        # psutil — works on Linux; occasionally Windows with driver support
        try:
            temps = psutil.sensors_temperatures()
            for name in ["coretemp", "k10temp", "cpu_thermal", "acpitz",
                         "cpu-thermal", "zenpower", "it8688"]:
                if name in temps and temps[name]:
                    return temps[name][0].current
            for entries in temps.values():
                if entries:
                    return entries[0].current
        except Exception:
            pass

        # Windows: wmi module (pure Python COM, zero subprocess). Reuse a single
        # connection — building a fresh wmi.WMI() on every poll spins up a COM
        # connection each time and is very slow. Give up after one failure.
        if _OS == "Windows" and self._wmi_ok is not False:
            try:
                if self._wmi_conn is None:
                    import wmi  # type: ignore
                    self._wmi_conn = wmi.WMI(namespace="root/wmi")
                tz = self._wmi_conn.MSAcpi_ThermalZoneTemperature()
                if tz:
                    return (tz[0].CurrentTemperature / 10.0) - 273.15
            except Exception:
                self._wmi_ok   = False
                self._wmi_conn = None

        return -1.0   # N/A — zero subprocess on all platforms

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "cpu": self.cpu,
                "mem": self.mem,
                "net": self.net,
                "gpu": self.gpu,
                "tmp": self.tmp,
            }


_metrics = _SysMetrics()

# ── 3D energy orb (centre of the HUD) ────────────────────────────────────────
class _OrbModel:
    """3D geometry for the energy-orb HUD core: dashed rings, particle streams
    swirling along them, a loose particle cloud and light rays around a bright
    centre. Pure numpy — no Qt — so stepping it every frame is cheap.
    Coordinates are in "orb units" (1.0 = orb radius)."""

    CAM_DIST = 4.0   # perspective camera distance (bigger = flatter)

    def __init__(self, seed: int = 7, n_particles: int = 520, n_rays: int = 18, style: str = "classic"):
        rng = np.random.default_rng(seed)
        self.style = style
        spark = style == "spark"
        if spark:                      # orange orb: more, longer rays and finer rings
            n_rays, n_particles = 36, 760
        self.ray_alpha = 1.35 if spark else 1.0
        self.ray_width = 1.1 if spark else 1.6

        def _basis(axis):
            h = np.array([1.0, 0.0, 0.0]) if abs(axis[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
            bu = np.cross(axis, h); bu /= np.linalg.norm(bu)
            return bu, np.cross(axis, bu)

        # ── rings: (radius, width, brightness, dash period, dash on, speed) ─
        specs = ([(1.00, 1.5, 1.00, 40, 37, 0.30), (0.95, 1.3, 0.95, 36, 33, -0.42),
                  (1.05, 1.1, 0.85, 30, 26, 0.55),  (0.90, 1.0, 0.80, 44, 40, -0.36),
                  (1.12, 0.9, 0.70, 26, 21, 0.48),  (0.84, 1.0, 0.75, 34, 30, 0.62),
                  (1.00, 0.9, 0.65, 50, 46, -0.28), (0.97, 0.8, 0.60, 22, 18, 0.70),
                  (1.08, 0.8, 0.55, 38, 34, -0.52)] if spark else None) or [(1.00, 2.8, 1.00, 18, 15, 0.35),
                 (0.90, 2.4, 0.95, 12,  9, -0.55),
                 (0.80, 1.4, 0.70, 10,  6, 0.80),
                 (0.68, 1.2, 0.65, 15, 11, -0.45),
                 (1.10, 1.0, 0.45,  8,  4, 0.30),
                 (0.56, 1.0, 0.55, 12,  9, 0.65)]
        self.rings = []
        k = np.linspace(0, 2 * np.pi, 145)
        for rad, width, bright, period, on, speed in specs:
            a = rng.normal(size=3); a /= np.linalg.norm(a)
            ru, rv = _basis(a)
            pts = rad * (np.cos(k)[:, None] * ru + np.sin(k)[:, None] * rv)
            self.rings.append({"pts": pts, "u": ru, "v": rv, "a": a, "rad": rad,
                               "width": width, "bright": bright,
                               "period": period, "on": on, "speed": speed})

        # ── particles: ~60% stream along the rings, the rest form a cloud ───
        n = n_particles
        u = np.zeros((n, 3)); v = np.zeros((n, 3)); r = np.zeros(n)
        on_ring = rng.random(n) < (0.75 if spark else 0.6)
        for i in range(n):
            if on_ring[i]:
                ring = self.rings[rng.integers(0, len(self.rings) if spark else 4)]   # main rings
                ax = ring["a"] + rng.normal(scale=0.06, size=3)
                ax /= np.linalg.norm(ax)
                r[i] = ring["rad"] * rng.uniform(0.95, 1.08)
            else:
                ax = rng.normal(size=3); ax /= np.linalg.norm(ax)
                r[i] = rng.uniform(0.80, 1.10) if rng.random() < 0.7 else rng.uniform(0.2, 0.8)
            u[i], v[i] = _basis(ax)
        self.p_u, self.p_v, self.p_r = u, v, r
        self.p_phase = rng.uniform(0, 2 * np.pi, n)
        self.p_speed = np.where(on_ring, rng.uniform(0.35, 0.75, n),
                                rng.uniform(0.12, 0.45, n) * np.where(rng.random(n) < 0.8, 1, -1))
        self.p_size  = rng.uniform(0.4, 1.0, n)

        # ── rays from the centre ─────────────────────────────────────────────
        d = rng.normal(size=(n_rays, 3))
        self.r_dir   = d / np.linalg.norm(d, axis=1, keepdims=True)
        self.r_len   = rng.uniform(1.2, 2.0, n_rays) if spark else rng.uniform(0.9, 1.6, n_rays)
        self.r_phase = rng.uniform(0, 2 * np.pi, n_rays)
        self.r_freq  = rng.uniform(1.5, 4.0, n_rays)

    @staticmethod
    def rotation(yaw: float, pitch: float):
        cy, sy = math.cos(yaw), math.sin(yaw)
        cp, sp = math.cos(pitch), math.sin(pitch)
        ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
        rx = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]])
        return rx @ ry

    def project(self, pts, rot):
        """-> screen x, y (orb units, y down), depth z (-1 back .. +1 front), scale."""
        q = pts @ rot.T
        s = self.CAM_DIST / (self.CAM_DIST - q[:, 2])
        return q[:, 0] * s, -q[:, 1] * s, q[:, 2], s

    def particle_positions(self, t: float):
        th = self.p_phase + self.p_speed * t
        return self.p_r[:, None] * (np.cos(th)[:, None] * self.p_u + np.sin(th)[:, None] * self.p_v)


def _ca(c: QColor, a: float) -> QColor:
    """Copy of colour c with alpha a (clamped 0–255)."""
    q = QColor(c); q.setAlpha(max(0, min(255, int(a)))); return q


def _mix(c1: QColor, c2: QColor, f: float) -> QColor:
    """Blend c1 → c2 by f (0 = c1, 1 = c2)."""
    return QColor(int(c1.red()   + (c2.red()   - c1.red())   * f),
                  int(c1.green() + (c2.green() - c1.green()) * f),
                  int(c1.blue()  + (c2.blue()  - c1.blue())  * f))


def _dpr(widget) -> float:
    """Screen scaling for this widget (1.0 = 100%, 1.5 = 150%…)."""
    try:
        return max(1.0, float(widget.devicePixelRatioF()))
    except Exception:
        return 1.0


class _PlexusModel:
    """The orb in the main window: a cloud of glowing particles (no lines), laid
    densely along curved threads so they read as soft wispy strands, like the
    reference recording. Particle groups:
      strands — laid along curved threads, so neighbours join into fibres; they
                form a hollow shell when open and pull into a cluster when closed
      core    — a dense bright knot in the middle
      dust    — loose particles drifting around the outside
    Everything is in units of the orb radius; the canvas scales it."""

    def __init__(self, n_strands: int = 95, per_strand: int = 22, n_core: int = 260,
                 n_dust: int = 170, seed: int = 11):
        rng = np.random.default_rng(seed)

        def unit(v):
            return v / np.linalg.norm(v, axis=-1, keepdims=True)

        # curved threads across the sphere
        # All strands are advanced together, one step at a time (fast even for
        # the 16,000-particle GPU orb).
        p = unit(rng.normal(size=(n_strands, 3)))
        t = unit(np.cross(p, unit(rng.normal(size=(n_strands, 3)))))
        step = rng.uniform(0.032, 0.05, (n_strands, 1))  # close together → reads as a wispy strand
        bend = rng.normal(0, 0.06, size=(n_strands, 3))
        ph = rng.uniform(0, 2 * np.pi, n_strands)
        sd_steps, sph_steps = [], []
        for i in range(per_strand):
            jit = rng.normal(0, 0.012, size=(n_strands, 3))   # a little fuzz so strands look soft
            sd_steps.append(unit(p + jit)); sph_steps.append(ph + i * 0.09)
            t = unit(t + bend + rng.normal(0, 0.05, size=(n_strands, 3)))
            p = unit(p + t * step)
            t = unit(t - (t * p).sum(1, keepdims=True) * p)    # keep the thread on the sphere
        sd = np.stack(sd_steps, 1).reshape(-1, 3)              # strand by strand
        sph = np.stack(sph_steps, 1).reshape(-1)
        n_str = len(sd)
        core = unit(rng.normal(size=(n_core, 3)))
        dust = unit(rng.normal(size=(n_dust, 3)))
        self.n = n_str + n_core + n_dust
        self.dir = np.vstack([np.array(sd), core, dust])
        self.kind = np.array([0] * n_str + [1] * n_core + [2] * n_dust)
        self.r_shell = np.concatenate([rng.uniform(0.86, 1.04, n_str), np.ones(n_core + n_dust)])
        self.r_core = rng.uniform(0.0, 1.0, self.n) ** 1.6 * 0.30 + 0.02
        self.r_dust = rng.uniform(1.15, 1.95, self.n)
        base_ph = np.concatenate([np.array(sph), rng.uniform(0, 2 * np.pi, n_core + n_dust)])
        self.phase = base_ph[:, None] + np.array([0.0, 2.1, 4.2])[None, :]
        self.freq = rng.uniform(0.3, 0.8, (self.n, 3))
        self.bright = rng.uniform(0.35, 1.0, self.n) ** 1.3
        self.lat = np.arcsin(np.clip(self.dir[:, 1], -1, 1))
        self.lon = np.arctan2(self.dir[:, 2], self.dir[:, 0])

    def positions(self, t: float, shell: float, wobble: float, wave: float) -> np.ndarray:
        """3D positions. shell 0 = tight cluster … 1 = open hollow shell.
        wobble = how much the threads drift; wave = rippling strands (speaking)."""
        d = self.dir + wobble * np.sin(self.freq * t + self.phase)
        d /= np.linalg.norm(d, axis=1, keepdims=True)
        k = self.kind
        r = np.where(k == 0, self.r_shell * (0.28 + 0.72 * shell),
            np.where(k == 1, self.r_core * (0.8 + 0.4 * (1 - shell)), self.r_dust))
        if wave > 0:                       # flowing ripples across the strands
            r = r * (1 + wave * np.sin(3 * self.lat + 2 * self.lon + t * 2.2)
                       * np.where(k == 1, 0.3, 1.0))
        return d * r[:, None]

    def edges(self, pts: np.ndarray, k_near: int = 3, max_len: float = 0.30):
        """Pairs of nearby particles to join with a line (each to its nearest few)."""
        sq = (pts * pts).sum(1)
        d2 = np.maximum(sq[:, None] + sq[None, :] - 2.0 * pts @ pts.T, 0.0)
        np.fill_diagonal(d2, np.inf)
        nn = np.argpartition(d2, k_near, axis=1)[:, :k_near]
        i = np.repeat(np.arange(len(pts)), k_near)
        j = nn.reshape(-1)
        a, b = np.minimum(i, j), np.maximum(i, j)          # each pair once
        _, first = np.unique(a * len(pts) + b, return_index=True)
        a, b = a[first], b[first]
        dl = np.sqrt(d2[a, b])
        keep = dl < max_len
        return a[keep], b[keep], dl[keep]

    @staticmethod
    def rotate(pts: np.ndarray, yaw: float, pitch: float) -> np.ndarray:
        cy, sy, cp, sp = math.cos(yaw), math.sin(yaw), math.cos(pitch), math.sin(pitch)
        x = pts[:, 0] * cy + pts[:, 2] * sy
        z = -pts[:, 0] * sy + pts[:, 2] * cy
        y = pts[:, 1] * cp - z * sp
        z = pts[:, 1] * sp + z * cp
        return np.stack([x, y, z], axis=1)


class HudCanvas(QWidget):
    def __init__(self, face_path: str, assistant_name: str = "J.A.R.V.I.S", parent=None,
                 orb_only: bool = False):
        super().__init__(parent)
        # orb_only = the main JARVIS window: solid black, just the orange orb,
        # which grows when JARVIS talks and shrinks back to a small spark.
        self.orb_only = orb_only
        self.gpu_backdrop = False      # True when core/gl_orb.py draws the orb underneath
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMinimumSize(300, 300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.muted    = False
        self.speaking = False
        self.state    = "INITIALISING"
        self._assistant_name = assistant_name

        self._tick       = 0
        self._scale      = 1.0
        self._tgt_scale  = 1.0
        self._halo       = 55.0
        self._tgt_halo   = 55.0
        self._last_t     = time.time()
        self._scan       = 0.0
        self._scan2      = 180.0
        self._rings      = [0.0, 120.0, 240.0]
        self._pulses: list[float] = [0.0, 50.0, 100.0]
        self._blink      = True
        self._blink_tick = 0
        self._particles: list[list[float]] = []
        self._face_px: QPixmap | None = None
        # Rescaled-face cache: the smooth rescale is expensive, so we keep the
        # last result and only rebuild it when the (quantised) size changes.
        self._face_cache: QPixmap | None = None
        self._face_cache_sz = -1
        # Static grid-dot layer, pre-rendered once per size/theme into a pixmap
        # so paintEvent blits it in one call instead of thousands of drawPoint()s.
        self._grid_cache: QPixmap | None = None
        self._grid_key = None
        # Repaint throttle counter (idle frames drop to ~20 Hz — see _step()).
        self._paint_tick = 0
        self._load_face(face_path)

        # Live audio reactivity: _live_amp is written from the audio threads
        # (0.0–1.0), _amp_disp is the smoothed value the paint code reads.
        self._live_amp  = 0.0
        self._amp_disp  = 0.0
        self._base_scale = 1.0    # slow "breathing" target; amp is added per-frame
        self._base_halo  = 55.0

        # ── 3D orb state ─────────────────────────────────────────────────────
        # Drag with the left mouse button to rotate, scroll to zoom, double-click
        # to reset. When left alone it slowly turns by itself.
        self._orb       = _OrbModel(style="spark" if orb_only else "classic")
        self._size      = 0.35 if orb_only else 1.0   # grow/shrink factor (orb window)
        self._ext       = [0.0, 0.0, 1.0]            # hand control: yaw, pitch, zoom×
        if orb_only:                                  # the plexus orb (main window)
            self._plex = _PlexusModel()
            self._plex_t = 0.0
            self._shell, self._wob, self._wave, self._spin = 0.15, 0.04, 0.0, 0.25
            self._plex_img = None
        self._orb_img: QImage | None = None
        self._orb_t     = 0.0                 # animation clock (runs faster when speaking)
        self._orb_last  = time.monotonic()
        self._yaw, self._pitch, self._zoom = self._HOME_VIEW
        self._vyaw = self._vpitch = 0.0       # spin left over after a drag (inertia)
        self._dragging  = False
        self._drag_last: QPointF | None = None
        self._hover     = False
        self._hint_until = time.monotonic() + 10.0
        self.setMouseTracking(True)

        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._tmr.start(16)

    # ── Mouse: rotate / zoom the orb ─────────────────────────────────────────
    _ZOOM_MIN, _ZOOM_MAX = 0.55, 1.5
    _HOME_VIEW = (1.6, -0.5, 1.0)   # yaw, pitch, zoom — double-click returns here
    _GLOW      = 0.8                # resting brightness of rays + core (0 = calm, 1 = max)

    def _orb_radius(self) -> float:
        return min(self.width(), self.height()) * 0.30 * self._zoom * self._scale * self._size

    def external_control(self, data) -> None:
        """Hand control (actions/orb_hand_control.py, via the tool bus): may be
        called from another thread, so it only stores numbers; _step applies them."""
        try:
            self._ext[0] += float(data.get("dyaw", 0.0))
            self._ext[1] += float(data.get("dpitch", 0.0))
            self._ext[2] *= float(data.get("zoom", 1.0))
        except Exception:
            pass

    def _over_orb(self, pos: QPointF) -> bool:
        dx, dy = pos.x() - self.width() / 2, pos.y() - self.height() / 2
        return dx * dx + dy * dy <= (self._orb_radius() * 1.15) ** 2

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._dragging  = True
            self._drag_last = e.position()
            self._vyaw = self._vpitch = 0.0
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            e.accept()
        else:
            super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        pos = e.position()
        if self._dragging and self._drag_last is not None:
            dx = pos.x() - self._drag_last.x()
            dy = pos.y() - self._drag_last.y()
            self._yaw   += dx * 0.01
            self._pitch  = max(-1.45, min(1.45, self._pitch + dy * 0.01))
            self._vyaw, self._vpitch = dx * 0.01, dy * 0.01
            self._drag_last = pos
            self.update()
            e.accept()
            return
        over = self._over_orb(pos)
        if over != self._hover:
            self._hover = over
            if over:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            else:
                self.unsetCursor()
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging  = False
            self._drag_last = None
            if self._over_orb(e.position()):
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            else:
                self.unsetCursor()
            e.accept()
        else:
            super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._yaw, self._pitch, self._zoom = self._HOME_VIEW
            self._vyaw = self._vpitch = 0.0
            self.update()
            e.accept()
        else:
            super().mouseDoubleClickEvent(e)

    def wheelEvent(self, e):
        steps = e.angleDelta().y() / 120.0
        if steps:
            self._zoom = max(self._ZOOM_MIN, min(self._ZOOM_MAX, self._zoom * (1.12 ** steps)))
            self.update()
        e.accept()

    def leaveEvent(self, e):
        if not self._dragging:
            self._hover = False
            self.unsetCursor()
        super().leaveEvent(e)

    def set_audio_level(self, level: float) -> None:
        """Thread-safe entry point for the audio threads. Stores the louder of
        the incoming level and the current value so brief gaps between chunks
        don't make the waveform stutter; _step() decays it back down."""
        try:
            lv = float(level)
        except (TypeError, ValueError):
            return
        if lv < 0.0:
            lv = 0.0
        elif lv > 1.0:
            lv = 1.0
        if lv > self._live_amp:
            self._live_amp = lv

    def _load_face(self, path: str):
        try:
            from PIL import Image, ImageDraw
            import io
            img = Image.open(path).convert("RGBA")
            sz  = min(img.size)
            img = img.resize((sz, sz), Image.LANCZOS)
            mk  = Image.new("L", (sz, sz), 0)
            ImageDraw.Draw(mk).ellipse((2, 2, sz - 2, sz - 2), fill=255)
            img.putalpha(mk)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            px = QPixmap(); px.loadFromData(buf.getvalue())
            self._face_px = px
        except Exception:
            self._face_px = None
        # New source image → drop the rescaled cache so it rebuilds on next paint.
        self._face_cache    = None
        self._face_cache_sz = -1

    def _make_grid(self, W: int, H: int) -> QPixmap:
        """Pre-render the static grid-dot background into a transparent pixmap so
        paintEvent can blit it once per frame instead of running a nested
        drawPoint() loop across the whole widget every 16 ms."""
        pm = QPixmap(max(1, W), max(1, H))
        pm.fill(Qt.GlobalColor.transparent)
        gp = QPainter(pm)
        gp.setPen(QPen(qcol(C.PRI_GHO), 1))
        for x in range(0, W, 48):
            for y in range(0, H, 48):
                gp.drawPoint(x, y)
        gp.end()
        return pm

    def _step(self):
        self._tick += 1
        now = time.time()

        # ── Live audio reactivity ────────────────────────────────────────────
        # Audio threads push peaks into _live_amp; decay it toward silence so
        # gaps between chunks fade out instead of freezing, then smooth it.
        self._live_amp *= 0.86
        self._amp_disp += (self._live_amp - self._amp_disp) * 0.45
        amp = self._amp_disp

        # Slow "breathing" base target (random shimmer), refreshed on a timer.
        if now - self._last_t > (0.12 if self.speaking else 0.5):
            if self.speaking:
                self._base_scale = 1.03
                self._base_halo  = 122.0
            elif self.muted:
                self._base_scale = random.uniform(0.998, 1.002)
                self._base_halo  = random.uniform(15, 28)
            else:
                self._base_scale = random.uniform(1.001, 1.008)
                self._base_halo  = random.uniform(48, 68)
            self._last_t = now

        # Every frame, the live audio level lifts the target on top of the base
        # — this is what makes the core visibly pulse to the actual voice.
        if self.muted:
            self._tgt_scale, self._tgt_halo = self._base_scale, self._base_halo
        elif self.speaking:
            self._tgt_scale = self._base_scale + amp * 0.13
            self._tgt_halo  = self._base_halo  + amp * 95.0
        else:
            self._tgt_scale = self._base_scale + amp * 0.06
            self._tgt_halo  = self._base_halo  + amp * 75.0

        sp = 0.38 if self.speaking else (0.30 if amp > 0.02 else 0.15)
        self._scale += (self._tgt_scale - self._scale) * sp
        self._halo  += (self._tgt_halo  - self._halo)  * sp

        # Rings/scanners spin faster while speaking, reacting to loudness.
        boost  = 1.0 + amp * 1.6
        speeds = ([1.3, -0.9, 2.0] if self.speaking else [0.55, -0.35, 0.9])
        for i, spd in enumerate(speeds):
            self._rings[i] = (self._rings[i] + spd * boost) % 360

        self._scan  = (self._scan  + (3.0 if self.speaking else 1.3) * boost) % 360
        self._scan2 = (self._scan2 + (-2.0 if self.speaking else -0.75) * boost) % 360

        fw  = min(self.width(), self.height())
        lim = fw * 0.74
        spd = 4.2 if self.speaking else 2.0
        self._pulses = [r + spd for r in self._pulses if r + spd < lim]
        if len(self._pulses) < 3 and random.random() < (0.07 if self.speaking else 0.025):
            self._pulses.append(0.0)

        if self.speaking and random.random() < 0.28:
            cx, cy = self.width() / 2, self.height() / 2
            ang = random.uniform(0, 2 * math.pi)
            r_s = fw * 0.28
            self._particles.append([
                cx + math.cos(ang) * r_s, cy + math.sin(ang) * r_s,
                math.cos(ang) * random.uniform(0.9, 2.4),
                math.sin(ang) * random.uniform(0.9, 2.4) - 0.4, 1.0,
            ])
        self._particles = [
            [p[0]+p[2], p[1]+p[3], p[2]*0.97, p[3]*0.97, p[4]-0.028]
            for p in self._particles if p[4] > 0
        ]

        # ── 3D orb: animation clock, auto-rotation and drag inertia ─────────
        mono = time.monotonic()
        dt = min(0.05, max(0.0, mono - self._orb_last))
        self._orb_last = mono
        if self.muted:
            spin = 0.35
        elif self.speaking:
            spin = 1.8 + amp * 2.5
        elif self.state in ("THINKING", "PROCESSING"):
            spin = 2.4
        else:
            spin = 1.0
        self._orb_t += dt * spin

        # hand control from the webcam (two-hand pinch = zoom, one-hand pinch = turn)
        dyaw, dpitch, zmul = self._ext
        if dyaw or dpitch or zmul != 1.0:
            self._ext = [0.0, 0.0, 1.0]
            self._yaw += dyaw
            self._pitch = max(-1.45, min(1.45, self._pitch + dpitch))
            self._zoom = max(self._ZOOM_MIN, min(self._ZOOM_MAX * 1.4, self._zoom * zmul))
            self._vyaw = dyaw * 0.5

        # orb window: a small spark at rest that grows into a big orb as JARVIS speaks
        if self.orb_only:
            breath = 0.025 * math.sin(mono * 1.6)
            # (size, shell openness, drift, ripple, spin) for each state
            if self.muted:
                tgt = (0.28, 0.25, 0.03, 0.0, 0.10)
            elif self.speaking:          # bursts out into big flowing strands
                tgt = (1.55 + 0.60 * amp, 0.80, 0.10 + 0.20 * amp, 0.10 + 0.22 * amp, 0.45)
            elif self.state in ("THINKING", "PROCESSING"):   # tight swirling ball
                tgt = (0.62 + 0.03 * math.sin(mono * 5), 0.85, 0.08, 0.04, 1.40)
            elif amp > 0.05:             # listening to you talk: opens into a shell
                tgt = (0.78 + 0.30 * amp, 1.00, 0.06, 0.03, 0.35)
            else:                        # idle: small bright cluster
                tgt = (0.36 + breath, 0.15, 0.04, 0.0, 0.25)
            sz, sh, wb, wv, sp = tgt
            self._size  += (sz - self._size) * (0.09 if sz > self._size else 0.045)
            self._shell += (sh - self._shell) * 0.06
            self._wob   += (wb - self._wob) * 0.08
            self._wave  += (wv - self._wave) * 0.08
            self._spin  += (sp - self._spin) * 0.05
            self._plex_t += dt * (0.6 + self._spin)

        if not self._dragging:
            self._yaw  += dt * (0.07 if self.muted else 0.18) + self._vyaw
            self._pitch = max(-1.45, min(1.45, self._pitch + self._vpitch))
            self._vyaw   *= 0.93
            self._vpitch *= 0.88

        self._blink_tick += 1
        if self._blink_tick >= 38:
            self._blink = not self._blink
            self._blink_tick = 0
            _blinked = True
        else:
            _blinked = False

        # Repaint throttling — advancing the animation state above is cheap at
        # 60 Hz, but the paint is heavy. Repaint every frame while something is
        # actually happening (speaking, audio, thinking) or when the blink
        # toggles; otherwise drop to ~20 Hz so an idle HUD stops pinning a CPU
        # core. The visuals stay smooth because the state keeps stepping.
        # The orb is always moving, so idle frames repaint at ~30 Hz (every 2nd
        # tick) and busy frames (speaking, dragging, spinning down) at ~60 Hz.
        self._paint_tick = (self._paint_tick + 1) % 2
        active = (self.orb_only or self.speaking or amp > 0.02 or self._dragging
                  or abs(self._vyaw) > 1e-4 or abs(self._vpitch) > 1e-4
                  or self.state in ("THINKING", "PROCESSING"))
        if active or _blinked or self._paint_tick == 0:
            self.update()

    def float_offset(self, H: float) -> float:
        """Gentle up-and-down float of the orb (a little livelier while speaking)."""
        mono = time.monotonic()
        return H * (0.030 * math.sin(mono * 0.9) + (0.012 * math.sin(mono * 2.6) if self.speaking else 0.0))

    def orb_colors(self):
        base = qcol(C.MUTED_C if self.muted else C.PRI)
        return base, _mix(base, qcol(C.WHITE), 0.55), qcol(C.WHITE), (0.5 if self.muted else 1.0)

    def _paint_plexus(self, p: QPainter, cx: float, cy: float, W: int, H: int) -> None:
        """The main-window orb: orange particles joined by fine glowing lines,
        drawn with additive blending so dense strands glow brighter."""
        m = self._plex
        R = self._orb_radius()
        if R < 4 or W < 8 or H < 8:
            return
        base = qcol(C.MUTED_C if self.muted else C.PRI)
        hot = _mix(base, qcol(C.WHITE), 0.55)
        energy = 0.5 if self.muted else 1.0
        amp = self._amp_disp
        px = max(0.6, min(1.6, R / 170.0))

        # Draw at the screen's REAL pixel size. With Windows display scaling (125%/150%)
        # an image made at the logical size gets stretched up — blurry, blocky orb.
        dpr = _dpr(self)
        pw, ph = max(1, int(W * dpr)), max(1, int(H * dpr))
        if self._plex_img is None or self._plex_img.width() != pw or self._plex_img.height() != ph:
            self._plex_img = QImage(pw, ph, QImage.Format.Format_ARGB32_Premultiplied)
            self._plex_img.setDevicePixelRatio(dpr)
        img = self._plex_img
        img.fill(Qt.GlobalColor.transparent)
        ip = QPainter(img)
        if not ip.isActive():
            return
        ip.setRenderHint(QPainter.RenderHint.Antialiasing)
        ip.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        centre = QPointF(cx, cy)

        # soft glow behind everything
        g = QRadialGradient(centre, R * 1.3)
        g.setColorAt(0.0, _ca(base, (70 + 40 * (1 - self._shell)) * energy))
        g.setColorAt(0.5, _ca(base, 22 * energy))
        g.setColorAt(1.0, _ca(base, 0))
        ip.setPen(Qt.PenStyle.NoPen)
        ip.setBrush(QBrush(g))
        ip.drawEllipse(centre, R * 1.3, R * 1.3)
        ip.setBrush(Qt.BrushStyle.NoBrush)

        pts = m.positions(self._plex_t, self._shell, self._wob, self._wave)
        rot = _PlexusModel.rotate(pts, self._yaw + self._plex_t * 0.15, self._pitch)
        persp = 1.0 / (1.0 - 0.18 * np.clip(rot[:, 2], -2.5, 2.5))
        sx = cx + rot[:, 0] * R * persp
        sy = cy + rot[:, 1] * R * persp
        depth = np.clip((rot[:, 2] + 1.2) / 2.4, 0.0, 1.0)      # 0 = back, 1 = front

        # particles only (no connecting lines). Brighter at the front and while
        # speaking. Pass 1: a faint halo per particle so dense areas glow like haze.
        lum = m.bright * (0.30 + 0.70 * depth) * energy * (1.0 + 0.35 * amp)
        halo = QPen(_ca(base, 18), 6.5 * px)
        halo.setCapStyle(Qt.PenCapStyle.RoundCap)
        ip.setPen(halo)
        sel = np.nonzero(lum > 0.25)[0]
        ip.drawPoints([QPointF(sx[a], sy[a]) for a in sel])
        # Pass 2: the sharp points, in a few brightness levels so they draw in batches.
        for lo, hi, col, size, alpha in ((0.0, 0.30, base, 1.1, 120), (0.30, 0.55, base, 1.5, 175),
                                         (0.55, 0.80, hot, 1.9, 215), (0.80, 9.0, qcol(C.WHITE), 2.3, 245)):
            sel = np.nonzero((lum >= lo) & (lum < hi))[0]
            if len(sel) == 0:
                continue
            pen = QPen(_ca(col, alpha), size * px)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            ip.setPen(pen)
            ip.drawPoints([QPointF(sx[a], sy[a]) for a in sel])

        # hot core — strongest when closed into a cluster
        core_r = R * (0.24 + 0.14 * (1 - self._shell)) * (1 + 0.25 * amp)
        cg = QRadialGradient(centre, core_r)
        cg.setColorAt(0.0, _ca(qcol(C.WHITE), (190 - 100 * self._shell) * energy))
        cg.setColorAt(0.35, _ca(hot, (150 - 70 * self._shell) * energy))
        cg.setColorAt(1.0, _ca(base, 0))
        ip.setPen(Qt.PenStyle.NoPen)
        ip.setBrush(QBrush(cg))
        ip.drawEllipse(centre, core_r, core_r)
        ip.end()
        p.drawImage(0, 0, img)

    def _paint_orb(self, p: QPainter, cx: float, cy: float, fw: float) -> None:
        """Draws the 3D orb into an off-screen image with additive blending (so
        overlapping light glows brighter), then puts that image on the HUD."""
        m      = self._orb
        R      = self._orb_radius()
        if R < 4:
            return
        base   = qcol(C.MUTED_C if self.muted else C.PRI)
        white  = qcol(C.WHITE)
        energy = 0.45 if self.muted else 1.0
        amp    = self._amp_disp
        t      = self._orb_t
        wall   = time.monotonic()
        px     = max(0.7, R / 160.0)            # line/dot thickness scales with size

        sz = max(16, int(R * 3.4))
        dpr = _dpr(self)
        if self._orb_img is None or self._orb_img.width() != int(sz * dpr):
            self._orb_img = QImage(int(sz * dpr), int(sz * dpr), QImage.Format.Format_ARGB32_Premultiplied)
            self._orb_img.setDevicePixelRatio(dpr)
        img = self._orb_img
        img.fill(Qt.GlobalColor.transparent)
        oc = sz / 2.0
        centre = QPointF(oc, oc)
        rot = _OrbModel.rotation(self._yaw, self._pitch)

        ip = QPainter(img)
        if not ip.isActive():
            return
        ip.setRenderHint(QPainter.RenderHint.Antialiasing)
        ip.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)

        # soft outer glow
        g = QRadialGradient(centre, R * 1.25)
        g.setColorAt(0.0,  _ca(base, 95 * energy))
        g.setColorAt(0.45, _ca(base, 32 * energy))
        g.setColorAt(1.0,  _ca(base, 0))
        ip.setPen(Qt.PenStyle.NoPen)
        ip.setBrush(QBrush(g))
        ip.drawEllipse(centre, R * 1.25, R * 1.25)
        ip.setBrush(Qt.BrushStyle.NoBrush)

        # light rays — longer and brighter while speaking / loud
        stretch = 0.85 + 0.6 * self._GLOW + 0.35 * amp + (0.2 if self.speaking else 0.0)
        ra, rw = m.ray_alpha, m.ray_width
        x, y, z, _s = m.project(m.r_dir * (m.r_len * stretch)[:, None], rot)
        for i in range(len(x)):
            flick = 0.55 + 0.45 * math.sin(wall * m.r_freq[i] + m.r_phase[i])
            a = min(1.0, (0.4 + 0.6 * (z[i] + 1) / 2) * flick * energy * ra)
            end = QPointF(oc + x[i] * R, oc + y[i] * R)
            lg = QLinearGradient(centre, end)
            lg.setColorAt(0.0, _ca(white, 230 * a))
            lg.setColorAt(0.3, _ca(base, 150 * a))
            lg.setColorAt(1.0, _ca(base, 0))
            ip.setPen(QPen(QBrush(lg), rw * px, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            ip.drawLine(centre, end)

        # dashed rings — split by depth so the far side is dimmer
        for ring in m.rings:
            x, y, z, _s = m.project(ring["pts"], rot)
            off = int(t * ring["speed"] * 12)
            paths = (QPainterPath(), QPainterPath(), QPainterPath())
            used = [False, False, False]
            for i in range(len(x) - 1):
                if (i + off) % ring["period"] >= ring["on"]:
                    continue
                zz = (z[i] + 1) / 2
                b = 0 if zz < 0.35 else (1 if zz < 0.65 else 2)
                paths[b].moveTo(oc + x[i] * R, oc + y[i] * R)
                paths[b].lineTo(oc + x[i + 1] * R, oc + y[i + 1] * R)
                used[b] = True
            w = ring["width"] * px
            for b, path in enumerate(paths):
                if not used[b]:
                    continue
                a = 255 * ring["bright"] * (0.3, 0.6, 1.0)[b] * energy
                ip.setPen(QPen(_ca(base, a * 0.22), w * 3.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                ip.drawPath(path)   # glow
                ip.setPen(QPen(_ca(base, a), w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                ip.drawPath(path)   # core line

        # particles — three depth layers: far = small/dim, near = big/bright
        x, y, z, _s = m.project(m.particle_positions(t), rot)
        layer = np.digitize((z + 1) / 2, [0.35, 0.65])
        for b, (size, alpha, whiten) in enumerate(((1.6, 90, 0.0), (2.3, 160, 0.25), (3.0, 235, 0.5))):
            sel = layer == b
            if not sel.any():
                continue
            poly = QPolygonF([QPointF(oc + xx * R, oc + yy * R) for xx, yy in zip(x[sel], y[sel])])
            col = _mix(base, white, whiten)
            if b == 2:
                ip.setPen(QPen(_ca(col, 45 * energy), size * px * 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                ip.drawPoints(poly)
            ip.setPen(QPen(_ca(col, alpha * energy), size * px, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            ip.drawPoints(poly)

        # bright core — swells with the voice
        cr = R * 0.26 * (1.0 + 0.55 * self._GLOW + 0.3 * amp)
        cg = QRadialGradient(centre, cr)
        cg.setColorAt(0.0,  _ca(white, 255 * energy))
        cg.setColorAt(0.2,  _ca(white, 235 * energy))
        cg.setColorAt(0.55, _ca(base, 150 * energy))
        cg.setColorAt(1.0,  _ca(base, 0))
        ip.setPen(Qt.PenStyle.NoPen)
        ip.setBrush(QBrush(cg))
        ip.drawEllipse(centre, cr, cr)
        ip.end()

        p.drawImage(QPointF(cx - oc, cy - oc), img)

    def paintEvent(self, _):
        p = QPainter(self)
        if not p.isActive():      # device not ready (e.g. 0-size during layout) — skip cleanly
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not (self.orb_only and self.gpu_backdrop):
            p.fillRect(self.rect(), QColor(0, 0, 0) if self.orb_only else qcol(C.BG))

        W, H = self.width(), self.height()
        cx, cy = W / 2, H / 2
        fw = min(W, H)

        if self.orb_only:            # main window: black, the orb, one line of status
            if not self.gpu_backdrop:
                self._paint_plexus(p, cx, cy + self.float_offset(H), W, H)
            txt = ("MUTED — clap twice or press F4" if self.muted else
                   "SPEAKING" if self.speaking else self.state)
            p.setPen(QPen(qcol(C.MUTED_C if self.muted else C.PRI, 150), 1))
            p.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
            p.drawText(QRectF(0, H - 34, W, 20), Qt.AlignmentFlag.AlignCenter, txt)
            if self._hover or self._dragging or time.monotonic() < self._hint_until:
                p.setPen(QPen(qcol(C.TEXT_DIM, 170), 1))
                p.setFont(QFont("Courier New", 8))
                p.drawText(QRectF(0, 10, W, 16), Qt.AlignmentFlag.AlignCenter,
                           "DRAG TO ROTATE  ·  SCROLL TO ZOOM  ·  DOUBLE-CLICK TO RESET  ·  CTRL+H = HUD")
            p.end()
            return

        # grid dots — blitted from a cached layer; rebuilt only when the size
        # or the theme's ghost colour changes (so live re-theming still works).
        _gkey = (W, H, C.PRI_GHO)
        if self._grid_cache is None or self._grid_key != _gkey:
            self._grid_cache = self._make_grid(W, H)
            self._grid_key   = _gkey
        p.drawPixmap(0, 0, self._grid_cache)

        # 3D energy orb (replaces the old rings + face)
        self._paint_orb(p, cx, cy, fw)

        # corner brackets
        bl = 24
        bc = qcol(C.PRI, 210)
        hl, hr = cx - fw // 2, cx + fw // 2
        ht, hb = cy - fw // 2, cy + fw // 2
        p.setPen(QPen(bc, 2))
        for bx, by, dx, dy in [(hl,ht,1,1),(hr,ht,-1,1),(hl,hb,1,-1),(hr,hb,-1,-1)]:
            p.drawLine(QPointF(bx, by), QPointF(bx + dx * bl, by))
            p.drawLine(QPointF(bx, by), QPointF(bx, by + dy * bl))

        # controls hint — first 10 s after start, and whenever the mouse is on the orb
        if self._hover or self._dragging or time.monotonic() < self._hint_until:
            p.setPen(QPen(qcol(C.TEXT_DIM, 200), 1))
            p.setFont(QFont("Courier New", 8))
            p.drawText(QRectF(0, cy - fw * 0.5 + 6, W, 16), Qt.AlignmentFlag.AlignCenter,
                       "DRAG TO ROTATE  ·  SCROLL TO ZOOM  ·  DOUBLE-CLICK TO RESET")

        # status text
        sy = cy + fw * 0.40
        if self.muted:
            txt, col = "⊘  MUTED",     qcol(C.MUTED_C)
        elif self.speaking:
            txt, col = "●  SPEAKING",  qcol(C.ACC)
        elif self.state == "THINKING":
            sym = "◈" if self._blink else "◇"
            txt, col = f"{sym}  THINKING",   qcol(C.ACC2)
        elif self.state == "PROCESSING":
            sym = "▷" if self._blink else "▶"
            txt, col = f"{sym}  PROCESSING", qcol(C.ACC2)
        elif self.state == "LISTENING":
            sym = "●" if self._blink else "○"
            txt, col = f"{sym}  LISTENING",  qcol(C.GREEN)
        else:
            sym = "●" if self._blink else "○"
            txt, col = f"{sym}  {self.state}", qcol(C.PRI)

        p.setPen(QPen(col, 1))
        p.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
        p.drawText(QRectF(0, sy, W, 26), Qt.AlignmentFlag.AlignCenter, txt)

        # waveform — reacts to the real audio level (mic while listening,
        # JARVIS's own voice while speaking). Falls back to a gentle idle
        # ripple when there's no sound. _amp_disp is the smoothed 0–1 level.
        wy = sy + 30
        N, bw = 36, 8
        wx0 = (W - N * bw) / 2
        amp = self._amp_disp
        mid = (N - 1) / 2.0
        for i in range(N):
            if self.muted:
                hgt, cl = 2, qcol(C.MUTED_C)
            else:
                env     = (1.0 - abs(i - mid) / mid) ** 0.7      # center-weighted hump
                shimmer = 0.55 + 0.45 * math.sin(self._tick * 0.18 + i * 0.7)
                idle    = 3.0 + 2.0 * math.sin(self._tick * 0.09 + i * 0.6)
                hgt     = int(max(2, min(24, idle + amp * 22.0 * env * shimmer)))
                if amp > 0.05:
                    cl = qcol(C.PRI) if hgt > 12 else qcol(C.PRI_DIM)
                else:
                    cl = qcol(C.BORDER_B)
            p.fillRect(QRectF(wx0 + i * bw, wy + 20 - hgt, bw - 1, hgt), cl)

        p.end()   # end deterministically so the backing store never flushes an active painter

class OrbWindow(QWidget):
    """The main JARVIS window: solid black with the orange orb in the middle.
    Everything else (log, typing, results, settings) is in the HUD window."""

    def __init__(self, hud_window, face_path: str, assistant_name: str):
        super().__init__()
        self._hud_window = hud_window
        self.setWindowTitle(assistant_name)
        self.setStyleSheet("background: #000000;")
        self.setMinimumSize(360, 360)
        self.canvas = HudCanvas(face_path, assistant_name, self, orb_only=True)
        self.gl = None
        cfg = _read_full_config()
        if cfg.get("gpu_orb", True):
            try:
                from core.gl_orb import GLOrbView
                n = max(3000, min(int(cfg.get("orb_particles", 16000)), 60000))
                per = 30
                model = _PlexusModel(n_strands=max(20, int(n * 0.74 / per)), per_strand=per,
                                     n_core=int(n * 0.13), n_dust=int(n * 0.13))
                self.gl = GLOrbView(self.canvas, model, self.canvas.orb_colors, self._gpu_failed, self)
            except Exception as e:
                print(f"[GPU orb] Not available ({e}) — using the normal orb")
                self.gl = None
        if self.gl is not None:
            lay = QStackedLayout(self)
            lay.setStackingMode(QStackedLayout.StackingMode.StackAll)
            lay.addWidget(self.gl)
            lay.addWidget(self.canvas)
            lay.setCurrentWidget(self.canvas)            # the canvas (text, mouse) sits on top
            self.canvas.gpu_backdrop = True
            self.canvas.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
            self.canvas.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        else:
            lay = QVBoxLayout(self)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.addWidget(self.canvas)

        self._hud_btn = QPushButton("≡  HUD", self)
        self._hud_btn.setFixedSize(70, 26)
        self._hud_btn.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._hud_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hud_btn.setToolTip("Show / hide the HUD window (Ctrl+H)")
        self._hud_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.TEXT_DIM};
                border: 1px solid {C.BORDER}; border-radius: 3px; }}
            QPushButton:hover {{ color: {C.PRI}; border-color: {C.PRI_DIM}; }}""")
        self._hud_btn.clicked.connect(self.toggle_hud)

        for keys, fn in (("F4", hud_window._toggle_mute), ("Escape", hud_window._do_interrupt),
                         ("F11", self._toggle_fullscreen), ("Ctrl+H", self.toggle_hud)):
            QShortcut(QKeySequence(keys), self).activated.connect(fn)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._hud_btn.move(12, self.height() - 38)
        self._hud_btn.raise_()

    def _gpu_failed(self, why: str) -> None:
        """The GPU orb couldn't run — switch to the normal (CPU) orb seamlessly."""
        self.canvas.gpu_backdrop = False
        self.canvas.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.canvas.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        if self.gl is not None:
            self.gl.hide()
        self.canvas.update()

    def toggle_hud(self):
        w = self._hud_window
        if w.isVisible() and not w.isMinimized():
            w.hide()
        else:
            w.showNormal(); w.raise_(); w.activateWindow()

    def _toggle_fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def closeEvent(self, e):
        # Closing the orb window closes JARVIS completely.
        QApplication.instance().quit()
        super().closeEvent(e)


class SuitUpPopup(QWidget):
    """Small glowing pop-up shown while the start-up ("suit up") sound plays:
    a wobbly ring of light with the assistant's name forming inside it."""

    def __init__(self, name: str, is_playing, anchor: QWidget | None = None,
                 fullscreen: bool = False, on_done=None, on_skip=None):
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        if not fullscreen:
            flags |= Qt.WindowType.Tool
        super().__init__(None, flags)
        # fullscreen = the intro screen after the PIN: solid black with the ring
        # in the middle while suit_up.mp3 plays; on_done opens the HUD + orb.
        self._fullscreen, self._on_done, self._on_skip = fullscreen, on_done, on_skip
        if not fullscreen:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._name, self._is_playing = name.upper(), is_playing
        self._t0 = time.monotonic()
        self._fade = 0.0          # 0 → 1 fade in, back to 0 when closing
        self._closing = False
        self._finished = False
        if fullscreen:
            self.setStyleSheet("background: #000000;")
            self.setCursor(Qt.CursorShape.BlankCursor)
            self.setGeometry(QApplication.primaryScreen().geometry())
        else:
            self.resize(320, 320)
            geo = (anchor.frameGeometry() if anchor is not None and anchor.isVisible()
                   else QApplication.primaryScreen().availableGeometry())
            self.move(geo.center().x() - 160, geo.center().y() - 160)
        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._tick)
        self._tmr.start(30)

    def _tick(self):
        if self._finished:
            return
        playing = True
        try:
            playing = bool(self._is_playing())
        except Exception:
            playing = False
        shown_for = time.monotonic() - self._t0
        min_show = 2.5 if self._fullscreen else 0.0
        if (not playing or shown_for > 65) and shown_for >= min_show and not self._closing:
            self._closing = True
        self._fade += (-0.06 if self._closing else 0.05)
        self._fade = max(0.0, min(1.0, self._fade))
        if self._closing and self._fade <= 0.0:
            self._finished = True
            self._tmr.stop()
            self.close()
            if self._on_done:
                done, self._on_done = self._on_done, None
                done()
            return
        self.update()

    def keyPressEvent(self, e):
        # Only a fresh Esc press skips the start-up sound — and not in the first
        # second, so the Enter used to submit the PIN can't skip it by accident.
        is_esc = False
        try:
            is_esc = e.key() == Qt.Key.Key_Escape and not e.isAutoRepeat()
        except Exception:
            pass
        if (self._fullscreen and self._on_skip and is_esc
                and time.monotonic() - self._t0 > 1.0):
            try:
                self._on_skip()
            except Exception:
                pass
            return
        super().keyPressEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        cx, cy = W / 2, H / 2
        R0 = min(W, H) * (0.17 if self._fullscreen else 0.36)
        t = time.monotonic() - self._t0
        f = self._fade
        base = qcol(C.PRI)
        if self._fullscreen:
            p.fillRect(self.rect(), QColor(0, 0, 0))

        # soft dark disc behind everything, so it reads on any desktop
        bg = QRadialGradient(QPointF(cx, cy), R0 * 1.35)
        bg.setColorAt(0.0, QColor(0, 0, 0, int(215 * f)))
        bg.setColorAt(0.85, QColor(0, 0, 0, int(170 * f)))
        bg.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(bg))
        p.drawEllipse(QPointF(cx, cy), R0 * 1.35, R0 * 1.35)
        p.setBrush(Qt.BrushStyle.NoBrush)

        # wobbly ring: several glowing strands with slowly drifting waves
        for k in range(7):
            path = QPainterPath()
            ph = k * 0.9
            for i in range(121):
                a = i / 120 * 2 * math.pi
                r = R0 * (1 + 0.045 * math.sin(3 * a + t * 1.3 + ph)
                          + 0.03 * math.sin(5 * a - t * 1.7 + ph * 1.7)
                          + 0.02 * math.sin(9 * a + t * 2.3 + k))
                pt = QPointF(cx + r * math.cos(a), cy + r * math.sin(a))
                path.moveTo(pt) if i == 0 else path.lineTo(pt)
            a_glow = int((26 if k else 40) * f)
            p.setPen(QPen(_ca(base, a_glow), 7)); p.drawPath(path)
            p.setPen(QPen(_ca(base, int((150 if k == 0 else 70) * f)), 1.2)); p.drawPath(path)

        # faint inner grid circle
        p.setPen(QPen(_ca(base, int(45 * f)), 1))
        p.drawEllipse(QPointF(cx, cy), R0 * 0.42, R0 * 0.42)
        for i in range(-3, 4):
            off = i * R0 * 0.12
            half = math.sqrt(max(0.0, (R0 * 0.42) ** 2 - off ** 2))
            p.drawLine(QPointF(cx - half, cy + off), QPointF(cx + half, cy + off))
            p.drawLine(QPointF(cx + off, cy - half), QPointF(cx + off, cy + half))

        # the name fades in after a moment
        txt_a = max(0.0, min(1.0, (t - 0.6) / 1.2)) * f
        p.setFont(QFont("Arial Black", 40 if self._fullscreen else 26, QFont.Weight.Black))
        for dx, alpha in ((2, 60), (0, 235)):
            p.setPen(QPen(_ca(qcol(C.WHITE) if dx == 0 else base, int(alpha * txt_a)), 1))
            p.drawText(QRectF(dx, 0, W, H), Qt.AlignmentFlag.AlignCenter, self._name)
        if self._fullscreen:
            p.setFont(QFont("Courier New", 9))
            p.setPen(QPen(_ca(base, int(110 * f)), 1))
            p.drawText(QRectF(0, H - 60, W, 20), Qt.AlignmentFlag.AlignCenter, "PRESS ESC TO SKIP")
        p.end()


class IntroHud(QWidget):
    """The screen shown while suit_up.mp3 plays (after the PIN): a dark-blue
    HUD panel — "J.A.R.V.I.S" title, boot-log lines typing out, faint code,
    and a glowing reactor target on the right. When the sound ends it fades
    out and on_done() opens the HUD window and the orb window.
    Colour: cyan like the reference; set "intro_color" (e.g. "#ff7a1a") in
    config/api_keys.json to change it."""

    LOG = ["INITIALIZING CORE SYSTEMS", "LOADING VOICE INTERFACE", "CONNECTING NEURAL LINK",
           "CALIBRATING MICROPHONE ARRAY", "SYNCING MEMORY MODULES", "MOUNTING TOOL REGISTRY",
           "VERIFYING SECURITY CLEARANCE", "ALL SYSTEMS ONLINE"]
    CODE = ["> core.boot(mode='full', voice=True)", "> memory.load('long_term.json')  # ok",
            "> tools.discover('actions/')      # 60 tools", "> link.connect(model='gemini-live')",
            "> audio.calibrate(rate=16000)", "> hud.render(orb='plexus')"]

    def __init__(self, name: str, is_playing, on_done=None, on_skip=None, color: str = "#00d4ff",
                 start_sound=None, timing=None):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._is_playing, self._on_done, self._on_skip = is_playing, on_done, on_skip
        # start_sound: this screen starts suit_up.mp3 itself once it's visible, so
        # you see it before you hear it. timing(): (real start moment, length) from
        # the player — the boot sequence finishes 1 s before the sound ends.
        self._start_sound, self._timing = start_sound, timing
        self._sound_started = start_sound is None
        self._no_audio = False
        self._anim_t0 = None          # animation clock = when the sound really started
        self._length = None
        nm = (name or "JARVIS").upper().replace(".", "")
        self._title = ".".join(nm) if len(nm) <= 8 else nm
        self._col = QColor(color) if QColor(color).isValid() else QColor(0, 212, 255)
        self._t0 = time.monotonic()
        self._fade, self._closing, self._finished = 0.0, False, False
        scr = QApplication.primaryScreen().availableGeometry()
        w = int(min(scr.width() * 0.72, 1280))
        h = int(w * 0.56)
        self.setGeometry(scr.center().x() - w // 2, scr.center().y() - h // 2, w, h)
        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._tick)
        self._tmr.start(30)

    # same timing rules as the ring pop-up: ≥ 2.5 s on screen, fade in/out, then on_done
    def _tick(self):
        if self._finished:
            return
        now = time.monotonic()
        shown = now - self._t0
        if not self._sound_started and shown >= 0.35:      # visible now → start the sound
            self._sound_started = True
            try:
                ok = bool(self._start_sound())
            except Exception:
                ok = False
            if not ok:
                self._no_audio = True
                self._anim_t0, self._length = now, 3.0
        if self._anim_t0 is None and self._timing is not None:
            try:
                t0, length = self._timing()
            except Exception:
                t0, length = None, None
            if t0 is not None:
                self._anim_t0, self._length = t0, length
        if self._anim_t0 is None and self._timing is None and self._sound_started:
            self._anim_t0, self._length = self._t0, None     # old behaviour: no timing info
        try:
            playing = bool(self._is_playing()) and not self._no_audio
        except Exception:
            playing = False
        if (((not playing) and self._sound_started) or shown > 65) and shown >= 2.5 and not self._closing:
            self._closing = True
        self._fade = max(0.0, min(1.0, self._fade + (-0.06 if self._closing else 0.06)))
        if self._closing and self._fade <= 0.0:
            self._finished = True
            self._tmr.stop()
            self.close()
            if self._on_done:
                done, self._on_done = self._on_done, None
                done()
            return
        self.update()

    def keyPressEvent(self, e):
        # Only a fresh Esc skips — not the Enter left over from the PIN screen.
        try:
            is_esc = e.key() == Qt.Key.Key_Escape and not e.isAutoRepeat()
        except Exception:
            is_esc = False
        if is_esc and self._on_skip and time.monotonic() - self._t0 > 1.0:
            try:
                self._on_skip()
            except Exception:
                pass
            return
        super().keyPressEvent(e)

    def _span(self) -> float:
        """Seconds the boot sequence should take: the sound's length minus 1 s
        (so everything is finished a second before the sound ends)."""
        if self._length:
            return max(2.0, self._length - 1.0)
        return 10.0

    def _anim_time(self) -> float:
        return 0.0 if self._anim_t0 is None else max(0.0, time.monotonic() - self._anim_t0)

    def _log_state(self, t: float):
        """For each boot-log line: how many characters are typed so far. The lines
        are spread evenly so the last one finishes exactly at _span()."""
        out = []
        n_lines = len(self.LOG)
        span = self._span()
        per = (span - 0.3) / n_lines
        type_dur = min(0.55, per * 0.85)
        for i, line in enumerate(self.LOG):
            start = 0.3 + i * per
            full = line + " " + "." * max(2, 34 - len(line)) + (" OK" if i < n_lines - 1 else "")
            n = int(max(0.0, t - start) / type_dur * len(full))
            out.append(full[:min(n, len(full))])
        return out

    def paintEvent(self, _):
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(self._fade)
        W, H = self.width(), self.height()
        t = time.monotonic() - self._t0
        c = self._col
        def a(alpha):
            q = QColor(c); q.setAlpha(max(0, min(255, int(alpha)))); return q
        m, cut = W * 0.012, W * 0.03

        # panel: angled frame filled with a dark-blue gradient
        frame = QPainterPath()
        pts = [(m + cut, m), (W - m, m), (W - m, H - m - cut), (W - m - cut, H - m),
               (m, H - m), (m, m + cut)]
        frame.moveTo(*pts[0])
        for x, y in pts[1:]:
            frame.lineTo(x, y)
        frame.closeSubpath()
        bg = QLinearGradient(0, 0, 0, H)
        bg.setColorAt(0.0, QColor(3, 14, 36, 245)); bg.setColorAt(1.0, QColor(5, 30, 66, 245))
        p.fillPath(frame, QBrush(bg))
        p.save(); p.setClipPath(frame)
        p.setPen(QPen(a(16), 1))                                      # faint grid
        for gx in range(0, W, 26):
            p.drawLine(QPointF(gx, 0), QPointF(gx, H))
        for gy in range(0, H, 26):
            p.drawLine(QPointF(0, gy), QPointF(W, gy))
        sy = (t * 0.22 % 1.0) * H                                     # moving scan line
        sg = QLinearGradient(0, sy - 40, 0, sy)
        sg.setColorAt(0.0, a(0)); sg.setColorAt(1.0, a(28))
        p.fillRect(QRectF(0, sy - 40, W, 40), QBrush(sg))
        p.restore()
        p.setPen(QPen(a(170), 1.6)); p.drawPath(frame)
        p.setPen(QPen(a(60), 1))
        p.drawRect(QRectF(m + 8, m + 8, W - 2 * m - 16, H - 2 * m - 16))

        # left tick bar and top-right ruler
        x0 = W * 0.035
        p.setPen(QPen(a(120), 2))
        p.drawLine(QPointF(x0, H * 0.24), QPointF(x0, H * 0.78))
        for k in range(12):
            yy = H * 0.24 + k * H * 0.049
            p.drawLine(QPointF(x0, yy), QPointF(x0 + (10 if k % 3 == 0 else 5), yy))
        ry, rx0, rx1 = H * 0.085, W * 0.55, W * 0.93
        p.setPen(QPen(a(150), 1.2)); p.drawLine(QPointF(rx0, ry), QPointF(rx1, ry))
        k = 0
        while rx0 + k * 12 <= rx1:
            xx = rx0 + k * 12
            p.drawLine(QPointF(xx, ry), QPointF(xx, ry - (7 if k % 5 == 0 else 3)))
            k += 1
        p.fillRect(QRectF(rx1 - W * 0.06, ry - 3, W * 0.06, 6), a(200))

        # title, subtitle
        x_txt = W * 0.075
        tf = QFont("Consolas", max(14, int(H * 0.058)), QFont.Weight.Bold)
        tf.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 118)
        p.setFont(tf)
        p.setPen(QPen(a(70), 1)); p.drawText(QPointF(x_txt + 2, H * 0.17 + 2), f"{self._title}   {APP_VERSION}")
        p.setPen(QPen(a(245), 1)); p.drawText(QPointF(x_txt, H * 0.17), f"{self._title}   {APP_VERSION}")
        p.setFont(QFont("Consolas", max(7, int(H * 0.018))))
        p.setPen(QPen(a(130), 1))
        p.drawText(QPointF(x_txt, H * 0.215), "PERSONAL AI SYSTEM  —  BOOT SEQUENCE")

        # boot log typing out, then faint code lines
        lf = QFont("Consolas", max(8, int(H * 0.024)), QFont.Weight.Bold)
        p.setFont(lf)
        y = H * 0.30
        at = self._anim_time()                 # boot-sequence clock (starts with the sound)
        span = self._span()
        lines = self._log_state(at)
        for i, ln in enumerate(lines):
            if not ln:
                break
            last = i == len(self.LOG) - 1
            p.setPen(QPen(a(255 if last else 225), 1))
            p.drawText(QPointF(x_txt, y), ln)
            y += H * 0.047
        if int(t * 2.5) % 2 == 0:                                       # blinking cursor
            p.fillRect(QRectF(x_txt, y - H * 0.03, H * 0.016, H * 0.032), a(220))
        p.setFont(QFont("Consolas", max(7, int(H * 0.019))))
        p.setPen(QPen(a(70), 1))
        yc = max(y + H * 0.04, H * 0.72)
        for i, code in enumerate(self.CODE):
            if at > 0.8 + i * max(0.3, (span - 1.5) / len(self.CODE)) and yc < H * 0.95:
                p.drawText(QPointF(x_txt, yc), code); yc += H * 0.034

        # reactor target on the right
        cx, cy, Rr = W * 0.78, H * 0.56, H * 0.27
        glow = QRadialGradient(QPointF(cx, cy), Rr * 1.15)
        glow.setColorAt(0.0, a(70)); glow.setColorAt(0.5, a(22)); glow.setColorAt(1.0, a(0))
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(glow))
        p.drawEllipse(QPointF(cx, cy), Rr * 1.15, Rr * 1.15); p.setBrush(Qt.BrushStyle.NoBrush)
        def ring_rect(r):
            return QRectF(cx - r, cy - r, 2 * r, 2 * r)
        rot = t * 14
        p.setPen(QPen(a(200), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))   # dashed outer ring
        for k in range(32):
            p.drawArc(ring_rect(Rr), int((rot + k * 11.25) * 16), int(6.5 * 16))
        p.setPen(QPen(a(150), 1.2)); p.drawEllipse(QPointF(cx, cy), Rr * 0.87, Rr * 0.87)
        p.setPen(QPen(a(120), 1))                                          # tick ring
        for k in range(72):
            ang = math.radians(k * 5)
            r1, r2 = Rr * 0.76, Rr * (0.80 if k % 6 else 0.83)
            p.drawLine(QPointF(cx + r1 * math.cos(ang), cy + r1 * math.sin(ang)),
                       QPointF(cx + r2 * math.cos(ang), cy + r2 * math.sin(ang)))
        p.setPen(QPen(a(210), 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))  # counter-rotating arcs
        for k in range(3):
            p.drawArc(ring_rect(Rr * 0.64), int((-t * 40 + k * 120) * 16), int(70 * 16))
        p.setPen(QPen(a(170), 1.6)); p.drawEllipse(QPointF(cx, cy), Rr * 0.48, Rr * 0.48)
        core_r = Rr * 0.24 * (1 + 0.08 * math.sin(t * 4.2))
        cg = QRadialGradient(QPointF(cx, cy), core_r * 1.6)
        cg.setColorAt(0.0, QColor(235, 252, 255, 255)); cg.setColorAt(0.25, a(255))
        cg.setColorAt(0.6, a(120)); cg.setColorAt(1.0, a(0))
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(cg))
        p.drawEllipse(QPointF(cx, cy), core_r * 1.6, core_r * 1.6)

        # bottom: progress and skip hint
        prog = min(1.0, at / span) if self._anim_t0 is not None else 0.0
        bx, by, bw = x_txt, H * 0.92, W * 0.30
        p.setPen(QPen(a(110), 1)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(bx, by, bw, 6))
        p.fillRect(QRectF(bx + 1, by + 1, (bw - 2) * prog, 4), a(220))
        p.setFont(QFont("Consolas", max(7, int(H * 0.016))))
        p.setPen(QPen(a(130), 1))
        p.drawText(QPointF(bx + bw + 12, by + 7), f"SYSTEM INTEGRITY {int(prog * 100)}%")
        p.drawText(QRectF(0, H - m - 26, W - m - cut - 10, 18),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "ESC TO SKIP")
        p.end()


class _SuitModel:
    """A generic armoured suit made of ~4,000 particles, built from separate pieces
    (helmet, chest, reactor, arms, legs…) so it can fly apart and reassemble."""

    def __init__(self, seed: int = 21):
        rng = np.random.default_rng(seed)
        pts, part, names, centres = [], [], [], []

        def add(name, p):
            centres.append(p.mean(axis=0)); names.append(name)
            pts.append(p); part.append(np.full(len(p), len(names) - 1))

        def ellipsoid(c, r, n):
            v = rng.normal(size=(n, 3)); v /= np.linalg.norm(v, axis=1, keepdims=True)
            return np.array(c) + v * np.array(r)

        def tube(a, b, r, n):
            a, b = np.array(a, float), np.array(b, float)
            t = rng.random(n)[:, None]; th = rng.random(n) * 2 * np.pi
            ax = b - a; ax /= np.linalg.norm(ax)
            u = np.cross(ax, [0, 0, 1.0]); u /= np.linalg.norm(u) + 1e-9; w = np.cross(ax, u)
            return a + (b - a) * t + r * (np.cos(th)[:, None] * u + np.sin(th)[:, None] * w)

        def box(c, size, n):
            p = (rng.random((n, 3)) - 0.5) * np.array(size)
            k = rng.integers(0, 3, n)                               # push each point onto a face
            p[np.arange(n), k] = np.sign(rng.random(n) - 0.5) * np.array(size)[k] / 2
            return np.array(c) + p

        def ring(c, r, n):
            th = np.linspace(0, 2 * np.pi, n, endpoint=False)
            return np.array(c) + np.stack([np.cos(th) * r, np.sin(th) * r, np.zeros(n)], 1)

        add("HELMET", np.vstack([ellipsoid((0, 0.84, 0), (0.12, 0.15, 0.13), 330),
                                 box((0, 0.84, 0.115), (0.13, 0.02, 0.01), 40)]))
        add("CHEST PLATE", box((0, 0.5, 0), (0.38, 0.27, 0.2), 560))
        add("CHEST REACTOR", np.vstack([ring((0, 0.5, 0.105), 0.05, 70), ring((0, 0.5, 0.105), 0.025, 40)]))
        add("ABDOMEN", box((0, 0.27, 0), (0.29, 0.18, 0.17), 320))
        add("PELVIS", box((0, 0.08, 0), (0.31, 0.11, 0.18), 220))
        for side, sx in (("LEFT", -1), ("RIGHT", 1)):
            add(f"{side} SHOULDER", ellipsoid((0.26 * sx, 0.58, 0), (0.1, 0.08, 0.1), 200))
            add(f"{side} ARM", np.vstack([tube((0.28 * sx, 0.5, 0), (0.32 * sx, 0.24, 0), 0.06, 220),
                                          tube((0.32 * sx, 0.21, 0), (0.34 * sx, -0.06, 0), 0.055, 200)]))
            add(f"{side} GAUNTLET", np.vstack([ellipsoid((0.35 * sx, -0.14, 0), (0.045, 0.07, 0.04), 120),
                                               ring((0.35 * sx, -0.14, 0.03), 0.018, 18)]))
            add(f"{side} LEG", np.vstack([tube((0.1 * sx, 0.02, 0), (0.11 * sx, -0.42, 0), 0.08, 300),
                                          tube((0.11 * sx, -0.46, 0), (0.11 * sx, -0.84, 0), 0.065, 260)]))
            add(f"{side} BOOT", box((0.11 * sx, -0.91, 0.03), (0.1, 0.07, 0.18), 130))
        self.p = np.vstack(pts).astype(float)
        self.part = np.concatenate(part)
        self.names = names
        self.centres = np.array(centres)
        d = self.centres - np.array([0, 0.3, 0])
        d[:, 2] += 0.25                                                  # pieces fly slightly forward too
        self.explode_dir = d / (np.linalg.norm(d, axis=1, keepdims=True) + 1e-9) * 0.55
        self.scatter = rng.normal(0, 0.9, self.p.shape)                  # where particles start / dissolve
        self.bright = rng.uniform(0.45, 1.0, len(self.p))
        self.glow = np.isin(self.part, [names.index("CHEST REACTOR")] +
                            [names.index(n) for n in names if n.endswith("GAUNTLET")])

    def positions(self, explode: float, form: float) -> np.ndarray:
        """explode 0 = assembled … 1 = exploded view; form 0 = scattered dust … 1 = solid suit."""
        p = self.p + self.explode_dir[self.part] * explode
        if form < 1.0:
            f = form * form * (3 - 2 * form)
            p = self.scatter * (1 - f) + p * f
        return p


class _HoloObject:
    """One hologram in the window: its points, colours, and its own transform
    (rotation, size, position, explode, spin) so hands can move each one alone."""
    _ids = 0

    def __init__(self, name: str, points, palette_hex: list, scheme: str, suit=None, base: str | None = None):
        _HoloObject._ids += 1
        self.id = _HoloObject._ids
        self.name = name
        self.suit = suit                                   # _SuitModel for the armour suit
        self.p = suit.p / max(1e-9, float(np.linalg.norm(suit.p, axis=1).max())) if suit is not None else points
        rng = np.random.default_rng(self.id)
        self.bright = rng.uniform(0.45, 1.0, len(self.p))
        self.scatter = rng.normal(0, 0.9, self.p.shape)
        if suit is not None:
            k = float(np.linalg.norm(suit.p, axis=1).max())
            self.explode_dir = suit.explode_dir[suit.part] / k
        else:
            self.explode_dir = self.p * 0.45
        self.form, self.form_t = 0.0, 1.0                  # 0 = dust … 1 = solid (materialise / dissolve)
        self.phase = rng.uniform(0, 6.28)
        # own transform (on top of the window's): gestures change these
        self.yaw, self.pitch = 0.0, 0.0
        self.scale = 1.0
        self.ex, self.ex_t = 0.0, 0.0
        self.off = [0.0, 0.0]                              # moved by a fist, in window fractions
        self.spin = True
        self.base = base
        self.set_colors(palette_hex, scheme)

    def set_colors(self, palette_hex: list, scheme: str, base: str | None = None) -> None:
        from core import holo_shapes as HS
        self.pal = [QColor(h) for h in (palette_hex or ["#00d4ff"])]
        self.scheme = scheme
        if base:
            self.base = base
        if not self.base:                                  # remember which wheel colour this is
            try:
                h = self.pal[len(self.pal) // 2 if scheme in ("monochromatic", "analogous") else 0].name().lower()
                self.base = {v: k for k, v in HS.HEX.items()}.get(h) or HS.nearest_wheel(h)
            except Exception:
                self.base = "cyan"
        self.cidx = HS.assign(self.p, len(self.pal), scheme, self.id)
        self.glow = None
        if self.suit is not None:
            self.glow = np.isin(self.suit.part, [self.suit.names.index("CHEST REACTOR")] +
                                [self.suit.names.index(n) for n in self.suit.names if n.endswith("GAUNTLET")])

    def copy_transform(self, other: "_HoloObject") -> None:
        self.yaw, self.pitch, self.scale = other.yaw, other.pitch, other.scale
        self.ex, self.ex_t, self.off, self.spin, self.phase = other.ex, other.ex_t, list(other.off), other.spin, other.phase

    def positions(self, explode: float) -> np.ndarray:
        p = self.p + self.explode_dir * min(1.6, explode + self.ex)
        if self.form < 1.0:
            f = self.form * self.form * (3 - 2 * self.form)
            p = self.scatter * (1 - f) + p * f
        return p


class HologramWindow(QWidget):
    """Holograms: one or more particle shapes (140 built in + text + custom shapes
    JARVIS designs) side by side, each in colours from the colour wheel. They
    materialise, rotate, explode and dissolve.
      Mouse: click = select one (click empty space = all) · drag = rotate ·
             scroll = zoom · double-click = explode/assemble.
      Keys:  ← → select · A = all · Del = remove · Space = spin · C / S = colour / scheme.
      Hands: every gesture in core/holo_gestures.py (webcam, actions/suit_hologram.py)."""

    MAX = 9

    def __init__(self, color: str = "#00d4ff"):
        super().__init__()
        from collections import deque
        self.setWindowTitle("Holograms")
        self.setStyleSheet("background: #000000;")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.resize(1000, 760)
        self._default = color if QColor(color).isValid() else "#00d4ff"
        self._objs: list[_HoloObject] = []
        self._yaw, self._pitch, self._zoom = 0.0, -0.08, 1.0
        self._spin = True
        self._explode, self._explode_t = 0.0, 0.0
        self._drag = None
        self._press = None
        self._ext = deque(maxlen=400)                     # hand commands from the webcam thread
        self._sel = None                                  # id of the selected hologram (None = all)
        self._cells = []                                  # [(id, cx, cy, S)] from the last paint
        self._cursors, self._cursor_t = [], 0.0
        self._mode = ""
        self._feedback, self._feedback_t = "", 0.0
        self._gestures = False
        self._hold = None
        self._banner = None                               # big instruction text (gesture calibration)
        self._stay_open_until = 0.0                       # after "open": don't auto-hide for a few seconds
        self._grab_prev = "none"                          # selection before a fist grabbed a hologram
        self._panel = True                                # HAND CONTROLS panel (H hides it)
        self._btns = []                                   # [(QRectF, mode)] of the mode buttons
        self._img = None
        self._t0 = time.monotonic()
        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._tmr.start(33)

    # ── objects ──
    def names(self) -> list[str]:
        return [f"{i + 1}. {o.name}" for i, o in enumerate(o for o in self._objs if o.form_t > 0)]

    def _alive(self):
        return [o for o in self._objs if o.form_t > 0]

    def _selected(self):
        return next((o for o in self._alive() if o.id == self._sel), None)

    def _gtargets(self) -> list:
        """What a gesture acts on: the selected hologram, or all of them."""
        o = self._selected()
        return [o] if o is not None else self._alive()

    def _targets(self, target) -> list:
        alive = self._alive()
        t = str(target or "").strip().lower()
        if t in ("", "all", "everything", "every"):
            return alive
        if t in ("selected", "this", "this one", "current"):
            return self._gtargets()
        if t in ("last", "latest", "newest"):
            return alive[-1:]
        if t in ("first", "oldest"):
            return alive[:1]
        if t.isdigit():
            i = int(t) - 1
            return [alive[i]] if 0 <= i < len(alive) else []
        from core import holo_shapes as HS
        key = HS.resolve(t) or t
        return [o for o in alive if o.name == key or t in o.name]

    def add(self, name: str, points, palette_hex: list, scheme: str, base: str | None = None) -> None:
        if len(self._alive()) >= self.MAX:
            old = self._alive()[0]
            old.form_t = 0.0                              # make room: dissolve the oldest
            if self._sel == old.id:
                self._sel = None
        suit = _SuitModel() if points is None else None
        self._objs.append(_HoloObject(name, points, palette_hex or [self._default], scheme, suit, base))
        self.showNormal(); self.raise_()

    def _say(self, text: str) -> None:
        self._feedback, self._feedback_t = text, time.monotonic()

    def select(self, how) -> None:
        """how: +1 / -1 (next / previous), 'all', or a target (name, number, 'last')."""
        alive = self._alive()
        if not alive:
            self._sel = None; return
        if how in (1, -1):
            ids = [o.id for o in alive]
            if self._sel in ids:
                i = (ids.index(self._sel) + how) % len(ids)
            else:
                i = 0 if how > 0 else len(ids) - 1
            self._sel = ids[i]
        elif str(how).lower() in ("all", "none", "everything", ""):
            self._sel = None
        else:
            hit = self._targets(how)
            self._sel = hit[0].id if hit else None
        o = self._selected()
        if o is None or len(alive) == 1:
            self._say("ALL HOLOGRAMS" if len(alive) > 1 else f"{o.name.upper() if o else ''}")
        else:
            self._say(f"▶ {alive.index(o) + 1} · {o.name.upper()}")

    def _swap_shape(self, o: _HoloObject, step: int) -> _HoloObject | None:
        """Replace one hologram with the next / previous built-in shape, keeping
        its colours, size, position and rotation."""
        from core import holo_shapes as HS
        name = o.name
        for _ in range(3):                                # skip a shape that fails to build
            name = HS.neighbour(name, step)
            try:
                pts = HS.build(name)
                break
            except Exception as e:
                print(f"[Holograms] couldn't build {name}: {e}")
        else:
            return None
        suit = _SuitModel() if pts is None else None
        new = _HoloObject(name, pts, [c.name() for c in o.pal], o.scheme, suit, o.base)
        new.copy_transform(o)
        new.form = 0.35                                   # quick re-materialise
        self._objs[self._objs.index(o)] = new
        if self._sel == o.id:
            self._sel = new.id
        return new

    def _recolor(self, objs, base=None, scheme=None) -> None:
        from core import holo_shapes as HS
        for o in objs:
            b = base or o.base or "cyan"
            s = scheme or o.scheme
            o.set_colors(HS.palette(b, s), s, b)

    # ── gesture / hand commands (drained on the GUI thread) ──
    def _apply_ext(self, d: dict) -> None:
        from core import holo_shapes as HS
        if "cursors" in d:
            self._cursors, self._cursor_t = list(d["cursors"] or []), time.monotonic()
        if "mode" in d:
            self._mode = str(d["mode"])
        if "banner" in d:                                  # {"title", "sub", "p"} or None
            b = d["banner"]
            self._banner = (str(b.get("title", "")), str(b.get("sub", "")), b.get("p")) if b else None
            if b and not self.isVisible():                  # instructions always bring the window up
                self.showNormal(); self.raise_(); self.activateWindow()
        if "hold" in d:                                    # a sign being held: ring fills up
            hd = d["hold"]
            self._hold = (str(hd.get("label", "")), max(0.0, min(1.0, float(hd.get("p", 0))))) if hd else None
        if "feedback" in d:
            self._say(str(d["feedback"]))
        if "grab_at" in d:                                 # a fist closed over a hologram → pick THAT one
            gx, gy = d["grab_at"]
            X, Y = float(gx) * self.width(), float(gy) * self.height()
            hit = min(((math.hypot(X - cx, Y - cy) / max(S, 1), i) for i, cx, cy, S in self._cells), default=None)
            if hit and hit[0] < 1.25:
                self._grab_prev = self._sel
                self._sel = hit[1]
                o = self._selected()
                self._say(f"✊  GRABBED {o.name.upper()}" if o else "✊  GRABBED")
            else:
                self._grab_prev = "none"
        if d.get("release"):                               # hand opened → drop it, selection as before
            if self._grab_prev != "none":
                self._sel = self._grab_prev if any(o.id == self._grab_prev for o in self._alive()) else None
                self._say("✋  DROPPED")
            self._grab_prev = "none"
        tg = self._gtargets()
        if "dyaw" in d or "dpitch" in d:
            for o in tg:
                o.yaw += float(d.get("dyaw", 0))
                o.pitch = max(-1.3, min(1.3, o.pitch + float(d.get("dpitch", 0))))
                o.spin = False if o is self._selected() else o.spin
            if not self._selected():
                self._spin = False                         # hands took over — stop the auto spin
        if "zoom" in d:                                    # (older hand control: whole view)
            self._zoom = max(0.4, min(2.5, self._zoom * float(d["zoom"])))
        if "scale" in d:
            for o in tg:
                o.scale = max(0.3, min(3.0, o.scale * float(d["scale"])))
        if "explode" in d:
            if self._selected() is None and len(tg) > 1:
                self._explode_t = max(0.0, min(1.0, self._explode_t + float(d["explode"])))
            else:
                for o in tg:
                    o.ex_t = max(0.0, min(1.0, o.ex_t + float(d["explode"])))
        if "move" in d:
            dx, dy = d["move"]
            for o in tg:
                o.off[0] = max(-0.45, min(0.45, o.off[0] + float(dx)))
                o.off[1] = max(-0.45, min(0.45, o.off[1] + float(dy)))
        op = d.get("op")
        if not op:
            return
        if op == "select":
            self.select(int(d.get("dir", 1)) if "dir" in d else d.get("target", "all"))
        elif op == "select_all":                           # ☝️ toggles all ↔ the one you had
            if self._selected() is not None:
                self._last_sel, self._sel = self._sel, None
                self._say("ALL HOLOGRAMS")
            else:
                back = getattr(self, "_last_sel", None)
                if any(o.id == back for o in self._alive()):
                    self._sel = back
                    self._say(f"▶ {self._selected().name.upper()}")
                else:
                    self.select(1)
        elif op == "spin_toggle":
            on = not all(o.spin for o in tg) or not self._spin
            for o in tg:
                o.spin = on
            if on:
                self._spin = True
            self._say("SPIN ON" if on else "SPIN OFF")
        elif op == "shape":
            last = None
            for o in list(tg):
                last = self._swap_shape(o, int(d.get("dir", 1))) or last
            if last is not None:
                self._say(("👍  " if int(d.get("dir", 1)) > 0 else "👎  ") + last.name.upper()
                          + f"  ({HS.ORDER.index(last.name) + 1}/{len(HS.ORDER)})")
        elif op == "next_color":
            for o in tg:
                b = o.base if o.base in HS.WHEEL else HS.nearest_wheel(o.pal[0].name())
                self._recolor([o], base=HS.WHEEL[(HS.WHEEL.index(b) + 1) % len(HS.WHEEL)])
            if tg:
                self._say(f"✌  {tg[-1].base.upper()}")
        elif op == "next_scheme":
            for o in tg:
                s = o.scheme if o.scheme in HS.SCHEMES else "single"
                self._recolor([o], scheme=HS.SCHEMES[(HS.SCHEMES.index(s) + 1) % len(HS.SCHEMES)])
            if tg:
                self._say(f"🤟  {tg[-1].scheme.upper()}")
        elif op == "remove_selected":
            for o in tg:
                o.form_t = 0.0
            self._sel = None
        elif op == "gestures":
            self._gestures = bool(d.get("on"))
            if not self._gestures:
                self._cursors, self._mode, self._hold = [], "", None

    def command(self, cmd) -> None:
        if isinstance(cmd, str) and cmd.startswith("{"):
            try:
                cmd = json.loads(cmd)
            except Exception:
                return
        if isinstance(cmd, dict):
            op = cmd.get("op")
            if op == "add":
                from core import holo_shapes as HS
                try:
                    pts = HS.build(cmd.get("shape") or cmd.get("name", ""), cmd.get("primitives"))
                except Exception as e:
                    print(f"[Holograms] couldn't build {cmd.get('name')}: {e}")
                    return
                self.add(cmd.get("name", "shape"), pts, cmd.get("palette") or [self._default],
                         cmd.get("scheme", "single"), cmd.get("base"))
            elif op == "remove":
                for o in self._targets(cmd.get("target")):
                    o.form_t = 0.0
                    if o.id == self._sel:
                        self._sel = None
            elif op == "color":
                for o in self._targets(cmd.get("target")):
                    o.set_colors(cmd.get("palette") or [self._default], cmd.get("scheme", "single"), cmd.get("base"))
            elif op == "select":
                self.select(cmd.get("target", "all"))
            elif op == "open":                                # show the window as it is (no default suit)
                self._stay_open_until = time.monotonic() + 8   # don't auto-hide before its content arrives
                self.showNormal(); self.raise_(); self.activateWindow()
            elif op == "gestures":
                self._apply_ext(cmd)
                if self._gestures:
                    self.showNormal(); self.raise_()
            return
        c = (cmd or "").lower()
        if c == "explode":
            self._explode_t = 1.0
        elif c == "assemble":
            self._explode_t = 0.0
            for o in self._objs:
                o.ex_t = 0.0
        elif c == "spin":
            self._spin = True
            for o in self._objs:
                o.spin = True
        elif c == "stop_spin":
            self._spin = False
        elif c == "reset":
            self._yaw, self._pitch, self._zoom, self._explode_t = 0.0, -0.08, 1.0, 0.0
            for o in self._objs:
                o.yaw = o.pitch = o.ex_t = 0.0
                o.scale, o.off, o.spin = 1.0, [0.0, 0.0], True
            self._spin = True
        elif c == "close":
            for o in self._objs:
                o.form_t = 0.0
            self._sel = None
        else:                                             # "show": the suit if nothing is up yet
            if not self._alive():
                self.add("suit", None, [self._default], "single")
            self.showNormal(); self.raise_(); self.activateWindow()

    def external(self, d) -> None:
        """Called from the webcam thread — just queue it; _step applies it."""
        if isinstance(d, dict):
            self._ext.append(d)

    def _step(self):
        n = len(self._ext)
        for _ in range(n):
            try:
                self._apply_ext(self._ext.popleft())
            except IndexError:
                break
            except Exception as e:
                print(f"[Holograms] gesture command failed: {e}")
        if self._spin and self._drag is None:
            for o in self._objs:
                if o.spin:
                    o.yaw += 0.008
        self._explode += (self._explode_t - self._explode) * 0.08
        for o in self._objs:
            o.form += (o.form_t - o.form) * (0.05 if o.form_t > o.form else 0.09)
            o.ex += (o.ex_t - o.ex) * 0.1
        self._objs = [o for o in self._objs if not (o.form_t == 0 and o.form < 0.03)]
        if self._sel is not None and self._selected() is None:
            self._sel = None
        if (not self._objs and self.isVisible() and not self._gestures and not self._banner
                and time.monotonic() > self._stay_open_until):
            self.hide()
        self.update()

    # ── mouse & keys ──
    def mousePressEvent(self, e):
        pos = e.position()
        if self._in_panel(pos.x()):                       # HAND CONTROLS panel: mode buttons
            self._drag = self._press = None
            for r, mode in self._btns:
                if r.contains(pos):
                    from core import gesture_modes
                    self._say({"hologram": "✋  SWITCHING TO HOLOGRAM MODE…", "pc": "🖥  SWITCHING TO PC MODE…",
                               "off": "HAND GESTURES OFF"}[mode])
                    gesture_modes.switch_async(mode)
            return
        self._drag = self._press = pos

    def mouseMoveEvent(self, e):
        if self._drag is not None:
            d = e.position() - self._drag; self._drag = e.position()
            sel = self._selected()
            if sel is not None:
                sel.yaw += d.x() * 0.01; sel.pitch = max(-1.3, min(1.3, sel.pitch + d.y() * 0.01)); sel.spin = False
            else:
                self._yaw += d.x() * 0.01; self._pitch = max(-1.2, min(1.2, self._pitch + d.y() * 0.01))
                self._spin = False

    def mouseReleaseEvent(self, e):
        if self._press is not None:
            d = e.position() - self._press
            if abs(d.x()) + abs(d.y()) < 5:                # a click, not a drag → select
                x, y = e.position().x(), e.position().y()
                hit = next((i for i, cx, cy, S in self._cells if abs(x - cx) < S * 1.1 and abs(y - cy) < S * 1.1), None)
                self._sel = hit
                o = self._selected()
                self._say(f"▶ {o.name.upper()}" if o is not None else "ALL HOLOGRAMS")
        self._drag = self._press = None

    def mouseDoubleClickEvent(self, e):
        if self._in_panel(e.position().x()):
            return
        sel = self._selected()
        if sel is not None:
            sel.ex_t = 0.0 if sel.ex_t > 0.5 else 1.0
        else:
            self._explode_t = 0.0 if self._explode_t > 0.5 else 1.0

    def wheelEvent(self, e):
        k = 1.1 if e.angleDelta().y() > 0 else 0.9
        sel = self._selected()
        if sel is not None:
            sel.scale = max(0.3, min(3.0, sel.scale * k))
        else:
            self._zoom = max(0.4, min(2.5, self._zoom * k))

    def keyPressEvent(self, e):
        k = e.key()
        K = Qt.Key
        if k in (K.Key_Right, K.Key_Tab):
            self._apply_ext({"op": "select", "dir": 1})
        elif k == K.Key_Left:
            self._apply_ext({"op": "select", "dir": -1})
        elif k in (K.Key_A, K.Key_Escape):
            self._sel = None; self._say("ALL HOLOGRAMS")
        elif k in (K.Key_Delete, K.Key_Backspace):
            self._apply_ext({"op": "remove_selected"})
        elif k == K.Key_Space:
            self._apply_ext({"op": "spin_toggle"})
        elif k == K.Key_Up:
            self._apply_ext({"op": "shape", "dir": 1})
        elif k == K.Key_Down:
            self._apply_ext({"op": "shape", "dir": -1})
        elif k == K.Key_C:
            self._apply_ext({"op": "next_color"})
        elif k == K.Key_S:
            self._apply_ext({"op": "next_scheme"})
        elif k == K.Key_R:
            self.command("reset")
        elif k in (K.Key_G, K.Key_P, K.Key_O):           # gesture modes
            from core import gesture_modes
            cur = gesture_modes.current()
            mode = {K.Key_G: "off" if cur == "hologram" else "hologram", K.Key_P: "pc", K.Key_O: "off"}[k]
            self._say({"hologram": "✋  SWITCHING TO HOLOGRAM MODE…", "pc": "🖥  SWITCHING TO PC MODE…",
                       "off": "HAND GESTURES OFF"}[mode])
            gesture_modes.switch_async(mode)
        elif k == K.Key_H:
            self._panel = not self._panel
        else:
            super().keyPressEvent(e)

    def closeEvent(self, e):
        """Closing the window also stops hologram hand control (frees the webcam)."""
        import sys
        for name, mod in list(sys.modules.items()):
            if name.endswith("suit_hologram") and isinstance(getattr(mod, "_st", None), dict):
                mod._st["stop"] = True
        self._gestures, self._cursors = False, []
        super().closeEvent(e)

    def layout_cells(self, k: int, W: int, H: int):
        """Grid of k cells → [(centre x, centre y, scale)] that fit the window."""
        cols = max(1, math.ceil(math.sqrt(k * W / max(1, H))))
        cols = min(cols, k)
        rows = math.ceil(k / cols)
        cw, ch = W / cols, (H - 70) / rows
        size = min(cw, ch) * 0.40 * self._zoom * (1 - 0.30 * self._explode)
        out = []
        for i in range(k):
            r, c = divmod(i, cols)
            n_in_row = min(cols, k - r * cols)
            x0 = (W - n_in_row * cw) / 2
            out.append((x0 + (c + 0.5) * cw, 40 + (r + 0.5) * ch, size))
        return out

    def paintEvent(self, _):
        p = QPainter(self)
        if not p.isActive():
            return
        W, H = self.width(), self.height()
        p.fillRect(self.rect(), QColor(0, 0, 0))
        dpr = _dpr(self)
        pw, ph = max(1, int(W * dpr)), max(1, int(H * dpr))
        if self._img is None or self._img.width() != pw or self._img.height() != ph:
            self._img = QImage(pw, ph, QImage.Format.Format_ARGB32_Premultiplied)
            self._img.setDevicePixelRatio(dpr)
        img = self._img
        img.fill(Qt.GlobalColor.transparent)
        ip = QPainter(img)
        ip.setRenderHint(QPainter.RenderHint.Antialiasing)
        ip.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        objs = self._objs
        pw = self._panel_w(W)
        cells = self.layout_cells(len(objs), W - pw, H) if objs else []
        t = time.monotonic() - self._t0
        white = QColor(230, 250, 255)
        labels = []
        self._cells = []
        for o, (cx, cy, S) in zip(objs, cells):
            cx, cy, S = cx + o.off[0] * W, cy + o.off[1] * H, S * o.scale
            if o.form_t > 0:
                self._cells.append((o.id, cx, cy, S))
            pts = o.positions(self._explode)
            rot = _PlexusModel.rotate(pts, self._yaw + o.yaw, max(-1.5, min(1.5, self._pitch + o.pitch)))
            persp = 1.0 / (1.0 - 0.22 * np.clip(rot[:, 2], -2, 2))
            sx = cx + rot[:, 0] * S * persp
            sy = cy - rot[:, 1] * S * persp
            depth = np.clip((rot[:, 2] + 0.6) / 1.2, 0, 1)
            lum = o.bright * (0.35 + 0.65 * depth)
            fade = max(0.0, min(1.0, o.form * 1.4))
            if self._sel is not None and o.id != self._sel:
                fade *= 0.55                               # the selected one stands out
            for ci, col in enumerate(o.pal):
                mine = o.cidx == ci
                if o.glow is not None:
                    mine &= ~o.glow
                def a(al, c_=col):
                    q = QColor(c_); q.setAlpha(max(0, min(255, int(al * fade)))); return q
                halo = QPen(a(16), 6); halo.setCapStyle(Qt.PenCapStyle.RoundCap); ip.setPen(halo)
                ip.drawPoints([QPointF(sx[i], sy[i]) for i in np.nonzero(mine & (lum > 0.55))[0]])
                for lo, hi, size, al, use_white in ((0, 0.45, 1.3, 140, False), (0.45, 0.75, 1.7, 200, False), (0.75, 9, 2.0, 235, True)):
                    sel = np.nonzero(mine & (lum >= lo) & (lum < hi))[0]
                    if len(sel) == 0:
                        continue
                    base = col if not use_white else QColor((col.red() + 2 * 230) // 3, (col.green() + 2 * 250) // 3, (col.blue() + 2 * 255) // 3)
                    pen = QPen(a(al, base), size); pen.setCapStyle(Qt.PenCapStyle.RoundCap); ip.setPen(pen)
                    ip.drawPoints([QPointF(sx[i], sy[i]) for i in sel])
            if o.glow is not None:
                q = QColor(white); q.setAlpha(int(255 * fade))
                pen = QPen(q, 2.6); pen.setCapStyle(Qt.PenCapStyle.RoundCap); ip.setPen(pen)
                ip.drawPoints([QPointF(sx[i], sy[i]) for i in np.nonzero(o.glow)[0]])
            ys = cy - S * math.sin(t * 0.9 + o.phase) * 0.95             # scanning line
            g = QLinearGradient(0, ys - 12, 0, ys + 12)
            sc = QColor(o.pal[0]); sc.setAlpha(0); g.setColorAt(0, sc)
            sc2 = QColor(o.pal[0]); sc2.setAlpha(int(60 * fade)); g.setColorAt(0.5, sc2); g.setColorAt(1, sc)
            ip.fillRect(QRectF(cx - S * 0.75, ys - 12, S * 1.5, 24), QBrush(g))
            labels.append((o, cx, cy, S, fade))
        ip.end()
        p.drawImage(0, 0, img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        for i, (o, cx, cy, S, fade) in enumerate(labels):              # name under each hologram
            c = QColor(o.pal[len(o.pal) // 2] if o.scheme == "monochromatic" else o.pal[0])   # readable label
            c.setAlpha(int(200 * fade)); p.setPen(QPen(c, 1))
            p.drawText(QRectF(cx - 120, cy + S * 1.08, 240, 16), Qt.AlignmentFlag.AlignCenter,
                       f"{i + 1} · {o.name.upper()}" + (f" · {o.scheme.upper()}" if o.scheme != "single" else ""))
            if o.id == self._sel and o.form_t > 0:                      # selection brackets
                bc = QColor(o.pal[0]); bc.setAlpha(int(90 + 80 * (0.5 + 0.5 * math.sin(t * 4))))
                p.setPen(QPen(bc, 1.6))
                r, L = S * 1.12, S * 0.22
                for sxn, syn in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
                    x0, y0 = cx + sxn * r, cy + syn * r
                    p.drawLine(QPointF(x0, y0), QPointF(x0 - sxn * L, y0))
                    p.drawLine(QPointF(x0, y0), QPointF(x0, y0 - syn * L))
            if o.suit is not None and self._explode + o.ex > 0.5 and o.form > 0.9:   # suit part labels
                k = float(np.linalg.norm(o.suit.p, axis=1).max())
                ex = min(1.6, self._explode + o.ex)
                cen = (o.suit.centres + o.suit.explode_dir * ex) / k
                crot = _PlexusModel.rotate(cen, self._yaw + o.yaw, max(-1.5, min(1.5, self._pitch + o.pitch)))
                p.setFont(QFont("Consolas", 7, QFont.Weight.Bold))
                kk = min(1.0, (ex - 0.5) * 2)
                for j, nm in enumerate(o.suit.names):
                    x = cx + crot[j, 0] * S + 12; y = cy - crot[j, 1] * S
                    c2 = QColor(o.pal[0]); c2.setAlpha(int(220 * kk)); p.setPen(QPen(c2, 1))
                    p.drawText(QPointF(x, y + 3), nm)
                p.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        c0 = QColor(self._objs[0].pal[0]) if self._objs else QColor(self._default)
        p.setPen(QPen(c0, 1)); p.setFont(QFont("Consolas", 13, QFont.Weight.Bold))
        p.drawText(QPointF(22, 30), "HOLOGRAMS")
        p.setFont(QFont("Consolas", 8)); c0.setAlpha(150); p.setPen(QPen(c0, 1))
        so = self._selected()
        p.drawText(QPointF(22, 48), f"{len(self._alive())} ACTIVE  ·  {sum(len(o.p) for o in self._objs)} PARTICLES"
                                    f"  ·  {'SELECTED: ' + so.name.upper() if so is not None else 'ALL SELECTED'}")
        now = time.monotonic()
        try:
            from core import gesture_modes as _GMODE
            gmode = _GMODE.current()
        except Exception:
            gmode = "hologram" if self._gestures else "off"
        seen = self._gestures and bool(self._cursors) and now - self._cursor_t < 0.6
        if seen:                                                         # hands: cursors, labels, hold ring
            from core.holo_gestures import NAMES as _GN
            hold = self._hold
            for k3, (x, y, m) in enumerate(self._cursors):
                X, Y = float(x) * W, float(y) * H
                cc = QColor(c0); cc.setAlpha(220 if m == "pinch" else 140)
                p.setPen(QPen(cc, 2 if m == "pinch" else 1.2)); p.setBrush(Qt.BrushStyle.NoBrush)
                rr = 9 if m == "pinch" else 16
                p.drawEllipse(QPointF(X, Y), rr, rr)
                p.drawPoint(QPointF(X, Y))
                name = _GN.get(m, "")                                    # what JARVIS sees this hand doing
                if name:
                    p.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
                    p.drawText(QPointF(X + rr + 6, Y + 4), name)
            if hold and hold[0]:                                          # hold-to-act ring around the sign
                hx, hy = (float(self._cursors[0][0]) * W, float(self._cursors[0][1]) * H)
                for (x, y, m) in self._cursors:
                    if m not in ("pinch", "hand", "Closed_Fist"):
                        hx, hy = float(x) * W, float(y) * H; break
                R = 30
                bg = QColor(c0); bg.setAlpha(50); p.setPen(QPen(bg, 4)); p.drawEllipse(QPointF(hx, hy), R, R)
                fg = QColor(c0); fg.setAlpha(240); pen = QPen(fg, 4); pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                p.drawArc(QRectF(hx - R, hy - R, 2 * R, 2 * R), 90 * 16, -int(360 * 16 * hold[1]))
                p.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
                p.drawText(QRectF(hx - 160, hy + R + 6, 320, 18), Qt.AlignmentFlag.AlignCenter, "HOLD  " + hold[0])
        if gmode == "pc":                                                # make it impossible to miss
            wc = QColor(255, 170, 60); wc.setAlpha(235); p.setPen(QPen(wc, 1))
            p.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
            p.drawText(QRectF(0, 58, W - pw, 18), Qt.AlignmentFlag.AlignCenter,
                       "🖥 PC GESTURE MODE — your hands control the COMPUTER, not the holograms  ·  press G to switch")
        if pw:
            self._draw_panel(p, W, H, pw, c0, gmode, seen)
        else:
            self._btns = []
            lc = QColor(c0); lc.setAlpha(150); p.setPen(QPen(lc, 1)); p.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
            p.drawText(QRectF(0, 14, W - 22, 16), Qt.AlignmentFlag.AlignRight,
                       f"HANDS: {({'hologram': '✋ HOLOGRAM', 'pc': '🖥 PC'}).get(gmode, 'OFF')}   ·   H = SHOW HAND CONTROLS")
            p.setFont(QFont("Consolas", 7))
            for k2, line in enumerate(["CLICK = SELECT   DRAG = ROTATE   SCROLL = SIZE   DOUBLE-CLICK = EXPLODE",
                                       "← → SELECT   ↑ ↓ SHAPE   C COLOUR   S SCHEME   SPACE SPIN   DEL REMOVE   R RESET"]):
                p.drawText(QRectF(0, H - 40 + k2 * 15, W - 22, 15), Qt.AlignmentFlag.AlignRight, line)
        if self._banner:                                                 # calibration / instructions
            bt, bs, bp = self._banner
            area = W - pw
            box = QRectF(area * 0.12, H * 0.30, area * 0.76, 150)
            p.fillRect(box, QColor(0, 0, 0, 200))
            bc = QColor(c0); bc.setAlpha(160); p.setPen(QPen(bc, 1.2)); p.drawRect(box)
            p.setPen(QPen(QColor(c0), 1)); p.setFont(QFont("Consolas", 22, QFont.Weight.Bold))
            p.drawText(QRectF(box.x(), box.y() + 14, box.width(), 40), Qt.AlignmentFlag.AlignCenter, bt)
            sc2 = QColor(c0); sc2.setAlpha(210); p.setPen(QPen(sc2, 1)); p.setFont(QFont("Consolas", 11))
            p.drawText(QRectF(box.x() + 12, box.y() + 60, box.width() - 24, 44),
                       Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, bs)
            if bp is not None:
                bar = QRectF(box.x() + 30, box.y() + 118, box.width() - 60, 10)
                bg2 = QColor(c0); bg2.setAlpha(50); p.fillRect(bar, bg2)
                p.fillRect(QRectF(bar.x(), bar.y(), bar.width() * max(0.0, min(1.0, float(bp))), bar.height()), QColor(c0))
        age = now - self._feedback_t
        if self._feedback and age < 1.6:                                 # big fading feedback text
            fc = QColor(c0); fc.setAlpha(int(255 * min(1.0, (1.6 - age) / 0.5)))
            p.setPen(QPen(fc, 1)); p.setFont(QFont("Consolas", 15, QFont.Weight.Bold))
            p.drawText(QRectF(0, H - 92, W - pw, 30), Qt.AlignmentFlag.AlignCenter, self._feedback)
        p.end()

    # ── HAND CONTROLS panel ──
    PANEL_ROWS = [
        ("ONE HAND", None, None, None),
        ("🤏", "Pinch + move", "ROTATE", "pinch"),
        ("✊", "Fist over it · move · push / pull", "GRAB · MOVE · NEAR = BIGGER", "Closed_Fist"),
        ("👋", "Swipe open palm ← →", "SELECT PREV / NEXT", "swipe"),
        ("✋", "Hold palm still 1 s", "SPIN ON / OFF", "Open_Palm"),
        ("☝", "Point up", "ALL ↔ ONE", "Pointing_Up"),
        ("👍", "Thumb up (hold)", "NEXT SHAPE", "Thumb_Up"),
        ("👎", "Thumb down (hold)", "PREVIOUS SHAPE", "Thumb_Down"),
        ("✌", "Victory / peace", "NEXT COLOUR", "Victory"),
        ("🤟", "Love-you sign", "NEXT COLOUR SCHEME", "ILoveYou"),
        ("TWO HANDS", None, None, None),
        ("🤏🤏", "Pinch both, apart / together", "BIGGER / SMALLER", "zoom"),
        ("✋✋", "Palms apart / together", "EXPLODE / ASSEMBLE", "explode"),
        ("👎👎", "Both thumbs down 1 s", "REMOVE IT", "remove"),
    ]

    def _panel_w(self, W: int) -> int:
        return 0 if not self._panel or W < 560 else int(min(300, max(240, W * 0.27)))

    def _draw_panel(self, p, W, H, pw, c0, gmode, seen):
        x0 = W - pw
        bg = QColor(4, 10, 14, 235); p.fillRect(QRectF(x0, 0, pw, H), bg)
        ln = QColor(c0); ln.setAlpha(70); p.setPen(QPen(ln, 1)); p.drawLine(QPointF(x0, 0), QPointF(x0, H))
        x, w = x0 + 14, pw - 28
        tc = QColor(c0); p.setPen(QPen(tc, 1)); p.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        p.drawText(QPointF(x, 26), "HAND CONTROLS")
        # mode buttons
        self._btns = []
        bw = (w - 12) / 3
        for i, (mode, label) in enumerate((("hologram", "✋ HOLOGRAM"), ("pc", "🖥 PC"), ("off", "OFF"))):
            r = QRectF(x + i * (bw + 6), 38, bw, 26)
            self._btns.append((r, mode))
            on = mode == gmode
            f = QColor(c0); f.setAlpha(110 if on else 0); b = QColor(c0); b.setAlpha(230 if on else 90)
            p.setBrush(QBrush(f)); p.setPen(QPen(b, 1.4 if on else 1)); p.drawRoundedRect(r, 4, 4)
            t = QColor(255, 255, 255) if on else QColor(c0)
            if not on:
                t.setAlpha(170)
            p.setPen(QPen(t, 1)); p.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, label)
        p.setBrush(Qt.BrushStyle.NoBrush)
        # status
        if gmode == "hologram":
            status = ("● " + (self._mode or "HAND SEEN")) if seen else "○ Show your hand to the camera"
        elif gmode == "pc":
            status = "Your hands control the COMPUTER (volume, mute, click). Click HOLOGRAM or press G to move holograms."
        else:
            status = "Hand gestures are off. Click HOLOGRAM or press G to move the holograms with your hands."
        sc = QColor(255, 170, 60) if gmode == "pc" else QColor(c0)
        sc.setAlpha(230); p.setPen(QPen(sc, 1)); p.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        p.drawText(QRectF(x, 70, w, 40), Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap, status)
        # which rows are happening now
        active = set()
        if gmode == "hologram" and seen:
            active |= {m for (_, _, m) in self._cursors}
            md = self._mode.upper()
            if "RESIZE" in md: active.add("zoom")
            if "EXPLODE" in md: active.add("explode")
            if self._hold and "REMOVE" in self._hold[0]: active.add("remove")
            if self._feedback and time.monotonic() - self._feedback_t < 0.8 and self._feedback.startswith("👋"):
                active.add("swipe")
        y = 116
        rh = max(22, min(30, (H - y - 52) / len(self.PANEL_ROWS)))
        dim = gmode != "hologram"
        for icon, gesture, action, key in self.PANEL_ROWS:
            if gesture is None:                                            # section header
                hc = QColor(c0); hc.setAlpha(120 if dim else 190); p.setPen(QPen(hc, 1))
                p.setFont(QFont("Consolas", 7, QFont.Weight.Bold))
                p.drawText(QPointF(x, y + rh * 0.7), icon)
                y += rh * 0.85
                continue
            if key in active:
                hl = QColor(c0); hl.setAlpha(60); p.fillRect(QRectF(x0 + 4, y, pw - 8, rh - 2), hl)
            ic = QColor(c0); ic.setAlpha(110 if dim else 255)
            p.setPen(QPen(ic, 1)); p.setFont(QFont("Segoe UI Emoji", 10))
            p.drawText(QRectF(x, y, 40, rh), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, icon)
            gc_ = QColor(c0); gc_.setAlpha(90 if dim else 170); p.setPen(QPen(gc_, 1)); p.setFont(QFont("Consolas", 7))
            p.drawText(QRectF(x + 42, y + 1, w - 42, rh / 2), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, gesture)
            ac = QColor(255, 255, 255) if key in active else QColor(c0)
            ac.setAlpha(120 if dim else 255); p.setPen(QPen(ac, 1)); p.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
            p.drawText(QRectF(x + 42, y + rh / 2 - 1, w - 42, rh / 2), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, action)
            y += rh
        fc = QColor(c0); fc.setAlpha(130); p.setPen(QPen(fc, 1)); p.setFont(QFont("Consolas", 7))
        for k, line in enumerate(("MOUSE  click select · drag rotate · scroll size",
                                  "KEYS  G hologram · P PC · O off · H hide this")):
            p.drawText(QPointF(x, H - 28 + k * 13), line)

    def _in_panel(self, x: float) -> bool:
        pw = self._panel_w(self.width())
        return bool(pw) and x >= self.width() - pw


class MetricBar(QWidget):

    def __init__(self, label: str, color: str = C.PRI, parent=None):
        super().__init__(parent)
        self._label = label
        self._color = color
        self._value = 0.0       # 0–100
        self._text  = "--"
        self.setFixedHeight(38)
        self.setMinimumWidth(80)

    def set_value(self, pct: float, text: str):
        v = max(0.0, min(100.0, pct))
        if v == self._value and text == self._text:
            return          # unchanged — skip the repaint
        self._value = v
        self._text  = text
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()

        p.setBrush(QBrush(qcol(C.PANEL2)))
        p.setPen(QPen(qcol(C.BORDER_A), 1))
        p.drawRoundedRect(QRectF(1, 1, W - 2, H - 2), 4, 4)

        bar_h   = 4
        bar_y   = H - bar_h - 5
        bar_w   = W - 12
        bar_x   = 6
        fill_w  = int(bar_w * self._value / 100)

        p.setBrush(QBrush(qcol(C.BAR_BG)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), 2, 2)

        if self._value > 85:
            bar_col = qcol(C.RED)
        elif self._value > 65:
            bar_col = qcol(C.ACC)
        else:
            bar_col = qcol(self._color)

        if fill_w > 0:
            p.setBrush(QBrush(bar_col))
            p.drawRoundedRect(QRectF(bar_x, bar_y, fill_w, bar_h), 2, 2)

        p.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(8, 5, 50, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._label)

        p.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        p.setPen(QPen(bar_col if self._text != "--" else qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(0, 4, W - 6, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self._text)

        p.end()

class LogWidget(QTextEdit):
    _sig = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        # Cap scrollback so an hours-long session can't grow the document
        # without bound — keeps memory flat and every insert cheap. Oldest
        # lines drop off the top automatically.
        self.document().setMaximumBlockCount(600)
        self.setFont(QFont("Courier New", 9))
        self.setStyleSheet(f"""
            QTextEdit {{
                background: {C.PANEL};
                color: {C.TEXT};
                border: 1px solid {C.BORDER};
                border-radius: 4px;
                padding: 6px;
                selection-background-color: {C.PRI_GHO};
            }}
            QScrollBar:vertical {{
                background: {C.BG};
                width: 8px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER_B};
                border-radius: 4px;
                min-height: 20px;
            }}
        """)
        self._queue: list[str] = []
        self._typing  = False
        self._text    = ""
        self._pos     = 0
        self._tag     = "sys"
        self._ai_name_lc = _assistant_display_name().lower()   # updated when the name changes
        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._sig.connect(self._enqueue)

    def append_log(self, text: str):
        self._sig.emit(text)

    def _enqueue(self, text: str):
        self._queue.append(text)
        if not self._typing:
            self._next()

    def _next(self):
        if not self._queue:
            self._typing = False
            return
        self._typing = True
        self._text   = self._queue.pop(0)
        # Actions/plugins still log as "JARVIS: …" — show their lines under the
        # assistant's current name so the log is consistent.
        if self._text[:7].lower() == "jarvis:" and self._ai_name_lc != "jarvis":
            self._text = self._ai_name_lc.upper() + ":" + self._text[7:]
        self._pos    = 0
        tl = self._text.lower()
        _ai_pfx = f"{self._ai_name_lc}:"
        if   tl.startswith("you:"):                              self._tag = "you"
        elif tl.startswith(_ai_pfx) or tl.startswith("jarvis:"): self._tag = "ai"
        elif tl.startswith("file:"):                             self._tag = "file"
        elif "err" in tl:                                        self._tag = "err"
        else:                                                    self._tag = "sys"
        self._tmr.start(6)

    def _step(self):
        if self._pos < len(self._text):
            ch  = self._text[self._pos]
            cur = self.textCursor()
            fmt = cur.charFormat()
            col = {
                "you":  qcol(C.WHITE),
                "ai":   qcol(C.PRI),
                "err":  qcol(C.RED),
                "file": qcol(C.GREEN),
                "sys":  qcol(C.ACC2),
            }.get(self._tag, qcol(C.TEXT))
            fmt.setForeground(QBrush(col))
            cur.movePosition(cur.MoveOperation.End)
            cur.insertText(ch, fmt)
            self.setTextCursor(cur)
            self.ensureCursorVisible()
            self._pos += 1
        else:
            self._tmr.stop()
            cur = self.textCursor()
            cur.movePosition(cur.MoveOperation.End)
            cur.insertText("\n")
            self.setTextCursor(cur)
            self.ensureCursorVisible()
            QTimer.singleShot(20, self._next)

_FILE_ICONS = {
    "image":   ("🖼", "#00d4ff"), "video":   ("🎬", "#ff6b00"),
    "audio":   ("🎵", "#cc44ff"), "pdf":     ("📄", "#ff4444"),
    "word":    ("📝", "#4488ff"), "excel":   ("📊", "#44bb44"),
    "code":    ("💻", "#ffcc00"), "archive": ("📦", "#ff8844"),
    "pptx":    ("📊", "#ff6622"), "text":    ("📃", "#aaaaaa"),
    "data":    ("🔧", "#88ddff"), "unknown": ("📎", "#888888"),
}
_EXT_TO_CAT = {
    **dict.fromkeys(["jpg","jpeg","png","gif","webp","bmp","tiff","svg","ico"], "image"),
    **dict.fromkeys(["mp4","avi","mov","mkv","wmv","flv","webm","m4v"],         "video"),
    **dict.fromkeys(["mp3","wav","ogg","m4a","aac","flac","wma","opus"],        "audio"),
    **dict.fromkeys(["pdf"],                                                     "pdf"),
    **dict.fromkeys(["doc","docx"],                                              "word"),
    **dict.fromkeys(["xls","xlsx","ods"],                                        "excel"),
    **dict.fromkeys(["ppt","pptx"],                                              "pptx"),
    **dict.fromkeys(["py","js","ts","jsx","tsx","html","css","java","c","cpp",
                     "cs","go","rs","rb","php","swift","kt","sh","sql","lua"],   "code"),
    **dict.fromkeys(["zip","rar","tar","gz","7z","bz2","xz"],                   "archive"),
    **dict.fromkeys(["txt","md","rst","log"],                                    "text"),
    **dict.fromkeys(["csv","tsv","json","xml"],                                  "data"),
}

def _file_category(path: Path) -> str:
    return _EXT_TO_CAT.get(path.suffix.lower().lstrip("."), "unknown")

def _fmt_size(size: int) -> str:
    if   size < 1024:    return f"{size} B"
    elif size < 1024**2: return f"{size/1024:.1f} KB"
    elif size < 1024**3: return f"{size/1024**2:.1f} MB"
    else:                return f"{size/1024**3:.1f} GB"


class FileDropZone(QWidget):
    file_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(100)
        self._current_file: str | None = None
        self._hovering  = False
        self._drag_over = False
        self._dash_offset = 0.0
        self._anim_tmr = QTimer(self)
        self._anim_tmr.timeout.connect(self._animate)
        self._anim_tmr.start(40)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._canvas = _DropCanvas(self)
        layout.addWidget(self._canvas)

    def _animate(self):
        # The marching-ants dashed border is only meaningful while the user is
        # hovering or dragging a file over the zone. When idle, skip the repaint
        # entirely instead of redrawing the whole zone 25×/s forever — that idle
        # repaint held the GIL and stole time from the audio/response threads.
        if not (self._hovering or self._drag_over):
            return
        self._dash_offset = (self._dash_offset + 0.8) % 20
        self._canvas.update()

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._drag_over = True; self._canvas.update()

    def dragLeaveEvent(self, e):
        self._drag_over = False; self._canvas.update()

    def dropEvent(self, e: QDropEvent):
        self._drag_over = False
        urls = e.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if Path(path).is_file():
                self._set_file(path)
        self._canvas.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._browse()

    def enterEvent(self, e):
        self._hovering = True; self._canvas.update()

    def leaveEvent(self, e):
        self._hovering = False; self._canvas.update()

    def current_file(self) -> str | None:
        return self._current_file

    def clear_file(self):
        self._current_file = None; self._canvas.update()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, f"Select a file for {_assistant_display_name()}", str(Path.home()),
            "All Files (*.*);;"
            "Images (*.jpg *.jpeg *.png *.gif *.webp *.bmp *.svg);;"
            "Documents (*.pdf *.docx *.txt *.md *.pptx);;"
            "Data (*.csv *.xlsx *.json *.xml);;"
            "Code (*.py *.js *.ts *.html *.css *.java *.cpp *.go);;"
            "Audio (*.mp3 *.wav *.ogg *.m4a *.aac *.flac);;"
            "Video (*.mp4 *.avi *.mov *.mkv *.wmv *.webm);;"
            "Archives (*.zip *.rar *.tar *.gz *.7z)",
        )
        if path:
            self._set_file(path)

    def _set_file(self, path: str):
        self._current_file = path
        self._canvas.update()
        self.file_selected.emit(path)


class _DropCanvas(QWidget):
    def __init__(self, zone: FileDropZone):
        super().__init__(zone)
        self._z = zone

    def paintEvent(self, _):
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        z    = self._z
        W, H = self.width(), self.height()
        pad  = 6
        rect = QRectF(pad, pad, W - pad * 2, H - pad * 2)

        bg_col = qcol("#001a24" if z._drag_over else ("#001218" if z._hovering else C.PANEL))
        p.setBrush(QBrush(bg_col)); p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(rect, 6, 6)

        if z._current_file:   border_col = qcol(C.GREEN, 200)
        elif z._drag_over:    border_col = qcol(C.PRI, 230)
        elif z._hovering:     border_col = qcol(C.BORDER_B, 200)
        else:                 border_col = qcol(C.BORDER, 160)

        pen = QPen(border_col, 1.5, Qt.PenStyle.DashLine)
        pen.setDashOffset(z._dash_offset)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, 6, 6)

        if z._current_file:   self._paint_file(p, W, H)
        elif z._drag_over:    self._paint_drag_over(p, W, H)
        else:                 self._paint_idle(p, W, H, z._hovering)

        p.end()

    def _paint_idle(self, p, W, H, hover):
        cx, cy = W / 2, H / 2
        col = qcol(C.PRI_DIM if not hover else C.PRI)
        p.setPen(QPen(col, 2)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(cx, cy - 14), QPointF(cx, cy + 4))
        p.drawLine(QPointF(cx - 8, cy - 6), QPointF(cx, cy - 14))
        p.drawLine(QPointF(cx + 8, cy - 6), QPointF(cx, cy - 14))
        p.drawLine(QPointF(cx - 14, cy + 4), QPointF(cx + 14, cy + 4))
        p.setFont(QFont("Courier New", 8))
        p.setPen(QPen(qcol(C.PRI_DIM if not hover else C.TEXT), 1))
        p.drawText(QRectF(0, cy + 8, W, 16), Qt.AlignmentFlag.AlignCenter,
                   "Drop file here  or  Click to Browse")
        p.setFont(QFont("Courier New", 7))
        p.setPen(QPen(qcol("#1a4a5a"), 1))
        p.drawText(QRectF(0, cy + 24, W, 14), Qt.AlignmentFlag.AlignCenter,
                   "Images · Video · Audio · PDF · Docs · Code · Data")

    def _paint_drag_over(self, p, W, H):
        cx, cy = W / 2, H / 2
        p.setFont(QFont("Courier New", 20))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(QRectF(0, cy - 24, W, 32), Qt.AlignmentFlag.AlignCenter, "⬇")
        p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(QRectF(0, cy + 12, W, 16), Qt.AlignmentFlag.AlignCenter, "Release to load")

    def _paint_file(self, p, W, H):
        path = Path(self._z._current_file)
        cat  = _file_category(path)
        icon, icon_col = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        size_str = _fmt_size(path.stat().st_size)
        ext_str  = path.suffix.upper().lstrip(".") or "FILE"

        block_x, block_w = 10, 60
        p.setFont(QFont("Segoe UI Emoji", 22) if _OS == "Windows" else QFont("Arial", 22))
        p.setPen(QPen(qcol(icon_col), 1))
        p.drawText(QRectF(block_x, 0, block_w, H), Qt.AlignmentFlag.AlignCenter, icon)

        tx = block_x + block_w + 6
        tw = W - tx - 38

        p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.WHITE), 1))
        name = path.name if len(path.name) <= 34 else path.name[:31] + "..."
        p.drawText(QRectF(tx, H * 0.18, tw, 16),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)

        p.setFont(QFont("Courier New", 7))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(tx, H * 0.18 + 18, tw, 14),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   f"{ext_str}  ·  {size_str}")

        p.setFont(QFont("Courier New", 6))
        p.setPen(QPen(qcol("#1e5c6a"), 1))
        par = str(path.parent)
        if len(par) > 42: par = "…" + par[-41:]
        p.drawText(QRectF(tx, H * 0.18 + 34, tw, 12),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, par)

        p.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.RED, 180), 1))
        p.drawText(QRectF(W - 34, 0, 28, H), Qt.AlignmentFlag.AlignCenter, "✕")

    def mousePressEvent(self, e):
        z = self._z
        if z._current_file and e.pos().x() > self.width() - 34:
            z.clear_file()
        else:
            z.mousePressEvent(e)


class _CameraPreview(QWidget):
    """Floating overlay that briefly shows what the camera captured."""

    _W, _H = 244, 188

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            _CameraPreview {{
                background: rgba(0, 6, 10, 242);
                border: 1px solid {C.PRI};
                border-radius: 6px;
            }}
        """)
        self.setFixedWidth(self._W)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 5, 6, 6)
        lay.setSpacing(4)

        hdr = QHBoxLayout()
        title = QLabel("◈  VISUAL INPUT")
        title.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        hdr.addWidget(title)
        hdr.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(16, 16)
        close_btn.setFont(QFont("Courier New", 8))
        close_btn.setStyleSheet(
            f"color: {C.TEXT_DIM}; background: transparent; border: none;"
        )
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.hide)
        hdr.addWidget(close_btn)
        lay.addLayout(hdr)

        self._img_lbl = QLabel()
        self._img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_lbl.setStyleSheet("background: transparent;")
        lay.addWidget(self._img_lbl)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

        self.hide()

    def show_frame(self, img_bytes: bytes) -> None:
        px = QPixmap()
        px.loadFromData(img_bytes)
        if not px.isNull():
            max_w = self._W - 12
            scaled = px.scaled(
                max_w, 160,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._img_lbl.setPixmap(scaled)
            self._img_lbl.setFixedSize(scaled.width(), scaled.height())
            self.adjustSize()
        self.show()
        self.raise_()
        self._timer.start(6_000)   # auto-dismiss after 6 s


class SetupOverlay(QWidget):
    done = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            SetupOverlay {{
                background: rgba(0, 6, 10, 245);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)

        detected = {"darwin": "mac", "windows": "windows"}.get(
            _OS.lower(), "linux"
        )
        self._sel_os = detected

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 22, 30, 22)
        layout.setSpacing(8)

        def _lbl(txt, font_size=9, bold=False, color=C.PRI,
                 align=Qt.AlignmentFlag.AlignCenter):
            w = QLabel(txt)
            w.setAlignment(align)
            w.setFont(QFont("Courier New", font_size,
                            QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            return w

        layout.addWidget(_lbl("◈  INITIALISATION REQUIRED", 13, True))
        layout.addWidget(_lbl("Configure J.A.R.V.I.S. before first boot.", 9, color=C.PRI_DIM))
        layout.addSpacing(6)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER};"); layout.addWidget(sep)
        layout.addSpacing(4)

        layout.addWidget(_lbl("GEMINI API KEY", 8, color=C.TEXT_DIM,
                               align=Qt.AlignmentFlag.AlignLeft))
        self._key_input = QLineEdit()
        self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_input.setPlaceholderText("AIza…")
        self._key_input.setFont(QFont("Courier New", 10))
        self._key_input.setFixedHeight(32)
        self._key_input.setStyleSheet(f"""
            QLineEdit {{
                background: #000d12; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 3px; padding: 4px 8px;
            }}
            QLineEdit:focus {{ border: 1px solid {C.PRI}; }}
        """)
        layout.addWidget(self._key_input)
        layout.addSpacing(12)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color: {C.BORDER};"); layout.addWidget(sep2)
        layout.addSpacing(4)

        layout.addWidget(_lbl("OPERATING SYSTEM", 8, color=C.TEXT_DIM,
                               align=Qt.AlignmentFlag.AlignLeft))
        det_name = {"windows": "Windows", "mac": "macOS", "linux": "Linux"}[detected]
        layout.addWidget(_lbl(f"Auto-detected: {det_name}", 8, color=C.ACC2,
                               align=Qt.AlignmentFlag.AlignLeft))

        os_row = QHBoxLayout(); os_row.setSpacing(6)
        self._os_btns: dict[str, QPushButton] = {}
        for key, label in [("windows","⊞  Windows"),("mac","  macOS"),("linux","🐧  Linux")]:
            btn = QPushButton(label)
            btn.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
            btn.setFixedHeight(32)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, k=key: self._sel(k))
            os_row.addWidget(btn)
            self._os_btns[key] = btn
        layout.addLayout(os_row)
        self._sel(detected)
        layout.addSpacing(12)

        init_btn = QPushButton("▸  INITIALISE SYSTEMS")
        init_btn.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        init_btn.setFixedHeight(36)
        init_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        init_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 3px;
            }}
            QPushButton:hover {{
                background: {C.PRI_GHO}; border: 1px solid {C.PRI};
            }}
        """)
        init_btn.clicked.connect(self._submit)
        layout.addWidget(init_btn)

    def _sel(self, key: str):
        self._sel_os = key
        pal = {"windows":(C.PRI,"#001a22"),"mac":(C.ACC2,"#1a1400"),"linux":(C.GREEN,"#001a0d")}
        for k, btn in self._os_btns.items():
            if k == key:
                fg, bg = pal[k]
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {fg}; color: {bg};
                        border: none; border-radius: 3px; font-weight: bold;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: #000d12; color: {C.TEXT_DIM};
                        border: 1px solid {C.BORDER}; border-radius: 3px;
                    }}
                    QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}
                """)

    def _submit(self):
        key = self._key_input.text().strip()
        if not key:
            self._key_input.setStyleSheet(
                self._key_input.styleSheet() +
                f" QLineEdit {{ border: 1px solid {C.RED}; }}"
            )
            return
        self.done.emit(key, self._sel_os)


class HueWheel(QWidget):
    """
    Circular colour picker. The user drags the handle (small white circle)
    around the wheel to choose from ALL hues. The filled circle in the centre
    is a live preview of the selected colour.
    """

    hue_picked    = pyqtSignal(str)   # while dragging (live)
    hue_committed = pyqtSignal(str)   # when the handle is released

    _RING = 16   # ring thickness (px)

    def __init__(self, initial_hex: str = DEFAULT_UI_COLOR, parent=None):
        super().__init__(parent)
        self.setFixedSize(148, 148)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hue  = 0.53
        self._drag = False
        self.set_color(initial_hex)

    # ── API ──────────────────────────────────────────────────────────────────
    def color(self) -> str:
        return QColor.fromHsvF(self._hue, 1.0, 1.0).name()

    def set_color(self, hex_str: str):
        c = QColor((hex_str or "").strip())
        if c.isValid() and c.hsvHueF() >= 0:
            self._hue = c.hsvHueF()
            self.update()

    # ── geometry helpers ─────────────────────────────────────────────────────
    def _ring_rect(self) -> QRectF:
        m = self._RING / 2 + 3
        return QRectF(self.rect()).adjusted(m, m, -m, -m)

    def _hue_from_pos(self, pos: QPointF) -> float:
        c  = QRectF(self.rect()).center()
        dx = pos.x() - c.x()
        dy = c.y() - pos.y()          # screen y goes down — flip to math axis
        ang = math.atan2(dy, dx)      # [-π, π], counter-clockwise
        return (ang / (2 * math.pi)) % 1.0

    # ── drawing ──────────────────────────────────────────────────────────────
    def paintEvent(self, _):
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect   = self._ring_rect()
        center = rect.center()

        grad = QConicalGradient(center, 0)
        for i in range(0, 361, 20):
            grad.setColorAt(i / 360.0, QColor.fromHsvF((i % 360) / 360.0, 1.0, 1.0))
        p.setPen(QPen(QBrush(grad), self._RING))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(rect)

        # centre preview circle
        preview = QColor.fromHsvF(self._hue, 1.0, 1.0)
        inner   = rect.adjusted(30, 30, -30, -30)
        p.setPen(QPen(qcol(C.BORDER_B), 1))
        p.setBrush(QBrush(preview))
        p.drawEllipse(inner)

        # draggable handle
        r   = rect.width() / 2
        ang = self._hue * 2 * math.pi
        hx  = center.x() + r * math.cos(ang)
        hy  = center.y() - r * math.sin(ang)
        p.setPen(QPen(QColor("#00060a"), 2))
        p.setBrush(QBrush(QColor("#ffffff")))
        p.drawEllipse(QPointF(hx, hy), 7.5, 7.5)
        p.end()

    # ── fare ─────────────────────────────────────────────────────────────────
    def mousePressEvent(self, e):
        self._drag = True
        self._hue  = self._hue_from_pos(e.position())
        self.update()
        self.hue_picked.emit(self.color())

    def mouseMoveEvent(self, e):
        if self._drag:
            self._hue = self._hue_from_pos(e.position())
            self.update()
            self.hue_picked.emit(self.color())

    def mouseReleaseEvent(self, e):
        if self._drag:
            self._drag = False
            self.hue_committed.emit(self.color())


class CustomizeOverlay(QWidget):
    """Floating overlay — change assistant name, user name, UI colour and voice."""

    saved = pyqtSignal(str, str, str, str)   # assistant_name, user_name, ui_color, voice
    _OW, _OH = 400, 588

    def __init__(self, assistant_name=DEFAULT_ASSISTANT_NAME, user_name="",
                 ui_color=DEFAULT_UI_COLOR, voice="", parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            CustomizeOverlay {{
                background: rgba(0, 6, 10, 245);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 18, 24, 18)
        lay.setSpacing(8)

        def _lbl(txt, fs=9, bold=False, color=C.PRI, align=Qt.AlignmentFlag.AlignCenter):
            w = QLabel(txt); w.setAlignment(align)
            w.setFont(QFont("Courier New", fs,
                            QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            return w

        _fs = (f"QLineEdit {{ background: #000d12; color: {C.TEXT}; "
               f"border: 1px solid {C.BORDER}; border-radius: 3px; padding: 4px 8px; }}"
               f"QLineEdit:focus {{ border: 1px solid {C.PRI}; }}")

        lay.addWidget(_lbl("⚙  CUSTOMISE ASSISTANT", 12, True))
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        lay.addWidget(sep)

        lay.addWidget(_lbl("ASSISTANT NAME", 8, color=C.TEXT_DIM,
                            align=Qt.AlignmentFlag.AlignLeft))
        self._name_input = QLineEdit(assistant_name)
        self._name_input.setFont(QFont("Courier New", 10))
        self._name_input.setFixedHeight(32)
        self._name_input.setStyleSheet(_fs)
        lay.addWidget(self._name_input)

        lay.addSpacing(4)
        lay.addWidget(_lbl("YOUR NAME  (leave blank for default sir / efendim)", 8,
                            color=C.TEXT_DIM, align=Qt.AlignmentFlag.AlignLeft))
        self._user_input = QLineEdit(user_name)
        self._user_input.setPlaceholderText("e.g.  Tony   (leave blank for auto)")
        self._user_input.setFont(QFont("Courier New", 10))
        self._user_input.setFixedHeight(32)
        self._user_input.setStyleSheet(_fs)
        lay.addWidget(self._user_input)

        # ── Assistant voice — Gemini prebuilt voices ─────────────────────────
        # Names are language-neutral proper nouns, so the row reads the same in
        # every locale. Selecting one and applying rebuilds the Live session.
        from memory.config_manager import AVAILABLE_VOICES, DEFAULT_VOICE
        lay.addSpacing(4)
        lay.addWidget(_lbl("ASSISTANT VOICE", 8, color=C.TEXT_DIM,
                            align=Qt.AlignmentFlag.AlignLeft))
        self._sel_voice   = (voice or DEFAULT_VOICE)
        if self._sel_voice not in AVAILABLE_VOICES:
            self._sel_voice = DEFAULT_VOICE
        self._voice_btns: dict[str, QPushButton] = {}
        voice_row = QHBoxLayout(); voice_row.setSpacing(4)
        for _v in AVAILABLE_VOICES:
            b = QPushButton(_v)
            b.setCheckable(True)
            b.setFixedHeight(28)
            b.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, name=_v: self._on_voice_pick(name))
            self._voice_btns[_v] = b
            voice_row.addWidget(b)
        lay.addLayout(voice_row)
        self._refresh_voice_btns()

        # ── UI colour — colour wheel ─────────────────────────────────────────
        lay.addSpacing(4)
        clr_hdr = QHBoxLayout()
        clr_hdr.addWidget(_lbl("UI COLOUR  —  drag the handle", 8,
                               color=C.TEXT_DIM, align=Qt.AlignmentFlag.AlignLeft))
        clr_hdr.addStretch()
        df_btn = QPushButton("DEFAULT")
        df_btn.setFixedSize(64, 20)
        df_btn.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        df_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        df_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        df_btn.clicked.connect(lambda: self._set_color(DEFAULT_UI_COLOR))
        clr_hdr.addWidget(df_btn)
        lay.addLayout(clr_hdr)

        self._initial_color = (ui_color or DEFAULT_UI_COLOR).strip().lower()
        self._sel_color     = self._initial_color
        self.on_preview     = None   # callable(hex) — live preview; MainWindow wires it

        self._wheel = HueWheel(self._sel_color)
        wheel_row = QHBoxLayout()
        wheel_row.addStretch(); wheel_row.addWidget(self._wheel); wheel_row.addStretch()
        lay.addLayout(wheel_row)
        self._wheel.hue_picked.connect(self._on_wheel_pick)
        self._wheel.hue_committed.connect(self._on_wheel_commit)

        self._hex_input = QLineEdit(self._sel_color)
        self._hex_input.setPlaceholderText("#00d4ff   (custom hex colour)")
        self._hex_input.setFont(QFont("Courier New", 10))
        self._hex_input.setFixedHeight(28)
        self._hex_input.setStyleSheet(_fs)
        self._hex_input.textEdited.connect(self._on_hex_edited)
        lay.addWidget(self._hex_input)

        lay.addSpacing(6)
        btn_row = QHBoxLayout(); btn_row.setSpacing(8)

        save_btn = QPushButton("▸  APPLY CHANGES")
        save_btn.setFixedHeight(34)
        save_btn.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 3px;
            }}
            QPushButton:hover {{ background: {C.PRI_GHO}; border: 1px solid {C.PRI}; }}
        """)
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)

        cancel_btn = QPushButton("CANCEL")
        cancel_btn.setFixedHeight(34)
        cancel_btn.setFont(QFont("Courier New", 9))
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        cancel_btn.clicked.connect(self._cancel)
        btn_row.addWidget(cancel_btn)
        lay.addLayout(btn_row)

    # ── voice selection ──────────────────────────────────────────────────────
    def _on_voice_pick(self, name: str):
        self._sel_voice = name
        self._refresh_voice_btns()

    def _refresh_voice_btns(self):
        """Highlight the selected voice pill; dim the rest."""
        for name, b in self._voice_btns.items():
            on = (name == self._sel_voice)
            b.setChecked(on)
            if on:
                b.setStyleSheet(f"""
                    QPushButton {{ background: {C.PRI_GHO}; color: {C.PRI};
                        border: 1px solid {C.PRI}; border-radius: 3px; }}
                """)
            else:
                b.setStyleSheet(f"""
                    QPushButton {{ background: transparent; color: {C.TEXT_MED};
                        border: 1px solid {C.BORDER}; border-radius: 3px; }}
                    QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
                """)

    # ── colour flow ──────────────────────────────────────────────────────────
    def _set_color(self, hx: str, update_wheel: bool = True, preview: bool = True):
        """Updates the selected colour; hex box + wheel stay in sync, theme is live-previewed."""
        self._sel_color = hx.strip().lower()
        self._hex_input.blockSignals(True)
        self._hex_input.setText(self._sel_color)
        self._hex_input.blockSignals(False)
        if update_wheel:
            self._wheel.set_color(self._sel_color)
        if preview and self.on_preview:
            self.on_preview(self._sel_color)

    def _on_wheel_pick(self, hx: str):
        # While dragging: update the hex box, don't apply the theme yet
        self._sel_color = hx
        self._hex_input.blockSignals(True)
        self._hex_input.setText(hx)
        self._hex_input.blockSignals(False)

    def _on_wheel_commit(self, hx: str):
        # Handle released → live-preview the whole interface
        self._set_color(hx, update_wheel=False)

    def _on_hex_edited(self, text: str):
        t = text.strip().lower()
        if t.startswith("#") and len(t) == 7:
            try:
                int(t[1:], 16)
            except ValueError:
                return
            self._set_color(t, update_wheel=True, preview=True)

    def _cancel(self):
        # If a preview was applied, revert to the colour from launch
        if self.on_preview and self._sel_color != self._initial_color:
            self.on_preview(self._initial_color)
        self.hide()

    def _save(self):
        name = self._name_input.text().strip() or DEFAULT_ASSISTANT_NAME
        user = self._user_input.text().strip()
        self.saved.emit(name, user, self._sel_color or DEFAULT_UI_COLOR, self._sel_voice)
        self.hide()


class PluginManagerOverlay(QWidget):
    """Floating overlay — lists discovered plugins with per-plugin ON/OFF toggles."""

    _OW = 420

    def __init__(self, plugins: list[dict], parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            PluginManagerOverlay {{
                background: rgba(0, 6, 10, 245);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)
        self.setFixedWidth(self._OW)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(6)

        hdr = QLabel("🧩  PLUGIN MANAGER")
        hdr.setFont(QFont("Courier New", 12, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        lay.addWidget(hdr)
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        lay.addWidget(sep)

        if not plugins:
            empty = QLabel("No plugins found in /plugins.")
            empty.setFont(QFont("Courier New", 8))
            empty.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
            lay.addWidget(empty)

        for p in plugins:
            lay.addLayout(self._build_row(p))

        lay.addSpacing(4)
        close_btn = QPushButton("CLOSE")
        close_btn.setFixedHeight(30)
        close_btn.setFont(QFont("Courier New", 9))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        close_btn.clicked.connect(self.hide)
        lay.addWidget(close_btn)
        self.adjustSize()

    def _build_row(self, p: dict) -> QHBoxLayout:
        row = QHBoxLayout(); row.setSpacing(6)

        label_text = p["name"] if p["valid"] else f"{p['name']}  (⚠ {p['file']})"
        lbl = QLabel(label_text)
        lbl.setFont(QFont("Courier New", 8))
        lbl.setStyleSheet(f"color: {C.TEXT if p['valid'] else C.TEXT_DIM}; background: transparent;")
        lbl.setToolTip(p["description"] if p["valid"] else p["error"])
        lbl.setWordWrap(False)
        row.addWidget(lbl, stretch=1)

        btn = QPushButton()
        btn.setFixedSize(72, 24)
        btn.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        if not p["valid"]:
            btn.setText("BROKEN")
            btn.setEnabled(False)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {C.TEXT_DIM};
                    border: 1px solid {C.BORDER}; border-radius: 3px;
                }}
            """)
        else:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._style_toggle(btn, p["enabled"])
            btn.clicked.connect(lambda _, name=p["name"], b=btn: self._toggle(name, b))
        row.addWidget(btn)
        return row

    def _style_toggle(self, btn: QPushButton, enabled: bool):
        if enabled:
            btn.setText("ON")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: #001a08; color: {C.GREEN};
                    border: 1px solid {C.GREEN_D}; border-radius: 3px;
                }}
                QPushButton:hover {{ background: #002010; }}
            """)
        else:
            btn.setText("OFF")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {C.TEXT_DIM};
                    border: 1px solid {C.BORDER}; border-radius: 3px;
                }}
                QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
            """)

    def _toggle(self, name: str, btn: QPushButton):
        from memory.config_manager import get_plugin_enabled, save_plugin_enabled
        new_val = not get_plugin_enabled(name)
        save_plugin_enabled(name, new_val)
        self._style_toggle(btn, new_val)


class _HudOverlay(QWidget):
    """Base for the floating panels placed by hand over the HUD.

    They are children of the central widget but sit in no layout, so Qt never
    invalidates the region they occupy when they hide or shrink: the HUD keeps
    painting around them and their last frame stays on screen as a ghost. Any
    overlay positioned with _centre_overlay needs this."""

    def hideEvent(self, e):
        p = self.parentWidget()
        if p is not None:
            # Repaint exactly what we were covering, before we stop covering it.
            p.update(self.geometry())
        super().hideEvent(e)

    def closeEvent(self, e):
        p = self.parentWidget()
        if p is not None:
            p.update(self.geometry())
        super().closeEvent(e)


# Every setting that used to need editing config/api_keys.json by hand.
# (key, label, kind, default, help) — kind: secret, text, int, float, bool, list, color
ADVANCED_SETTINGS = [
    ("KEYS & SERVICES", [
        ("gemini_api_key", "Gemini API key", "secret", "", "From aistudio.google.com (an adult's verified account)."),
        ("tinyfish_api_key", "TinyFish API key", "secret", "", "Free web search — agent.tinyfish.ai/api-keys. Empty = Gemini search."),
        ("telegram_token", "Telegram bot token", "secret", "", "From @BotFather."),
        ("nasa_api_key", "NASA API key", "secret", "", "Optional, for the space photo (DEMO_KEY works a few times a day)."),
        ("ha_url", "Home Assistant URL", "text", "", "e.g. http://192.168.1.20:8123"),
        ("ha_token", "Home Assistant token", "secret", "", ""),
        ("github_token", "GitHub token", "secret", "", "Only for updates from a PRIVATE repo (read-only token)."),
    ]),
    ("YOU", [
        ("home_city", "Your city", "text", "", "Weather, rain alerts, air quality, ISS passes."),
        ("camera_index", "Webcam number", "int", 0, "0 = first webcam, 1 = second…"),
        ("adb_path", "ADB path", "text", "", "Only if adb isn't found automatically (phone features)."),
    ]),
    ("SPEED & COST", [
        ("lean_mode", "Lean mode", "bool", True, "Cheaper, faster turns. Keep ON."),
        ("core_tools", "Always-loaded extra tools", "list", [], "Comma-separated tool names you use a lot."),
        ("gpu_orb", "GPU orb", "bool", True, "Draw the orb on the graphics card. Turn OFF if it looks wrong."),
        ("orb_particles", "GPU orb particles", "int", 16000, "3000–60000. Lower if the PC struggles."),
    ]),
    ("CLAPS", [
        ("clap_threshold", "Clap sensitivity", "float", 0.30, "0.2 = more sensitive … 0.5 = less."),
        ("clap_mute", "One clap mutes", "bool", True, "Two claps always unmute."),
        ("whistle_shutdown", "Whistle shuts down", "bool", True, "Whistle ~1 second → JARVIS closes, no confirmation."),
        ("whistle_seconds", "Whistle length (s)", "float", 0.7, "How long you must whistle. Higher = fewer accidents."),
        ("confirm_close", "Ask before 'close JARVIS'", "bool", True, "OFF = closing by voice skips the confirm box too."),
    ]),
    ("IMAGES", [
        ("image_provider", "Image maker", "text", "auto", "auto (Google, free fallback) · gemini · pollinations · openai"),
        ("image_size", "Image resolution", "text", "2K", "1K, 2K or 4K (4K only on some models)."),
        ("image_model", "Force image model", "text", "", "Leave empty — JARVIS finds the best one on your key."),
        ("image_status_seconds", "Image progress updates (s)", "int", 12, "Spoken update every N seconds while an image is made. 0 = off."),
        ("openai_api_key", "OpenAI API key", "secret", "", "Only if Image maker = openai."),
    ]),
    ("GESTURES", [
        ("gesture_sensitivity", "Gesture sensitivity", "float", 0.4,
         "Lowest sign confidence that counts. 0.3 = picks signs up more easily … 0.6 = stricter, fewer mistakes."),
        ("gesture_hold", "Gesture hold time (s)", "float", 0.3, "How long to hold a hologram sign before it acts (0.2–1)."),
    ]),
    ("HEADS-UPS", [
        ("meeting_heads_up", "Heads-up before meetings", "bool", True, "JARVIS speaks first before each Google Calendar event."),
        ("meeting_heads_up_minutes", "Minutes before a meeting", "int", 10, "How early the meeting heads-up comes."),
        ("heads_up_max", "Most heads-ups a day", "int", 6, "Optional heads-ups (meetings, rain, disk…). Alarms & reminders don't count."),
        ("heads_up_quiet", "Quiet hours", "text", "22-7", "No optional heads-ups in these hours, e.g. 22-7. Empty = never quiet."),
    ]),
    ("LOOK", [
        ("intro_color", "Intro screen colour", "color", "#00d4ff", "e.g. #ff7a1a for orange."),
        ("hologram_color", "Default hologram colour", "color", "#00d4ff", "Used when you don't name a colour."),
    ]),
    ("SECURITY & UPDATES", [
        ("secure_keys", "Lock keys when closed", "bool", True, "Encrypts your keys whenever JARVIS isn't running."),
        ("update_repo", "Update from GitHub repo", "text", "", "owner/repo, e.g. ranjan/jarvis"),
        ("auto_update_check", "Check for updates daily", "bool", True, ""),
        ("git_auto_save", "Save code to GitHub daily", "bool", False, "Once a day, if something changed (needs setup_github.bat done once)."),
    ]),
]


def validate_setting(kind: str, raw: str, default):
    """Text from the form → the stored value. Raises ValueError with a friendly message."""
    import re as _re
    raw = (raw or "").strip()
    if kind == "bool":
        return raw.upper() in ("ON", "TRUE", "YES", "1")
    if kind == "int":
        if raw == "":
            return default
        return int(raw)
    if kind == "float":
        if raw == "":
            return default
        return float(raw)
    if kind == "list":
        return [x.strip() for x in raw.split(",") if x.strip()]
    if kind == "color":
        if raw and not _re.fullmatch(r"#[0-9a-fA-F]{6}", raw):
            try:                                     # a colour-wheel name is fine too
                from core import holo_shapes as HS
                if HS.color_name(raw):
                    return raw.lower()
            except Exception:
                pass
            raise ValueError("colours look like #ff7a1a or a colour-wheel name (teal, amber…)")
        return raw
    return raw


class AdvancedSettingsOverlay(_HudOverlay):
    """⚙ → ADVANCED SETTINGS: a form for every setting in config/api_keys.json,
    with checks, so nobody has to edit the JSON by hand (one missing comma used to
    break JARVIS)."""

    _OW = 540

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            AdvancedSettingsOverlay {{ background: rgba(0, 6, 10, 248); border: 1px solid {C.BORDER_B}; border-radius: 6px; }}
            QLabel {{ background: transparent; }}
            QLineEdit, QComboBox {{ background: {C.PANEL}; color: {C.TEXT}; border: 1px solid {C.BORDER};
                                     border-radius: 3px; padding: 3px 6px; font-family: 'Courier New'; font-size: 9pt; }}
        """)
        self.setFixedWidth(self._OW)
        cfg = _read_full_config()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(6)
        hdr = QLabel("⚙  ADVANCED SETTINGS")
        hdr.setFont(QFont("Courier New", 12, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.PRI};")
        lay.addWidget(hdr)
        body = QWidget(); body.setStyleSheet("background: transparent;")
        form = QVBoxLayout(body); form.setSpacing(4); form.setContentsMargins(0, 0, 6, 0)
        self._fields = {}
        for section, items in ADVANCED_SETTINGS:
            sl = QLabel(section)
            sl.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
            sl.setStyleSheet(f"color: {C.PRI_DIM}; margin-top: 8px;")
            form.addWidget(sl)
            for key, label, kind, default, help_ in items:
                row = QHBoxLayout()
                lab = QLabel(label); lab.setFixedWidth(190)
                lab.setFont(QFont("Courier New", 8)); lab.setStyleSheet(f"color: {C.TEXT};")
                if help_:
                    lab.setToolTip(help_)
                cur = cfg.get(key, default)
                if kind == "bool":
                    w = QComboBox(); w.addItems(["ON", "OFF"]); w.setCurrentText("ON" if cur else "OFF")
                else:
                    w = QLineEdit(", ".join(cur) if kind == "list" and isinstance(cur, list) else str(cur if cur is not None else ""))
                    if kind == "secret":
                        w.setEchoMode(QLineEdit.EchoMode.Password)
                    if help_:
                        w.setPlaceholderText(help_[:60])
                w.setToolTip(help_)
                row.addWidget(lab); row.addWidget(w, 1)
                form.addLayout(row)
                self._fields[key] = (kind, default, w)
        scroll = QScrollArea(); scroll.setWidget(body); scroll.setWidgetResizable(True)
        scroll.setFixedHeight(430)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        lay.addWidget(scroll)
        self._msg = QLabel("Hover a name for help. Most changes apply after restarting JARVIS.")
        self._msg.setWordWrap(True); self._msg.setFont(QFont("Courier New", 8))
        self._msg.setStyleSheet(f"color: {C.TEXT_DIM};")
        lay.addWidget(self._msg)
        btns = QHBoxLayout()
        for text, fn in (("SAVE", self._save), ("CLOSE", self.close)):
            b = QPushButton(text); b.setFixedHeight(28); b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
            b.setStyleSheet(f"QPushButton {{ background: transparent; color: {C.PRI}; border: 1px solid {C.PRI_DIM}; "
                            f"border-radius: 3px; }} QPushButton:hover {{ background: {C.PRI_GHO}; }}")
            b.clicked.connect(fn); btns.addWidget(b)
        lay.addLayout(btns)

    def _save(self):
        new, bad = {}, []
        for key, (kind, default, w) in self._fields.items():
            raw = w.currentText() if kind == "bool" else w.text()
            try:
                new[key] = validate_setting(kind, raw, default)
            except ValueError as e:
                bad.append(f"{key}: {e if 'colour' in str(e) else 'not a valid number'}")
        if bad:
            self._msg.setText("Not saved — fix: " + "; ".join(bad))
            self._msg.setStyleSheet(f"color: {C.RED if hasattr(C, 'RED') else '#ff4d4d'};")
            return
        try:
            data = json.loads(API_FILE.read_text(encoding="utf-8")) if API_FILE.exists() else {}
            if not isinstance(data, dict):
                data = {}
        except Exception:
            data = {}
        for k, v in new.items():
            if v in ("", None, []) and k not in data:
                continue                       # don't fill the file with empty optional keys
            data[k] = v
        os.makedirs(CONFIG_DIR, exist_ok=True)
        tmp = API_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=4), encoding="utf-8")
        os.replace(tmp, API_FILE)              # atomic: never a half-written settings file
        self._msg.setText("Saved ✓ — restart JARVIS for speed / orb / clap changes.")
        self._msg.setStyleSheet(f"color: {C.PRI};")


class ConfirmBanner(_HudOverlay):
    """The gate in front of an action that cannot be taken back.

    The old confirmation was a tool parameter the model filled in itself, which
    means it confirmed its own shutdown requests. This is the interface asking,
    and the answer travels from a human finger to core/confirm.py without the
    model in the loop. Nothing blocks while it is up: the assistant keeps
    talking, so this costs no latency — unlike the old gate, which spent two
    tool round trips on every power command."""

    answered = pyqtSignal(bool)
    _OW = 430

    def __init__(self, title: str, detail: str, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            ConfirmBanner {{
                background: rgba(14, 3, 0, 250);
                border: 1px solid {C.ACC};
                border-radius: 6px;
            }}
        """)
        self.setFixedWidth(self._OW)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(8)

        hdr = QLabel("⚠  CONFIRM")
        hdr.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.ACC}; background: transparent;")
        lay.addWidget(hdr)

        ttl = QLabel(title)
        ttl.setWordWrap(True)
        ttl.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        ttl.setStyleSheet(f"color: {C.TEXT}; background: transparent;")
        lay.addWidget(ttl)

        if detail:
            dtl = QLabel(detail)
            dtl.setWordWrap(True)
            dtl.setFont(QFont("Courier New", 8))
            dtl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
            lay.addWidget(dtl)

        row = QHBoxLayout(); row.setSpacing(8)

        yes = QPushButton("▸  CONFIRM")
        yes.setFixedHeight(32)
        yes.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        yes.setCursor(Qt.CursorShape.PointingHandCursor)
        yes.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.ACC};
                border: 1px solid {C.ACC}; border-radius: 3px; }}
            QPushButton:hover {{ background: rgba(255,107,0,40); }}
        """)
        yes.clicked.connect(lambda: self.answered.emit(True))
        row.addWidget(yes)

        no = QPushButton("CANCEL")
        no.setFixedHeight(32)
        no.setFont(QFont("Courier New", 9))
        no.setCursor(Qt.CursorShape.PointingHandCursor)
        no.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px; }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        no.clicked.connect(lambda: self.answered.emit(False))
        row.addWidget(no)
        lay.addLayout(row)

        # Default focus on CANCEL: if someone hits Enter without reading, the
        # safe answer wins.
        no.setDefault(True)
        no.setFocus()


class AudioDeviceOverlay(_HudOverlay):
    """Choose which microphone JARVIS listens to and which speakers it uses.

    Both audio streams used to open with no `device=` at all, so they always
    took the OS default — which on Windows moves by itself the moment a headset
    is plugged in. 'JARVIS can't hear me' is usually 'JARVIS is listening to the
    webcam'."""

    picked = pyqtSignal()      # emitted after Apply, when something changed
    _OW = 460

    def __init__(self, parent=None):
        super().__init__(parent)
        from core.audio_devices import list_devices, DEFAULT_LABEL
        from memory.config_manager import get_input_device, get_output_device

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            AudioDeviceOverlay {{
                background: rgba(0, 6, 10, 245);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)
        self.setFixedWidth(self._OW)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(6)

        hdr = QLabel("🎧  AUDIO DEVICES")
        hdr.setFont(QFont("Courier New", 12, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        lay.addWidget(hdr)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        lay.addWidget(sep)

        _combo_css = (
            f"QComboBox {{ background: #000d12; color: {C.TEXT}; "
            f"border: 1px solid {C.BORDER}; border-radius: 3px; padding: 4px 8px; }}"
            f"QComboBox:hover {{ border-color: {C.BORDER_B}; }}"
            f"QComboBox QAbstractItemView {{ background: #000d12; color: {C.TEXT}; "
            f"selection-background-color: {C.PRI_GHO}; border: 1px solid {C.BORDER}; }}"
        )

        def _row(label: str, kind: str, current: str) -> QComboBox:
            cap = QLabel(label)
            cap.setFont(QFont("Courier New", 8))
            cap.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
            lay.addWidget(cap)

            box = QComboBox()
            box.setFont(QFont("Courier New", 9))
            box.setFixedHeight(30)
            box.setStyleSheet(_combo_css)
            # The list is served from a cache warmed on a background thread at
            # startup, so opening this panel never blocks the Qt thread on the
            # host audio API.
            box.addItem(DEFAULT_LABEL, "")
            for name in list_devices(kind):
                box.addItem(name, name)
            idx = box.findData(current) if current else 0
            box.setCurrentIndex(idx if idx >= 0 else 0)
            if current and idx < 0:
                # Saved device is not plugged in right now. Show it rather than
                # silently resetting the user's choice to default.
                box.addItem(f"{current}  (not connected)", current)
                box.setCurrentIndex(box.count() - 1)
            lay.addWidget(box)
            return box

        self._in_box  = _row("MICROPHONE — what JARVIS hears you with",
                             "input", get_input_device())
        lay.addSpacing(4)
        self._out_box = _row("SPEAKERS — what JARVIS talks through",
                             "output", get_output_device())

        note = QLabel("Applying reconnects the session. Your conversation is kept.")
        note.setWordWrap(True)
        note.setFont(QFont("Courier New", 7))
        note.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        lay.addSpacing(6)
        lay.addWidget(note)

        row = QHBoxLayout(); row.setSpacing(8)
        ok = QPushButton("▸  APPLY")
        ok.setFixedHeight(32)
        ok.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        ok.setCursor(Qt.CursorShape.PointingHandCursor)
        ok.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 3px; }}
            QPushButton:hover {{ background: {C.PRI_GHO}; border-color: {C.PRI}; }}
        """)
        ok.clicked.connect(self._apply)
        row.addWidget(ok)

        cancel = QPushButton("CLOSE")
        cancel.setFixedHeight(32)
        cancel.setFont(QFont("Courier New", 9))
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px; }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        cancel.clicked.connect(self.hide)
        row.addWidget(cancel)
        lay.addLayout(row)

    def _apply(self):
        from memory.config_manager import (
            get_input_device, get_output_device,
            save_input_device, save_output_device,
        )
        new_in  = self._in_box.currentData()  or ""
        new_out = self._out_box.currentData() or ""
        changed = (new_in != get_input_device()) or (new_out != get_output_device())
        save_input_device(new_in)
        save_output_device(new_out)
        self.hide()
        # Only rebuild the session if something actually moved — a no-op Apply
        # should not cost a reconnect.
        if changed:
            self.picked.emit()


class MemoryOverlay(_HudOverlay):
    """Everything JARVIS has stored about you, and when it learned it.

    Memory used to be a 2200-character store that deleted its oldest entries
    when full and mentioned it only on stdout. The cap is gone; this panel is
    the other half of that change — a memory you cannot inspect is a memory you
    cannot trust, and 'delete' has to be something the person can do."""

    _OW = 520

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            MemoryOverlay {{
                background: rgba(0, 6, 10, 246);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)
        self.setFixedWidth(self._OW)

        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(20, 16, 20, 16)
        self._lay.setSpacing(5)
        self._rebuild()

    def _clear_layout(self):
        """Take every item out of the layout and detach it from the widget tree
        in this call.

        deleteLater() on its own is not enough: it queues destruction for the
        next event-loop pass, and until then the old rows are still children of
        this widget and still paint — which is what drew half of the previous
        panel over the new one. setParent(None) removes them from the tree now;
        deleteLater() then frees them safely."""
        while self._lay.count():
            item = self._lay.takeAt(0)
            w = item.widget()
            if w is not None:
                # hide() stops it painting in this frame; deleteLater() frees it
                # safely afterwards. setParent(None) would also stop the paint,
                # but it turns the widget into a top-level window for the moment
                # between the two calls, which is not something to leave lying
                # around inside a click handler.
                w.hide()
                w.deleteLater()
                continue
            sub = item.layout()
            if sub is not None:
                while sub.count():
                    si = sub.takeAt(0)
                    sw = si.widget()
                    if sw is not None:
                        sw.hide()
                        sw.deleteLater()
                sub.deleteLater()

    def _settle(self, before):
        """Size the panel to its content, re-centre it, and repaint what the old
        size covered.

        The re-size has to happen here rather than at the end of _rebuild
        because Qt has not polished the freshly-created children at that point,
        so the size hint it would read is the empty-layout one. Measured: a
        first adjustSize() returned 32 px for a panel whose content needed 155,
        and a second call — after the same widgets had been through the event
        loop — returned 155. So this runs twice: once now, once on the next
        turn, from _rebuild.

        The re-centre and the repaint are needed because the overlay is placed
        by hand and is in no layout: shrinking it leaves it off-centre and
        leaves its former pixels on screen, since nothing tells the parent that
        region changed. The repaint has to cover the union of the old and new
        rectangles."""
        self._lay.invalidate()
        self._lay.activate()
        self.updateGeometry()
        self.adjustSize()

        p = self.parentWidget()
        if p is None:
            self.update()
            return
        self.move(max(0, (p.width()  - self.width())  // 2),
                  max(0, (p.height() - self.height()) // 2))
        p.update(before.united(self.geometry()))
        self.update()

    def _rebuild(self):
        before = self.geometry()
        self._clear_layout()

        from memory.memory_manager import all_entries_for_ui

        hdr = QLabel(f"🧠  WHAT {_assistant_display_name()} REMEMBERS")
        hdr.setFont(QFont("Courier New", 12, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        self._lay.addWidget(hdr)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        self._lay.addWidget(sep)

        rows = all_entries_for_ui()

        cap = QLabel(f"{len(rows)} stored facts — newest first. "
                     f"Nothing here is sent anywhere; it lives in "
                     f"memory/long_term.json on this machine.")
        cap.setWordWrap(True)
        cap.setFont(QFont("Courier New", 7))
        cap.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        self._lay.addWidget(cap)

        if not rows:
            empty = QLabel("Nothing stored yet.")
            empty.setFont(QFont("Courier New", 9))
            empty.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
            self._lay.addWidget(empty)
        else:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFixedHeight(min(420, 34 * len(rows) + 10))
            scroll.setStyleSheet(
                f"QScrollArea {{ border: 1px solid {C.BORDER}; border-radius: 3px; "
                f"background: transparent; }}"
            )
            inner = QWidget()
            ilay  = QVBoxLayout(inner)
            ilay.setContentsMargins(6, 6, 6, 6)
            ilay.setSpacing(3)

            for r in rows:
                line = QHBoxLayout(); line.setSpacing(6)
                txt = QLabel(f"<b>{r['key'].replace('_', ' ')}</b> "
                             f"<span style='color:{C.TEXT_MED}'>— {r['value']}</span>")
                txt.setWordWrap(True)
                txt.setFont(QFont("Courier New", 8))
                txt.setStyleSheet(f"color: {C.TEXT}; background: transparent;")
                line.addWidget(txt, 1)

                meta = QLabel(f"{r['category'][:4]} · {r['updated'] or '—'}")
                meta.setFont(QFont("Courier New", 7))
                meta.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
                line.addWidget(meta)

                rm = QPushButton("✕")
                rm.setFixedSize(20, 20)
                rm.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
                rm.setCursor(Qt.CursorShape.PointingHandCursor)
                rm.setToolTip("Forget this")
                rm.setStyleSheet(f"""
                    QPushButton {{ background: transparent; color: {C.TEXT_DIM};
                        border: 1px solid {C.BORDER}; border-radius: 3px; }}
                    QPushButton:hover {{ color: {C.RED}; border-color: {C.RED}; }}
                """)
                rm.clicked.connect(
                    lambda _=False, c=r["category"], k=r["key"]: self._forget(c, k))
                line.addWidget(rm)

                holder = QWidget()
                holder.setLayout(line)
                ilay.addWidget(holder)

            ilay.addStretch()
            scroll.setWidget(inner)
            self._lay.addWidget(scroll)

        close = QPushButton("CLOSE")
        close.setFixedHeight(30)
        close.setFont(QFont("Courier New", 9))
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px; }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        close.clicked.connect(self.hide)
        self._lay.addWidget(close)

        self._settle(before)
        # …and again once Qt has polished the new children, because the size
        # hint is not final until then. Harmless when the first pass already
        # got it right: _settle is idempotent.
        QTimer.singleShot(0, lambda g=before: self._settle(g))

    def _forget(self, category: str, key: str):
        from memory.memory_manager import forget
        forget(key, category)
        # Rebuild on the NEXT event-loop turn, not inside this click handler.
        # The rebuild destroys the very ✕ button that emitted this signal, and
        # Qt is entitled to touch the sender after a slot returns; tearing it
        # down mid-emission is how a widget ends up half-alive on screen.
        QTimer.singleShot(0, self._rebuild)


class ClipboardPanel(QWidget):
    """Floating panel shown when text is copied — offers quick Jarvis actions."""

    action_requested = pyqtSignal(str)
    _W, _H = 326, 112

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            ClipboardPanel {{
                background: rgba(0, 8, 14, 248);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)
        self.setFixedWidth(self._W)
        self._clip_text = ""

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 7)
        lay.setSpacing(4)

        hdr = QHBoxLayout(); hdr.setSpacing(4)
        icon_lbl = QLabel("◈  CLIPBOARD DETECTED")
        icon_lbl.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        icon_lbl.setStyleSheet(f"color: {C.ACC2}; background: transparent;")
        hdr.addWidget(icon_lbl); hdr.addStretch()
        x_btn = QPushButton("✕")
        x_btn.setFixedSize(16, 16)
        x_btn.setFont(QFont("Courier New", 8))
        x_btn.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none;")
        x_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        x_btn.clicked.connect(self.hide)
        hdr.addWidget(x_btn)
        lay.addLayout(hdr)

        self._preview = QLabel()
        self._preview.setFont(QFont("Courier New", 8))
        self._preview.setStyleSheet(f"""
            color: {C.TEXT}; background: {C.PANEL2};
            border: 1px solid {C.BORDER}; border-radius: 3px; padding: 4px 6px;
        """)
        self._preview.setWordWrap(False)
        self._preview.setFixedHeight(28)
        lay.addWidget(self._preview)

        btn_row = QHBoxLayout(); btn_row.setSpacing(4)
        _bs = (f"QPushButton {{ background: {C.PANEL2}; color: {C.TEXT_MED}; "
               f"border: 1px solid {C.BORDER}; border-radius: 2px; }}"
               f"QPushButton:hover {{ color: {C.PRI}; border-color: {C.BORDER_B}; }}")
        for label, cmd_fmt in [
            ("TRANSLATE", "Translate this text to English: {text}"),
            ("SUMMARISE", "Summarise this: {text}"),
            ("EXPLAIN",   "Explain this: {text}"),
            ("FIX",       "Fix grammar and spelling: {text}"),
        ]:
            b = QPushButton(label)
            b.setFixedHeight(22)
            b.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(_bs)
            b.clicked.connect(lambda _, c=cmd_fmt: self._trigger(c))
            btn_row.addWidget(b)
        lay.addLayout(btn_row)

        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self.hide)
        self.hide()

    def _trigger(self, cmd_fmt: str):
        if self._clip_text:
            self.action_requested.emit(cmd_fmt.format(text=self._clip_text[:800]))
        self.hide()

    def show_clipboard(self, text: str):
        self._clip_text = text
        preview = text[:58].replace('\n', ' ')
        if len(text) > 58:
            preview += "…"
        self._preview.setText(f'"{preview}"')
        self.show(); self.raise_()
        self._dismiss_timer.start(8000)


class PluginSettingsOverlay(QWidget):
    """Floating overlay — renders per-plugin settings forms.

    Fully generic: it iterates the settings schemas a plugin declared via its
    PLUGIN_SETTINGS constant (delivered by PluginRegistry.settings_schemas) and
    builds a form for each. It knows NOTHING about any specific plugin, so the
    core stays clean and plugins remain pure drop-in — install a plugin that
    declares fields (e.g. the 3D-printer suite) and its section appears here;
    install none and this panel simply says there's nothing to configure.
    """

    _test_done = pyqtSignal(str, bool, str)   # namespace, ok, message
    _OW = 460

    def __init__(self, sections: list[dict], parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            PluginSettingsOverlay {{
                background: rgba(0, 6, 10, 245);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)
        self._sections = sections or []
        self._widgets: dict[tuple, object] = {}    # (namespace, key) -> input widget
        self._types:   dict[tuple, str]    = {}     # (namespace, key) -> field type
        self._status_labels: dict[str, QLabel] = {} # namespace -> status QLabel
        self._test_done.connect(self._on_test_done)

        self._fs = (f"QLineEdit {{ background: #000d12; color: {C.TEXT}; "
                    f"border: 1px solid {C.BORDER}; border-radius: 3px; padding: 4px 8px; }}"
                    f"QLineEdit:focus {{ border: 1px solid {C.PRI}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 16, 22, 16)
        root.setSpacing(8)

        root.addWidget(self._lbl("⚙  PLUGIN SETTINGS", 12, True))
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        root.addWidget(sep)

        if not self._sections:
            root.addWidget(self._lbl(
                "No configurable plugins are installed.\nDrop a plugin that needs "
                "settings (like the 3D-printer suite) into the plugins folder and "
                "it will show up here.", 9, color=C.TEXT_DIM))
        else:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setStyleSheet("QScrollArea { background: transparent; }")
            inner = QWidget()
            inner.setStyleSheet("background: transparent;")
            form = QVBoxLayout(inner)
            form.setContentsMargins(0, 0, 6, 0)
            form.setSpacing(6)
            for sec in self._sections:
                self._build_section(form, sec)
            form.addStretch(1)
            scroll.setWidget(inner)
            root.addWidget(scroll, 1)

        # ── bottom buttons ───────────────────────────────────────────────────
        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        if self._sections:
            save_btn = QPushButton("▸  SAVE")
            save_btn.setFixedHeight(34)
            save_btn.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
            save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            save_btn.setStyleSheet(f"""
                QPushButton {{ background: transparent; color: {C.PRI};
                    border: 1px solid {C.PRI_DIM}; border-radius: 3px; }}
                QPushButton:hover {{ background: {C.PRI_GHO}; border: 1px solid {C.PRI}; }}
            """)
            save_btn.clicked.connect(self._save_all)
            btn_row.addWidget(save_btn)

        close_btn = QPushButton("CLOSE")
        close_btn.setFixedHeight(34)
        close_btn.setFont(QFont("Courier New", 9))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px; }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        close_btn.clicked.connect(self.hide)
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)

    # ── helpers ───────────────────────────────────────────────────────────────
    def _lbl(self, txt, fs=9, bold=False, color=C.PRI,
             align=Qt.AlignmentFlag.AlignLeft):
        w = QLabel(txt); w.setAlignment(align); w.setWordWrap(True)
        w.setFont(QFont("Courier New", fs,
                        QFont.Weight.Bold if bold else QFont.Weight.Normal))
        w.setStyleSheet(f"color: {color}; background: transparent;")
        return w

    def _build_section(self, form: QVBoxLayout, sec: dict):
        ns     = sec.get("namespace") or sec.get("plugin") or "plugin"
        title  = sec.get("title") or ns
        fields = sec.get("fields") or []
        values = sec.get("values") or {}

        form.addSpacing(4)
        form.addWidget(self._lbl(title, 10, True, C.PRI))

        for field in fields:
            if not isinstance(field, dict) or not field.get("key"):
                continue
            key   = field["key"]
            ftype = (field.get("type") or "text").lower()
            label = field.get("label") or key
            default = field.get("default")
            stored  = values.get(key, default)

            form.addWidget(self._lbl(label.upper(), 8, color=C.TEXT_DIM))

            if ftype == "choice":
                w = QComboBox()
                w.addItems([str(o) for o in field.get("options", [])])
                w.setFont(QFont("Courier New", 9))
                w.setFixedHeight(30)
                w.setStyleSheet(
                    f"QComboBox {{ background: #000d12; color: {C.TEXT}; "
                    f"border: 1px solid {C.BORDER}; border-radius: 3px; padding: 2px 8px; }}"
                    f"QComboBox QAbstractItemView {{ background: #000d12; color: {C.TEXT}; "
                    f"selection-background-color: {C.PRI_GHO}; }}")
                if stored is not None:
                    w.setCurrentText(str(stored))
            elif ftype == "toggle":
                w = QPushButton()
                w.setCheckable(True)
                w.setChecked(bool(stored))
                w.setFixedHeight(28)
                w.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
                w.setCursor(Qt.CursorShape.PointingHandCursor)
                self._style_toggle(w)
                w.toggled.connect(lambda _=False, b=w: self._style_toggle(b))
            else:  # text / password
                w = QLineEdit("" if stored is None else str(stored))
                w.setFont(QFont("Courier New", 10))
                w.setFixedHeight(30)
                w.setStyleSheet(self._fs)
                if field.get("placeholder"):
                    w.setPlaceholderText(str(field["placeholder"]))
                if ftype == "password":
                    w.setEchoMode(QLineEdit.EchoMode.Password)

            self._widgets[(ns, key)] = w
            self._types[(ns, key)]   = ftype
            form.addWidget(w)

        # optional test/connect action button + status line
        action = sec.get("action")
        if isinstance(action, dict) and callable(action.get("run")):
            form.addSpacing(2)
            ab = QPushButton(str(action.get("label") or "TEST"))
            ab.setFixedHeight(30)
            ab.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
            ab.setCursor(Qt.CursorShape.PointingHandCursor)
            ab.setStyleSheet(f"""
                QPushButton {{ background: #00091a; color: {C.PRI};
                    border: 1px solid {C.PRI_DIM}; border-radius: 3px; }}
                QPushButton:hover {{ background: {C.PRI_GHO}; border-color: {C.PRI}; }}
            """)
            ab.clicked.connect(lambda _=False, n=ns: self._run_action(n))
            form.addWidget(ab)

        status = self._lbl("", 8, color=C.TEXT_DIM)
        self._status_labels[ns] = status
        form.addWidget(status)

        line = QFrame(); line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color: {C.BORDER}; margin: 4px 0;")
        form.addWidget(line)

    def _style_toggle(self, btn: QPushButton):
        on = btn.isChecked()
        btn.setText("ON" if on else "OFF")
        if on:
            btn.setStyleSheet(f"QPushButton {{ background: {C.PRI_GHO}; color: {C.PRI}; "
                              f"border: 1px solid {C.PRI}; border-radius: 3px; }}")
        else:
            btn.setStyleSheet(f"QPushButton {{ background: transparent; color: {C.TEXT_MED}; "
                              f"border: 1px solid {C.BORDER}; border-radius: 3px; }}")

    # ── data ──────────────────────────────────────────────────────────────────
    def _gather(self, ns: str) -> dict:
        out = {}
        for (n, key), w in self._widgets.items():
            if n != ns:
                continue
            t = self._types.get((n, key), "text")
            if t == "choice":
                out[key] = w.currentText()
            elif t == "toggle":
                out[key] = w.isChecked()
            else:
                out[key] = w.text().strip()
        return out

    def _save_ns(self, ns: str):
        from memory.config_manager import save_plugin_config
        save_plugin_config(ns, self._gather(ns))

    def _save_all(self):
        for sec in self._sections:
            ns = sec.get("namespace") or sec.get("plugin")
            if ns:
                self._save_ns(ns)
                lbl = self._status_labels.get(ns)
                if lbl:
                    lbl.setText("Saved ✓")
                    lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")

    def _run_action(self, ns: str):
        sec = next((s for s in self._sections
                    if (s.get("namespace") or s.get("plugin")) == ns), None)
        if not sec:
            return
        run_fn = (sec.get("action") or {}).get("run")
        if not callable(run_fn):
            return
        self._save_ns(ns)                 # persist what the user typed before testing
        values = self._gather(ns)
        lbl = self._status_labels.get(ns)
        if lbl:
            lbl.setText("Testing…")
            lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")

        def worker():
            try:
                res = run_fn(values)
                if isinstance(res, tuple) and len(res) == 2:
                    ok, msg = bool(res[0]), str(res[1])
                else:
                    ok, msg = bool(res), str(res)
            except Exception as e:
                ok, msg = False, str(e)
            self._test_done.emit(ns, ok, msg)

        threading.Thread(target=worker, daemon=True).start()

    def _on_test_done(self, ns: str, ok: bool, msg: str):
        lbl = self._status_labels.get(ns)
        if not lbl:
            return
        lbl.setText(msg)
        color = C.PRI if ok else "#ff6b6b"
        lbl.setStyleSheet(f"color: {color}; background: transparent;")


class RemoteKeyOverlay(QWidget):
    """Floating overlay — QR code for instant phone pairing + manual key fallback."""

    closed = pyqtSignal()

    _OW, _OH = 400, 465

    def __init__(self, url: str, key: str, auto_login_url: str = "",
                 manual_url: str = "", expiry_secs: int = 600, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            RemoteKeyOverlay {{
                background: rgba(0, 4, 12, 0.95);
                border: 1px solid {C.BORDER_B};
                border-radius: 14px;
            }}
        """)
        self._expiry          = time.time() + expiry_secs
        self._on_new_key      = None
        self._auto_login_url  = auto_login_url
        self._manual_url      = manual_url or url

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 16, 24, 16)
        lay.setSpacing(5)

        def _lbl(txt, fs=9, bold=False, color=C.PRI,
                 align=Qt.AlignmentFlag.AlignCenter):
            w = QLabel(txt)
            w.setAlignment(align)
            w.setFont(QFont("Courier New", fs,
                            QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            w.setWordWrap(True)
            return w

        lay.addWidget(_lbl("◈  REMOTE ACCESS", 12, True))
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 1px 0;")
        lay.addWidget(sep)

        # ── QR code ───────────────────────────────────────────────────────────
        self._qr_label = QLabel()
        self._qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._qr_label.setFixedSize(176, 176)
        self._qr_label.setStyleSheet(
            "background: white; border-radius: 10px; padding: 4px;"
        )
        qr_row = QHBoxLayout()
        qr_row.addStretch()
        qr_row.addWidget(self._qr_label)
        qr_row.addStretch()
        lay.addLayout(qr_row)

        self._update_qr(auto_login_url)

        lay.addWidget(_lbl("Scan with phone camera to connect instantly", 8, color=C.TEXT_DIM))

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color: {C.BORDER}; margin: 1px 0;")
        lay.addWidget(sep2)

        lay.addWidget(_lbl("Or enter manually:", 7, color=C.TEXT_DIM,
                           align=Qt.AlignmentFlag.AlignLeft))

        self._url_lbl = QLabel(self._manual_url)
        self._url_lbl.setFont(QFont("Courier New", 8))
        self._url_lbl.setStyleSheet(f"color: {C.PRI_DIM}; background: transparent;")
        self._url_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._url_lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self._url_lbl)

        self._key_lbl = QLabel(key)
        self._key_lbl.setFont(QFont("Courier New", 28, QFont.Weight.Bold))
        self._key_lbl.setStyleSheet(f"""
            color: {C.ACC};
            background: {C.PANEL2};
            border: 1px solid {C.BORDER_B};
            border-radius: 8px;
            padding: 6px 4px;
            letter-spacing: 10px;
        """)
        self._key_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._key_lbl)

        self._timer_lbl = QLabel()
        self._timer_lbl.setFont(QFont("Courier New", 8))
        self._timer_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        self._timer_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._timer_lbl)

        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        new_btn = QPushButton("NEW KEY")
        new_btn.setFixedHeight(32)
        new_btn.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.PANEL}; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 5px;
            }}
            QPushButton:hover {{ background: {C.PRI_GHO}; border: 1px solid {C.PRI}; }}
        """)
        new_btn.clicked.connect(self._refresh_key)
        btn_row.addWidget(new_btn)

        close_btn = QPushButton("DISMISS")
        close_btn.setFixedHeight(32)
        close_btn.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 5px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}
        """)
        close_btn.clicked.connect(self._do_close)
        btn_row.addWidget(close_btn)
        lay.addLayout(btn_row)

        self._ctimer = QTimer(self)
        self._ctimer.timeout.connect(self._tick)
        self._ctimer.start(1000)
        self._tick()

    def set_new_key_callback(self, fn) -> None:
        self._on_new_key = fn

    def _update_qr(self, url: str) -> None:
        if not url:
            self._qr_label.setText("—")
            return
        try:
            import qrcode as _qrmod
            from io import BytesIO
            qr = _qrmod.QRCode(
                box_size=5, border=2,
                error_correction=_qrmod.constants.ERROR_CORRECT_M,
            )
            qr.add_data(url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buf = BytesIO()
            img.save(buf, format="PNG")
            px = QPixmap()
            px.loadFromData(buf.getvalue())
            self._qr_label.setPixmap(
                px.scaled(170, 170,
                          Qt.AspectRatioMode.KeepAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
            )
        except ImportError:
            self._qr_label.setText("pip install\nqrcode[pil]")
            self._qr_label.setFont(QFont("Courier New", 8))
            self._qr_label.setStyleSheet(
                "color: #888; background: white; border-radius: 10px; padding: 4px;"
            )
        except Exception:
            self._qr_label.setText(url[:28])
            self._qr_label.setFont(QFont("Courier New", 7))
            self._qr_label.setStyleSheet(
                f"color: {C.PRI}; background: white; border-radius: 10px; padding: 4px;"
            )

    def _tick(self):
        remaining = max(0, int(self._expiry - time.time()))
        m, s = divmod(remaining, 60)
        self._timer_lbl.setText(f"Key expires in  {m:02d}:{s:02d}")
        if remaining == 0:
            self._do_close()

    def mark_connected(self) -> None:
        """Call from any thread when a phone successfully connects."""
        self._ctimer.stop()
        self._key_lbl.setText("CONNECTED")
        self._key_lbl.setStyleSheet(f"""
            color: {C.GREEN};
            background: rgba(34,197,94,0.08);
            border: 2px solid rgba(34,197,94,0.4);
            border-radius: 8px;
            padding: 6px 4px;
            letter-spacing: 4px;
        """)
        self._qr_label.setText("✓")
        self._qr_label.setFont(QFont("Courier New", 54, QFont.Weight.Bold))
        self._qr_label.setStyleSheet(
            "color: #00ff88; background: #001a0d; border-radius: 10px;"
        )
        self._timer_lbl.setText(f"Phone connected — {_assistant_display_name()} ready")
        self._timer_lbl.setStyleSheet(f"color: {C.GREEN}; background: transparent;")

    def _refresh_key(self):
        if self._on_new_key:
            result = self._on_new_key()
            if result:
                url    = result[0]
                key    = result[1]
                auto   = result[2] if len(result) >= 3 else ""
                manual = result[3] if len(result) >= 4 else url
                self._manual_url     = manual or url
                self._url_lbl.setText(self._manual_url)
                self._key_lbl.setText(key)
                self._auto_login_url = auto
                self._update_qr(auto or url)
                self._expiry = time.time() + 600
                self._key_lbl.setStyleSheet(f"""
                    color: {C.ACC};
                    background: {C.PANEL2};
                    border: 1px solid {C.BORDER_B};
                    border-radius: 8px;
                    padding: 6px 4px;
                    letter-spacing: 10px;
                """)
                self._timer_lbl.setStyleSheet(
                    f"color: {C.TEXT_MED}; background: transparent;"
                )
                self._ctimer.start(1000)
                self._tick()

    def _do_close(self):
        self._ctimer.stop()
        self.hide()
        self.closed.emit()


class MainWindow(QMainWindow):
    _log_sig        = pyqtSignal(str)
    _state_sig      = pyqtSignal(str)
    _content_sig    = pyqtSignal(str, str)   # (title, text) — thread-safe content display
    _reconfig_sig   = pyqtSignal()           # trigger setup overlay from any thread
    _camera_sig     = pyqtSignal(bytes)      # show camera frame preview (small overlay)
    _cam_stream_sig = pyqtSignal(bool)       # True=start live stream, False=stop
    _cam_frame_sig  = pyqtSignal(bytes)      # live camera frame → HUD area
    _clipboard_sig  = pyqtSignal(str)        # clipboard text changed (thread-safe)
    _confirm_sig    = pyqtSignal(str, str)   # (title, detail) — irreversible-action gate
    _confirm_hide_sig = pyqtSignal()
    _wake_dl_sig    = pyqtSignal(bool, str)  # wake-word install finished (ok, message)
    _mute_sig       = pyqtSignal(bool)       # thread-safe mute / unmute (voice, double clap)
    _holo_sig       = pyqtSignal(str)        # thread-safe: suit hologram commands
    _intro_sig      = pyqtSignal(object)     # thread-safe: show the start-up pop-up

    def __init__(self, face_path: str):
        super().__init__()
        self._face_path = face_path

        # Load customization from config
        _cfg = _read_full_config()
        self._assistant_name: str = (_cfg.get("assistant_name") or DEFAULT_ASSISTANT_NAME).strip()
        _display = self._assistant_name.upper()

        # Apply the saved UI colour BEFORE panels/stylesheets are built
        _ui_color = (_cfg.get("ui_color") or DEFAULT_UI_COLOR).strip()
        if _ui_color.lower() != _PALETTE_DEFAULTS["PRI"]:
            apply_ui_accent(_ui_color)

        self.setWindowTitle(f"{_display} — HUD")
        self.setMinimumSize(_MIN_W, _MIN_H)
        self.resize(_DEFAULT_W, _DEFAULT_H)

        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            (screen.width()  - _DEFAULT_W) // 2,
            (screen.height() - _DEFAULT_H) // 2,
        )

        self.on_text_command   = None
        self.on_remote_clicked = None   # callable: () -> (url, key) | None
        self.on_interrupt      = None   # callable: () -> None — stop JARVIS mid-speech
        self.on_voice_change   = None   # callable: () -> None — rebuild session with new voice
        self.on_audio_device_change = None  # callable: () -> None — reopen audio streams
        self._confirm_overlay  = None   # live ConfirmBanner, if one is on screen
        self.get_plugins       = None   # callable: () -> list[dict], set by JarvisLive
        self.get_plugin_settings = None # callable: () -> list[dict] settings schemas, set by JarvisLive
        self.on_wake_toggle    = None   # callable: (enable: bool) -> str, set by JarvisLive
        self.on_wake_manual    = None   # callable: () -> None — manual sleep/wake
        self.wake_get_state    = None   # callable: () -> dict {enabled, awake, ready}
        self._muted            = False
        self._current_file: str | None = None
        self._remote_overlay: RemoteKeyOverlay | None = None
        self._customize_overlay: CustomizeOverlay | None = None

        central = QWidget()
        central.setStyleSheet(f"background: {C.BG};")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self._left_panel = self._build_left_panel()
        body.addWidget(self._left_panel, stretch=0)

        # The orb now lives in its own black window (OrbWindow); self.hud points at
        # its canvas so every state / mute / audio update still reaches it.
        self.orb_window = OrbWindow(self, face_path, _display)
        self.hud = self.orb_window.canvas
        self._content_panel = self._build_content_panel()

        # Live camera container — replaces HUD when camera stream is active
        _cam_cont = QWidget()
        _cam_cont.setStyleSheet("background: #000308;")
        _cam_v = QVBoxLayout(_cam_cont)
        _cam_v.setContentsMargins(0, 0, 0, 0)
        _cam_v.setSpacing(0)
        _cam_hdr = QHBoxLayout()
        _cam_hdr.setContentsMargins(8, 5, 8, 5)
        _cam_title = QLabel("◈  CAMERA FEED")
        _cam_title.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        _cam_title.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        _cam_hdr.addWidget(_cam_title)
        _cam_hdr.addStretch()
        _cam_x = QPushButton("✕  CLOSE")
        _cam_x.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        _cam_x.setCursor(Qt.CursorShape.PointingHandCursor)
        _cam_x.setStyleSheet(f"""
            QPushButton {{
                color: {C.TEXT_DIM}; background: transparent;
                border: none; padding: 2px 6px;
            }}
            QPushButton:hover {{ color: {C.PRI}; }}
        """)
        _cam_x.clicked.connect(self.stop_camera_stream)
        _cam_hdr.addWidget(_cam_x)
        _cam_v.addLayout(_cam_hdr)
        self._cam_live_lbl = QLabel()
        self._cam_live_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cam_live_lbl.setStyleSheet("background: transparent;")
        self._cam_live_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        _cam_v.addWidget(self._cam_live_lbl, stretch=1)

        # Stack: 0 = animated HUD, 1 = live camera
        self._hud_cam_stack = QStackedWidget()
        self._hud_cam_stack.addWidget(self._build_hud_info())
        self._hud_cam_stack.addWidget(_cam_cont)

        self._center_split = QSplitter(Qt.Orientation.Vertical)
        self._center_split.setStyleSheet(f"""
            QSplitter::handle {{
                background: {C.BORDER};
                height: 4px;
            }}
            QSplitter::handle:hover {{
                background: {C.PRI_DIM};
            }}
        """)
        self._center_split.addWidget(self._hud_cam_stack)
        self._center_split.addWidget(self._content_panel)
        self._center_split.setStretchFactor(0, 3)
        self._center_split.setStretchFactor(1, 1)
        self._center_split.setCollapsible(0, False)
        body.addWidget(self._center_split, stretch=5)

        self._right_panel = self._build_right_panel()
        body.addWidget(self._right_panel, stretch=0)

        root.addLayout(body, stretch=1)
        root.addWidget(self._build_footer())

        # Quick-access drawer (floating overlay, built after central widget layout is done)
        self._quick_drawer = self._build_quick_drawer()
        self._update_autostart_btn(self._check_autostart())
        from memory.config_manager import get_brief_enabled as _gbe
        self._update_brief_btn(_gbe())

        self._clock_tmr = QTimer(self)
        self._clock_tmr.timeout.connect(self._tick_clock)
        self._clock_tmr.start(1000)
        self._tick_clock()

        # Metric update timer
        self._metric_tmr = QTimer(self)
        self._metric_tmr.timeout.connect(self._update_metrics)
        self._metric_tmr.start(2000)
        self._update_metrics()

        self._log_sig.connect(self._log.append_log)
        self._state_sig.connect(self._apply_state)
        self._content_sig.connect(self._show_content)
        self._reconfig_sig.connect(self._show_setup)
        self._camera_sig.connect(self._show_camera_frame)
        self._confirm_sig.connect(self._show_confirm_banner)
        self._confirm_hide_sig.connect(self._hide_confirm_banner)
        self._cam_stream_sig.connect(self._on_cam_stream)
        self._cam_frame_sig.connect(self._on_cam_frame)
        self._clipboard_sig.connect(self._show_clipboard_panel)
        self._wake_dl_sig.connect(self._on_wake_install_done)
        self._mute_sig.connect(self._set_muted)
        self._holo_sig.connect(self._holo_cmd)
        self._intro_sig.connect(self.show_intro_popup)
        self._cam_stop = threading.Event()

        # Camera preview overlay (child of central widget, positioned in resizeEvent)
        self._cam_preview = _CameraPreview(self.centralWidget())

        # Clipboard panel (child of central widget, bottom-center)
        self._clipboard_panel = ClipboardPanel(self.centralWidget())
        self._clipboard_panel.action_requested.connect(self._on_clipboard_action)
        QApplication.clipboard().dataChanged.connect(self._on_clipboard_changed)

        self._overlay: SetupOverlay | None = None
        self._ready = self._check_config()
        if not self._ready:
            self._show_setup()

        sc_mute = QShortcut(QKeySequence("F4"), self)
        sc_mute.activated.connect(self._toggle_mute)
        sc_full = QShortcut(QKeySequence("F11"), self)
        sc_full.activated.connect(self._toggle_fullscreen)
        sc_intr = QShortcut(QKeySequence("Escape"), self)
        sc_intr.activated.connect(self._do_interrupt)

    def _show_camera_frame(self, img_bytes: bytes):
        """Slot — display camera preview overlay (main thread)."""
        self._cam_preview.show_frame(img_bytes)
        cw = self.centralWidget()
        pw = _CameraPreview._W
        ph = self._cam_preview.height()
        self._cam_preview.setGeometry(
            cw.width() - _RIGHT_W - pw - 12,
            cw.height() - ph - 28,
            pw, ph,
        )

    # --- Live camera stream in HUD area ------------------------------------
    def _on_cam_stream(self, start: bool) -> None:
        if start:
            self._hud_cam_stack.setCurrentIndex(1)
        else:
            self._hud_cam_stack.setCurrentIndex(0)
            self._cam_live_lbl.clear()

    def _on_cam_frame(self, data: bytes) -> None:
        px = QPixmap()
        px.loadFromData(data)
        if not px.isNull():
            w, h = self._cam_live_lbl.width(), self._cam_live_lbl.height()
            if w > 1 and h > 1:
                self._cam_live_lbl.setPixmap(
                    px.scaled(w, h,
                              Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
                )

    def start_camera_stream(self) -> None:
        self._cam_stop.clear()
        self._cam_stream_sig.emit(True)
        t = threading.Thread(target=self._cam_loop, daemon=True, name="cam-stream")
        t.start()

    def _cam_loop(self) -> None:
        try:
            import cv2
            # Reuse camera index detected by screen_processor (cached in api_keys.json)
            cam_idx = 0
            try:
                import json as _j
                cfg = _j.loads((CONFIG_DIR / "api_keys.json").read_text())
                cam_idx = int(cfg.get("camera_index", 0))
            except Exception:
                pass
            try:
                backend = cv2.CAP_DSHOW if _OS == "Windows" else cv2.CAP_ANY
            except AttributeError:
                backend = 0
            cap = cv2.VideoCapture(cam_idx, backend)
            if not cap.isOpened():
                cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                return
            # warm-up frames
            for _ in range(5):
                cap.read()
            while not self._cam_stop.wait(0.033) and cap.isOpened():
                ret, frame = cap.read()
                if ret and frame is not None:
                    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 65])
                    self._cam_frame_sig.emit(buf.tobytes())
            cap.release()
        except Exception as e:
            print(f"[Camera] Stream error: {e}")
        finally:
            self._cam_stream_sig.emit(False)

    def stop_camera_stream(self) -> None:
        self._cam_stop.set()

    # ------------------------------------------------------------------
    # Icon generation — arc-reactor style, rendered with Pillow
    # ------------------------------------------------------------------
    @staticmethod
    def _build_jarvis_icon(out_path: Path) -> bool:
        """
        Render a JARVIS arc-reactor icon at 4× resolution and downsample
        for crisp results at all sizes. Saves a multi-res .ico to out_path.
        Returns True on success.
        """
        try:
            import math
            import PIL.Image
            import PIL.ImageDraw
            import PIL.ImageFilter
        except ImportError:
            return False

        CYAN   = (0, 212, 255)
        DIM    = (0, 100, 140)
        DARK   = (0, 6, 10)
        GLOW   = (0, 160, 200)
        WHITE  = (220, 240, 255)

        def _render(sz: int) -> PIL.Image.Image:
            S  = sz * 4                     # draw at 4× then downscale
            img = PIL.Image.new("RGBA", (S, S), (0, 0, 0, 0))
            d   = PIL.ImageDraw.Draw(img)
            cx = cy = S // 2

            # ── filled background circle ──────────────────────────────────
            R = S // 2 - 2
            d.ellipse([cx-R, cy-R, cx+R, cy+R], fill=(*DARK, 255))

            # ── outer border ring ─────────────────────────────────────────
            lw = max(2, S // 40)
            d.ellipse([cx-R, cy-R, cx+R, cy+R],
                      outline=(*CYAN, 220), width=lw)

            # ── mid decorative ring ───────────────────────────────────────
            R2 = int(R * 0.72)
            d.ellipse([cx-R2, cy-R2, cx+R2, cy+R2],
                      outline=(*DIM, 180), width=max(1, lw // 2))

            # ── 6 radial spokes (hex bolt) ────────────────────────────────
            R_inner = int(R * 0.30)
            R_outer = int(R * 0.62)
            spoke_w = max(1, S // 80)
            for i in range(6):
                angle = math.radians(i * 60 - 30)
                x1 = cx + int(R_inner * math.cos(angle))
                y1 = cy + int(R_inner * math.sin(angle))
                x2 = cx + int(R_outer * math.cos(angle))
                y2 = cy + int(R_outer * math.sin(angle))
                d.line([x1, y1, x2, y2], fill=(*GLOW, 200), width=spoke_w)

            # ── 6 tick marks on outer ring ────────────────────────────────
            for i in range(6):
                angle = math.radians(i * 60)
                for dr in range(lw * 2):
                    rx = (R - lw - dr)
                    d.point(
                        [cx + int(rx * math.cos(angle)),
                         cy + int(rx * math.sin(angle))],
                        fill=(*WHITE, 220),
                    )

            # ── inner glowing ring ────────────────────────────────────────
            Ri = int(R * 0.26)
            d.ellipse([cx-Ri, cy-Ri, cx+Ri, cy+Ri],
                      outline=(*CYAN, 255), width=max(2, lw))

            # ── bright glow soft blur applied before core ─────────────────
            # (draw a slightly larger cyan circle on a separate layer)
            glow_layer = PIL.Image.new("RGBA", (S, S), (0, 0, 0, 0))
            gd = PIL.ImageDraw.Draw(glow_layer)
            Rc = int(R * 0.13)
            gd.ellipse([cx-Rc*2, cy-Rc*2, cx+Rc*2, cy+Rc*2],
                       fill=(*CYAN, 110))
            glow_layer = glow_layer.filter(PIL.ImageFilter.GaussianBlur(S // 14))
            img = PIL.Image.alpha_composite(img, glow_layer)
            d   = PIL.ImageDraw.Draw(img)

            # ── core dot ──────────────────────────────────────────────────
            d.ellipse([cx-Rc, cy-Rc, cx+Rc, cy+Rc], fill=(*WHITE, 255))

            # ── downscale to target size ──────────────────────────────────
            return img.resize((sz, sz), PIL.Image.LANCZOS)

        try:
            sizes  = [256, 128, 64, 48, 32, 16]
            frames = [_render(s) for s in sizes]
            frames[0].save(
                out_path,
                format="ICO",
                append_images=frames[1:],
                sizes=[(s, s) for s in sizes],
            )
            return True
        except Exception as e:
            print(f"[Shortcut] ⚠️  Icon generation failed: {e}")
            return False

    @staticmethod
    def _create_lnk_windows(lnk: str, target: str, args: str,
                             work_dir: str, icon_loc: str) -> None:
        """
        Create a Windows .lnk shortcut WITHOUT launching PowerShell or cmd.
        Tries win32com (pywin32) first; falls back to wscript.exe + VBScript.
        wscript.exe is a GUI-mode host — it never opens a console window.
        """
        # ── Option 1: pywin32 (pure Python COM, zero subprocess) ──────────
        try:
            from win32com.client import Dispatch   # type: ignore
            sh = Dispatch("WScript.Shell")
            sc = sh.CreateShortCut(lnk)
            sc.TargetPath       = target
            sc.Arguments        = f'"{args}"'
            sc.WorkingDirectory = work_dir
            sc.Description      = "J.A.R.V.I.S AI Assistant"
            sc.IconLocation     = icon_loc
            sc.save()
            return
        except ImportError:
            pass

        # ── Option 2: wscript.exe + VBScript (always available on Windows,
        #    GUI-mode executable — never opens a console window) ────────────
        vbs = "\n".join([
            'Set ws = CreateObject("WScript.Shell")',
            f'Set sc = ws.CreateShortcut("{lnk}")',
            f'sc.TargetPath = "{target}"',
            f'sc.Arguments = Chr(34) & "{args}" & Chr(34)',
            f'sc.WorkingDirectory = "{work_dir}"',
            'sc.Description = "J.A.R.V.I.S AI Assistant"',
            f'sc.IconLocation = "{icon_loc}"',
            'sc.Save',
        ])
        import tempfile
        fd, tmp = tempfile.mkstemp(suffix=".vbs")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(vbs)
            proc = subprocess.Popen(
                ["wscript.exe", "/nologo", tmp],
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
            )
            proc.wait(timeout=10)
        finally:
            try:
                os.unlink(tmp)
            except Exception:
                pass

    @staticmethod
    def _get_desktop_dir() -> Path:
        """
        Resolve the user's REAL desktop directory instead of assuming
        ~/Desktop, which breaks when:
          • OneDrive "Known Folder Move" relocates the desktop
            (C:/Users/x/OneDrive/Desktop) — very common on Win 10/11;
          • the XDG desktop is localized on Linux (~/Masaüstü,
            ~/Schreibtisch, ~/Bureau, …).
        Falls back to ~/Desktop only as a last resort.
        """
        home = Path.home()
        _os = platform.system()

        if _os == "Windows":
            # ── 1) SHGetKnownFolderPath(FOLDERID_Desktop) — the canonical
            #       answer; follows OneDrive redirection. No dependencies. ──
            try:
                import ctypes
                from ctypes import wintypes

                class _GUID(ctypes.Structure):
                    _fields_ = [("Data1", wintypes.DWORD),
                                ("Data2", wintypes.WORD),
                                ("Data3", wintypes.WORD),
                                ("Data4", ctypes.c_ubyte * 8)]

                # FOLDERID_Desktop {B4BFCC3A-DB2C-424C-B029-7FE99A87C641}
                fid = _GUID(0xB4BFCC3A, 0xDB2C, 0x424C,
                            (ctypes.c_ubyte * 8)(0xB0, 0x29, 0x7F, 0xE9,
                                                 0x9A, 0x87, 0xC6, 0x41))
                buf = ctypes.c_wchar_p()
                if ctypes.windll.shell32.SHGetKnownFolderPath(
                        ctypes.byref(fid), 0, None, ctypes.byref(buf)) == 0:
                    p = Path(buf.value)
                    ctypes.windll.ole32.CoTaskMemFree(buf)
                    if p.is_dir():
                        return p
            except Exception:
                pass

            # ── 2) Registry: User Shell Folders (may contain %VARS%) ──────
            try:
                import winreg
                with winreg.OpenKey(
                        winreg.HKEY_CURRENT_USER,
                        r"Software\Microsoft\Windows\CurrentVersion"
                        r"\Explorer\User Shell Folders") as key:
                    val, _t = winreg.QueryValueEx(key, "Desktop")
                p = Path(os.path.expandvars(val))
                if p.is_dir():
                    return p
            except Exception:
                pass

        elif _os == "Linux":
            # ── xdg-user-dir honours localized names (~/Masaüstü, …) ──────
            try:
                out = subprocess.run(["xdg-user-dir", "DESKTOP"],
                                     capture_output=True, text=True, timeout=5)
                p = Path(out.stdout.strip())
                if out.stdout.strip() and p != home and p.is_dir():
                    return p
            except Exception:
                pass
            try:
                cfg = home / ".config" / "user-dirs.dirs"
                for line in cfg.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith("XDG_DESKTOP_DIR"):
                        val = line.split("=", 1)[1].strip().strip('"')
                        p = Path(val.replace("$HOME", str(home)))
                        if p != home and p.is_dir():
                            return p
            except Exception:
                pass

        # macOS: ~/Desktop is always the real path (localization is
        # display-only). Everything else lands here as a last resort.
        return home / "Desktop"

    def _create_desktop_shortcut(self):
        """
        Create a desktop shortcut on Windows / macOS / Linux.
        Never opens a terminal, console, or PowerShell window on any platform.
        """
        import stat as _stat
        script  = Path(__file__).resolve().parent / "main.py"
        python  = Path(sys.executable)
        desktop = self._get_desktop_dir()

        # Arc-reactor icon (.ico — also exported as .png for Linux/macOS)
        ico_path = Path(__file__).resolve().parent / "config" / "jarvis.ico"
        if not ico_path.exists():
            self._build_jarvis_icon(ico_path)

        try:
            _os = platform.system()

            # ── Windows ───────────────────────────────────────────────────────
            if _os == "Windows":
                pythonw  = python.parent / "pythonw.exe"
                target   = str(pythonw if pythonw.exists() else python)
                lnk      = str(desktop / "J.A.R.V.I.S.lnk")
                icon_loc = str(ico_path) if ico_path.exists() else f"{target},0"
                self._create_lnk_windows(lnk, target, str(script),
                                         str(script.parent), icon_loc)

            # ── macOS — proper .app bundle (no Terminal window) ───────────────
            elif _os == "Darwin":
                app     = desktop / "J.A.R.V.I.S.app"
                mac_dir = app / "Contents" / "MacOS"
                res_dir = app / "Contents" / "Resources"
                mac_dir.mkdir(parents=True, exist_ok=True)
                res_dir.mkdir(exist_ok=True)

                # Launcher executable (bash — runs as background process,
                # macOS does NOT open Terminal for executables inside .app bundles)
                launcher = mac_dir / "JARVIS"
                launcher.write_text(
                    "#!/usr/bin/env bash\n"
                    f'cd "{script.parent}"\n'
                    f'exec "{python}" "{script}"\n'
                )
                launcher.chmod(launcher.stat().st_mode
                               | _stat.S_IEXEC | _stat.S_IXGRP | _stat.S_IXOTH)

                # Minimal Info.plist (required for .app recognition)
                (app / "Contents" / "Info.plist").write_text(
                    '<?xml version="1.0" encoding="UTF-8"?>\n'
                    '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                    '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                    '<plist version="1.0"><dict>\n'
                    '  <key>CFBundleExecutable</key><string>JARVIS</string>\n'
                    '  <key>CFBundleIdentifier</key>'
                    '<string>com.jarvis.assistant</string>\n'
                    '  <key>CFBundleName</key><string>J.A.R.V.I.S</string>\n'
                    '  <key>CFBundlePackageType</key><string>APPL</string>\n'
                    '  <key>CFBundleVersion</key><string>1.0</string>\n'
                    '</dict></plist>\n'
                )

                # Optional: copy icon as .icns (skip silently if Pillow is missing)
                try:
                    import PIL.Image
                    icns = res_dir / "AppIcon.icns"
                    PIL.Image.open(ico_path).save(icns, format="ICNS")
                    # Inject icon reference into plist
                    plist = app / "Contents" / "Info.plist"
                    txt = plist.read_text()
                    plist.write_text(
                        txt.replace(
                            '</dict></plist>',
                            '  <key>CFBundleIconFile</key>'
                            '<string>AppIcon</string>\n</dict></plist>\n',
                        )
                    )
                except Exception:
                    pass  # icon is optional

            # ── Linux — .desktop file (Terminal=false, no console) ────────────
            else:
                # Export .ico → .png for better desktop integration
                png_path = ico_path.with_suffix(".png")
                if not png_path.exists() and ico_path.exists():
                    try:
                        import PIL.Image
                        PIL.Image.open(ico_path).resize(
                            (256, 256), PIL.Image.LANCZOS
                        ).save(png_path, format="PNG")
                    except Exception:
                        png_path = ico_path  # fallback to .ico

                icon_line = f"Icon={png_path}\n" if png_path.exists() else ""
                desk = desktop / "J.A.R.V.I.S.desktop"
                desk.write_text(
                    "[Desktop Entry]\n"
                    "Name=J.A.R.V.I.S\n"
                    f"Exec={python} {script}\n"
                    f"Path={script.parent}\n"
                    "Type=Application\n"
                    "Terminal=false\n"
                    "Categories=Utility;\n"
                    + icon_line
                )
                desk.chmod(desk.stat().st_mode | 0o755)

            self._log.append_log("SYS: Desktop shortcut created.")
        except Exception as e:
            self._log.append_log(f"ERR: Shortcut failed — {e}")

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cw = self.centralWidget()
        if self._overlay and self._overlay.isVisible():
            ow, oh = 460, 390
            self._overlay.setGeometry(
                (cw.width()  - ow) // 2,
                (cw.height() - oh) // 2,
                ow, oh,
            )
        if self._remote_overlay and self._remote_overlay.isVisible():
            ow, oh = RemoteKeyOverlay._OW, RemoteKeyOverlay._OH
            self._remote_overlay.setGeometry(
                (cw.width()  - ow) // 2,
                (cw.height() - oh) // 2,
                ow, oh,
            )
        if self._customize_overlay and self._customize_overlay.isVisible():
            ow, oh = CustomizeOverlay._OW, CustomizeOverlay._OH
            self._customize_overlay.setGeometry(
                (cw.width()  - ow) // 2,
                (cw.height() - oh) // 2,
                ow, oh,
            )
        # Camera preview — bottom-right corner of the center/HUD area
        pw = _CameraPreview._W
        ph = self._cam_preview.height() or _CameraPreview._H
        self._cam_preview.setGeometry(
            cw.width() - _RIGHT_W - pw - 12,
            cw.height() - ph - 28,
            pw, ph,
        )
        # Clipboard panel — bottom-center
        if hasattr(self, '_clipboard_panel') and self._clipboard_panel.isVisible():
            self._position_clipboard_panel()
        # Quick drawer — reposition if open
        if hasattr(self, '_quick_drawer') and self._quick_drawer.isVisible():
            self._position_quick_drawer()

    def _update_metrics(self):
        snap = _metrics.snapshot()

        # CPU
        cpu = snap["cpu"]
        self._bar_cpu.set_value(cpu, f"{cpu:.0f}%")

        # MEM
        mem = snap["mem"]
        self._bar_mem.set_value(mem, f"{mem:.0f}%")

        # NET
        net = snap["net"]
        if net < 1.0:
            net_str = f"{net*1024:.0f}KB/s"
        else:
            net_str = f"{net:.1f}MB/s"
        net_pct = min(100, net * 10)  # 10 MB/s = %100
        self._bar_net.set_value(net_pct, net_str)

        # GPU
        gpu = snap["gpu"]
        if gpu >= 0:
            self._bar_gpu.set_value(gpu, f"{gpu:.0f}%")
        else:
            self._bar_gpu.set_value(0, "N/A")

        # TMP
        tmp = snap["tmp"]
        if tmp >= 0:
            tmp_pct = min(100, (tmp / 100) * 100)
            self._bar_tmp.set_value(tmp_pct, f"{tmp:.0f}°C")
        else:
            self._bar_tmp.set_value(0, "N/A")

        try:
            boot_t  = psutil.boot_time()
            elapsed = time.time() - boot_t
            h = int(elapsed // 3600)
            m = int((elapsed % 3600) // 60)
            self._uptime_lbl.setText(f"UP  {h:02d}:{m:02d}")
        except Exception:
            self._uptime_lbl.setText("UP  --:--")

        try:
            proc_count = len(psutil.pids())
            self._proc_lbl.setText(f"PROC  {proc_count}")
        except Exception:
            self._proc_lbl.setText("PROC  --")


    def _build_header(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(54)
        w.setStyleSheet(f"background: {C.DARK}; border-bottom: 1px solid {C.BORDER_B};")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(16, 0, 16, 0)

        def _badge(txt, color=C.TEXT_MED):
            l = QLabel(txt)
            l.setFont(QFont("Courier New", 8))
            l.setStyleSheet(f"color: {color}; background: transparent;")
            return l

        lay.addWidget(_badge(APP_VERSION, C.PRI_DIM))
        lay.addSpacing(8)
        self._drawer_btn = QPushButton("⚙")
        self._drawer_btn.setFixedSize(26, 26)
        self._drawer_btn.setFont(QFont("Courier New", 11))
        self._drawer_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._drawer_btn.setToolTip("Settings & Controls")
        self._drawer_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_DIM};
                border: 1px solid {C.BORDER}; border-radius: 4px;
            }}
            QPushButton:hover {{ color: {C.PRI}; border-color: {C.PRI_DIM}; }}
            QPushButton:checked {{ color: {C.PRI}; border-color: {C.PRI}; background: {C.PRI_GHO}; }}
        """)
        self._drawer_btn.setCheckable(True)
        self._drawer_btn.clicked.connect(self._toggle_drawer)
        lay.addWidget(self._drawer_btn)
        lay.addStretch()

        mid = QVBoxLayout(); mid.setSpacing(1)
        _disp = self._assistant_name.upper()
        self._title_lbl = QLabel(_disp)
        self._title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title_lbl.setFont(QFont("Courier New", 17, QFont.Weight.Bold))
        self._title_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        mid.addWidget(self._title_lbl)
        _sub_text = ("Just A Rather Very Intelligent System"
                     if _disp in ("JARVIS", "J.A.R.V.I.S")
                     else "Personal AI Assistant")
        self._sub_lbl = QLabel(_sub_text)
        self._sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._sub_lbl.setFont(QFont("Courier New", 7))
        self._sub_lbl.setStyleSheet(f"color: {C.PRI_DIM}; background: transparent;")
        mid.addWidget(self._sub_lbl)
        lay.addLayout(mid)
        lay.addStretch()

        right_col = QVBoxLayout(); right_col.setSpacing(2)
        self._clock_lbl = QLabel("00:00:00")
        self._clock_lbl.setFont(QFont("Courier New", 14, QFont.Weight.Bold))
        self._clock_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        self._clock_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_col.addWidget(self._clock_lbl)
        self._date_lbl = QLabel("")
        self._date_lbl.setFont(QFont("Courier New", 7))
        self._date_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        self._date_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_col.addWidget(self._date_lbl)
        lay.addLayout(right_col)
        return w

    def _tick_clock(self):
        self._clock_lbl.setText(time.strftime("%H:%M:%S"))
        self._date_lbl.setText(time.strftime("%a %d %b %Y"))

    def _build_left_panel(self) -> QWidget:
        w = QWidget()
        w.setFixedWidth(_LEFT_W)
        w.setStyleSheet(f"background: {C.DARK}; border-right: 1px solid {C.BORDER};")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 10, 8, 10)
        lay.setSpacing(6)

        hdr = QLabel("◈ SYS MONITOR")
        hdr.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.PRI}; background: transparent; "
                          f"border-bottom: 1px solid {C.BORDER}; padding-bottom: 4px;")
        lay.addWidget(hdr)
        lay.addSpacing(2)

        self._bar_cpu = MetricBar("CPU", C.PRI)
        self._bar_mem = MetricBar("MEM", C.ACC2)
        self._bar_net = MetricBar("NET", C.GREEN)
        self._bar_gpu = MetricBar("GPU", C.ACC)
        self._bar_tmp = MetricBar("TMP", "#ff6688")

        for bar in [self._bar_cpu, self._bar_mem, self._bar_net,
                    self._bar_gpu, self._bar_tmp]:
            lay.addWidget(bar)

        lay.addSpacing(4)

        info_panel = QWidget()
        info_panel.setStyleSheet(
            f"background: {C.PANEL2}; border: 1px solid {C.BORDER}; border-radius: 4px;"
        )
        ip_lay = QVBoxLayout(info_panel)
        ip_lay.setContentsMargins(6, 5, 6, 5)
        ip_lay.setSpacing(3)

        self._uptime_lbl = QLabel("UP  --:--")
        self._uptime_lbl.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._uptime_lbl.setStyleSheet(f"color: {C.GREEN}; background: transparent; border: none;")
        ip_lay.addWidget(self._uptime_lbl)

        self._proc_lbl = QLabel("PROC  --")
        self._proc_lbl.setFont(QFont("Courier New", 8))
        self._proc_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
        ip_lay.addWidget(self._proc_lbl)

        os_name = {"Windows": "WIN", "Darwin": "macOS", "Linux": "LINUX"}.get(_OS, _OS.upper())
        os_lbl = QLabel(f"OS  {os_name}")
        os_lbl.setFont(QFont("Courier New", 8))
        os_lbl.setStyleSheet(f"color: {C.ACC2}; background: transparent; border: none;")
        ip_lay.addWidget(os_lbl)

        lay.addWidget(info_panel)
        lay.addSpacing(4)

        lay.addStretch()

        for txt, col in [
            ("AI CORE\nACTIVE",  C.GREEN),
            ("SEC\nCLEARED",     C.PRI),
            ("PROTOCOL\n" + APP_PROTOCOL,   C.TEXT_DIM),
        ]:
            lbl = QLabel(txt)
            lbl.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(
                f"color: {col}; background: {C.PANEL2};"
                f"border: 1px solid {C.BORDER_A}; border-radius: 3px; padding: 4px;"
            )
            lay.addWidget(lbl)

        return w
    def _build_right_panel(self) -> QWidget:
        w = QWidget()
        w.setFixedWidth(_RIGHT_W)
        w.setStyleSheet(f"background: {C.DARK}; border-left: 1px solid {C.BORDER};")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        def _sec(txt):
            l = QLabel(f"▸ {txt}")
            l.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
            l.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
            return l

        lay.addWidget(_sec("ACTIVITY LOG"))
        self._log = LogWidget()
        lay.addWidget(self._log, stretch=1)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        lay.addWidget(sep)

        lay.addWidget(_sec("FILE UPLOAD"))
        self._drop_zone = FileDropZone()
        self._drop_zone.file_selected.connect(self._on_file_selected)
        lay.addWidget(self._drop_zone)

        self._file_hint = QLabel("No file loaded — drop or click above to upload")
        self._file_hint.setFont(QFont("Courier New", 7))
        self._file_hint.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        self._file_hint.setWordWrap(True)
        lay.addWidget(self._file_hint)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        lay.addWidget(sep2)

        lay.addWidget(_sec("COMMAND INPUT"))
        lay.addLayout(self._build_input_row())

        self._interrupt_btn = QPushButton("✋  INTERRUPT  [ESC]")
        self._interrupt_btn.setFixedHeight(34)
        self._interrupt_btn.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._interrupt_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._interrupt_btn.setStyleSheet(f"""
            QPushButton {{
                background: #140008; color: {C.MUTED_C};
                border: 1px solid {C.MUTED_C}; border-radius: 3px;
            }}
            QPushButton:hover {{
                background: #200010; border: 1px solid #ff6688;
            }}
            QPushButton:pressed {{
                background: #300018;
            }}
        """)
        self._interrupt_btn.clicked.connect(self._do_interrupt)
        lay.addWidget(self._interrupt_btn)

        self._mute_btn = QPushButton("🎙  MICROPHONE ACTIVE")
        self._mute_btn.setFixedHeight(30)
        self._mute_btn.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._mute_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mute_btn.clicked.connect(self._toggle_mute)
        self._style_mute_btn()
        lay.addWidget(self._mute_btn)

        return w

    def _build_quick_drawer(self) -> QWidget:
        """Floating overlay panel shown when the ⚙ header button is toggled."""
        _BTN_STYLE_PRI = f"""
            QPushButton {{
                background: #00091a; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 3px;
                text-align: left; padding: 0 8px;
            }}
            QPushButton:hover {{ background: {C.PRI_GHO}; border-color: {C.PRI}; }}
        """
        _BTN_STYLE_DIM = f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px;
                text-align: left; padding: 0 8px;
            }}
            QPushButton:hover {{ color: {C.PRI}; border-color: {C.BORDER_B}; }}
        """

        w = QWidget(self.centralWidget())
        w.setObjectName("QuickDrawer")
        w.setStyleSheet(f"""
            QWidget#QuickDrawer {{
                background: {C.DARK};
                border: 1px solid {C.BORDER_B};
                border-top: none;
                border-radius: 0 0 6px 6px;
            }}
        """)
        w.hide()

        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(5)

        hdr = QLabel("◈ CONTROLS")
        hdr.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.PRI_DIM}; background: transparent; "
                          f"border-bottom: 1px solid {C.BORDER}; padding-bottom: 4px;")
        lay.addWidget(hdr)

        remote_btn = QPushButton("◉  REMOTE CONTROL")
        remote_btn.setFixedHeight(30)
        remote_btn.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        remote_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remote_btn.setStyleSheet(_BTN_STYLE_PRI)
        remote_btn.clicked.connect(self._open_remote)
        lay.addWidget(remote_btn)

        fs_btn = QPushButton("⛶  FULLSCREEN  [F11]")
        fs_btn.setFixedHeight(26)
        fs_btn.setFont(QFont("Courier New", 7))
        fs_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        fs_btn.setStyleSheet(_BTN_STYLE_DIM)
        fs_btn.clicked.connect(self._toggle_fullscreen)
        lay.addWidget(fs_btn)

        sc_btn = QPushButton("⊞  CREATE DESKTOP SHORTCUT")
        sc_btn.setFixedHeight(26)
        sc_btn.setFont(QFont("Courier New", 7))
        sc_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        sc_btn.setStyleSheet(_BTN_STYLE_DIM)
        sc_btn.clicked.connect(self._create_desktop_shortcut)
        lay.addWidget(sc_btn)

        self._autostart_btn = QPushButton("◉  AUTO-START: OFF")
        self._autostart_btn.setFixedHeight(26)
        self._autostart_btn.setFont(QFont("Courier New", 7))
        self._autostart_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._autostart_btn.clicked.connect(self._toggle_autostart)
        lay.addWidget(self._autostart_btn)

        cust_btn = QPushButton("⚙  CUSTOMISE ASSISTANT")
        cust_btn.setFixedHeight(26)
        cust_btn.setFont(QFont("Courier New", 7))
        cust_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cust_btn.setStyleSheet(_BTN_STYLE_DIM)
        cust_btn.clicked.connect(self._open_customize)
        lay.addWidget(cust_btn)

        self._brief_btn = QPushButton()
        self._brief_btn.setFixedHeight(26)
        self._brief_btn.setFont(QFont("Courier New", 7))
        self._brief_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._brief_btn.clicked.connect(self._toggle_brief)
        lay.addWidget(self._brief_btn)

        # ── Wake word ──────────────────────────────────────────────────────────
        self._wake_btn = QPushButton()
        self._wake_btn.setFixedHeight(26)
        self._wake_btn.setFont(QFont("Courier New", 7))
        self._wake_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._wake_btn.clicked.connect(self._toggle_wake_word)
        lay.addWidget(self._wake_btn)

        self._wake_sleep_btn = QPushButton()
        self._wake_sleep_btn.setFixedHeight(26)
        self._wake_sleep_btn.setFont(QFont("Courier New", 7))
        self._wake_sleep_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._wake_sleep_btn.clicked.connect(self._tap_wake_manual)
        lay.addWidget(self._wake_sleep_btn)
        # Neutral placeholder now; the real state (which may load the model to
        # check readiness) is resolved lazily the first time the drawer opens.
        self._wake_btn.setText("🎙  WAKE WORD")
        self._wake_btn.setStyleSheet(_BTN_STYLE_DIM)
        self._wake_sleep_btn.hide()

        audio_btn = QPushButton("🎧  AUDIO DEVICES")
        audio_btn.setFixedHeight(26)
        audio_btn.setFont(QFont("Courier New", 7))
        audio_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        audio_btn.setStyleSheet(_BTN_STYLE_DIM)
        audio_btn.clicked.connect(self._open_audio_devices)
        lay.addWidget(audio_btn)

        mem_btn = QPushButton("🧠  MEMORY")
        mem_btn.setFixedHeight(26)
        mem_btn.setFont(QFont("Courier New", 7))
        mem_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        mem_btn.setStyleSheet(_BTN_STYLE_DIM)
        mem_btn.clicked.connect(self._open_memory_panel)
        lay.addWidget(mem_btn)

        plugin_btn = QPushButton("🧩  PLUGINS")
        plugin_btn.setFixedHeight(26)
        plugin_btn.setFont(QFont("Courier New", 7))
        plugin_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        plugin_btn.setStyleSheet(_BTN_STYLE_DIM)
        plugin_btn.clicked.connect(self._open_plugin_manager)
        lay.addWidget(plugin_btn)

        adv_btn = QPushButton("🛠  ADVANCED SETTINGS")
        adv_btn.setFixedHeight(26)
        adv_btn.setFont(QFont("Courier New", 7))
        adv_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        adv_btn.setStyleSheet(_BTN_STYLE_DIM)
        adv_btn.clicked.connect(self._open_advanced_settings)
        lay.addWidget(adv_btn)

        settings_btn = QPushButton("⚙  PLUGIN SETTINGS")
        settings_btn.setFixedHeight(26)
        settings_btn.setFont(QFont("Courier New", 7))
        settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        settings_btn.setStyleSheet(_BTN_STYLE_DIM)
        settings_btn.clicked.connect(self._open_plugin_settings)
        lay.addWidget(settings_btn)

        w.adjustSize()
        return w

    def _toggle_drawer(self, checked: bool):
        if checked:
            self._refresh_wake_btns()   # resolve wake state on open (lazy)
            self._position_quick_drawer()
            self._quick_drawer.show()
            self._quick_drawer.raise_()
        else:
            self._quick_drawer.hide()

    def _position_quick_drawer(self):
        if not hasattr(self, '_quick_drawer'):
            return
        _W = 220
        self._quick_drawer.setFixedWidth(_W)
        self._quick_drawer.adjustSize()
        self._quick_drawer.setGeometry(12, 54, _W, self._quick_drawer.sizeHint().height())

    def _build_input_row(self) -> QHBoxLayout:
        row = QHBoxLayout(); row.setSpacing(5)
        self._input = QLineEdit()
        self._input.setPlaceholderText("Type a command or question…")
        self._input.setFont(QFont("Courier New", 9))
        self._input.setFixedHeight(30)
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: #000d14; color: {C.WHITE};
                border: 1px solid {C.BORDER}; border-radius: 3px; padding: 3px 7px;
            }}
            QLineEdit:focus {{ border: 1px solid {C.PRI}; }}
        """)
        self._input.returnPressed.connect(self._send)
        row.addWidget(self._input)

        send = QPushButton("▸")
        send.setFixedSize(30, 30)
        send.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
        send.setCursor(Qt.CursorShape.PointingHandCursor)
        send.setStyleSheet(f"""
            QPushButton {{
                background: {C.PANEL}; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 3px;
            }}
            QPushButton:hover {{ background: {C.PRI_GHO}; border: 1px solid {C.PRI}; }}
        """)
        send.clicked.connect(self._send)
        row.addWidget(send)
        return row

    def _build_hud_info(self) -> QWidget:
        """What the HUD shows in the middle when there's nothing else to show."""
        w = QLabel(
            "◈  HUD\n\nThe orb is in the main JARVIS window.\n"
            "Results, lists, notes and the camera appear here.\n\n"
            "Ctrl+H — show / hide this window\nF4 — mute  ·  Esc — interrupt")
        w.setAlignment(Qt.AlignmentFlag.AlignCenter)
        w.setWordWrap(True)
        w.setFont(QFont("Courier New", 9))
        w.setStyleSheet(f"color: {C.TEXT_DIM}; background: {C.BG};")
        return w

    def show_intro_popup(self, is_playing) -> None:
        self._intro_popup = SuitUpPopup(self._assistant_name, is_playing, self.orb_window)
        self._intro_popup.show()

    def _holo_cmd(self, cmd: str) -> None:
        win = getattr(self, "_holo_win", None)
        if win is None:
            if cmd == "close" or '"remove"' in cmd or ('"gestures"' in cmd and '"on": false' in cmd):
                return
            color = (_read_full_config().get("hologram_color") or "#00d4ff").strip()
            try:                                    # colour-wheel names ("teal", "amber"…) → hex
                from core import holo_shapes as HS
                cn = HS.color_name(color)
                color = HS.HEX.get(cn, cn) if cn else color
            except Exception:
                pass
            win = self._holo_win = HologramWindow(color)
            win.show()
        win.command(cmd)

    def _holo_ext(self, d) -> None:
        win = getattr(self, "_holo_win", None)
        if win is not None:
            win.external(d)

    def _set_muted(self, v: bool) -> None:
        if bool(v) != self._muted:
            self._toggle_mute()

    def closeEvent(self, e):
        # Closing the HUD only hides it — the orb window keeps JARVIS running.
        if self.orb_window.isVisible():
            e.ignore()
            self.hide()
        else:
            super().closeEvent(e)
            QApplication.instance().quit()      # no orb window → closing the HUD quits

    def _build_content_panel(self) -> QWidget:
        """
        Collapsible panel below the HUD — shows search results, news, briefings.
        Hidden by default; appears when show_content() is called.
        """
        w = QWidget()
        w.setObjectName("ContentPanel")
        w.setStyleSheet(f"""
            QWidget#ContentPanel {{
                background: {C.PANEL};
                border-top: 1px solid {C.BORDER_B};
            }}
        """)
        w.hide()

        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 7, 12, 8)
        lay.setSpacing(5)

        # ── header row ───────────────────────────────────────────────────────
        hdr = QHBoxLayout(); hdr.setSpacing(6)

        dot = QLabel("◈")
        dot.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        dot.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        hdr.addWidget(dot)

        self._content_title_lbl = QLabel("BRIEFING")
        self._content_title_lbl.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._content_title_lbl.setStyleSheet(
            f"color: {C.PRI}; background: transparent; letter-spacing: 1px;"
        )
        hdr.addWidget(self._content_title_lbl)
        hdr.addStretch()

        self._content_ts_lbl = QLabel("")
        self._content_ts_lbl.setFont(QFont("Courier New", 7))
        self._content_ts_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        hdr.addWidget(self._content_ts_lbl)

        dismiss = QPushButton("DISMISS  ✕")
        dismiss.setFont(QFont("Courier New", 7))
        dismiss.setFixedHeight(18)
        dismiss.setCursor(Qt.CursorShape.PointingHandCursor)
        dismiss.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_DIM};
                border: 1px solid {C.BORDER}; border-radius: 2px; padding: 0 5px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        dismiss.clicked.connect(w.hide)
        hdr.addWidget(dismiss)
        lay.addLayout(hdr)

        # ── separator ─────────────────────────────────────────────────────────
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER};"); lay.addWidget(sep)

        # ── text display ──────────────────────────────────────────────────────
        self._content_display = QTextEdit()
        self._content_display.setReadOnly(True)
        self._content_display.setFont(QFont("Courier New", 8))
        self._content_display.setMinimumHeight(60)
        self._content_display.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._content_display.setStyleSheet(f"""
            QTextEdit {{
                background: {C.DARK};
                color: {C.TEXT};
                border: 1px solid {C.BORDER};
                border-radius: 3px;
                padding: 6px 8px;
                selection-background-color: {C.PRI_GHO};
            }}
            QScrollBar:vertical {{
                background: {C.BG}; width: 6px; border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER_B}; border-radius: 3px; min-height: 16px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0; border: none;
            }}
        """)
        lay.addWidget(self._content_display)

        return w

    def _show_content(self, title: str, text: str):
        """Slot — runs on Qt main thread. Updates and shows the content panel."""
        import time as _time
        self._content_title_lbl.setText(title.upper()[:48])
        self._content_ts_lbl.setText(_time.strftime("%H:%M:%S"))
        self._content_display.setPlainText(text)
        self._content_display.moveCursor(
            self._content_display.textCursor().MoveOperation.Start
        )
        first_show = not self._content_panel.isVisible()
        self._content_panel.show()
        if first_show:
            total = self._center_split.height()
            self._center_split.setSizes([max(total - 220, 120), 220])

    def _build_footer(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(22)
        w.setStyleSheet(f"background: {C.DARK}; border-top: 1px solid {C.BORDER};")
        lay = QHBoxLayout(w); lay.setContentsMargins(14, 0, 14, 0)

        def _fl(txt, color=C.TEXT_MED):
            l = QLabel(txt); l.setFont(QFont("Courier New", 7))
            l.setStyleSheet(f"color: {color}; background: transparent;")
            return l

        lay.addWidget(_fl("[F4] Mute  ·  [F11] Fullscreen"))
        lay.addStretch()
        lay.addWidget(_fl("By FatihMakes", C.PRI_DIM))
        return w

    def _on_file_selected(self, path: str):
        self._current_file = path
        p    = Path(path)
        cat  = _file_category(p)
        icon, _ = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        size = _fmt_size(p.stat().st_size)
        self._file_hint.setText(f"{icon}  {p.name}  ·  {size}  ·  Tell {self._assistant_name} what to do with it")
        self._log.append_log(f"FILE: {p.name} ({size}) loaded")
        if self.on_text_command:
            msg = (
                f"[FILE_UPLOADED] path={path} | name={p.name} | "
                f"type={p.suffix.lstrip('.')} | size={size} | "
                f"Briefly tell the user you can see the file '{p.name}' "
                f"({size}) has been uploaded and ask what they'd like to do with it."
            )
            threading.Thread(target=self.on_text_command, args=(msg,), daemon=True).start()

    def notify_phone_connected(self) -> None:
        if self._remote_overlay and self._remote_overlay.isVisible():
            self._remote_overlay.mark_connected()

    def _open_remote(self):
        if not self.on_remote_clicked:
            self._log.append_log("SYS: Dashboard not running — remote unavailable.")
            return
        result = self.on_remote_clicked()
        if not result:
            self._log.append_log("SYS: Could not generate remote key.")
            return
        url    = result[0]
        key    = result[1]
        auto   = result[2] if len(result) >= 3 else ""
        manual = result[3] if len(result) >= 4 else url
        if self._remote_overlay:
            self._remote_overlay._do_close()
        cw  = self.centralWidget()
        ow, oh = RemoteKeyOverlay._OW, RemoteKeyOverlay._OH
        ov  = RemoteKeyOverlay(url, key, auto_login_url=auto, manual_url=manual,
                               expiry_secs=600, parent=cw)
        ov.set_new_key_callback(self.on_remote_clicked)
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.closed.connect(lambda: setattr(self, '_remote_overlay', None))
        ov.show()
        self._remote_overlay = ov
        self._log.append_log(f"SYS: Remote key generated — manual: {manual or url}")

    # ── Auto-start ──────────────────────────────────────────────────────────────

    def _check_autostart(self) -> bool:
        """Returns True if auto-start is currently registered on this OS."""
        try:
            if _OS == "Windows":
                import winreg
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
                try:
                    winreg.QueryValueEx(key, "JARVIS_AI")
                    return True
                except FileNotFoundError:
                    return False
                finally:
                    winreg.CloseKey(key)
            elif _OS == "Darwin":
                return (Path.home() / "Library" / "LaunchAgents"
                        / "com.jarvis.assistant.plist").exists()
            else:
                return (Path.home() / ".config" / "autostart" / "jarvis.desktop").exists()
        except Exception:
            return False

    def _toggle_autostart(self):
        currently_on = self._check_autostart()
        try:
            script = str(Path(__file__).resolve().parent / "main.py")
            if _OS == "Windows":
                import winreg
                reg = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_ALL_ACCESS)
                if currently_on:
                    winreg.DeleteValue(reg, "JARVIS_AI")
                else:
                    pythonw = Path(sys.executable).parent / "pythonw.exe"
                    exe = str(pythonw if pythonw.exists() else sys.executable)
                    winreg.SetValueEx(reg, "JARVIS_AI", 0, winreg.REG_SZ,
                                      f'"{exe}" "{script}"')
                winreg.CloseKey(reg)
            elif _OS == "Darwin":
                plist_dir = Path.home() / "Library" / "LaunchAgents"
                plist_dir.mkdir(parents=True, exist_ok=True)
                plist = plist_dir / "com.jarvis.assistant.plist"
                if currently_on:
                    plist.unlink(missing_ok=True)
                else:
                    plist.write_text(
                        '<?xml version="1.0" encoding="UTF-8"?>\n'
                        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                        '<plist version="1.0"><dict>\n'
                        '  <key>Label</key><string>com.jarvis.assistant</string>\n'
                        '  <key>ProgramArguments</key><array>\n'
                        f'    <string>{sys.executable}</string>\n'
                        f'    <string>{script}</string>\n'
                        '  </array>\n'
                        '  <key>RunAtLoad</key><true/>\n'
                        '</dict></plist>\n'
                    )
            else:
                desk_dir = Path.home() / ".config" / "autostart"
                desk_dir.mkdir(parents=True, exist_ok=True)
                desk = desk_dir / "jarvis.desktop"
                if currently_on:
                    desk.unlink(missing_ok=True)
                else:
                    desk.write_text(
                        "[Desktop Entry]\n"
                        f"Name={self._assistant_name}\n"
                        f"Exec={sys.executable} {script}\n"
                        "Type=Application\nTerminal=false\n"
                        "X-GNOME-Autostart-enabled=true\n"
                    )
            enabled = not currently_on
            self._update_autostart_btn(enabled)
            self._log.append_log(
                f"SYS: Auto-start {'enabled' if enabled else 'disabled'}.")
        except Exception as e:
            self._log.append_log(f"ERR: Auto-start failed — {e}")

    def _update_autostart_btn(self, enabled: bool):
        if not hasattr(self, '_autostart_btn'):
            return
        if enabled:
            self._autostart_btn.setText("◉  AUTO-START: ON")
            self._autostart_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #001a08; color: {C.GREEN};
                    border: 1px solid {C.GREEN_D}; border-radius: 3px;
                }}
                QPushButton:hover {{ background: #002010; }}
            """)
        else:
            self._autostart_btn.setText("◉  AUTO-START: OFF")
            self._autostart_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {C.TEXT_DIM};
                    border: 1px solid {C.BORDER}; border-radius: 3px;
                }}
                QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}
            """)

    def _toggle_brief(self):
        from memory.config_manager import get_brief_enabled, save_brief_enabled
        new_val = not get_brief_enabled()
        save_brief_enabled(new_val)
        self._update_brief_btn(new_val)

    # ── Wake word settings ───────────────────────────────────────────────────

    def _wake_state(self) -> dict:
        """Combined state for the two wake-word buttons. Readiness is a cheap,
        deterministic on-disk check now (see core.wake_word.is_ready), so there
        is nothing to cache — the button never flickers to a stale value."""
        if self.wake_get_state:
            try:
                s = self.wake_get_state()
                return {"ready": bool(s.get("ready")),
                        "enabled": bool(s.get("enabled")),
                        "awake": bool(s.get("awake"))}
            except Exception:
                pass
        # Before JarvisLive has wired its callback (drawer built at startup).
        ready, enabled = False, False
        try:
            from core.wake_word import is_ready
            from memory.config_manager import get_wake_word_enabled
            ready, enabled = is_ready(), get_wake_word_enabled()
        except Exception:
            pass
        return {"ready": ready, "enabled": enabled, "awake": True}

    def _refresh_wake_btns(self):
        if not hasattr(self, '_wake_btn'):
            return
        st = self._wake_state()
        _on = f"""
            QPushButton {{ background: #001a08; color: {C.GREEN};
                border: 1px solid {C.GREEN_D}; border-radius: 3px;
                text-align: left; padding: 0 8px; }}
            QPushButton:hover {{ background: #002010; }}"""
        _off = f"""
            QPushButton {{ background: transparent; color: {C.TEXT_DIM};
                border: 1px solid {C.BORDER}; border-radius: 3px;
                text-align: left; padding: 0 8px; }}
            QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}"""
        self._wake_btn.setEnabled(True)
        if not st["ready"]:
            self._wake_btn.setText("⬇  WAKE WORD: DOWNLOAD")
            self._wake_btn.setStyleSheet(_off)
            self._wake_sleep_btn.hide()
        elif st["enabled"]:
            self._wake_btn.setText("🎙  WAKE WORD: ON")
            self._wake_btn.setStyleSheet(_on)
            self._wake_sleep_btn.show()
            self._wake_sleep_btn.setText("😴  SLEEP NOW" if st["awake"] else "👂  WAKE NOW")
            self._wake_sleep_btn.setStyleSheet(_off)
        else:
            self._wake_btn.setText("🎙  WAKE WORD: OFF")
            self._wake_btn.setStyleSheet(_off)
            self._wake_sleep_btn.hide()

    def _toggle_wake_word(self):
        st = self._wake_state()
        if not st["ready"]:
            # First time: download openwakeword + model in a worker thread.
            self._wake_btn.setText("⬇  DOWNLOADING… (one-time)")
            self._wake_btn.setEnabled(False)
            def _work():
                try:
                    from core.wake_word import install_and_download
                    ok, msg = install_and_download(
                        logger=lambda m: self._log_sig.emit(f"SYS: {m}"))
                except Exception as e:
                    ok, msg = False, str(e)
                if ok and self.on_wake_toggle:
                    try:
                        self.on_wake_toggle(True)   # auto-enable after a successful download
                    except Exception:
                        pass
                self._wake_dl_sig.emit(ok, msg)
            threading.Thread(target=_work, daemon=True).start()
            return
        # Already downloaded → just flip enabled/disabled through JarvisLive.
        if self.on_wake_toggle:
            try:
                self.on_wake_toggle(not st["enabled"])
            except Exception:
                pass
        self._refresh_wake_btns()

    def _on_wake_install_done(self, ok: bool, msg: str):
        self._log_sig.emit(f"SYS: {'Wake word ready.' if ok else 'Wake word setup failed: ' + msg}")
        self._refresh_wake_btns()

    def _tap_wake_manual(self):
        if self.on_wake_manual:
            try:
                self.on_wake_manual()
            except Exception:
                pass
        self._refresh_wake_btns()

    def _update_brief_btn(self, enabled: bool):
        if not hasattr(self, '_brief_btn'):
            return
        if enabled:
            self._brief_btn.setText("☀  MORNING BRIEF: ON")
            self._brief_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #001a08; color: {C.GREEN};
                    border: 1px solid {C.GREEN_D}; border-radius: 3px;
                    text-align: left; padding: 0 8px;
                }}
                QPushButton:hover {{ background: #002010; }}
            """)
        else:
            self._brief_btn.setText("☀  MORNING BRIEF: OFF")
            self._brief_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {C.TEXT_DIM};
                    border: 1px solid {C.BORDER}; border-radius: 3px;
                    text-align: left; padding: 0 8px;
                }}
                QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}
            """)

    # ── Customization ────────────────────────────────────────────────────────────

    def _open_customize(self):
        cfg = _read_full_config()
        if self._customize_overlay:
            self._customize_overlay.hide()
        cw = self.centralWidget()
        ov = CustomizeOverlay(
            cfg.get("assistant_name", DEFAULT_ASSISTANT_NAME) or DEFAULT_ASSISTANT_NAME,
            cfg.get("user_name", ""),
            cfg.get("ui_color", "") or DEFAULT_UI_COLOR,
            cfg.get("voice_name", ""),
            parent=cw,
        )
        ow, oh = CustomizeOverlay._OW, CustomizeOverlay._OH
        oh = min(oh, cw.height() - 16)
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.on_preview = self._preview_ui_color
        ov.saved.connect(self._apply_name_update)
        ov.show()
        self._customize_overlay = ov

    def _preview_ui_color(self, hex_color: str):
        """Live preview — paints the whole interface the new colour (does NOT write to config)."""
        old = current_palette()
        if apply_ui_accent(hex_color):
            retheme_all_widgets(old, current_palette())

    def _apply_name_update(self, name: str, user_name: str, ui_color: str = "",
                           voice: str = ""):
        """Update all name/theme-dependent UI elements and persist to config."""
        self._assistant_name = name.strip() or DEFAULT_ASSISTANT_NAME
        display = self._assistant_name.upper()
        self.setWindowTitle(f"{display} — HUD")
        self.orb_window.setWindowTitle(display)
        self._title_lbl.setText(display)
        if display in ("JARVIS", "J.A.R.V.I.S"):
            self._sub_lbl.setText("Just A Rather Very Intelligent System")
        else:
            self._sub_lbl.setText("Personal AI Assistant")
        self._log._ai_name_lc = self._assistant_name.lower()
        self.hud._assistant_name = display

        color_changed = False
        if ui_color:
            old = current_palette()
            if apply_ui_accent(ui_color):
                # Live-paint the whole interface (panels, buttons, borders, HUD)
                retheme_all_widgets(old, current_palette())
                color_changed = old["PRI"] != C.PRI

        # Voice change → persist and, if it actually changed, rebuild the Live
        # session so the new voice takes effect (it's fixed at connect time).
        voice_changed = False
        if voice:
            from memory.config_manager import get_voice, save_voice
            if voice != get_voice():
                save_voice(voice)
                voice_changed = True

        try:
            data = _read_full_config()
            data["assistant_name"] = self._assistant_name
            data["user_name"] = user_name.strip()
            if ui_color:
                data["ui_color"] = ui_color.strip().lower()
            API_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")
            self._log.append_log(f"SYS: Identity updated — {display}")
            if color_changed:
                self._log.append_log(f"SYS: UI colour applied — {ui_color}")
            if voice_changed:
                self._log.append_log(f"SYS: Voice set — {voice}")
        except Exception as e:
            self._log.append_log(f"ERR: Config save failed — {e}")

        if voice_changed and self.on_voice_change:
            self.on_voice_change()

    def _centre_overlay(self, ov) -> None:
        """Place a floating overlay in the middle of the HUD and show it."""
        cw = self.centralWidget()
        ov.adjustSize()
        ov.setGeometry(
            max(0, (cw.width()  - ov.width())  // 2),
            max(0, (cw.height() - ov.height()) // 2),
            ov.width(), ov.height(),
        )
        ov.show()
        ov.raise_()

    # ── Audio devices ────────────────────────────────────────────────────────

    def _open_audio_devices(self):
        ov = AudioDeviceOverlay(parent=self.centralWidget())
        ov.picked.connect(self._on_audio_devices_applied)
        self._centre_overlay(ov)
        self._audio_overlay = ov            # keep a reference so it isn't GC'd

    def _on_audio_devices_applied(self):
        self._log.append_log("SYS: Audio devices updated.")
        if self.on_audio_device_change:
            self.on_audio_device_change()

    # ── Memory panel ─────────────────────────────────────────────────────────

    def _open_advanced_settings(self):
        ov = AdvancedSettingsOverlay(parent=self.centralWidget())
        self._centre_overlay(ov)
        self._adv_overlay = ov

    def _open_memory_panel(self):
        ov = MemoryOverlay(parent=self.centralWidget())
        self._centre_overlay(ov)
        self._memory_overlay = ov

    # ── Irreversible-action confirmation ─────────────────────────────────────

    def _show_confirm_banner(self, title: str, detail: str):
        self._hide_confirm_banner()
        ov = ConfirmBanner(title, detail, parent=self.centralWidget())
        ov.answered.connect(self._on_confirm_answered)
        self._centre_overlay(ov)
        self._confirm_overlay = ov

    def _hide_confirm_banner(self):
        ov = getattr(self, "_confirm_overlay", None)
        if ov is not None:
            ov.hide()
            ov.deleteLater()
            self._confirm_overlay = None

    def _on_confirm_answered(self, accepted: bool):
        # Tear the banner down first: core.confirm.resolve() may be about to
        # shut the machine down, and a live widget mid-callback is not where you
        # want to be when that happens.
        self._hide_confirm_banner()
        try:
            from core.confirm import resolve
            resolve(bool(accepted))
        except Exception as e:
            self._log.append_log(f"ERR: Confirmation failed — {e}")

    def _open_plugin_manager(self):
        plugins = self.get_plugins() if self.get_plugins else []
        cw = self.centralWidget()
        ov = PluginManagerOverlay(plugins, parent=cw)
        ov.adjustSize()
        ov.setGeometry(
            (cw.width()  - ov.width())  // 2,
            (cw.height() - ov.height()) // 2,
            ov.width(), ov.height(),
        )
        ov.show()
        ov.raise_()
        self._plugin_manager_overlay = ov   # keep a reference so it isn't GC'd

    def _open_plugin_settings(self):
        sections = self.get_plugin_settings() if self.get_plugin_settings else []
        cw = self.centralWidget()
        ov = PluginSettingsOverlay(sections, parent=cw)
        ow = PluginSettingsOverlay._OW
        oh = min(560, cw.height() - 16)
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.show()
        ov.raise_()
        self._plugin_settings_overlay = ov   # keep a reference so it isn't GC'd

    # ── Clipboard intelligence ───────────────────────────────────────────────────

    def _on_clipboard_changed(self):
        try:
            text = QApplication.clipboard().text().strip()
            if len(text) >= 10:
                self._clipboard_sig.emit(text)
        except Exception:
            pass

    def _show_clipboard_panel(self, text: str):
        self._clipboard_panel.show_clipboard(text)
        self._position_clipboard_panel()

    def _position_clipboard_panel(self):
        cw = self.centralWidget()
        pw = ClipboardPanel._W
        ph = self._clipboard_panel.sizeHint().height() or ClipboardPanel._H
        x = (cw.width() - pw) // 2
        y = cw.height() - ph - 6
        self._clipboard_panel.setGeometry(x, y, pw, ph)
        self._clipboard_panel.raise_()

    def _on_clipboard_action(self, cmd: str):
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(cmd,), daemon=True).start()

    # ────────────────────────────────────────────────────────────────────────────

    def _do_interrupt(self):
        if self.on_interrupt:
            self.on_interrupt()

    def _toggle_mute(self):
        self._muted = not self._muted
        self.hud.muted = self._muted
        self._style_mute_btn()
        if self._muted:
            self._apply_state("MUTED")
            self._log.append_log("SYS: Microphone muted.")
        else:
            self._apply_state("LISTENING")
            self._log.append_log("SYS: Microphone active.")

    def _style_mute_btn(self):
        if self._muted:
            self._mute_btn.setText("🔇  MICROPHONE MUTED")
            self._mute_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #140006; color: {C.MUTED_C};
                    border: 1px solid {C.MUTED_C}; border-radius: 3px;
                }}
            """)
        else:
            self._mute_btn.setText("🎙  MICROPHONE ACTIVE")
            self._mute_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #00140a; color: {C.GREEN};
                    border: 1px solid {C.GREEN}; border-radius: 3px;
                }}
                QPushButton:hover {{ background: #001f10; }}
            """)

    def _send(self):
        txt = self._input.text().strip()
        if not txt: return
        self._input.clear()
        self._log.append_log(f"You: {txt}")
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(txt,), daemon=True).start()

    def _apply_state(self, state: str):
        self.hud.state    = state
        self.hud.speaking = (state == "SPEAKING")

    def _check_config(self) -> bool:
        if not API_FILE.exists(): return False
        try:
            d = json.loads(API_FILE.read_text(encoding="utf-8"))
            return bool(d.get("gemini_api_key")) and bool(d.get("os_system"))
        except Exception:
            return False

    def _show_setup(self):
        ov = SetupOverlay(self.centralWidget())
        cw = self.centralWidget()
        ow, oh = 460, 390
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.done.connect(self._on_setup_done)
        ov.show()
        self._overlay = ov

    def _on_setup_done(self, key: str, os_name: str):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        # Merge into the existing settings — writing ONLY the key used to wipe the
        # Google Client ID/secret, the PIN, colours and everything else.
        try:
            data = json.loads(API_FILE.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {}
        except Exception:
            data = {}
        data.update({"gemini_api_key": key, "os_system": os_name})
        API_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")
        self._ready = True
        if self._overlay:
            self._overlay.hide()
            self._overlay = None
        self._apply_state("LISTENING")
        self._assistant_name = _read_full_config().get("assistant_name", DEFAULT_ASSISTANT_NAME) or DEFAULT_ASSISTANT_NAME
        self._log.append_log(f"SYS: Initialised. OS={os_name.upper()}. {self._assistant_name} online.")


class _RootShim:
    def __init__(self, app: QApplication):
        self._app = app
    def mainloop(self):
        self._app.exec()
    def protocol(self, *_):
        pass


class JarvisUI:
    def __init__(self, face_path: str, size=None, intro_playing=None, intro_skip=None,
                 intro_start=None, intro_timing=None):
        self._app = QApplication.instance() or QApplication(sys.argv)
        self._app.setStyle("Fusion")
        # The intro screen is briefly the ONLY window. Qt's default is to quit the
        # app when the last window closes — which killed JARVIS right after the
        # intro. JARVIS now quits only when the orb window is closed.
        self._app.setQuitOnLastWindowClosed(False)
        self._shown = False
        self._intro_screen = None
        if intro_playing is not None:
            # After the PIN: black screen + glowing ring while suit_up.mp3 plays.
            # The HUD and the orb window open when it ends (see _show_main_windows).
            _cfg = _read_full_config()
            if (_cfg.get("ui_color") or DEFAULT_UI_COLOR).strip().lower() != _PALETTE_DEFAULTS["PRI"]:
                apply_ui_accent((_cfg.get("ui_color") or DEFAULT_UI_COLOR).strip())
            name = (_cfg.get("assistant_name") or "JARVIS").strip()
            self._intro_screen = IntroHud(name, intro_playing, on_done=self._show_main_windows,
                                          on_skip=intro_skip,
                                          color=(_cfg.get("intro_color") or "#00d4ff").strip(),
                                          start_sound=intro_start, timing=intro_timing)
            self._intro_screen.show()
            self._intro_screen.activateWindow()
            self._app.processEvents()
        self._win = MainWindow(face_path)
        self.root = _RootShim(self._app)
        # Orb window on the left/centre, HUD window on the right side.
        scr = QApplication.primaryScreen().availableGeometry()
        hud_w = min(max(_MIN_W, int(scr.width() * 0.42)), scr.width())
        orb_w = max(360, scr.width() - hud_w)
        self._win.orb_window.setGeometry(scr.x(), scr.y(), orb_w, scr.height())
        self._win.resize(hud_w, scr.height())
        self._win.move(scr.x() + scr.width() - hud_w, scr.y())
        if self._intro_screen is None:
            self._show_main_windows()
        try:                                    # hand control → orb (actions/orb_hand_control.py)
            from core import tool_bus
            tool_bus.subscribe("orb_control", self._win.hud.external_control)
            tool_bus.subscribe("hologram_control", self._win._holo_ext)
        except Exception:
            pass

    def _show_main_windows(self) -> None:
        """Opens the HUD window (log, code, every function) and then, a moment
        later, the orange orb window in front of it."""
        if self._shown:
            return
        if not hasattr(self, "_win"):                 # still being built — try again shortly
            QTimer.singleShot(100, self._show_main_windows)
            return
        self._shown = True
        self._win.show()
        def _orb():
            ow = self._win.orb_window
            ow.show(); ow.raise_(); ow.activateWindow()
        QTimer.singleShot(450, _orb)

    def hologram(self, cmd) -> None:
        """Thread-safe hologram command: a word (show / explode / assemble / spin / stop_spin /
        reset / close) or a dict {"op": "add"|"remove"|"color", ...}."""
        self._win._holo_sig.emit(cmd if isinstance(cmd, str) else json.dumps(cmd))

    def hologram_names(self) -> list:
        win = getattr(self._win, "_holo_win", None)
        try:
            return win.names() if win is not None else []
        except Exception:
            return []

    def set_muted(self, v: bool) -> None:
        """Thread-safe mute / unmute (voice command, double clap)."""
        self._win._mute_sig.emit(bool(v))

    def show_intro_popup(self, is_playing) -> None:
        """Thread-safe: small glowing pop-up while the start-up sound plays."""
        self._win._intro_sig.emit(is_playing)

    @property
    def muted(self) -> bool:
        return self._win._muted

    @muted.setter
    def muted(self, v: bool):
        if v != self._win._muted:
            self._win._toggle_mute()

    @property
    def current_file(self) -> str | None:
        return self._win._drop_zone.current_file()

    @property
    def on_text_command(self):
        return self._win.on_text_command

    @on_text_command.setter
    def on_text_command(self, cb):
        self._win.on_text_command = cb

    @property
    def on_remote_clicked(self):
        return self._win.on_remote_clicked

    @on_remote_clicked.setter
    def on_remote_clicked(self, cb):
        self._win.on_remote_clicked = cb

    @property
    def on_interrupt(self):
        return self._win.on_interrupt

    @on_interrupt.setter
    def on_interrupt(self, cb):
        self._win.on_interrupt = cb

    @property
    def on_voice_change(self):
        return self._win.on_voice_change

    @on_voice_change.setter
    def on_voice_change(self, cb):
        self._win.on_voice_change = cb

    @property
    def on_audio_device_change(self):
        return self._win.on_audio_device_change

    @on_audio_device_change.setter
    def on_audio_device_change(self, cb):
        self._win.on_audio_device_change = cb

    def show_confirm(self, title: str, detail: str) -> None:
        """Thread-safe: raise the irreversible-action gate. Called from action
        handlers running in executor threads, so it goes through a signal."""
        self._win._confirm_sig.emit(str(title)[:120], str(detail)[:300])

    def hide_confirm(self) -> None:
        """Thread-safe: take the gate down."""
        self._win._confirm_hide_sig.emit()

    @property
    def get_plugins(self):
        return self._win.get_plugins

    @get_plugins.setter
    def get_plugins(self, cb):
        self._win.get_plugins = cb

    @property
    def get_plugin_settings(self):
        return self._win.get_plugin_settings

    @get_plugin_settings.setter
    def get_plugin_settings(self, cb):
        self._win.get_plugin_settings = cb

    @property
    def on_wake_toggle(self):
        return self._win.on_wake_toggle

    @on_wake_toggle.setter
    def on_wake_toggle(self, cb):
        self._win.on_wake_toggle = cb

    @property
    def on_wake_manual(self):
        return self._win.on_wake_manual

    @on_wake_manual.setter
    def on_wake_manual(self, cb):
        self._win.on_wake_manual = cb

    @property
    def wake_get_state(self):
        return self._win.wake_get_state

    @wake_get_state.setter
    def wake_get_state(self, cb):
        self._win.wake_get_state = cb

    def set_audio_level(self, level: float) -> None:
        """Thread-safe: feed a 0.0–1.0 live audio level to the HUD waveform.
        Called from the audio threads; a plain float store is atomic under the
        GIL, so no signal/lock is needed for this cosmetic value."""
        try:
            self._win.hud.set_audio_level(level)
        except Exception:
            pass

    def notify_phone_connected(self) -> None:
        self._win.notify_phone_connected()

    def set_state(self, state: str):
        self._win._state_sig.emit(state)

    def write_log(self, text: str):
        self._win._log_sig.emit(text)

    def wait_for_api_key(self):
        while not self._win._ready:
            time.sleep(0.1)

    def show_content(self, title: str, text: str):
        """Thread-safe: display content in the panel below the HUD."""
        self._win._content_sig.emit(title[:48], text[:4000])

    def prompt_reconfig(self):
        """Thread-safe: show the API key setup overlay (e.g. after an auth error)."""
        self._win._ready = False
        self._win._reconfig_sig.emit()

    def show_camera_frame(self, img_bytes: bytes):
        """Thread-safe: show a webcam frame in the small overlay (screen captures)."""
        self._win._camera_sig.emit(img_bytes)

    def start_camera_stream(self) -> None:
        """Thread-safe: start live camera feed in the full HUD area."""
        self._win.start_camera_stream()

    def stop_camera_stream(self) -> None:
        """Thread-safe: stop the live camera feed."""
        self._win.stop_camera_stream()

    @property
    def assistant_name(self) -> str:
        return self._win._assistant_name

    def start_speaking(self):
        self.set_state("SPEAKING")

    def stop_speaking(self):
        if not self.muted:
            self.set_state("LISTENING")