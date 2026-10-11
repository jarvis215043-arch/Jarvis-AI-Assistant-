"""
core/gl_orb.py — The orange particle orb, drawn by the graphics card (OpenGL).

The normal orb (ui.py, HudCanvas._paint_plexus) is drawn by Python on the
processor, which limits it to ~2,500 particles. Here every particle's position,
colour and glow is calculated in a shader on the GPU, so it can draw ~16,000
particles with soft glows at a steady frame rate while using almost no CPU.

It does NOT have its own logic: the existing orb canvas (HudCanvas, sitting on
top as a transparent layer) still handles the states (idle / listening /
thinking / speaking / muted), the mouse, hand control and the status text. This
view just reads those numbers every frame and draws the particles.

If anything goes wrong (no PyOpenGL, old driver, shader error) it calls
on_fail(), and ui.py switches back to the normal orb — JARVIS never breaks
because of this file. Turn it off with  "gpu_orb": false  in config/api_keys.json.
"""
import ctypes
import math
import time

import numpy as np
from PyQt6.QtCore import QTimer
from PyQt6.QtOpenGLWidgets import QOpenGLWidget

VERT = """
#version 120
attribute vec4 a0;   // dir.xyz, kind (0 strand, 1 core, 2 dust)
attribute vec4 a1;   // r_shell, r_core, r_dust, brightness
attribute vec4 a2;   // phase.xyz, latitude
attribute vec4 a3;   // freq.xyz, longitude
uniform float t; uniform float shell; uniform float wobble; uniform float wave;
uniform float yaw; uniform float pitch; uniform float R; uniform float px;
uniform float energy; uniform float amp; uniform float dpr;
uniform vec2 center; uniform vec2 view;
uniform vec3 cBase; uniform vec3 cHot; uniform vec3 cWhite;
varying vec3 vCol; varying float vA; varying float vCore; varying float vHalo;
void main() {
    vec3 d = normalize(a0.xyz + wobble * sin(a3.xyz * t + a2.xyz));
    float kind = a0.w;
    float r;
    if (kind < 0.5)      r = a1.x * (0.28 + 0.72 * shell);
    else if (kind < 1.5) r = a1.y * (0.8 + 0.4 * (1.0 - shell));
    else                 r = a1.z;
    if (wave > 0.0) {
        float k = (kind > 0.5 && kind < 1.5) ? 0.3 : 1.0;
        r *= 1.0 + wave * sin(3.0 * a2.w + 2.0 * a3.w + t * 2.2) * k;
    }
    vec3 p = d * r;
    float cy = cos(yaw); float sy = sin(yaw); float cp = cos(pitch); float sp = sin(pitch);
    float x  = p.x * cy + p.z * sy;
    float z  = -p.x * sy + p.z * cy;
    float y  = p.y * cp - z * sp;
    float z2 = p.y * sp + z * cp;
    float persp = 1.0 / (1.0 - 0.18 * clamp(z2, -2.5, 2.5));
    vec2 s = center + vec2(x, y) * R * persp;
    gl_Position = vec4(s.x / view.x * 2.0 - 1.0, 1.0 - s.y / view.y * 2.0, 0.0, 1.0);
    float depth = clamp((z2 + 1.2) / 2.4, 0.0, 1.0);
    float lum = a1.w * (0.30 + 0.70 * depth) * energy * (1.0 + 0.35 * amp);
    vCol = lum < 0.55 ? cBase : (lum < 0.8 ? cHot : cWhite);
    float core = mix(1.1, 2.3, clamp(lum, 0.0, 1.0)) * px * dpr;
    float size = max(core, 6.5 * px * dpr);
    gl_PointSize = size;
    vCore = core / size;
    vA = mix(0.47, 0.96, clamp(lum, 0.0, 1.0));
    vHalo = lum > 0.25 ? 0.07 : 0.0;
}
"""

FRAG = """
#version 120
varying vec3 vCol; varying float vA; varying float vCore; varying float vHalo;
void main() {
    float d = length(gl_PointCoord - vec2(0.5)) * 2.0;
    if (d > 1.0) discard;
    float core = 1.0 - smoothstep(vCore * 0.55, vCore, d);
    float halo = vHalo * (1.0 - d) * (1.0 - d);
    float a = core * vA + halo;
    gl_FragColor = vec4(vCol * a, a);
}
"""

# A soft round glow (used for the background haze and the hot centre).
BLOB_VERT = """
#version 120
attribute vec4 q;    // ndc.xy, uv.xy (-1..1)
varying vec2 uv;
void main() { uv = q.zw; gl_Position = vec4(q.xy, 0.0, 1.0); }
"""
BLOB_FRAG = """
#version 120
varying vec2 uv;
uniform vec3 c0; uniform vec3 c1; uniform vec3 c2;
uniform float a0; uniform float a1; uniform float a2; uniform float s1;
void main() {
    float r = length(uv);
    if (r > 1.0) discard;
    vec4 inner = vec4(c0 * a0, a0); vec4 mid = vec4(c1 * a1, a1); vec4 outer = vec4(c2 * a2, a2);
    gl_FragColor = r < s1 ? mix(inner, mid, r / s1) : mix(mid, outer, (r - s1) / (1.0 - s1));
}
"""


