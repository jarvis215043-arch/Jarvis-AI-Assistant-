"""
core/holo_shapes.py — Shapes and colours for the hologram window.

SHAPES   60+ built-in particle shapes (geometry, science & space, tech, nature,
         objects) + the armour suit + "text:<WORD>" + CUSTOM shapes that JARVIS
         designs from simple parts (spheres, boxes, cylinders…) for anything else.
COLOURS  The 12-colour wheel from the colour-theory chart (red, vermilion, orange,
         amber, yellow, chartreuse, green, teal, blue, violet, purple, magenta),
         plus cyan/white/gray/black, and the colour relationships: analogous,
         complementary, triadic, split complementary, square, monochromatic,
         warm, cool, grayscale and rainbow. Moods map to colours using the chart's
         colour meanings (calm → blue, energy → red, nature → green…).

Every shape is returned as an (N, 3) array of points, centred and scaled to fit
inside a unit sphere, so the window can place several side by side.
"""
import math

import numpy as np

# ── colours ──────────────────────────────────────────────────────────────────
WHEEL = ["red", "vermilion", "orange", "amber", "yellow", "chartreuse",
         "green", "teal", "blue", "violet", "purple", "magenta"]
HEX = {"red": "#ff2a2a", "vermilion": "#ff5a1f", "orange": "#ff8c1a", "amber": "#ffbf00",
       "yellow": "#ffee33", "chartreuse": "#a6ff1a", "green": "#22e04a", "teal": "#1ae0c0",
       "blue": "#2a6bff", "violet": "#6a3cff", "purple": "#b03cff", "magenta": "#ff2fbf",
       "cyan": "#00d4ff", "white": "#e6faff", "gray": "#9aa4ad", "black": "#3a3f45"}
ALIASES = {"red-orange": "vermilion", "red orange": "vermilion", "yellow-orange": "amber", "yellow orange": "amber",
           "gold": "amber", "golden": "amber", "lime": "chartreuse", "yellow-green": "chartreuse",
           "yellow green": "chartreuse", "blue-green": "teal", "blue green": "teal", "turquoise": "teal",
           "aqua": "cyan", "blue-violet": "violet", "blue violet": "violet", "indigo": "violet",
           "red-violet": "magenta", "red violet": "magenta", "pink": "magenta", "grey": "gray", "silver": "gray",
           "hologram": "cyan", "default": "cyan", "jarvis": "orange"}
MOODS = {  # from the chart's COLOUR MEANINGS
    "red": ["intense", "fire", "energy", "energetic", "danger", "love", "passion", "strong", "strength", "angry",
            "power up", "excited", "aggressive"],
    "purple": ["royal", "royalty", "power", "noble", "wealth", "ambition", "mysterious", "mystery", "magic"],
    "blue": ["sky", "sea", "ocean", "deep", "stable", "trust", "calm", "tranquil", "peaceful", "relax", "chill",
             "sad", "focus"],
    "green": ["nature", "growth", "fresh", "healing", "safe", "safety", "money", "earth", "forest"],
    "yellow": ["sunshine", "sunny", "joy", "cheerful", "happy", "intellect", "smart", "attention", "bright"],
    "orange": ["warm", "stimulating", "enthusiasm", "success", "creative", "autumn", "fun"],
}
SCHEMES = ["single", "analogous", "complementary", "triadic", "split complementary", "square",
           "monochromatic", "warm", "cool", "grayscale", "rainbow"]


def color_name(text: str) -> str | None:
    t = (text or "").strip().lower()
    if not t:
        return None
    if t.startswith("#") and len(t) == 7:
        return t
    for k in sorted(ALIASES, key=len, reverse=True):
        if k in t:
            return ALIASES[k]
    for k in sorted(HEX, key=len, reverse=True):
        if k in t:
            return k
    for c, words in MOODS.items():
        if any(w in t for w in words):
            return c
    return None


def scheme_name(text: str) -> str:
    t = (text or "").lower()
    for s in ("split complementary", "split-complementary", "split"):
        if s in t:
            return "split complementary"
    for s in SCHEMES:
        if s in t:
            return s
    if "complement" in t or "opposite" in t:
        return "complementary"
    if "tetradic" in t or "four" in t:
        return "square"
    if "mono" in t or "shades" in t:
        return "monochromatic"
    if "gray" in t or "grey" in t or "black and white" in t:
        return "grayscale"
    return "single"


def _hex_to_rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _shade(h: str, f: float) -> str:
    r, g, b = _hex_to_rgb(h)
    if f >= 1:
        r, g, b = (int(c + (255 - c) * (f - 1)) for c in (r, g, b))
    else:
        r, g, b = (int(c * f) for c in (r, g, b))
    return "#%02x%02x%02x" % (r, g, b)


def nearest_wheel(hex_color: str) -> str:
    """The colour-wheel colour whose hue is closest to this colour."""
    import colorsys
    r, g, b = (c / 255 for c in _hex_to_rgb(hex_color))
    h = colorsys.rgb_to_hsv(r, g, b)[0]
    def dist(name):
        hh = colorsys.rgb_to_hsv(*(c / 255 for c in _hex_to_rgb(HEX[name])))[0]
        d = abs(h - hh)
        return min(d, 1 - d)
    return min(WHEEL, key=dist)


def palette(base: str, scheme: str = "single") -> list[str]:
    """1–4 hex colours for a base colour name and a colour relationship."""
    base = base if base in HEX or base.startswith("#") else "cyan"
    bh = HEX.get(base, base)
    if scheme not in ("single", "monochromatic") and base not in WHEEL and base not in ("white", "gray", "black"):
        base = nearest_wheel(bh)          # cyan / any hex → the closest of the 12 wheel colours
    i = WHEEL.index(base) if base in WHEEL else None
    at = lambda k: HEX[WHEEL[(i + k) % 12]]
    if scheme == "rainbow":
        return [HEX[c] for c in ("red", "orange", "yellow", "green", "blue", "violet")]
    if scheme == "warm":
        return [HEX[c] for c in ("red", "vermilion", "orange", "amber")]
    if scheme == "cool":
        return [HEX[c] for c in ("teal", "blue", "violet", "purple")]
    if scheme == "grayscale":
        return ["#ffffff", "#c8cdd2", "#8a9096"]
    if scheme == "monochromatic":
        return [_shade(bh, 0.55), bh, _shade(bh, 1.45)]
    if i is None:                                        # cyan / white / gray / hex: no wheel position
        return [bh] if scheme == "single" else [_shade(bh, 0.6), bh, _shade(bh, 1.4)]
    return {"single": [bh], "analogous": [at(-1), bh, at(1)], "complementary": [bh, at(6)],
            "triadic": [bh, at(4), at(8)], "split complementary": [bh, at(5), at(7)],
            "square": [bh, at(3), at(6), at(9)]}.get(scheme, [bh])


def assign(points: np.ndarray, n_colors: int, scheme: str, seed: int = 3) -> np.ndarray:
    """Which palette colour each point gets: bands by height for gradients, sectors
    around the shape for triadic/square, random sparkle for monochromatic."""
    n = len(points)
    if n_colors <= 1:
        return np.zeros(n, int)
    if scheme in ("monochromatic", "grayscale"):
        return np.random.default_rng(seed).integers(0, n_colors, n)
    if scheme in ("triadic", "square", "split complementary"):
        ang = (np.arctan2(points[:, 2], points[:, 0]) + math.pi) / (2 * math.pi)
        return np.minimum((ang * n_colors).astype(int), n_colors - 1)
    y = points[:, 1]
    t = (y - y.min()) / (np.ptp(y) + 1e-9)
    return np.minimum((t * n_colors).astype(int), n_colors - 1)


# ── geometry helpers ─────────────────────────────────────────────────────────
_R = np.random.default_rng(7)


def _u(v):
    return v / (np.linalg.norm(v, axis=-1, keepdims=True) + 1e-12)


def _axis(p, axis):
    """Points built around Y → around the given axis."""
    if axis == "x":
        return p[:, [1, 0, 2]]
    if axis == "z":
        return p[:, [0, 2, 1]]
    return p


def sph(n, c=(0, 0, 0), r=1.0):
    return np.array(c, float) + _u(_R.normal(size=(n, 3))) * np.array(r, float)


def box(n, c=(0, 0, 0), size=(1, 1, 1)):
    size = np.array(size, float)
    p = (_R.random((n, 3)) - 0.5) * size
    k = _R.integers(0, 3, n)
    p[np.arange(n), k] = np.sign(_R.random(n) - 0.5) * size[k] / 2
    return np.array(c, float) + p


def cyl(n, c=(0, 0, 0), r=0.5, h=1.0, axis="y", caps=True):
    th = _R.random(n) * 2 * np.pi
    y = (_R.random(n) - 0.5) * h
    rr = np.full(n, float(r))
    if caps:
        m = _R.random(n) < 0.25
        y[m] = np.sign(_R.random(m.sum()) - 0.5) * h / 2
        rr[m] = r * np.sqrt(_R.random(m.sum()))
    return np.array(c, float) + _axis(np.stack([rr * np.cos(th), y, rr * np.sin(th)], 1), axis)


def cone(n, c=(0, 0, 0), r=0.5, h=1.0, axis="y"):
    t = np.sqrt(_R.random(n))                       # more points near the wide base
    th = _R.random(n) * 2 * np.pi
    y = h * (1 - t) - h / 2
    rr = r * t
    return np.array(c, float) + _axis(np.stack([rr * np.cos(th), y, rr * np.sin(th)], 1), axis)


def torus(n, c=(0, 0, 0), R=0.7, r=0.2, axis="y"):
    a, b = _R.random(n) * 2 * np.pi, _R.random(n) * 2 * np.pi
    p = np.stack([(R + r * np.cos(b)) * np.cos(a), r * np.sin(b), (R + r * np.cos(b)) * np.sin(a)], 1)
    return np.array(c, float) + _axis(p, axis)


def ring(n, c=(0, 0, 0), R=1.0, axis="y", w=0.0):
    a = _R.random(n) * 2 * np.pi
    rr = R + (_R.random(n) - 0.5) * w
    return np.array(c, float) + _axis(np.stack([rr * np.cos(a), np.zeros(n), rr * np.sin(a)], 1), axis)


def line(n, a, b, j=0.01):
    t = _R.random((n, 1))
    return np.array(a, float) + (np.array(b, float) - np.array(a, float)) * t + _R.normal(0, j, (n, 3))


def curve(fn, n, tube=0.0):
    t = _R.random(n)
    p = np.array([fn(x) for x in t], float)
    return p + (_R.normal(0, tube, (n, 3)) if tube else 0)


def lathe(n, profile, axis="y"):
    """profile: [(radius, y), ...] from bottom to top → surface of revolution."""
    pr = np.array(profile, float)
    seg = np.linalg.norm(np.diff(pr, axis=0), axis=1)
    cum = np.concatenate([[0], np.cumsum(seg)])
    s = _R.random(n) * cum[-1]
    k = np.clip(np.searchsorted(cum, s) - 1, 0, len(seg) - 1)
    f = ((s - cum[k]) / (seg[k] + 1e-12))[:, None]
    rp = pr[k] + (pr[k + 1] - pr[k]) * f
    th = _R.random(n) * 2 * np.pi
    return _axis(np.stack([rp[:, 0] * np.cos(th), rp[:, 1], rp[:, 0] * np.sin(th)], 1), axis)