def _txt(v) -> str:
    return (v.decode(errors="replace") if isinstance(v, bytes) else str(v or ""))[:300]


def attribute_array(m) -> np.ndarray:
    """Interleaved per-particle data (16 floats each) from a _PlexusModel."""
    n = m.n
    a = np.zeros((n, 16), np.float32)
    a[:, 0:3] = m.dir;         a[:, 3] = m.kind
    a[:, 4] = m.r_shell;       a[:, 5] = m.r_core;  a[:, 6] = m.r_dust;  a[:, 7] = m.bright
    a[:, 8:11] = m.phase;      a[:, 11] = m.lat
    a[:, 12:15] = m.freq;      a[:, 15] = m.lon
    return a


def reference_positions(m, t, shell, wobble, wave, yaw, pitch):
    """The exact maths of the vertex shader, in numpy (used by the tests to prove
    the GPU orb matches the CPU orb)."""
    a = attribute_array(m).astype(np.float64)
    d = a[:, 0:3] + wobble * np.sin(a[:, 12:15] * t + a[:, 8:11])
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    kind = a[:, 3]
    r = np.where(kind < 0.5, a[:, 4] * (0.28 + 0.72 * shell),
        np.where(kind < 1.5, a[:, 5] * (0.8 + 0.4 * (1 - shell)), a[:, 6]))
    if wave > 0:
        k = np.where((kind > 0.5) & (kind < 1.5), 0.3, 1.0)
        r = r * (1 + wave * np.sin(3 * a[:, 11] + 2 * a[:, 15] + t * 2.2) * k)
    p = d * r[:, None]
    cy, sy, cp, sp = math.cos(yaw), math.sin(yaw), math.cos(pitch), math.sin(pitch)
    x = p[:, 0] * cy + p[:, 2] * sy
    z = -p[:, 0] * sy + p[:, 2] * cy
    y = p[:, 1] * cp - z * sp
    z2 = p[:, 1] * sp + z * cp
    return np.stack([x, y, z2], 1)