def edges(verts, pairs, n):
    v = np.array(verts, float)
    per = max(2, n // max(1, len(pairs)))
    return np.vstack([line(per, v[a], v[b], 0.006) for a, b in pairs])


def surf(fn, n):
    u, v = _R.random(n), _R.random(n)
    return np.array([fn(a, b) for a, b in zip(u, v)], float)


def hull_edges(verts, length=None):
    v = np.array(verts, float)
    d = np.linalg.norm(v[:, None] - v[None], axis=2)
    L = length or np.min(d[d > 1e-6]) * 1.01
    return [(i, j) for i in range(len(v)) for j in range(i + 1, len(v)) if d[i, j] <= L]


PHI = (1 + 5 ** 0.5) / 2


# ── the shapes (each returns points; ~2,200 per shape) ───────────────────────
N = 2200


def s_sphere():      return sph(N)
def s_cube():        return box(N, size=(1.4, 1.4, 1.4))
def s_cone():        return cone(N, r=0.8, h=1.6)
def s_cylinder():    return cyl(N, r=0.6, h=1.6)
def s_torus():       return torus(N, R=0.75, r=0.28)
def s_capsule():     return np.vstack([cyl(N // 2, r=0.45, h=1.0, caps=False), sph(N // 4, (0, 0.5, 0), 0.45), sph(N // 4, (0, -0.5, 0), 0.45)])
def s_ring():        return np.vstack([ring(N // 2, R=1.0, w=0.05), ring(N // 2, R=0.8, w=0.05)])


def s_pyramid():
    v = [(-1, -0.8, -1), (1, -0.8, -1), (1, -0.8, 1), (-1, -0.8, 1), (0, 0.9, 0)]
    return np.vstack([edges(v, [(0, 1), (1, 2), (2, 3), (3, 0), (0, 4), (1, 4), (2, 4), (3, 4)], N // 2),
                      box(N // 2, (0, -0.8, 0), (2, 0.0, 2))])


def s_tetrahedron():
    v = [(1, 1, 1), (1, -1, -1), (-1, 1, -1), (-1, -1, 1)]
    return edges(v, hull_edges(v), N)


def s_octahedron():
    v = [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)]
    return edges(v, hull_edges(v), N)


def s_icosahedron():
    v = [(0, s1, s2 * PHI) for s1 in (-1, 1) for s2 in (-1, 1)] + [(s1, s2 * PHI, 0) for s1 in (-1, 1) for s2 in (-1, 1)] \
        + [(s2 * PHI, 0, s1) for s1 in (-1, 1) for s2 in (-1, 1)]
    return edges(v, hull_edges(v), N)


def s_dodecahedron():
    v = [(a, b, c) for a in (-1, 1) for b in (-1, 1) for c in (-1, 1)]
    for a in (-1, 1):
        for b in (-1, 1):
            v += [(0, a / PHI, b * PHI), (a / PHI, b * PHI, 0), (a * PHI, 0, b / PHI)]
    return edges(v, hull_edges(v), N)


def s_tesseract():
    v4 = np.array([(a, b, c, d) for a in (-1, 1) for b in (-1, 1) for c in (-1, 1) for d in (-1, 1)], float)
    v3 = v4[:, :3] / (2.6 - v4[:, 3:4] * 0.9)          # 4D → 3D perspective
    pairs = [(i, j) for i in range(16) for j in range(i + 1, 16) if np.sum(v4[i] != v4[j]) == 1]
    return edges(v3, pairs, N)


def s_prism():
    a = np.linspace(0, 2 * np.pi, 7)[:-1]
    top = [(math.cos(x), 0.8, math.sin(x)) for x in a]; bot = [(math.cos(x), -0.8, math.sin(x)) for x in a]
    v = top + bot
    pairs = [(i, (i + 1) % 6) for i in range(6)] + [(6 + i, 6 + (i + 1) % 6) for i in range(6)] + [(i, i + 6) for i in range(6)]
    return edges(v, pairs, N)


def s_star():
    pts = []
    for k in range(10):
        r = 1.0 if k % 2 == 0 else 0.42
        a = math.pi / 2 + k * math.pi / 5
        pts.append((r * math.cos(a), r * math.sin(a)))
    out = []
    for z in np.linspace(-0.18, 0.18, 5):
        for k in range(10):
            (x1, y1), (x2, y2) = pts[k], pts[(k + 1) % 10]
            out.append(line(N // 50, (x1, y1, z), (x2, y2, z), 0.004))
    out.append(np.column_stack([_R.normal(0, 0.25, N // 5), _R.normal(0, 0.25, N // 5), _R.normal(0, 0.06, N // 5)]))
    return np.vstack(out)


def s_heart():
    t = _R.random(N) * 2 * np.pi
    s = np.sqrt(_R.random(N))
    x = 16 * np.sin(t) ** 3 * s
    y = (13 * np.cos(t) - 5 * np.cos(2 * t) - 2 * np.cos(3 * t) - np.cos(4 * t)) * s
    z = _R.normal(0, 1, N) * 4 * np.sqrt(np.clip(1 - s ** 2, 0, 1)) + _R.normal(0, 0.3, N)
    return np.stack([x, y, z], 1)


def s_diamond():     return lathe(N, [(0, -1), (0.9, 0.25), (0.6, 0.55), (0, 0.55)])
def s_vase():        return lathe(N, [(0.35, -1), (0.6, -0.7), (0.7, -0.2), (0.35, 0.4), (0.3, 0.7), (0.45, 1)])
def s_trophy():      return np.vstack([lathe(N * 2 // 3, [(0.5, -1), (0.5, -0.85), (0.12, -0.75), (0.1, -0.2), (0.7, 0.1), (0.75, 0.9)]),
                                       torus(N // 6, (0.82, 0.45, 0), 0.22, 0.04, "z"), torus(N // 6, (-0.82, 0.45, 0), 0.22, 0.04, "z")])
def s_bell():        return lathe(N, [(0.95, -0.9), (0.7, -0.6), (0.55, 0.1), (0.4, 0.6), (0.15, 0.85), (0.0, 0.9)])
def s_cup():         return np.vstack([lathe(N * 4 // 5, [(0.5, -0.8), (0.6, 0.6), (0.62, 0.6)]), torus(N // 5, (0.7, -0.1, 0), 0.25, 0.05, "z")])
def s_lightbulb():   return np.vstack([sph(N * 2 // 3, (0, 0.3, 0), 0.65), cyl(N // 3, (0, -0.55, 0), 0.25, 0.45)])
def s_chess_pawn():  return lathe(N, [(0.6, -1), (0.6, -0.85), (0.3, -0.7), (0.18, 0.1), (0.35, 0.2), (0.18, 0.3), (0.3, 0.55), (0.3, 0.85), (0.0, 1.0)])
def s_chess_king():  return np.vstack([lathe(N * 4 // 5, [(0.6, -1), (0.6, -0.85), (0.3, -0.7), (0.2, 0.3), (0.4, 0.45), (0.25, 0.55), (0.4, 0.75), (0, 0.8)]),
                                       box(N // 10, (0, 0.95, 0), (0.08, 0.35, 0.08)), box(N // 10, (0, 1.0, 0), (0.3, 0.08, 0.08))])


def s_helix():       return curve(lambda t: (0.6 * math.cos(t * 6 * math.pi), t * 2 - 1, 0.6 * math.sin(t * 6 * math.pi)), N, 0.03)
def s_spring():      return curve(lambda t: (0.6 * math.cos(t * 16 * math.pi), t * 2 - 1, 0.6 * math.sin(t * 16 * math.pi)), N, 0.015)


def s_dna():
    a = curve(lambda t: (0.5 * math.cos(t * 6 * math.pi), t * 2.2 - 1.1, 0.5 * math.sin(t * 6 * math.pi)), N * 2 // 5, 0.02)
    b = curve(lambda t: (0.5 * math.cos(t * 6 * math.pi + math.pi), t * 2.2 - 1.1, 0.5 * math.sin(t * 6 * math.pi + math.pi)), N * 2 // 5, 0.02)
    rungs = []
    for k in range(18):
        t = k / 17; th = t * 6 * math.pi; y = t * 2.2 - 1.1
        rungs.append(line(N // 90, (0.5 * math.cos(th), y, 0.5 * math.sin(th)), (-0.5 * math.cos(th), y, -0.5 * math.sin(th))))
    return np.vstack([a, b] + rungs)


def s_torus_knot():
    p, q = 2, 3
    return curve(lambda t: ((2 + math.cos(q * 2 * math.pi * t)) * math.cos(p * 2 * math.pi * t),
                            math.sin(q * 2 * math.pi * t), (2 + math.cos(q * 2 * math.pi * t)) * math.sin(p * 2 * math.pi * t)), N, 0.08)


def s_infinity():    return curve(lambda t: (math.cos(2 * math.pi * t) / (1 + math.sin(2 * math.pi * t) ** 2),
                                             math.sin(2 * math.pi * t) * math.cos(2 * math.pi * t) / (1 + math.sin(2 * math.pi * t) ** 2), 0), N, 0.05)
def s_lissajous():   return curve(lambda t: (math.sin(3 * 2 * math.pi * t + 0.5), math.sin(4 * 2 * math.pi * t), math.sin(5 * 2 * math.pi * t)), N, 0.01)
def s_mobius():      return surf(lambda u, v: ((1 + (v - 0.5) * 0.6 * math.cos(u * math.pi)) * math.cos(u * 2 * math.pi),
                                               (v - 0.5) * 0.6 * math.sin(u * math.pi),
                                               (1 + (v - 0.5) * 0.6 * math.cos(u * math.pi)) * math.sin(u * 2 * math.pi)), N)
def s_wave():        return surf(lambda u, v: (u * 2 - 1, 0.25 * math.sin(u * 9) * math.cos(v * 7), v * 2 - 1), N)
def s_saddle():      return surf(lambda u, v: (u * 2 - 1, ((u * 2 - 1) ** 2 - (v * 2 - 1) ** 2) * 0.6, v * 2 - 1), N)
def s_hyperboloid(): return surf(lambda u, v: (0.4 * math.cosh(v * 2 - 1) * math.cos(u * 2 * math.pi), (v * 2 - 1),
                                               0.4 * math.cosh(v * 2 - 1) * math.sin(u * 2 * math.pi)), N)
def s_wormhole():    return surf(lambda u, v: ((0.25 + 1.2 * (v * 2 - 1) ** 2) * math.cos(u * 2 * math.pi), (v * 2 - 1),
                                               (0.25 + 1.2 * (v * 2 - 1) ** 2) * math.sin(u * 2 * math.pi)), N)


def s_atom():
    nuc = np.vstack([sph(N // 14, c, 0.12) for c in _R.normal(0, 0.1, (6, 3))])
    orbits = [_rot(ring(N // 4, R=1.0, w=0.02), a) for a in ((1.2, 0), (-1.2, 0.5), (0, 1.3))]
    electrons = [sph(N // 25, _rot(np.array([[1.0, 0, 0]]), a)[0], 0.07) for a in ((1.2, 0), (-1.2, 0.5), (0, 1.3))]
    return np.vstack([nuc] + orbits + electrons)


def _rot(p, ang):
    """Tilt points: ang = (about x, about z) in radians."""
    ax, az = ang
    cx, sx, cz, sz = math.cos(ax), math.sin(ax), math.cos(az), math.sin(az)
    x, y, z = p[:, 0], p[:, 1], p[:, 2]
    y, z = y * cx - z * sx, y * sx + z * cx
    x, y = x * cz - y * sz, x * sz + y * cz
    return np.stack([x, y, z], 1)


def s_solar_system():
    parts = [sph(N // 5, (0, 0, 0), 0.22)]
    for k, (R, r) in enumerate(((0.38, 0.03), (0.52, 0.05), (0.68, 0.055), (0.84, 0.04), (1.05, 0.11))):
        parts.append(ring(N // 12, R=R, w=0.005))
        a = k * 1.3
        parts.append(sph(N // 30 + int(r * 600), (R * math.cos(a), 0, R * math.sin(a)), r))
    return np.vstack(parts)


def s_saturn():      return np.vstack([sph(N // 2, r=0.55), _rot(np.vstack([ring(N // 4, R=0.85, w=0.12), ring(N // 4, R=1.05, w=0.18)]), (0.35, 0.15))])


def s_galaxy():
    k = _R.integers(0, 2, N)
    r = _R.random(N) ** 0.7
    a = r * 4.0 + k * math.pi + _R.normal(0, 0.25, N)
    p = np.stack([r * np.cos(a), _R.normal(0, 0.04, N) * (1 - r), r * np.sin(a)], 1)
    return np.vstack([p, sph(N // 6, r=0.12)])


def s_black_hole():
    r = 0.35 + _R.random(N) ** 1.5 * 0.75
    a = _R.random(N) * 2 * np.pi
    disk = np.stack([r * np.cos(a), _R.normal(0, 0.02, N), r * np.sin(a)], 1)
    return np.vstack([_rot(disk, (0.25, 0)), ring(N // 3, R=0.33, axis="z", w=0.02)])


def s_globe():
    lat = np.vstack([ring(N // 14, (0, math.sin(b), 0), math.cos(b)) for b in np.linspace(-1.2, 1.2, 7)])
    lon = np.vstack([_rotY(ring(N // 14, R=1.0, axis="z"), a) for a in np.linspace(0, math.pi, 7, endpoint=False)])
    return np.vstack([lat, lon])


def _rotY(p, a):
    c, s = math.cos(a), math.sin(a)
    return np.stack([p[:, 0] * c + p[:, 2] * s, p[:, 1], -p[:, 0] * s + p[:, 2] * c], 1)


def s_sun():
    rays = [line(N // 40, (0, 0, 0), tuple(d * 1.3), 0.01) for d in _u(_R.normal(size=(24, 3)))]
    return np.vstack([sph(N // 2, r=0.6)] + rays)


def s_comet():
    tail = np.stack([_R.random(N) ** 2 * 2.0, _R.normal(0, 1, N), _R.normal(0, 1, N)], 1)
    tail[:, 1:] *= (0.04 + tail[:, :1] * 0.18)
    return np.vstack([sph(N // 5, (0, 0, 0), 0.15), tail * [1, 1, 1]]) - [0.8, 0, 0]


def s_molecule():
    atoms = [((0, 0, 0), 0.3), ((0.75, 0.45, 0), 0.18), ((-0.75, 0.45, 0), 0.18), ((0, -0.8, 0.3), 0.22), ((0.6, -1.2, 0.5), 0.15)]
    parts = [sph(N // 8, c, r) for c, r in atoms]
    for a, b in ((0, 1), (0, 2), (0, 3), (3, 4)):
        parts.append(line(N // 25, atoms[a][0], atoms[b][0], 0.02))
    return np.vstack(parts)


def s_arc_reactor():
    return np.vstack([ring(N // 5, R=1.0, axis="z", w=0.03), ring(N // 5, R=0.8, axis="z", w=0.02),
                      ring(N // 6, R=0.45, axis="z", w=0.02), sph(N // 6, r=(0.3, 0.3, 0.08))]
                     + [line(N // 60, (0.45 * math.cos(a), 0.45 * math.sin(a), 0), (0.8 * math.cos(a), 0.8 * math.sin(a), 0))
                        for a in np.linspace(0, 2 * math.pi, 10, endpoint=False)])


def s_gear():
    t = _R.random(N) * 2 * np.pi
    r = 0.8 + 0.18 * (np.sin(t * 12) > 0)
    z = (_R.random(N) - 0.5) * 0.3
    return np.vstack([np.stack([r * np.cos(t), r * np.sin(t), z], 1), ring(N // 5, R=0.25, axis="z", w=0.05)])


def s_drone():
    arms = [line(N // 12, (0, 0, 0), (0.75 * math.cos(a), 0, 0.75 * math.sin(a))) for a in (0.785, 2.356, 3.927, 5.498)]
    rotors = [ring(N // 8, (0.75 * math.cos(a), 0.06, 0.75 * math.sin(a)), 0.3, w=0.02) for a in (0.785, 2.356, 3.927, 5.498)]
    return np.vstack([box(N // 6, size=(0.4, 0.15, 0.4))] + arms + rotors)


def s_rocket():
    return np.vstack([cyl(N // 2, (0, -0.1, 0), 0.25, 1.3), cone(N // 5, (0, 0.85, 0), 0.25, 0.5),
                      box(N // 12, (0.3, -0.65, 0), (0.25, 0.3, 0.03)), box(N // 12, (-0.3, -0.65, 0), (0.25, 0.3, 0.03)),
                      cone(N // 8, (0, -0.95, 0), 0.15, -0.3)])


def s_satellite():
    return np.vstack([box(N // 3, size=(0.45, 0.45, 0.45)), box(N // 4, (0.9, 0, 0), (0.9, 0.02, 0.4)),
                      box(N // 4, (-0.9, 0, 0), (0.9, 0.02, 0.4)), cone(N // 8, (0, 0.4, 0), 0.25, -0.2)])


def s_shield():
    """A knight's (heater) shield: flat top, curved sides meeting in a point, with a rim and a centre ridge."""
    def outline(t):                                  # t 0..1 around the edge
        if t < 0.25:                                 # top edge, left → right
            return (-0.8 + 6.4 * t, 0.9)
        u = (t - 0.25) / 0.75                        # right side down to the point and back up the left
        side = 1 if u < 0.5 else -1
        k = u * 2 if u < 0.5 else (1 - u) * 2       # 0 at top corner → 1 at the bottom point
        return (side * 0.8 * math.cos(k * math.pi / 2), 0.9 - 1.9 * k ** 1.15)
    ts = _R.random(N // 2)
    rim = np.array([(*outline(t), 0.0) for t in ts]) + _R.normal(0, 0.008, (N // 2, 3))
    face = []
    while len(face) < N // 2:                        # points inside the outline, slightly domed
        x, y = _R.uniform(-0.8, 0.8), _R.uniform(-1.0, 0.9)
        k = min(1.0, max(0.0, (0.9 - y) / 1.9)) ** (1 / 1.15)
        if abs(x) <= 0.8 * math.cos(k * math.pi / 2):
            face.append((x, y, 0.12 * (1 - (x / 0.8) ** 2)))
    ridge = line(N // 10, (0, 0.85, 0.13), (0, -0.85, 0.05))
    return np.vstack([rim, np.array(face), ridge])
def s_sword():       return np.vstack([box(N // 2, (0, 0.35, 0), (0.12, 1.3, 0.02)), cone(N // 10, (0, 1.05, 0), 0.06, 0.15),
                                       box(N // 6, (0, -0.35, 0), (0.6, 0.06, 0.08)), cyl(N // 6, (0, -0.65, 0), 0.04, 0.5)])
def s_hammer():      return np.vstack([box(N * 2 // 3, (0, 0.55, 0), (0.75, 0.4, 0.4)), cyl(N // 3, (0, -0.3, 0), 0.06, 1.3)])


def s_tower():
    v = [(-0.5, -1, -0.5), (0.5, -1, -0.5), (0.5, -1, 0.5), (-0.5, -1, 0.5), (0, 1, 0)]
    ls = [(i, 4) for i in range(4)] + [(0, 1), (1, 2), (2, 3), (3, 0)]
    cross = [line(N // 40, (-0.5 + 0.5 * f, -1 + 2 * f, -0.5 + 0.5 * f), (0.5 - 0.5 * g, -1 + 2 * g, -0.5 + 0.5 * g))
             for f, g in ((0, 0.25), (0.25, 0.5), (0.5, 0.75))]
    rings_ = [_square((0, -1 + 2 * f, 0), 0.5 * (1 - f)) for f in (0.25, 0.5, 0.75)]
    return np.vstack([edges(v, ls, N // 2)] + cross + rings_)


def _square(c, h):
    x, y, z = c
    return np.vstack([line(40, (x - h, y, z - h), (x + h, y, z - h)), line(40, (x + h, y, z - h), (x + h, y, z + h)),
                      line(40, (x + h, y, z + h), (x - h, y, z + h)), line(40, (x - h, y, z + h), (x - h, y, z - h))])


def s_house():
    v = [(-1, -0.8, -0.7), (1, -0.8, -0.7), (1, -0.8, 0.7), (-1, -0.8, 0.7), (-1, 0.2, -0.7), (1, 0.2, -0.7),
         (1, 0.2, 0.7), (-1, 0.2, 0.7), (-1, 0.9, 0), (1, 0.9, 0)]
    pairs = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7),
             (4, 8), (7, 8), (5, 9), (6, 9), (8, 9)]
    return np.vstack([edges(v, pairs, N * 3 // 4), box(N // 4, (0, -0.45, 0.7), (0.35, 0.7, 0.0))])


def s_car():
    return np.vstack([box(N // 2, (0, -0.15, 0), (1.9, 0.4, 0.85)), box(N // 4, (-0.1, 0.25, 0), (0.95, 0.4, 0.8))]
                     + [torus(N // 16, (x, -0.38, z), 0.17, 0.06, "z") for x in (-0.6, 0.6) for z in (-0.45, 0.45)])


def s_plane():
    return np.vstack([cyl(N // 3, (0, 0, 0), 0.14, 1.9, "x"), box(N // 4, (0.05, 0, 0), (0.45, 0.03, 2.0)),
                      box(N // 10, (-0.85, 0.05, 0), (0.25, 0.03, 0.7)), box(N // 12, (-0.85, 0.25, 0), (0.25, 0.4, 0.03)),
                      cone(N // 12, (1.05, 0, 0), 0.14, -0.25, "x")])


def s_tree():
    trunk = cyl(N // 5, (0, -0.6, 0), 0.12, 0.9)
    crown = np.vstack([sph(N // 4, c, r) for c, r in (((0, 0.25, 0), 0.55), ((0.35, 0.05, 0.1), 0.35),
                                                       ((-0.35, 0.1, -0.1), 0.38), ((0, 0.65, 0), 0.35))])
    crown += _R.normal(0, 0.05, crown.shape)
    return np.vstack([trunk, crown])


def s_flower():
    petals = []
    for k in range(8):
        a = k * math.pi / 4
        petals.append(sph(N // 12, (0.35 * math.cos(a), 0.55, 0.35 * math.sin(a)), (0.25, 0.06, 0.12)))
    return np.vstack(petals + [sph(N // 10, (0, 0.58, 0), 0.14), line(N // 6, (0, -1, 0), (0, 0.5, 0), 0.02),
                               sph(N // 12, (0.25, -0.3, 0), (0.25, 0.04, 0.1))])


def s_mushroom():    return np.vstack([lathe(N * 2 // 3, [(0, 0.1), (0.95, 0.15), (0.75, 0.55), (0.3, 0.8), (0, 0.82)]), cyl(N // 3, (0, -0.4, 0), 0.22, 1.0)])


def s_crystal():
    parts = []
    for a, tilt, h in ((0, 0, 1.6), (1.2, 0.35, 1.1), (2.6, -0.4, 1.0), (4.0, 0.45, 0.8), (5.2, -0.3, 0.9)):
        p = np.vstack([cyl(N // 8, (0, 0, 0), 0.18, h, caps=False), cone(N // 25, (0, h / 2 + 0.12, 0), 0.18, 0.25)])
        p = _rot(p, (tilt * math.sin(a), tilt * math.cos(a)))
        parts.append(p + [0, -0.4, 0])
    return np.vstack(parts)


def s_mountain():
    x, z = _R.random(N) * 2 - 1, _R.random(N) * 2 - 1
    y = 0.9 * np.exp(-(x ** 2 + z ** 2) * 3) + 0.4 * np.exp(-((x - 0.5) ** 2 + (z + 0.3) ** 2) * 8) \
        + 0.04 * np.sin(x * 15) * np.cos(z * 13) - 0.6
    return np.stack([x, y, z], 1)


def s_butterfly():
    t = _R.random(N) * 12 * np.pi
    r = np.exp(np.sin(t)) - 2 * np.cos(4 * t) + np.sin((2 * t - np.pi) / 24) ** 5
    s = np.sqrt(_R.random(N))
    x, y = r * np.sin(t) * s, r * np.cos(t) * s
    z = np.abs(x) * 0.35
    return np.stack([x, y, z], 1)


def s_brain():
    p = np.vstack([sph(N // 2, (0.33, 0, 0), (0.42, 0.55, 0.7)), sph(N // 2, (-0.33, 0, 0), (0.42, 0.55, 0.7))])
    p += _u(p) * 0.05 * np.sin(p[:, :1] * 30 + p[:, 2:3] * 25)
    return p


def s_eye():
    return np.vstack([sph(N // 2, r=1.0), ring(N // 6, (0, 0, 0.92), 0.4, "z", 0.15), sph(N // 6, (0, 0, 0.95), (0.18, 0.18, 0.04))])


def s_cross():       return np.vstack([box(N // 2, size=(0.35, 2.0, 0.35)), box(N // 2, (0, 0.3, 0), (1.3, 0.35, 0.35))])
def s_moon_phase():  return np.vstack([sph(N, r=1.0)])


def s_suit():
    return None                                           # the window builds the armour suit itself


BUILTIN = {
    # geometry
    "sphere": s_sphere, "cube": s_cube, "pyramid": s_pyramid, "cone": s_cone, "cylinder": s_cylinder,
    "torus": s_torus, "capsule": s_capsule, "rings": s_ring, "tetrahedron": s_tetrahedron, "octahedron": s_octahedron,
    "icosahedron": s_icosahedron, "dodecahedron": s_dodecahedron, "tesseract": s_tesseract, "hexagonal prism": s_prism,
    "star": s_star, "heart": s_heart, "diamond": s_diamond, "cross": s_cross,
    # curves & surfaces
    "helix": s_helix, "spring": s_spring, "dna": s_dna, "torus knot": s_torus_knot, "infinity": s_infinity,
    "lissajous": s_lissajous, "mobius strip": s_mobius, "wave": s_wave, "saddle": s_saddle,
    "hyperboloid": s_hyperboloid, "wormhole": s_wormhole,
    # science & space
    "atom": s_atom, "solar system": s_solar_system, "saturn": s_saturn, "galaxy": s_galaxy, "black hole": s_black_hole,
    "globe": s_globe, "sun": s_sun, "comet": s_comet, "molecule": s_molecule, "brain": s_brain, "eye": s_eye,
    "moon": s_moon_phase,
    # tech
    "reactor core": s_arc_reactor, "gear": s_gear, "drone": s_drone, "rocket": s_rocket, "satellite": s_satellite,
    "shield": s_shield, "sword": s_sword, "hammer": s_hammer, "tower": s_tower, "house": s_house, "car": s_car,
    "plane": s_plane, "suit": s_suit,
    # nature & objects
    "tree": s_tree, "flower": s_flower, "mushroom": s_mushroom, "crystal": s_crystal, "mountain": s_mountain,
    "butterfly": s_butterfly, "vase": s_vase, "trophy": s_trophy, "bell": s_bell, "cup": s_cup,
    "lightbulb": s_lightbulb, "chess pawn": s_chess_pawn, "chess king": s_chess_king,
}
SYNONYMS = {"ball": "sphere", "box": "cube", "donut": "torus", "doughnut": "torus", "knot": "torus knot",
            "mobius": "mobius strip", "möbius": "mobius strip", "hypercube": "tesseract", "4d cube": "tesseract",
            "planet": "saturn", "ringed planet": "saturn", "earth": "globe", "world": "globe", "spiral galaxy": "galaxy",
            "reactor": "reactor core", "arc reactor": "reactor core", "cog": "gear", "quadcopter": "drone", "spaceship": "rocket", "airplane": "plane",
            "jet": "plane", "home": "house", "building": "tower", "armour": "suit", "armor": "suit", "iron suit": "suit",
            "robot suit": "suit", "gem": "diamond", "bulb": "lightbulb", "pawn": "chess pawn", "king": "chess king",
            "double helix": "dna", "coil": "spring", "flask": "vase", "planets": "solar system", "lemniscate": "infinity",
            "prism": "hexagonal prism", "love": "heart", "d20": "icosahedron", "dice": "cube"}


def names() -> list[str]:
    return sorted(BUILTIN)


def resolve(name: str) -> str | None:
    n = (name or "").strip().lower().replace("_", " ").replace("-", " ")
    if n.startswith("text:") or n.startswith("text "):
        return "text:" + name.split(":", 1)[-1].split(" ", 1)[-1].strip()[:16]
    if n in BUILTIN:
        return n
    if n in SYNONYMS:
        return SYNONYMS[n]
    for k in sorted(list(BUILTIN) + list(SYNONYMS), key=len, reverse=True):
        if k in n:
            return SYNONYMS.get(k, k)
    return None


def text_points(word: str, n: int = N) -> np.ndarray:
    from PIL import Image, ImageDraw, ImageFont
    word = (word or "JARVIS")[:16]
    font = None
    for f in ("arialbd.ttf", "DejaVuSans-Bold.ttf", "arial.ttf"):
        try:
            font = ImageFont.truetype(f, 120); break
        except Exception:
            continue
    font = font or ImageFont.load_default()
    img = Image.new("L", (130 * len(word) + 40, 170), 0)
    ImageDraw.Draw(img).text((20, 10), word, fill=255, font=font)
    a = np.asarray(img)
    ys, xs = np.nonzero(a > 128)
    if len(xs) == 0:
        return sph(n)
    k = _R.integers(0, len(xs), n)
    return np.stack([xs[k] + _R.random(n), -(ys[k] + _R.random(n)), _R.normal(0, 4, n)], 1)


PRIMS = ("sphere", "box", "cylinder", "cone", "torus", "ring", "line")


def from_primitives(parts: list, n: int = N) -> np.ndarray:
    """Build a custom shape from simple parts designed by JARVIS:
    {"type": sphere|box|cylinder|cone|torus|ring|line, "pos": [x,y,z], "size": [..], "axis": "x|y|z", "to": [x,y,z]}"""
    parts = [p for p in (parts or []) if isinstance(p, dict) and p.get("type") in PRIMS][:40]
    if not parts:
        raise ValueError("no usable parts")
    per = max(40, n // len(parts))
    out = []
    for p in parts:
        c = [float(v) for v in (p.get("pos") or [0, 0, 0])][:3] + [0.0] * (3 - len((p.get("pos") or [0, 0, 0])[:3]))
        s = p.get("size") or [0.3]
        s = [float(v) for v in (s if isinstance(s, list) else [s])]
        ax = p.get("axis", "y") if p.get("axis") in ("x", "y", "z") else "y"
        t = p["type"]
        if t == "sphere":
            out.append(sph(per, c, s if len(s) == 3 else s[0]))
        elif t == "box":
            out.append(box(per, c, (s + s * 3)[:3] if len(s) < 3 else s[:3]))
        elif t == "cylinder":
            out.append(cyl(per, c, s[0], s[1] if len(s) > 1 else s[0] * 2, ax))
        elif t == "cone":
            out.append(cone(per, c, s[0], s[1] if len(s) > 1 else s[0] * 2, ax))
        elif t == "torus":
            out.append(torus(per, c, s[0], s[1] if len(s) > 1 else s[0] * 0.25, ax))
        elif t == "ring":
            out.append(ring(per, c, s[0], ax, 0.02))
        elif t == "line":
            out.append(line(per, c, [float(v) for v in (p.get("to") or [0, 1, 0])][:3]))
    return np.vstack(out)


CUSTOM_PROMPT = ("Design a 3D hologram of '{what}' using ONLY simple parts. Coordinates: y is up, the whole object fits in "
                 "a box from -1 to 1 on every axis. Use 4 to 30 parts. ONLY JSON, a list like: "
                 '[{{"type":"sphere","pos":[0,0.6,0],"size":[0.3]}}, {{"type":"box","pos":[0,0,0],"size":[0.6,0.8,0.4]}}, '
                 '{{"type":"cylinder","pos":[0,-0.6,0],"size":[0.1,0.6],"axis":"y"}}, {{"type":"cone","pos":[0,1,0],"size":[0.2,0.4]}}, '
                 '{{"type":"torus","pos":[0,0,0],"size":[0.5,0.08],"axis":"y"}}, {{"type":"ring","pos":[0,0,0],"size":[0.9],"axis":"y"}}, '
                 '{{"type":"line","pos":[0,0,0],"to":[0.5,0.5,0]}}]. Types allowed: sphere (size [r] or [rx,ry,rz]), box '
                 "(size [w,h,d]), cylinder/cone (size [radius,height], axis), torus (size [R,r], axis), ring (size [R], axis), "
                 "line (pos → to). Make it clearly recognisable.")


def normalise(p: np.ndarray, n: int = N) -> np.ndarray:
    p = np.asarray(p, float)
    if len(p) > n:
        p = p[_R.choice(len(p), n, replace=False)]
    p = p - (p.max(0) + p.min(0)) / 2
    r = np.linalg.norm(p, axis=1).max() or 1.0
    return p / r


def build(name: str, primitives: list | None = None) -> np.ndarray | None:
    """Points for a shape name (or custom primitives). None = the armour suit."""
    if primitives:
        return normalise(from_primitives(primitives))
    key = resolve(name)
    if key is None:
        raise KeyError(name)
    if key.startswith("text:"):
        return normalise(text_points(key[5:]))
    if key == "suit":
        return None
    return normalise(BUILTIN[key]())


# ════════════════════════════════════════════════════════════════════════════
# 2.2 — 73 MORE SHAPES
# ════════════════════════════════════════════════════════════════════════════
def _jit(p, s=0.006):
    return p + _R.normal(0, s, p.shape)


def _bezier(n, pts):
    """Points along a Catmull-Rom-ish smooth path through control points."""
    P = np.array(pts, float)
    t = _R.random(n) * (len(P) - 1)
    k = np.minimum(t.astype(int), len(P) - 2)
    f = (t - k)[:, None]
    p0, p1 = P[np.maximum(k - 1, 0)], P[k]
    p2, p3 = P[k + 1], P[np.minimum(k + 2, len(P) - 1)]
    return 0.5 * ((2 * p1) + (-p0 + p2) * f + (2 * p0 - 5 * p1 + 4 * p2 - p3) * f ** 2 + (-p0 + 3 * p1 - 3 * p2 + p3) * f ** 3)


def _attractor(step, x0, n=N, burn=300, dt=0.01, every=3):
    x = np.array(x0, float)
    out = []
    for i in range(burn + n * every):
        x = x + np.array(step(*x)) * dt
        if i >= burn and i % every == 0:
            out.append(x.copy())
    return np.array(out)


# ── space & science ──────────────────────────────────────────────────────────
def s_nebula():
    blobs = [(_R.normal(0, 0.45, 3), _R.uniform(0.2, 0.45)) for _ in range(9)]
    return np.vstack([np.array(c) + _R.normal(0, 1, (N // 9, 3)) * r * np.array([1.4, 0.7, 1.0]) for c, r in blobs])


def s_pulsar():
    beams = [cone(N // 5, (0, sgn * 0.7, 0), 0.22, -sgn * 1.0) for sgn in (1, -1)]
    field = []
    for a in np.linspace(0, 2 * math.pi, 8, endpoint=False):     # dipole field loops around the star
        th = _R.random(N // 16) * math.pi
        r = 0.9 * np.sin(th) ** 2
        field.append(np.stack([r * np.sin(th) * math.cos(a), r * np.cos(th), r * np.sin(th) * math.sin(a)], 1))
    return np.vstack([sph(N // 8, r=0.18)] + beams + field)


def s_supernova():
    core = sph(N // 6, r=0.15)
    shell = sph(N // 2, r=1.0) * (0.85 + 0.15 * _R.random((N // 2, 1)))
    rays = np.vstack([line(N // 60, (0, 0, 0), tuple(d)) for d in _u(_R.normal(size=(20, 3))) * _R.uniform(0.6, 1.0, (20, 1))])
    return np.vstack([core, shell, rays])


def s_asteroid():
    d = _u(_R.normal(size=(N, 3)))
    bump = 0.75 + 0.12 * np.sin(3 * d[:, 0] + 1) * np.cos(4 * d[:, 1]) + 0.08 * np.sin(7 * d[:, 2] + 2)
    for c in _u(_R.normal(size=(7, 3))):                          # craters
        bump -= 0.12 * np.exp(-np.linalg.norm(d - c, axis=1) ** 2 / 0.03)
    return d * bump[:, None] * np.array([1.0, 0.75, 0.85])


def s_space_station():
    spokes = [line(N // 20, (0, 0, 0), (0.85 * math.cos(a), 0, 0.85 * math.sin(a))) for a in np.linspace(0, 2 * math.pi, 6, endpoint=False)]
    return np.vstack([torus(N // 2, R=0.9, r=0.1), cyl(N // 8, r=0.12, h=0.9), sph(N // 10, r=0.18)] + spokes
                     + [box(N // 12, (0, 0.6, 0), (1.4, 0.02, 0.35))])


def s_ufo():
    disc = lathe(N * 2 // 3, [(0.0, -0.18), (0.6, -0.12), (1.0, 0.0), (0.6, 0.1), (0.35, 0.14)])
    dome = sph(N // 4, (0, 0.14, 0), (0.35, 0.3, 0.35))
    dome = dome[dome[:, 1] >= 0.14]
    lights = ring(N // 10, (0, -0.05, 0), 0.8, w=0.02)
    beam = cone(N // 8, (0, -0.65, 0), 0.5, -0.9)
    return np.vstack([disc, dome, lights, beam])


def s_radio_dish():
    r = np.sqrt(_R.random(N // 2)) * 0.9
    a = _R.random(N // 2) * 2 * np.pi
    dish = np.stack([r * np.cos(a), 0.45 * r ** 2, r * np.sin(a)], 1)
    dish = _rot(dish, (0.6, 0)) + np.array([0, 0.25, 0])
    return np.vstack([dish, line(N // 12, (0, 0.25, 0), (0, 0.95, -0.25)), cyl(N // 6, (0, -0.4, 0), 0.08, 0.9),
                      cone(N // 8, (0, -0.9, 0), 0.4, 0.15)])


def s_telescope():
    tube = _rot(cyl(N // 2, (0, 0, 0), 0.16, 1.4), (0, 0.7)) + np.array([0, 0.35, 0])
    legs = [line(N // 10, (0, -0.1, 0), (0.6 * math.cos(a), -1.0, 0.6 * math.sin(a))) for a in (0.3, 2.4, 4.5)]
    return np.vstack([tube, ring(N // 10, (0.48, 0.85, 0), 0.2, "x", 0.02)] + legs)


def s_magnetic_field():
    out = [sph(N // 10, r=(0.12, 0.3, 0.12))]
    for a in np.linspace(0, 2 * math.pi, 10, endpoint=False):
        for L in (0.5, 0.8, 1.1):
            th = _R.uniform(0.15, math.pi - 0.15, N // 34)
            r = L * np.sin(th) ** 2
            out.append(np.stack([r * np.sin(th) * math.cos(a), r * np.cos(th), r * np.sin(th) * math.sin(a)], 1))
    return np.vstack(out)


def s_orbitals():
    out = [sph(N // 10, r=0.08)]
    for ax in range(3):
        for s in (1, -1):
            c = np.zeros(3); c[ax] = 0.5 * s
            r = np.array([0.22, 0.22, 0.22]); r[ax] = 0.42
            out.append(sph(N // 7, tuple(c), tuple(r)) * (0.6 + 0.4 * _R.random((N // 7, 1))))
    return np.vstack(out)


def s_crystal_lattice():
    g = np.linspace(-0.8, 0.8, 4)
    nodes = np.array([(x, y, z) for x in g for y in g for z in g])
    atoms = np.vstack([sph(18, tuple(c), 0.07) for c in nodes])
    pairs = hull_edges(nodes)
    return np.vstack([atoms, edges(nodes, pairs, N // 2)])


def _ico():
    v = [(-1, PHI, 0), (1, PHI, 0), (-1, -PHI, 0), (1, -PHI, 0), (0, -1, PHI), (0, 1, PHI), (0, -1, -PHI), (0, 1, -PHI),
         (PHI, 0, -1), (PHI, 0, 1), (-PHI, 0, -1), (-PHI, 0, 1)]
    return _u(np.array(v, float))


def s_buckyball():
    ico = _ico()
    pr = hull_edges(ico)
    verts = []
    for a, b in pr:                                   # truncate each edge at 1/3 and 2/3 → C60
        verts += [ico[a] + (ico[b] - ico[a]) / 3, ico[a] + 2 * (ico[b] - ico[a]) / 3]
    v = _u(np.array(verts))
    return np.vstack([np.vstack([sph(10, tuple(c), 0.035) for c in v]), edges(v, hull_edges(v), N * 2 // 3)])


def s_geodesic():
    v = _ico()
    pr = hull_edges(v)
    mids = _u(np.array([(v[a] + v[b]) / 2 for a, b in pr]))
    allv = np.vstack([v, mids])
    return edges(allv, hull_edges(allv), N)


def s_virus():
    body = sph(N // 2, r=0.6)
    spikes = []
    for d in _u(_R.normal(size=(40, 3))):
        spikes.append(line(N // 140, tuple(d * 0.6), tuple(d * 0.9)))
        spikes.append(sph(N // 140, tuple(d * 0.93), 0.06))
    return np.vstack([body] + spikes)


def s_neuron():
    out = [sph(N // 6, r=0.22)]
    def branch(start, d, length, depth):
        end = start + d * length
        out.append(line(max(8, int(N // 30 * length)), tuple(start), tuple(end), 0.008))
        if depth > 0:
            for _ in range(2):
                nd = _u(d + _R.normal(0, 0.55, 3))
                branch(end, nd, length * 0.62, depth - 1)
    for d in _u(_R.normal(size=(6, 3))):
        if d[0] < 0.3:
            branch(d * 0.2, d, 0.35, 3)
    out.append(line(N // 6, (0.2, 0, 0), (1.0, 0.1, 0.0), 0.012))           # axon
    for k in range(4):
        out.append(ring(N // 40, (0.35 + k * 0.17, 0.03 * k, 0), 0.05, "x", 0.01))
    return np.vstack(out)


# ── maths & fractals ─────────────────────────────────────────────────────────
def s_lorenz():
    p = _attractor(lambda x, y, z: (10 * (y - x), x * (28 - z) - y, x * y - 8 / 3 * z), (0.1, 0, 20), dt=0.006)
    return np.stack([p[:, 0], p[:, 2] - 25, p[:, 1] * 0.6], 1)          # the "butterfly" faces you


def s_aizawa():
    a, b, c, d, e, f = 0.95, 0.7, 0.6, 3.5, 0.25, 0.1
    p = _attractor(lambda x, y, z: ((z - b) * x - d * y, d * x + (z - b) * y,
                                    c + a * z - z ** 3 / 3 - (x * x + y * y) * (1 + e * z) + f * z * x ** 3),
                   (0.1, 0, 0), dt=0.01)
    return np.stack([p[:, 0], p[:, 2], p[:, 1]], 1)                     # its axis points up


def s_klein_bottle():
    def fn(u, v):
        u *= 2 * math.pi; v *= 2 * math.pi
        r = 4 * (1 - math.cos(u) / 2)
        if u < math.pi:
            x = 6 * math.cos(u) * (1 + math.sin(u)) + r * math.cos(u) * math.cos(v)
            y = 16 * math.sin(u) + r * math.sin(u) * math.cos(v)
        else:
            x = 6 * math.cos(u) * (1 + math.sin(u)) + r * math.cos(v + math.pi)
            y = 16 * math.sin(u)
        return (x, -y, r * math.sin(v))
    return surf(fn, N)


def s_trefoil():
    return curve(lambda t: (math.sin(2 * math.pi * t) + 2 * math.sin(4 * math.pi * t),
                            math.cos(2 * math.pi * t) - 2 * math.cos(4 * math.pi * t),
                            -math.sin(6 * math.pi * t)), N, 0.06)


def s_sierpinski():
    v = np.array([(0, 1, 0), (-0.94, -0.33, -0.54), (0.94, -0.33, -0.54), (0, -0.33, 1.09)])
    p = np.zeros(3); out = []
    for i in range(N + 20):
        p = (p + v[_R.integers(0, 4)]) / 2
        if i >= 20:
            out.append(p.copy())
    return np.array(out)


def s_menger():
    cells = [(i, j, k) for i in (-1, 0, 1) for j in (-1, 0, 1) for k in (-1, 0, 1)
             if (i == 0) + (j == 0) + (k == 0) < 2]           # 20 cubes: the holes go right through
    ed = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)]
    out = []
    for i, j, k in cells:                                       # see-through → glowing edges read best
        c = np.array([i, j, k]) * 0.5
        v = [c + 0.22 * np.array(d) for d in [(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
                                              (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]]
        out.append(edges(v, ed, N // len(cells)))
    return np.vstack(out)


def s_mandelbrot():
    pts = []
    while len(pts) < N:
        c = complex(_R.uniform(-2.0, 0.6), _R.uniform(-1.2, 1.2))
        z, it = 0j, 0
        while abs(z) <= 2 and it < 60:
            z = z * z + c; it += 1
        if 12 <= it < 60:                            # near the edge of the set → the glowing outline
            pts.append((c.real + 0.7, c.imag, (it / 60) * 0.3))           # stands up, facing you
    return np.array(pts)


def s_fern():
    p = np.zeros(2); out = []
    for i in range(N + 20):
        r = _R.random()
        x, y = p
        if r < 0.01:   p = np.array([0, 0.16 * y])
        elif r < 0.86: p = np.array([0.85 * x + 0.04 * y, -0.04 * x + 0.85 * y + 1.6])
        elif r < 0.93: p = np.array([0.2 * x - 0.26 * y, 0.23 * x + 0.22 * y + 1.6])
        else:          p = np.array([-0.15 * x + 0.28 * y, 0.26 * x + 0.24 * y + 0.44])
        if i >= 20:
            out.append((p[0], p[1], 0.15 * math.sin(p[1] * 0.8)))
    return np.array(out)


def s_snowflake():
    out = []
    for a in np.linspace(0, 2 * math.pi, 6, endpoint=False):
        d = np.array([math.cos(a), math.sin(a), 0])
        out.append(line(N // 18, (0, 0, 0), tuple(d)))
        for t, L in ((0.35, 0.3), (0.6, 0.25), (0.8, 0.15)):
            base = d * t
            for s in (1, -1):
                b = a + s * math.pi / 3
                out.append(line(N // 70, tuple(base), tuple(base + np.array([math.cos(b), math.sin(b), 0]) * L)))
    out.append(ring(N // 16, R=0.18, axis="z", w=0.01))
    return np.vstack(out)


def s_honeycomb():
    out = []
    for q in range(-3, 4):
        for r in range(-3, 4):
            if abs(q + r) > 3:
                continue
            cx, cz = 0.27 * (q + r / 2), 0.27 * r * 0.866
            hexv = [(cx + 0.15 * math.cos(a), 0, cz + 0.15 * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 7)[:-1] + math.pi / 6]
            out.append(edges(hexv, [(i, (i + 1) % 6) for i in range(6)], N // 37))
    p = np.vstack(out)
    p[:, 1] += 0.08 * np.sin(p[:, 0] * 3) * np.cos(p[:, 2] * 3)
    return np.stack([p[:, 0], -p[:, 2], p[:, 1]], 1)        # stood up to face you


# ── tech ─────────────────────────────────────────────────────────────────────
def s_robot():
    return np.vstack([box(N // 7, (0, 0.72, 0), (0.42, 0.34, 0.36)), sph(N // 40, (-0.1, 0.75, 0.19), 0.05),
                      sph(N // 40, (0.1, 0.75, 0.19), 0.05), line(N // 40, (0, 0.89, 0), (0, 1.0, 0)), sph(N // 50, (0, 1.02, 0), 0.04),
                      box(N // 4, (0, 0.2, 0), (0.62, 0.62, 0.38)), ring(N // 30, (0, 0.25, 0.2), 0.1, "z", 0.01),
                      cyl(N // 12, (-0.42, 0.18, 0), 0.07, 0.6), cyl(N // 12, (0.42, 0.18, 0), 0.07, 0.6),
                      sph(N // 30, (-0.42, -0.16, 0), 0.09), sph(N // 30, (0.42, -0.16, 0), 0.09),
                      cyl(N // 10, (-0.16, -0.45, 0), 0.09, 0.62), cyl(N // 10, (0.16, -0.45, 0), 0.09, 0.62),
                      box(N // 24, (-0.16, -0.8, 0.05), (0.2, 0.08, 0.3)), box(N // 24, (0.16, -0.8, 0.05), (0.2, 0.08, 0.3))])


def s_mech():
    """A two-legged walker (an original design)."""
    out = [box(N // 5, (0, 0.45, 0), (0.9, 0.42, 0.65)), box(N // 14, (0, 0.72, 0.28), (0.42, 0.16, 0.12)),
           cyl(N // 12, (-0.55, 0.5, 0.15), 0.07, 0.7, "z"), cyl(N // 12, (0.55, 0.5, 0.15), 0.07, 0.7, "z"),
           box(N // 18, (0, 0.72, -0.2), (0.25, 0.18, 0.25))]
    for s in (-1, 1):
        hip, knee, foot = (0.3 * s, 0.22, 0), (0.42 * s, -0.25, 0.25), (0.35 * s, -0.85, -0.05)
        out += [line(N // 14, hip, knee, 0.03), line(N // 14, knee, foot, 0.03), sph(N // 40, knee, 0.07),
                box(N // 18, (foot[0], -0.9, 0.05), (0.25, 0.08, 0.42))]
    return np.vstack(out)


def s_starfighter():
    body = cone(N // 3, (0, 0, 0.1), 0.18, 1.6, "z")
    wings = []
    for s in (-1, 1):
        tri = np.array([(0.12 * s, 0, -0.3), (0.95 * s, 0, -0.6), (0.12 * s, 0, 0.35)])
        a, b = _R.random((2, N // 6))
        m = a + b > 1; a[m], b[m] = 1 - a[m], 1 - b[m]
        wings.append(tri[0] + (tri[1] - tri[0]) * a[:, None] + (tri[2] - tri[0]) * b[:, None])
    fin = np.array([(0, 0, -0.6), (0, 0.4, -0.75), (0, 0, -0.1)])
    a, b = _R.random((2, N // 12)); m = a + b > 1; a[m], b[m] = 1 - a[m], 1 - b[m]
    fin = fin[0] + (fin[1] - fin[0]) * a[:, None] + (fin[2] - fin[0]) * b[:, None]
    return np.vstack([body, fin, cyl(N // 12, (0, 0, -0.72), 0.1, 0.12, "z"), sph(N // 14, (0, 0.1, 0.25), (0.08, 0.06, 0.2))] + wings)


def s_helicopter():
    blades = [line(N // 10, (0, 0.42, 0), (1.0 * math.cos(a), 0.42, 1.0 * math.sin(a))) for a in (0.3, 1.87, 3.44, 5.01)]
    return np.vstack([sph(N // 3, (0, 0, 0.1), (0.38, 0.3, 0.55)), cyl(N // 8, (0, 0.06, -0.75), 0.05, 0.8, "z"),
                      ring(N // 14, (0.06, 0.1, -1.12), 0.16, "x", 0.01), cyl(N // 30, (0, 0.36, 0), 0.04, 0.12),
                      line(N // 12, (-0.3, -0.38, -0.3), (-0.3, -0.38, 0.5)), line(N // 12, (0.3, -0.38, -0.3), (0.3, -0.38, 0.5)),
                      line(N // 40, (-0.25, -0.25, 0.1), (-0.3, -0.38, 0.1)), line(N // 40, (0.25, -0.25, 0.1), (0.3, -0.38, 0.1))] + blades)


def s_submarine():
    hull = lathe(N // 2, [(0.0, -1.0), (0.18, -0.85), (0.24, -0.4), (0.24, 0.5), (0.15, 0.85), (0.0, 1.0)], "z")
    return np.vstack([hull, box(N // 8, (0, 0.3, 0.15), (0.12, 0.3, 0.38)), line(N // 30, (0, 0.45, 0.2), (0, 0.65, 0.2)),
                      box(N // 20, (0, 0, -0.95), (0.55, 0.02, 0.12)), box(N // 20, (0, 0, -0.95), (0.02, 0.45, 0.12)),
                      ring(N // 20, (0, 0, -1.02), 0.12, "z", 0.01)])


def s_laptop():
    base = box(N // 2, (0, -0.25, 0.2), (1.4, 0.05, 0.9))
    keys = np.array([(x, -0.22, z) for x in np.linspace(-0.55, 0.55, 12) for z in np.linspace(0.05, 0.4, 5)])
    screen = _rot(box(N // 2, (0, 0.3, 0), (1.4, 0.9, 0.04)), (0, 0)) + np.array([0, 0.18, -0.3])
    screen[:, 2] -= (screen[:, 1] - 0) * 0.25
    return np.vstack([base, screen, np.vstack([sph(4, tuple(k), 0.02) for k in keys])])


def s_smartphone():
    body = box(N * 2 // 3, size=(0.62, 1.3, 0.07))
    icons = np.array([(x, y, 0.04) for x in np.linspace(-0.2, 0.2, 4) for y in np.linspace(0.45, -0.15, 5)])
    return np.vstack([body, np.vstack([box(12, tuple(c), (0.08, 0.08, 0.005)) for c in icons]),
                      ring(N // 25, (0.12, 0.38, -0.05), 0.06, "z", 0.01), box(N // 30, (0, 0.6, 0.04), (0.15, 0.025, 0.005))])


def s_headphones():
    band = curve(lambda t: (0.75 * math.cos(math.pi * t), 0.15 + 0.75 * math.sin(math.pi * t), 0), N // 3, 0.03)
    cups = [cyl(N // 4, (s * 0.8, -0.1, 0), 0.28, 0.16, "x") for s in (-1, 1)]
    pads = [torus(N // 10, (s * 0.7, -0.1, 0), 0.24, 0.06, "x") for s in (-1, 1)]
    return np.vstack([band] + cups + pads)


def s_game_controller():
    outline = curve(lambda t: (0.95 * math.cos(2 * math.pi * t) * (1 + 0.15 * math.cos(4 * math.pi * t)),
                               0.45 * math.sin(2 * math.pi * t) - 0.18 * max(0, -math.sin(2 * math.pi * t)) * abs(math.cos(2 * math.pi * t)) * 2,
                               0.0), N // 3, 0.015)
    top = outline.copy(); top[:, 2] = 0.12
    btns = [sph(N // 30, (0.45 + dx, 0.05 + dy, 0.15), 0.06) for dx, dy in ((0.13, 0), (-0.13, 0), (0, 0.13), (0, -0.13))]
    dpad = [box(N // 20, (-0.45, 0.05, 0.14), (0.3, 0.09, 0.03)), box(N // 20, (-0.45, 0.05, 0.14), (0.09, 0.3, 0.03))]
    sticks = [cyl(N // 18, (x, -0.2, 0.18), 0.1, 0.08, "z") for x in (-0.2, 0.2)]
    return np.vstack([outline, top] + btns + dpad + sticks)


def s_circuit_board():
    out = [box(N // 4, size=(1.6, 0.04, 1.2))]
    for _ in range(26):                                # traces with right-angle bends
        x, z = _R.uniform(-0.75, 0.75), _R.uniform(-0.55, 0.55)
        x2, z2 = _R.uniform(-0.75, 0.75), _R.uniform(-0.55, 0.55)
        out += [line(N // 110, (x, 0.03, z), (x2, 0.03, z)), line(N // 110, (x2, 0.03, z), (x2, 0.03, z2)),
                sph(6, (x, 0.03, z), 0.02), sph(6, (x2, 0.03, z2), 0.02)]
    out += [box(N // 10, (0, 0.08, 0), (0.42, 0.08, 0.42))]
    out += [line(4, (x, 0.05, 0.21), (x, 0.03, 0.3)) for x in np.linspace(-0.18, 0.18, 8)]
    out += [box(N // 30, (0.55, 0.06, -0.35), (0.25, 0.06, 0.15)), box(N // 30, (-0.55, 0.06, 0.35), (0.2, 0.06, 0.2))]
    p = np.vstack(out)
    return np.stack([p[:, 0], -p[:, 2], p[:, 1]], 1)        # stood up to face you


def s_neural_network():
    layers = [5, 8, 8, 4]
    nodes = []
    for li, n in enumerate(layers):                      # each layer is a ring of neurons → real depth
        x = -0.9 + li * 0.6
        r = 0.25 + 0.06 * n
        nodes.append([(x, r * math.cos(a), r * math.sin(a)) for a in np.linspace(0, 2 * math.pi, n, endpoint=False)])
    out = [np.vstack([sph(34, c, 0.07) for layer in nodes for c in layer])]
    for a, b in zip(nodes, nodes[1:]):                  # faint dotted connections, bright neurons
        for p in a:
            for q in b:
                out.append(line(5, p, q, 0.002))
    return np.vstack(out)


def s_equalizer():
    out = []
    for i, x in enumerate(np.linspace(-0.9, 0.9, 16)):
        h = 0.25 + 1.2 * abs(math.sin(i * 0.9) * math.cos(i * 0.37))
        out.append(box(N // 16, (x, -0.8 + h / 2, 0), (0.08, h, 0.08)))
    return np.vstack(out)


# ── places & structures ──────────────────────────────────────────────────────
def s_eiffel_tower():
    out = []
    prof = lambda y: 0.55 * (1 - (y + 1) / 2.1) ** 1.8 + 0.02
    for sx in (-1, 1):
        for sz in (-1, 1):
            out.append(curve(lambda t, sx=sx, sz=sz: (sx * prof(t * 2 - 1), t * 2 - 1, sz * prof(t * 2 - 1)), N // 6, 0.01))
    for y in (-0.55, 0.0, 0.5):
        r = prof(y)
        out.append(edges([(-r, y, -r), (r, y, -r), (r, y, r), (-r, y, r)], [(0, 1), (1, 2), (2, 3), (3, 0)], N // 25))
    out.append(curve(lambda t: (0.42 * math.cos(math.pi * t), -1 + 0.18 * math.sin(math.pi * t), 0.42), N // 20, 0.005))
    out.append(line(N // 25, (0, 0.95, 0), (0, 1.15, 0)))
    return np.vstack(out)


def s_pyramids():
    def pyr(c, s, n):
        v = [(c[0] - s, -1, c[1] - s), (c[0] + s, -1, c[1] - s), (c[0] + s, -1, c[1] + s), (c[0] - s, -1, c[1] + s),
             (c[0], -1 + s * 1.27, c[1])]
        fill = []
        for a, b in ((0, 1), (1, 2), (2, 3), (3, 0)):
            u, w = _R.random((2, n // 4)); m = u + w > 1; u[m], w[m] = 1 - u[m], 1 - w[m]
            P = np.array(v)
            fill.append(P[a] + (P[b] - P[a]) * u[:, None] + (P[4] - P[a]) * w[:, None])
        return np.vstack(fill)
    return np.vstack([pyr((-0.55, 0.0), 0.55, N // 2), pyr((0.45, 0.45), 0.4, N // 3), pyr((0.95, -0.2), 0.25, N // 6)])


def s_city():
    out = [box(N // 10, (0, -0.95, 0), (2.0, 0.02, 2.0))]
    for x in np.linspace(-0.8, 0.8, 6):
        for z in np.linspace(-0.8, 0.8, 6):
            if _R.random() < 0.15:
                continue
            h = _R.uniform(0.2, 1.4) * (1.3 - 0.5 * (abs(x) + abs(z)))
            out.append(box(max(12, int(N // 40 * h)), (x, -0.95 + h / 2, z), (0.2, h, 0.2)))
    return np.vstack(out)


def s_bridge():
    out = [box(N // 5, (0, -0.2, 0), (2.0, 0.04, 0.3))]
    for x in (-0.6, 0.6):
        for z in (-0.13, 0.13):
            out.append(line(N // 20, (x, -0.7, z), (x, 0.55, z), 0.012))
        out.append(line(N // 40, (x, 0.45, -0.13), (x, 0.45, 0.13)))
    for z in (-0.13, 0.13):
        out.append(curve(lambda t, z=z: (t * 2 - 1, 0.55 - 0.7 * (1 - ((t * 2 - 1) / 0.6) ** 2) if abs(t * 2 - 1) <= 0.6
                                          else 0.55 - (abs(t * 2 - 1) - 0.6) * 1.6, z), N // 6, 0.006))
        for x in np.linspace(-0.55, 0.55, 12):
            y = 0.55 - 0.7 * (1 - (x / 0.6) ** 2)
            out.append(line(6, (x, -0.2, z), (x, y, z)))
    out.append(box(N // 12, (0, -0.95, 0), (2.0, 0.02, 0.8)))
    return np.vstack(out)


def s_castle():
    out = []
    for x in (-0.7, 0.7):
        for z in (-0.7, 0.7):
            out += [cyl(N // 14, (x, -0.2, z), 0.18, 1.3), cone(N // 25, (x, 0.65, z), 0.22, 0.4)]
    for a, b in (((-0.7, -0.7), (0.7, -0.7)), ((0.7, -0.7), (0.7, 0.7)), ((0.7, 0.7), (-0.7, 0.7)), ((-0.7, 0.7), (-0.7, -0.7))):
        cx, cz = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        out.append(box(N // 14, (cx, -0.4, cz), (abs(b[0] - a[0]) + 0.05, 0.9, abs(b[1] - a[1]) + 0.05)))
        for t in np.linspace(0.1, 0.9, 5):
            out.append(box(10, (a[0] + (b[0] - a[0]) * t, 0.1, a[1] + (b[1] - a[1]) * t), (0.1, 0.1, 0.1)))
    out += [box(N // 8, (0, -0.1, 0), (0.5, 1.4, 0.5)), cone(N // 20, (0, 0.85, 0), 0.32, 0.5)]
    return np.vstack(out)


def s_lighthouse():
    tower = lathe(N // 2, [(0.32, -1), (0.2, 0.45)])
    bands = [ring(N // 25, (0, y, 0), 0.32 - (y + 1) / 1.45 * 0.12, w=0.02) for y in (-0.6, -0.2, 0.2)]
    beams = [cone(N // 10, (sgn * 0.65, 0.62, 0), 0.18, -sgn * 1.0, "x") for sgn in (1, -1)]   # narrow at the lamp
    return np.vstack([tower, cyl(N // 10, (0, 0.6, 0), 0.22, 0.3), cone(N // 20, (0, 0.85, 0), 0.25, 0.22),
                      ring(N // 25, (0, 0.45, 0), 0.32, w=0.02)] + bands + beams)


def s_wind_turbine():
    blades = [line(N // 7, (0, 0.55, 0.12), (0.95 * math.cos(a), 0.55 + 0.95 * math.sin(a), 0.12), 0.012)
              for a in (math.pi / 2, math.pi / 2 + 2.094, math.pi / 2 + 4.189)]
    return np.vstack([lathe(N // 3, [(0.07, -1), (0.035, 0.5)]), box(N // 15, (0, 0.55, 0), (0.12, 0.12, 0.3)),
                      sph(N // 30, (0, 0.55, 0.16), 0.06)] + blades)


def s_ferris_wheel():
    out = [ring(N // 4, (0, 0.1, 0), 0.85, "z", 0.02), ring(N // 8, (0, 0.1, 0), 0.6, "z", 0.01), sph(N // 40, (0, 0.1, 0), 0.06)]
    for a in np.linspace(0, 2 * math.pi, 12, endpoint=False):
        p = (0.85 * math.cos(a), 0.1 + 0.85 * math.sin(a), 0)
        out += [line(N // 80, (0, 0.1, 0), p), box(N // 70, (p[0], p[1] - 0.09, 0), (0.1, 0.1, 0.1))]
    out += [line(N // 20, (0, 0.1, 0), (-0.5, -1, 0)), line(N // 20, (0, 0.1, 0), (0.5, -1, 0))]
    return np.vstack(out)


# ── nature & objects ─────────────────────────────────────────────────────────
def s_jellyfish():
    bell = lathe(N // 3, [(0.0, 0.6), (0.4, 0.5), (0.6, 0.2), (0.62, 0.05)])
    out = [bell]
    for a in np.linspace(0, 2 * math.pi, 12, endpoint=False):
        ph = _R.uniform(0, 6.28)
        out.append(curve(lambda t, a=a, ph=ph: ((0.5 - 0.1 * t) * math.cos(a) + 0.08 * math.sin(t * 9 + ph),
                                                0.05 - 1.1 * t, (0.5 - 0.1 * t) * math.sin(a) + 0.08 * math.cos(t * 9 + ph)), N // 20, 0.01))
    for a in np.linspace(0, 2 * math.pi, 4, endpoint=False):
        out.append(curve(lambda t, a=a: (0.12 * math.cos(a) + 0.1 * math.sin(t * 6), 0.1 - 0.7 * t,
                                         0.12 * math.sin(a)), N // 25, 0.04))
    return np.vstack(out)


def s_fish():
    body = sph(N // 2, r=(0.65, 0.32, 0.16))
    tail = np.array([(-0.6, 0, 0), (-1.0, 0.35, 0), (-1.0, -0.35, 0)])
    a, b = _R.random((2, N // 6)); m = a + b > 1; a[m], b[m] = 1 - a[m], 1 - b[m]
    tail = tail[0] + (tail[1] - tail[0]) * a[:, None] + (tail[2] - tail[0]) * b[:, None]
    fin = np.array([(-0.1, 0.3, 0), (0.25, 0.3, 0), (-0.25, 0.55, 0)])
    a, b = _R.random((2, N // 14)); m = a + b > 1; a[m], b[m] = 1 - a[m], 1 - b[m]
    fin = fin[0] + (fin[1] - fin[0]) * a[:, None] + (fin[2] - fin[0]) * b[:, None]
    return np.vstack([body, tail, fin, sph(N // 40, (0.42, 0.08, 0.13), 0.05), sph(N // 40, (0.42, 0.08, -0.13), 0.05)])


def s_snake():
    path = curve(lambda t: (math.sin(t * 9) * 0.6 * (1 - 0.4 * t), -0.9 + 1.5 * t + 0.0 * t, math.cos(t * 9) * 0.6 * (1 - 0.4 * t)),
                 N * 3 // 4, 0.05)
    head = sph(N // 8, (math.sin(9) * 0.36, 0.62, math.cos(9) * 0.36), (0.12, 0.08, 0.16))
    return np.vstack([path, head])


def s_spider_web():
    out = []
    for a in np.linspace(0, 2 * math.pi, 14, endpoint=False):
        out.append(line(N // 28, (0, 0, 0), (math.cos(a), math.sin(a), 0), 0.004))
    out.append(curve(lambda t: ((0.06 + 0.92 * t) * math.cos(t * 2 * math.pi * 11),
                                (0.06 + 0.92 * t) * math.sin(t * 2 * math.pi * 11), 0.0), N // 2, 0.004))
    p = np.vstack(out)
    p[:, 2] = -0.1 * (p[:, 0] ** 2 + p[:, 1] ** 2)
    return p


def s_palm_tree():
    trunk = curve(lambda t: (0.3 * t ** 2, -1 + 1.6 * t, 0), N // 3, 0.06)
    top = np.array([0.3, 0.6, 0])
    fronds = []
    for a in np.linspace(0, 2 * math.pi, 9, endpoint=False):
        d = np.array([math.cos(a), 0, math.sin(a)])
        fronds.append(curve(lambda t, d=d: tuple(top + d * 0.85 * t + np.array([0, 0.25 * t - 0.6 * t * t, 0])), N // 13, 0.03))
    return np.vstack([trunk, sph(N // 25, tuple(top), 0.1)] + fronds)


def s_pine_tree():
    tiers = [cone(N // 5, (0, y, 0), r, 0.55) for y, r in ((-0.35, 0.75), (0.05, 0.6), (0.4, 0.45), (0.72, 0.3))]
    return np.vstack(tiers + [cyl(N // 10, (0, -0.8, 0), 0.08, 0.35)])


def s_cactus():
    out = [cyl(N // 3, (0, -0.05, 0), 0.18, 1.6), sph(N // 15, (0, 0.75, 0), 0.18)]
    for s, y in ((-1, -0.05), (1, 0.15)):
        out += [curve(lambda t, s=s, y=y: (s * (0.18 + 0.25 * min(1, t * 2)), y + max(0, t * 2 - 1) * 0.5, 0), N // 10, 0.08),
                sph(N // 30, (s * 0.43, y + 0.5, 0), 0.08)]
    out.append(lathe(N // 8, [(0.35, -1), (0.42, -0.75), (0.3, -0.75)]))
    return np.vstack(out)


def s_volcano():
    mount = lathe(N // 2, [(1.0, -1), (0.6, -0.4), (0.25, 0.2), (0.18, 0.2)])
    mount += _R.normal(0, 0.02, mount.shape)
    plume = _R.normal(0, 1, (N // 3, 3)) * np.array([0.12, 0.25, 0.12])
    plume[:, 1] = np.abs(plume[:, 1]) * 2.2 + 0.25
    plume[:, [0, 2]] *= (1 + plume[:, 1:2] * 1.2)
    lava = curve(lambda t: (0.18 + 0.6 * t, 0.2 - 1.1 * t, 0.15 * math.sin(t * 6)), N // 10, 0.03)
    return np.vstack([mount, plume, lava])


def s_flame():
    t = _R.random(N)
    y = t * 1.8 - 0.9
    r = 0.55 * np.sin(np.pi * np.clip(t, 0, 1) ** 0.6) * (1 - t) ** 0.4
    a = _R.random(N) * 2 * np.pi
    w = 0.08 * np.sin(y * 7 + a * 2)
    return np.stack([r * np.cos(a) + w, y, r * np.sin(a)], 1) * np.sqrt(_R.random((N, 1))) ** 0.3


def s_water_drop():
    return np.vstack([lathe(N * 4 // 5, [(0.0, 0.95), (0.12, 0.6), (0.4, 0.05), (0.5, -0.35), (0.38, -0.7), (0.0, -0.82)]),
                      ring(N // 5, (0, -0.95, 0), 0.6, w=0.15)])


def s_clock():
    out = [ring(N // 3, R=1.0, axis="z", w=0.04), sph(N // 40, r=0.05)]
    for k in range(60):
        a = k * math.pi / 30
        L = 0.15 if k % 5 == 0 else 0.06
        out.append(line(6 if k % 5 else 14, (0.92 * math.cos(a), 0.92 * math.sin(a), 0), ((0.92 - L) * math.cos(a), (0.92 - L) * math.sin(a), 0)))
    out += [line(N // 14, (0, 0, 0.01), (0.45 * math.cos(1.0), 0.45 * math.sin(1.0), 0.01), 0.012),
            line(N // 10, (0, 0, 0.02), (0.75 * math.cos(2.4), 0.75 * math.sin(2.4), 0.02), 0.008)]
    return np.vstack(out)


def s_anchor():
    return np.vstack([line(N // 4, (0, 0.75, 0), (0, -0.8, 0), 0.03), ring(N // 8, (0, 0.88, 0), 0.13, "z", 0.04),
                      line(N // 10, (-0.35, 0.5, 0), (0.35, 0.5, 0), 0.025),
                      curve(lambda t: (0.75 * math.cos(math.pi + math.pi * t), -0.2 + 0.75 * math.sin(math.pi + math.pi * t), 0), N // 3, 0.03),
                      cone(N // 16, (-0.75, -0.12, 0), 0.1, 0.25), cone(N // 16, (0.75, -0.12, 0), 0.1, 0.25)])


def s_crown():
    t = _R.random(N * 2 // 3)
    a = t * 2 * np.pi
    top = 0.15 + 0.45 * np.abs(np.sin(a * 2.5)) ** 1.5
    y = -0.45 + _R.random(len(t)) * (top + 0.45)
    band = np.stack([0.8 * np.cos(a), y, 0.8 * np.sin(a)], 1)
    gems = [sph(N // 40, (0.8 * math.cos(b), 0.62 + 0.0, 0.8 * math.sin(b)), 0.07) for b in np.linspace(0, 2 * math.pi, 5, endpoint=False) + math.pi / 10]
    return np.vstack([band, ring(N // 10, (0, -0.45, 0), 0.82, w=0.04), ring(N // 10, (0, -0.25, 0), 0.82, w=0.02)] + gems)


def s_skull():
    cranium = sph(N // 2, (0, 0.2, 0), (0.62, 0.62, 0.7))
    cranium = cranium[~((cranium[:, 1] < 0.05) & (cranium[:, 2] > 0.25))]
    jaw = lathe(N // 5, [(0.35, -0.55), (0.45, -0.3), (0.5, 0.0)])
    jaw[:, 2] = jaw[:, 2] * 0.8 + 0.1
    eyes = [ring(N // 14, (s * 0.24, 0.05, 0.58), 0.13, "z", 0.04) for s in (-1, 1)]
    nose = edges([(0, -0.08, 0.65), (-0.07, -0.22, 0.62), (0.07, -0.22, 0.62)], [(0, 1), (1, 2), (2, 0)], N // 25)
    teeth = [box(8, (x, -0.42, 0.42), (0.05, 0.08, 0.02)) for x in np.linspace(-0.22, 0.22, 9)]
    return np.vstack([cranium, jaw, nose] + eyes + teeth)


def s_newtons_cradle():
    out = [line(N // 10, (-0.75, 0.8, -0.3), (0.75, 0.8, -0.3)), line(N // 10, (-0.75, 0.8, 0.3), (0.75, 0.8, 0.3)),
           box(N // 8, (0, -0.9, 0), (1.7, 0.06, 0.8))]
    for x in (-0.75, 0.75):
        for z in (-0.3, 0.3):
            out.append(line(N // 25, (x, 0.8, z), (x, -0.9, z)))
    for i, x in enumerate(np.linspace(-0.4, 0.4, 5)):
        bx, by = (x, -0.35) if i else (x - 0.45, -0.1)
        out += [sph(N // 14, (bx, by, 0), 0.1), line(N // 70, (x, 0.8, -0.3), (bx, by, 0)), line(N // 70, (x, 0.8, 0.3), (bx, by, 0))]
    return np.vstack(out)


def s_hourglass():
    glass = lathe(N // 2, [(0.5, -0.85), (0.45, -0.5), (0.06, 0.0), (0.45, 0.5), (0.5, 0.85)])
    sand_top = lathe(N // 8, [(0.0, 0.05), (0.3, 0.3)])
    sand_bot = lathe(N // 6, [(0.42, -0.8), (0.0, -0.45)])
    stream = line(N // 30, (0, 0.0, 0), (0, -0.45, 0), 0.005)
    return np.vstack([glass, sand_top, sand_bot, stream, cyl(N // 10, (0, 0.92, 0), 0.6, 0.06), cyl(N // 10, (0, -0.92, 0), 0.6, 0.06)]
                     + [line(N // 30, (0.55 * math.cos(a), -0.92, 0.55 * math.sin(a)), (0.55 * math.cos(a), 0.92, 0.55 * math.sin(a)))
                        for a in (0.5, 2.6, 4.7)])


def s_gyroscope():
    return np.vstack([ring(N // 4, R=1.0, axis="y", w=0.03), _rot(ring(N // 4, R=0.9, axis="y", w=0.03), (0.0, 1.3)),
                      _rot(ring(N // 4, R=0.8, axis="y", w=0.03), (1.1, 0.6)), cyl(N // 6, r=0.45, h=0.08),
                      line(N // 20, (0, -0.95, 0), (0, 0.95, 0))])


def s_puzzle_cube():
    g = (-0.63, -0.21, 0.21, 0.63)
    out = []
    for ax in range(3):                                         # a clean 3×3 grid on every face
        o = [i for i in range(3) if i != ax]
        for side in (-0.63, 0.63):
            for t in g:
                for along in (0, 1):
                    a, b = [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
                    a[ax] = b[ax] = side
                    a[o[along]], b[o[along]] = -0.63, 0.63
                    a[o[1 - along]] = b[o[1 - along]] = t
                    out.append(line(N // 48, tuple(a), tuple(b), 0.004))
    return np.vstack(out)


def s_dice():
    out = [box(N // 2, size=(1.2, 1.2, 1.2))]
    faces = {(0, 0.61, 0): [(0, 0)], (0, -0.61, 0): [(-.3, -.3), (-.3, 0), (-.3, .3), (.3, -.3), (.3, 0), (.3, .3)],
             (0.61, 0, 0): [(-.3, -.3), (0, 0), (.3, .3)], (-0.61, 0, 0): [(-.3, -.3), (-.3, .3), (.3, -.3), (.3, .3)],
             (0, 0, 0.61): [(-.3, -.3), (.3, .3)], (0, 0, -0.61): [(-.3, -.3), (-.3, .3), (.3, -.3), (.3, .3), (0, 0)]}
    for c, dots in faces.items():
        for u, v in dots:
            p = list(c)
            free = [i for i in range(3) if c[i] == 0]
            p[free[0]], p[free[1]] = u, v
            r = [0.1 if c[i] == 0 else 0.015 for i in range(3)]
            out.append(sph(N // 35, tuple(p), tuple(r)))
    return np.vstack(out)


def s_cricket_bat():
    blade = box(N // 2, (0, -0.25, 0), (0.32, 1.1, 0.12))
    blade[:, 2] += 0.06 * np.clip(-blade[:, 1] - 0.2, 0, 1)        # the bulge at the back
    return np.vstack([blade, cyl(N // 5, (0, 0.55, 0), 0.06, 0.6), sph(N // 15, (0.55, -0.6, 0.2), 0.12),
                      ring(N // 20, (0.55, -0.6, 0.2), 0.122, "x", 0.01)])


def s_cricket_ball():
    ball = sph(N * 3 // 4, r=0.9)
    seam = np.vstack([ring(N // 10, (s * 0.04, 0, 0), 0.905, "x", 0.012) for s in (-1, 1)])
    stitches = np.vstack([line(3, (s * 0.06, 0.905 * math.sin(a), 0.905 * math.cos(a)), (s * 0.02, 0.905 * math.sin(a), 0.905 * math.cos(a)))
                          for s in (-1, 1) for a in np.linspace(0, 2 * math.pi, 60, endpoint=False)])
    return np.vstack([ball, seam, stitches])


def s_basketball():
    ball = sph(N * 2 // 3, r=0.9)
    seams = [ring(N // 12, R=0.91, axis="x", w=0.01), ring(N // 12, R=0.91, axis="z", w=0.01)]
    for sgn in (-1, 1):                                           # the two curved side seams
        def f(t, sgn=sgn):
            a = 2 * math.pi * t
            th = 0.75 + 0.25 * math.cos(a)                        # distance from the pole wobbles
            return (sgn * 0.91 * math.cos(th), 0.91 * math.sin(th) * math.sin(a), 0.91 * math.sin(th) * math.cos(a))
        seams.append(curve(f, N // 12, 0.008))
    return np.vstack([ball] + seams)


def s_guitar():
    lower, upper = ((0, -0.5), 0.42), ((0, -0.02), 0.31)        # two bouts → the figure-eight body
    def outline(n):
        out = []
        for (cx, cy), r, (oc, orr) in ((lower[0], lower[1], upper), (upper[0], upper[1], lower)):
            a = _R.random(n) * 2 * np.pi
            p = np.stack([cx + r * np.cos(a), cy + r * np.sin(a)], 1)
            keep = np.hypot(p[:, 0] - oc[0], p[:, 1] - oc[1]) > orr     # drop the part inside the other bout
            out.append(p[keep])
        return np.vstack(out)
    o = outline(N // 4)
    front = np.column_stack([o, np.full(len(o), 0.06)])
    back = np.column_stack([o, np.full(len(o), -0.06)])
    hole = ring(N // 15, (0, -0.2, 0.06), 0.1, "z", 0.01)
    neck = box(N // 7, (0, 0.62, 0), (0.1, 0.95, 0.05))
    head = box(N // 20, (0, 1.15, 0), (0.17, 0.2, 0.05))
    bridge = box(N // 40, (0, -0.62, 0.07), (0.25, 0.04, 0.02))
    strings = [line(N // 50, (x, -0.62, 0.08), (x * 0.6, 1.08, 0.04), 0.002) for x in np.linspace(-0.06, 0.06, 6)]
    return np.vstack([front, back, hole, neck, head, bridge] + strings)


def s_music_note():
    heads = [sph(N // 6, (x, -0.55 + dy, 0), (0.24, 0.17, 0.12)) for x, dy in ((-0.45, 0), (0.45, 0.2))]
    stems = [line(N // 10, (x + 0.22, -0.5 + dy, 0), (x + 0.22, 0.65 + dy, 0), 0.02) for x, dy in ((-0.45, 0), (0.45, 0.2))]
    beam = box(N // 6, (0.0, 0.75, 0), (0.92, 0.14, 0.06))
    beam[:, 1] += (beam[:, 0]) * 0.22
    return np.vstack(heads + stems + [beam])


def s_heartbeat():
    def ecg(t):
        x = t * 2 - 1
        k = (x * 1.5 + 0.2) % 1.0                    # three heartbeats across
        y = 0.0
        if 0.35 < k < 0.42: y = (k - 0.35) * 2.5
        elif 0.42 < k < 0.47: y = 0.18 - (k - 0.42) * 20
        elif 0.47 < k < 0.52: y = -0.82 + (k - 0.47) * 32
        elif 0.52 < k < 0.58: y = 0.78 - (k - 0.52) * 15
        elif 0.68 < k < 0.8: y = 0.15 * math.sin((k - 0.68) / 0.12 * math.pi)
        return (x, y * 0.9, 0.0)
    t = np.sort(_R.random(N))
    p = np.array([ecg(v) for v in t])
    return _jit(p, 0.008)


def s_spiral_staircase():
    out = [cyl(N // 6, r=0.07, h=2.0)]
    for i in range(18):
        a, y = i * 0.62, -0.95 + i * 0.11
        out.append(_rot_y(box(N // 40, (0.38, 0, 0), (0.6, 0.03, 0.18)), a) + np.array([0, y, 0]))
    out.append(curve(lambda t: (0.68 * math.cos(t * 0.62 * 17), -0.75 + t * 0.11 * 17, 0.68 * math.sin(t * 0.62 * 17)), N // 6, 0.008))
    return np.vstack(out)


def _rot_y(p, a):
    c, s = math.cos(a), math.sin(a)
    return np.stack([p[:, 0] * c - p[:, 2] * s, p[:, 1], p[:, 0] * s + p[:, 2] * c], 1)


def s_key():
    return np.vstack([ring(N // 3, (0, 0.55, 0), 0.32, "z", 0.08), line(N // 4, (0, 0.23, 0), (0, -0.9, 0), 0.03),
                      box(N // 12, (0.12, -0.6, 0), (0.2, 0.08, 0.04)), box(N // 12, (0.1, -0.82, 0), (0.16, 0.08, 0.04))])


def s_padlock():
    return np.vstack([box(N // 2, (0, -0.35, 0), (0.95, 0.8, 0.3)),
                      curve(lambda t: (0.32 * math.cos(math.pi * t), 0.05 + 0.6 * math.sin(math.pi * t) + 0.0, 0), N // 4, 0.04),
                      line(N // 20, (-0.32, 0.05, 0), (-0.32, -0.0, 0)), line(N // 20, (0.32, 0.05, 0), (0.32, -0.0, 0)),
                      ring(N // 20, (0, -0.3, 0.16), 0.07, "z", 0.02), line(N // 30, (0, -0.35, 0.16), (0, -0.5, 0.16))])


EXTRA = {
    # space & science
    "nebula": s_nebula, "pulsar": s_pulsar, "supernova": s_supernova, "asteroid": s_asteroid, "space station": s_space_station,
    "ufo": s_ufo, "radio dish": s_radio_dish, "telescope": s_telescope, "magnetic field": s_magnetic_field,
    "orbitals": s_orbitals, "crystal lattice": s_crystal_lattice, "buckyball": s_buckyball, "geodesic sphere": s_geodesic,
    "virus": s_virus, "neuron": s_neuron,
    # maths & fractals
    "lorenz attractor": s_lorenz, "aizawa attractor": s_aizawa, "klein bottle": s_klein_bottle, "trefoil knot": s_trefoil,
    "sierpinski": s_sierpinski, "menger sponge": s_menger, "mandelbrot": s_mandelbrot, "fern": s_fern,
    "snowflake": s_snowflake, "honeycomb": s_honeycomb,
    # tech
    "robot": s_robot, "mech": s_mech, "starfighter": s_starfighter, "helicopter": s_helicopter, "submarine": s_submarine,
    "laptop": s_laptop, "smartphone": s_smartphone, "headphones": s_headphones, "game controller": s_game_controller,
    "circuit board": s_circuit_board, "neural network": s_neural_network, "equalizer": s_equalizer,
    # places & structures
    "eiffel tower": s_eiffel_tower, "pyramids": s_pyramids, "city": s_city, "bridge": s_bridge, "castle": s_castle,
    "lighthouse": s_lighthouse, "wind turbine": s_wind_turbine, "ferris wheel": s_ferris_wheel,
    # nature & objects
    "jellyfish": s_jellyfish, "fish": s_fish, "snake": s_snake, "spider web": s_spider_web, "palm tree": s_palm_tree,
    "pine tree": s_pine_tree, "cactus": s_cactus, "volcano": s_volcano, "flame": s_flame, "water drop": s_water_drop,
    "clock": s_clock, "anchor": s_anchor, "crown": s_crown, "skull": s_skull, "newtons cradle": s_newtons_cradle,
    "hourglass": s_hourglass, "gyroscope": s_gyroscope, "puzzle cube": s_puzzle_cube, "dice": s_dice,
    "cricket bat": s_cricket_bat, "cricket ball": s_cricket_ball, "basketball": s_basketball, "guitar": s_guitar,
    "music note": s_music_note, "heartbeat": s_heartbeat, "spiral staircase": s_spiral_staircase, "key": s_key,
    "padlock": s_padlock,
}
BUILTIN.update(EXTRA)
SYNONYMS.pop("dice", None)
SYNONYMS.update({
    "lorenz": "lorenz attractor", "butterfly attractor": "lorenz attractor", "aizawa": "aizawa attractor",
    "attractor": "lorenz attractor", "klein": "klein bottle", "trefoil": "trefoil knot", "sierpinski triangle": "sierpinski",
    "fractal": "sierpinski", "menger": "menger sponge", "mandelbrot set": "mandelbrot", "soccer ball": "buckyball",
    "football": "buckyball", "c60": "buckyball", "fullerene": "buckyball", "geodesic": "geodesic sphere",
    "geodesic dome": "geodesic sphere", "germ": "virus", "bacteria": "virus", "nerve": "neuron", "brain cell": "neuron",
    "neutron star": "pulsar", "explosion": "supernova", "rock": "asteroid", "meteor": "asteroid",
    "station": "space station", "flying saucer": "ufo", "alien ship": "ufo", "satellite dish": "radio dish",
    "dish": "radio dish", "magnet": "magnetic field", "orbital": "orbitals", "electron cloud": "orbitals",
    "lattice": "crystal lattice", "android": "robot", "walker": "mech", "fighter": "starfighter", "jet fighter": "starfighter",
    "space fighter": "starfighter", "chopper": "helicopter", "sub": "submarine", "computer": "laptop", "phone": "smartphone",
    "mobile": "smartphone", "headset": "headphones", "controller": "game controller", "gamepad": "game controller",
    "pcb": "circuit board", "motherboard": "circuit board", "chip": "circuit board", "ai": "neural network",
    "neural net": "neural network", "sound bars": "equalizer", "audio": "equalizer", "eiffel": "eiffel tower",
    "paris": "eiffel tower", "egypt": "pyramids", "skyline": "city", "skyscrapers": "city", "golden gate": "bridge",
    "fort": "castle", "turbine": "wind turbine", "windmill": "wind turbine", "big wheel": "ferris wheel",
    "jelly": "jellyfish", "web": "spider web", "cobweb": "spider web", "palm": "palm tree", "christmas tree": "pine tree",
    "fir": "pine tree", "fire": "flame", "drop": "water drop", "raindrop": "water drop", "watch": "clock",
    "time": "hourglass", "sand timer": "hourglass", "rubiks cube": "puzzle cube", "rubik": "puzzle cube", "die": "dice",
    "bat": "cricket bat", "cricket": "cricket bat", "ball": "sphere", "note": "music note", "music": "music note",
    "ecg": "heartbeat", "pulse": "heartbeat", "stairs": "spiral staircase", "staircase": "spiral staircase",
    "lock": "padlock", "newton": "newtons cradle", "newton's cradle": "newtons cradle", "king's crown": "crown",
})


# ════════════════════════════════════════════════════════════════════════════
# 2.3 — categories + shape order (the "shapes" list and 👍/👎 flicking use these)
# ════════════════════════════════════════════════════════════════════════════
CATEGORIES = {
    "Geometry": ["sphere", "cube", "pyramid", "cone", "cylinder", "torus", "capsule", "rings", "tetrahedron",
                 "octahedron", "icosahedron", "dodecahedron", "tesseract", "hexagonal prism", "star", "heart",
                 "diamond", "cross", "geodesic sphere", "buckyball"],
    "Curves, maths & fractals": ["helix", "spring", "dna", "torus knot", "trefoil knot", "infinity", "lissajous",
                                 "mobius strip", "klein bottle", "wave", "saddle", "hyperboloid", "wormhole",
                                 "lorenz attractor", "aizawa attractor", "sierpinski", "menger sponge",
                                 "mandelbrot", "fern", "snowflake", "honeycomb"],
    "Science & space": ["atom", "orbitals", "molecule", "crystal lattice", "magnetic field", "virus", "neuron",
                        "brain", "eye", "solar system", "sun", "moon", "saturn", "globe", "galaxy", "nebula",
                        "black hole", "pulsar", "supernova", "comet", "asteroid", "space station", "ufo",
                        "radio dish", "telescope"],
    "Tech & vehicles": ["suit", "robot", "mech", "reactor core", "gear", "drone", "rocket", "satellite",
                        "starfighter", "plane", "helicopter", "submarine", "car", "laptop", "smartphone",
                        "headphones", "game controller", "circuit board", "neural network", "equalizer"],
    "Places & structures": ["house", "tower", "castle", "lighthouse", "eiffel tower", "pyramids", "city",
                            "bridge", "wind turbine", "ferris wheel", "spiral staircase"],
    "Nature": ["tree", "pine tree", "palm tree", "cactus", "flower", "mushroom", "crystal", "mountain",
               "volcano", "flame", "water drop", "butterfly", "jellyfish", "fish", "snake", "spider web"],
    "Objects & fun": ["shield", "sword", "hammer", "crown", "skull", "anchor", "key", "padlock", "clock",
                      "hourglass", "gyroscope", "newtons cradle", "puzzle cube", "dice", "cricket bat",
                      "cricket ball", "basketball", "guitar", "music note", "heartbeat", "vase", "trophy",
                      "bell", "cup", "lightbulb", "chess pawn", "chess king"],
}
for _k in list(CATEGORIES):                                 # never list a shape that doesn't exist
    CATEGORIES[_k] = [n for n in CATEGORIES[_k] if n in BUILTIN]
_listed = {n for v in CATEGORIES.values() for n in v}
if any(n not in _listed for n in BUILTIN):                  # never hide a shape that does
    CATEGORIES["More"] = [n for n in names() if n not in _listed]
ORDER = [n for v in CATEGORIES.values() for n in v]


def neighbour(name: str, step: int = 1) -> str:
    """The shape after (step=1) or before (step=-1) this one in ORDER — for flicking
    through every shape with a thumb. Text / custom shapes start at the beginning."""
    key = resolve(name or "") if not str(name or "").startswith("text:") else None
    if key not in ORDER:
        return ORDER[0] if step > 0 else ORDER[-1]
    return ORDER[(ORDER.index(key) + step) % len(ORDER)]