class GLOrbView(QOpenGLWidget):
    def __init__(self, canvas, model, colors, on_fail, parent=None):
        """canvas: the HudCanvas that owns the orb state. model: a _PlexusModel.
        colors(): returns (base, hot, white, energy) as QColors + float.
        on_fail(reason): called once if the GPU path can't run."""
        super().__init__(parent)
        self._canvas, self._m, self._colors, self._on_fail = canvas, model, colors, on_fail
        self._data = attribute_array(model)
        self._ok = False
        self._failed = False
        self.frames = 0
        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self.update)
        self._tmr.start(16)

    # ── helpers ──
    def _fail(self, why: str) -> None:
        if self._failed:
            return
        self._failed = True
        self._tmr.stop()
        print(f"[GPU orb] Off — using the normal orb ({why})")
        QTimer.singleShot(0, lambda: self._on_fail(why))

    def _program(self, vs: str, fs: str, attrs: list[str]):
        from OpenGL import GL
        prog = GL.glCreateProgram()
        for src, kind in ((vs, GL.GL_VERTEX_SHADER), (fs, GL.GL_FRAGMENT_SHADER)):
            sh = GL.glCreateShader(kind)
            GL.glShaderSource(sh, src)
            GL.glCompileShader(sh)
            if not GL.glGetShaderiv(sh, GL.GL_COMPILE_STATUS):
                raise RuntimeError("shader: " + _txt(GL.glGetShaderInfoLog(sh)))
            GL.glAttachShader(prog, sh)
        for i, name in enumerate(attrs):
            GL.glBindAttribLocation(prog, i, name)
        GL.glLinkProgram(prog)
        if not GL.glGetProgramiv(prog, GL.GL_LINK_STATUS):
            raise RuntimeError("link: " + _txt(GL.glGetProgramInfoLog(prog)))
        return prog

    # ── Qt OpenGL hooks ──
    def initializeGL(self):
        try:
            from OpenGL import GL
            self._GL = GL
            self._p = self._program(VERT, FRAG, ["a0", "a1", "a2", "a3"])
            self._b = self._program(BLOB_VERT, BLOB_FRAG, ["q"])
            self._u = {n: GL.glGetUniformLocation(self._p, n) for n in
                       ("t", "shell", "wobble", "wave", "yaw", "pitch", "R", "px", "energy", "amp", "dpr",
                        "center", "view", "cBase", "cHot", "cWhite")}
            self._ub = {n: GL.glGetUniformLocation(self._b, n) for n in ("c0", "c1", "c2", "a0", "a1", "a2", "s1")}
            self._vao = None
            try:                                         # needed only on "core profile" drivers
                self._vao = GL.glGenVertexArrays(1)
            except Exception:
                self._vao = None
            self._vbo = GL.glGenBuffers(1)
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._vbo)
            GL.glBufferData(GL.GL_ARRAY_BUFFER, self._data.nbytes, self._data, GL.GL_STATIC_DRAW)
            self._qbo = GL.glGenBuffers(1)
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
            for cap in (0x8642, 0x8861):                 # PROGRAM_POINT_SIZE, POINT_SPRITE (older drivers)
                try:
                    GL.glEnable(cap)
                except Exception:
                    pass
            self._ok = True
        except Exception as e:
            self._fail(str(e))

    def _blob(self, cx, cy, r, vw, vh, stops):
        """Soft round glow centred at (cx, cy) with radius r (device pixels)."""
        GL = self._GL
        x0, x1 = (cx - r) / vw * 2 - 1, (cx + r) / vw * 2 - 1
        y0, y1 = 1 - (cy - r) / vh * 2, 1 - (cy + r) / vh * 2
        q = np.array([x0, y0, -1, -1, x1, y0, 1, -1, x0, y1, -1, 1, x1, y1, 1, 1], np.float32)
        GL.glUseProgram(self._b)
        (c0, a0), (s1, c1, a1), (c2, a2) = stops
        for name, c in (("c0", c0), ("c1", c1), ("c2", c2)):
            GL.glUniform3f(self._ub[name], c.redF(), c.greenF(), c.blueF())
        GL.glUniform1f(self._ub["a0"], a0); GL.glUniform1f(self._ub["a1"], a1)
        GL.glUniform1f(self._ub["a2"], a2); GL.glUniform1f(self._ub["s1"], s1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._qbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, q.nbytes, q, GL.GL_DYNAMIC_DRAW)
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(0, 4, GL.GL_FLOAT, GL.GL_FALSE, 16, ctypes.c_void_p(0))
        GL.glDrawArrays(GL.GL_TRIANGLE_STRIP, 0, 4)
        GL.glDisableVertexAttribArray(0)

    def paintGL(self):
        if not self._ok or self._failed:
            return
        try:
            GL = self._GL
            c = self._canvas
            dpr = max(1.0, float(self.devicePixelRatioF()))
            W, H = self.width(), self.height()
            vw, vh = max(1.0, W * dpr), max(1.0, H * dpr)
            GL.glViewport(0, 0, int(vw), int(vh))
            GL.glClearColor(0.0, 0.0, 0.0, 1.0)
            GL.glClear(GL.GL_COLOR_BUFFER_BIT)
            if self._vao is not None:
                GL.glBindVertexArray(self._vao)
            GL.glDisable(GL.GL_DEPTH_TEST)
            GL.glEnable(GL.GL_BLEND)
            GL.glBlendFunc(GL.GL_ONE, GL.GL_ONE)            # additive light, like the CPU orb

            base, hot, white, energy = self._colors()
            R = c._orb_radius() * dpr
            cx, cy = vw / 2, (H / 2 + c.float_offset(H)) * dpr
            shell, amp = c._shell, c._amp_disp
            if R >= 4:
                # background haze
                self._blob(cx, cy, R * 1.3, vw, vh,
                           ((base, (70 + 40 * (1 - shell)) / 255 * energy), (0.5, base, 22 / 255 * energy), (base, 0.0)))
                # particles
                GL.glUseProgram(self._p)
                u = self._u
                vals = {"t": c._plex_t, "shell": shell, "wobble": c._wob, "wave": c._wave,
                        "yaw": c._yaw + c._plex_t * 0.15, "pitch": c._pitch, "R": R,
                        "px": max(0.6, min(1.6, R / dpr / 170.0)), "energy": energy, "amp": amp, "dpr": dpr}
                for k, v in vals.items():
                    GL.glUniform1f(u[k], float(v))
                GL.glUniform2f(u["center"], cx, cy)
                GL.glUniform2f(u["view"], vw, vh)
                for k, col in (("cBase", base), ("cHot", hot), ("cWhite", white)):
                    GL.glUniform3f(u[k], col.redF(), col.greenF(), col.blueF())
                GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._vbo)
                for i in range(4):
                    GL.glEnableVertexAttribArray(i)
                    GL.glVertexAttribPointer(i, 4, GL.GL_FLOAT, GL.GL_FALSE, 64, ctypes.c_void_p(16 * i))
                GL.glDrawArrays(GL.GL_POINTS, 0, self._m.n)
                for i in range(4):
                    GL.glDisableVertexAttribArray(i)
                # hot centre
                core_r = R * (0.24 + 0.14 * (1 - shell)) * (1 + 0.25 * amp)
                self._blob(cx, cy, core_r, vw, vh,
                           ((white, (190 - 100 * shell) / 255 * energy), (0.35, hot, (150 - 70 * shell) / 255 * energy),
                            (base, 0.0)))
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
            GL.glUseProgram(0)
            if self._vao is not None:
                GL.glBindVertexArray(0)
            GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
            self.frames += 1
        except Exception as e:
            self._fail(str(e))
