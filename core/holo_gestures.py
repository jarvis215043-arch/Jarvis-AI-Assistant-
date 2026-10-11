"""
core/holo_gestures.py — Turns what the webcam sees into hologram commands.

Each frame, actions/suit_hologram.py passes the hands MediaPipe found (21
landmarks + MediaPipe's guess at the sign and how sure it is). This file:

  1. READS THE SIGN TWICE — MediaPipe's guess, and a check of the hand's own
     shape (which fingers are straight, where the thumb points). A thumbs-up
     that MediaPipe calls "fist" or isn't sure about is still a thumbs-up.
  2. SMOOTHS IT — every hand is followed from frame to frame and the sign is a
     vote over the last ~0.35 s, so one bad frame doesn't cancel what you hold.
  3. HOLDS WITH A GRACE GAP — a hold survives short drop-outs (0.3 s), and the
     window shows a ring filling up while you hold.
  4. PINCH WITH HYSTERESIS — easy to start, hard to lose mid-move, and never
     confused with a thumbs-up or a fist (the index must not be folded into the palm).

It never touches the camera, so it can be tested with made-up hands.

GESTURES (act on the SELECTED hologram, or all of them when none is selected)
  one hand
    🤏 pinch + move        rotate
    ✊ fist + move          grab and move it around
    👋 swipe open palm      select the next / previous hologram
    ✋ hold open palm 1 s   spin on / off
    ☝️ point up             select all ↔ back to one
    👍 thumb up             next shape (keep holding to flick through all 140)
    👎 thumb down           previous shape
    ✌️ victory              next colour on the colour wheel
    🤟 love-you sign        next colour scheme (analogous, triadic, rainbow…)
  two hands
    🤏🤏 pinch both, pull apart / together   bigger / smaller
    ✋✋ open both, pull apart / together     explode / reassemble
    👎👎 both thumbs down, hold 1 s          remove it

Tuning (⚙ → 🛠 ADVANCED SETTINGS → GESTURES): "gesture_sensitivity" (the
lowest MediaPipe confidence that counts, default 0.4 — lower = picks up signs
more easily) and "gesture_hold" (seconds a sign is held before it acts, 0.3).
"""
import math
import time
from collections import Counter, deque

# ── tuning ──
MIN_SCORE = 0.40          # MediaPipe guesses below this are ignored (the shape check still runs)
HOLD = 0.30               # seconds a sign must be held before it acts
GRACE = 0.30              # a hold survives drop-outs this long
REPEAT = 0.80             # thumb up/down repeats this often while held
VOTE_WINDOW = 0.35        # seconds of frames each hand's sign is voted over
PINCH_IN = 0.30           # thumb–index gap / hand size below this starts a pinch (touching tips ≈ 0.05–0.25)
PINCH_OUT = 0.45          # … and above this ends it (a relaxed hand ≈ 0.8, a thumbs-up ≈ 0.5)
SWIPE_SPEED = 0.9         # screen-widths per second
SWIPE_DIST = 0.18         # minimum horizontal travel for a swipe
JUMP = 0.20               # a bigger move in one frame is a tracking glitch, not the hand
SMOOTH = 0.55             # cursor smoothing (1 = raw, lower = steadier)

SIGNS = ("Open_Palm", "Closed_Fist", "Pointing_Up", "Thumb_Up", "Thumb_Down", "Victory", "ILoveYou")
STRONG = {"Open_Palm", "Pointing_Up", "Thumb_Up", "Thumb_Down", "Victory", "ILoveYou"}   # never a pinch
LABELS = {"pinch": "🤏 ROTATE", "grab": "✊ GRAB · MOVE · NEAR = BIGGER", "zoom": "🤏🤏 RESIZE", "explode": "✋✋ EXPLODE"}
NAMES = {"Open_Palm": "✋ PALM", "Closed_Fist": "✊ FIST", "Pointing_Up": "☝ POINT", "Thumb_Up": "👍 THUMB UP",
         "Thumb_Down": "👎 THUMB DOWN", "Victory": "✌ VICTORY", "ILoveYou": "🤟 LOVE-YOU", "pinch": "🤏 PINCH"}
HOLD_ACTIONS = {"Thumb_Up": "👍  NEXT SHAPE", "Thumb_Down": "👎  PREVIOUS SHAPE", "Victory": "✌  NEXT COLOUR",
                "ILoveYou": "🤟  NEXT COLOUR SCHEME", "Pointing_Up": "☝  ALL / ONE"}

_FINGERS = ((5, 6, 8), (9, 10, 12), (13, 14, 16), (17, 18, 20))   # index, middle, ring, pinky: MCP, PIP, TIP


def configure(sensitivity=None, hold=None) -> None:
    """Apply the two Advanced Settings (called by the hands loop at start)."""
    global MIN_SCORE, HOLD
    try:
        if sensitivity is not None:
            MIN_SCORE = max(0.1, min(0.9, float(sensitivity)))
        if hold is not None:
            HOLD = max(0.1, min(1.5, float(hold)))
    except (TypeError, ValueError):
        pass


TIGHT_PINCH = 0.18        # tips this close = pinch even if the index is folded (a tight pinch)
CALIBRATED = None         # the saved calibration (dict) once applied


def calibration_path():
    import sys
    from pathlib import Path
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
    return base / "config" / "gesture_calibration.json"


def apply_calibration() -> dict | None:
    """Use the thresholds measured on YOUR hand (actions/gesture_calibration.py), if saved.
    They override the Gesture sensitivity setting. Returns them, or None."""
    global MIN_SCORE, PINCH_IN, PINCH_OUT, TIGHT_PINCH, CALIBRATED
    try:
        import json
        c = json.loads(calibration_path().read_text(encoding="utf-8"))
        MIN_SCORE = max(0.15, min(0.8, float(c.get("min_score", MIN_SCORE))))
        PINCH_IN = max(0.10, min(0.50, float(c.get("pinch_in", PINCH_IN))))
        PINCH_OUT = max(PINCH_IN + 0.05, min(0.65, float(c.get("pinch_out", PINCH_OUT))))
        TIGHT_PINCH = min(TIGHT_PINCH, PINCH_IN * 0.75)
        CALIBRATED = c
        return c
    except Exception:
        return None


def _dist(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


# ── the hand's own shape ─────────────────────────────────────────────────────
def hand_shape(lm) -> dict:
    """Which fingers are straight and where the thumb points, from landmarks alone."""
    size = _dist(lm[0], lm[9]) or 1e-3                     # wrist → middle knuckle
    w = lm[0]
    ext = [_dist(lm[t], w) > _dist(lm[p], w) * 1.10 for (_, p, t) in _FINGERS]
    # curled = the tip comes back well inside the middle joint (fist ≈ 0.7, a relaxed hand ≈ 0.95)
    curled = [_dist(lm[t], w) < _dist(lm[p], w) * 0.86 for (_, p, t) in _FINGERS]
    tx, ty = lm[4][0] - lm[2][0], lm[4][1] - lm[2][1]       # thumb: MCP → tip
    tlen = math.hypot(tx, ty)
    thumb_out = _dist(lm[4], lm[5]) > 0.40 * size and _dist(lm[4], lm[9]) > 0.50 * size and tlen > 0.25 * size
    # thumbs up / down: the thumb tip is the highest / lowest point of the whole hand and the thumb points that way
    knuckles_y = [lm[i][1] for i in (5, 9, 13, 17)]
    tips_y = [lm[i][1] for i in (8, 12, 16, 20)]
    long_thumb = tlen > 0.22 * size and _dist(lm[4], lm[8]) > 0.45 * size   # touching the index = a pinch, not a thumb sign
    up = (long_thumb and -ty > 0.6 * tlen and lm[4][1] < min(knuckles_y) - 0.05 * size
          and lm[4][1] < min(tips_y))
    down = (long_thumb and ty > 0.6 * tlen and lm[4][1] > max(knuckles_y) + 0.05 * size
            and lm[4][1] > max(tips_y))
    index_up = lm[8][1] < lm[5][1] - 0.45 * size
    folded = _dist(lm[8], w) < _dist(lm[5], w) * 1.05     # index tip pulled into the palm (fist / thumbs)
    return {"size": size, "ext": ext, "curled": curled, "thumb_out": thumb_out, "thumb_up": up,
            "thumb_down": down, "index_up": index_up, "index_folded": folded,
            "pinch_ratio": _dist(lm[4], lm[8]) / size}


def shape_sign(s: dict):
    """A sign from the hand's shape alone (or None when it's unclear)."""
    ext, cur = s["ext"], s["curled"]
    n_ext = sum(ext)
    if n_ext == 4:
        return "Open_Palm"
    if ext[0] and ext[1] and cur[2] and cur[3]:
        return "Victory"
    if ext[0] and ext[3] and cur[1] and cur[2]:
        return "ILoveYou"
    if ext[0] and cur[1] and cur[2] and cur[3]:
        return "Pointing_Up" if s["index_up"] else None
    if sum(cur) >= 3 and not ext[0]:
        if s["thumb_up"]:
            return "Thumb_Up"
        if s["thumb_down"]:
            return "Thumb_Down"
        if all(cur):                                       # a fist only when ALL four fingers are curled in
            return "Closed_Fist"
    return None


def hand_info(lm, gesture=None, score: float = 1.0) -> dict:
    """lm: 21 (x, y[, z]) landmarks in 0..1 screen coords (already mirrored);
    gesture/score: MediaPipe's top sign for this hand and how sure it is."""
    s = hand_shape(lm)
    model = gesture if gesture in SIGNS and score >= MIN_SCORE else None
    geo = shape_sign(s)
    if geo in ("Thumb_Up", "Thumb_Down") and model in (None, "Closed_Fist"):
        sign = geo                                         # MediaPipe often calls a thumbs-up a fist
    elif model == "Closed_Fist" and (geo in ("Open_Palm", "Victory", "ILoveYou", "Pointing_Up") or sum(s["curled"]) <= 1):
        sign = geo                                         # straight / relaxed fingers can't be a fist
    elif model is None:
        sign = geo
    elif geo is not None and geo != model and score < MIN_SCORE + 0.15:
        sign = geo                                         # unsure model vs a clear shape → shape
    else:
        sign = model
    # touching thumb + index tips = pinch, even when MediaPipe calls the hand a fist (a tight pinch looks like one)
    # a fist folds the index into the palm — only count that as a pinch when the tips really touch
    can_pinch = sign not in STRONG and (not s["index_folded"] or s["pinch_ratio"] < TIGHT_PINCH)
    palm = (sum(lm[i][0] for i in (0, 5, 9, 13, 17)) / 5, sum(lm[i][1] for i in (0, 5, 9, 13, 17)) / 5)
    tip = ((lm[4][0] + lm[8][0]) / 2, (lm[4][1] + lm[8][1]) / 2)
    pinch = can_pinch and s["pinch_ratio"] < PINCH_IN
    return {"pinch": pinch, "pr": s["pinch_ratio"], "can_pinch": can_pinch, "palm": palm, "tip": tip,
            "pt": tip if pinch else palm, "g": None if pinch else sign, "raw": sign, "size": s["size"],
            "model": model, "score": float(score or 0.0), "geo": geo}


# ── following each hand between frames ───────────────────────────────────────
class _Track:
    _n = 0

    def __init__(self, h, now):
        _Track._n += 1
        self.id = _Track._n
        self.palm = h["palm"]
        self.seen = now
        self.pinch = False
        self.pt = h["palm"]
        self.size = h.get("size", 0.1)                     # apparent hand size: bigger = nearer the camera
        self.votes = deque()                               # (t, sign or None)

    def feed(self, h, now) -> dict:
        self.palm, self.seen = h["palm"], now
        sz = h.get("size", self.size)
        self.size = sz if abs(sz - self.size) > 0.5 * self.size else self.size + (sz - self.size) * 0.35
        was = self.pinch                                   # pinch with hysteresis
        self.pinch = h["can_pinch"] and h["pr"] < (PINCH_OUT if was else PINCH_IN)
        raw_pt = h["tip"] if self.pinch else h["palm"]
        if self.pinch != was or _dist(raw_pt, self.pt) > JUMP:
            self.pt = raw_pt                               # mode change / glitch: jump, don't glide
        else:
            self.pt = (self.pt[0] + (raw_pt[0] - self.pt[0]) * SMOOTH, self.pt[1] + (raw_pt[1] - self.pt[1]) * SMOOTH)
        self.votes.append((now, "pinch" if self.pinch else h["raw"]))
        while self.votes and now - self.votes[0][0] > VOTE_WINDOW:
            self.votes.popleft()
        c = Counter(v for _, v in self.votes if v)
        sign = None
        if c:
            best, k = c.most_common(1)[0]
            if k >= max(2, 0.45 * len(self.votes)) or (len(self.votes) <= 2 and self.votes[-1][1] == best):
                sign = best
        if sign == "pinch" and not self.pinch:
            sign = None
        return {"pinch": self.pinch, "palm": self.palm, "pt": self.pt, "g": None if self.pinch or sign == "pinch" else sign,
                "tid": self.id, "size": self.size}


class HoloGestureEngine:
    def __init__(self):
        self.tracks: list[_Track] = []
        self.cool = {}                 # action → earliest next time
        self.hold_g = None             # sign being held, when it started, when last seen
        self.hold_t0 = self.hold_last = 0.0
        self.fired = False
        self.last_one = None           # (mode, track id, point) of the single active hand last frame
        self.last_two = None           # (mode, distance) of the two-hand gesture last frame
        self.palm_hist = deque()       # (t, x, y) of an open palm, for swipes / holding still
        self.palm_still_since = None
        self.both_down_since = None
        self.mode = ""
        self.was_grab = False
        self.grab_size = None          # hand size when the grab started / last scaled

    # small helpers
    def _ready(self, key, now, gap):
        if now >= self.cool.get(key, 0):
            self.cool[key] = now + gap
            return True
        return False

    def _match(self, hands, now) -> list:
        """Pair this frame's hands with last frame's (nearest palm), so votes and pinch state carry over."""
        out, free = [], list(self.tracks)
        for h in hands:
            best = min(free, key=lambda tr: _dist(tr.palm, h["palm"]), default=None)
            if best is not None and _dist(best.palm, h["palm"]) < 0.25:
                free.remove(best)
            else:
                best = _Track(h, now)
                self.tracks.append(best)
            out.append(best.feed(h, now))
        self.tracks = [tr for tr in self.tracks if now - tr.seen < 0.5]
        return out

    def _reset_hold(self):
        self.hold_g, self.fired = None, False

    def _hold(self, g, now):
        """How long sign g has been held (tolerating short gaps). None = not holding."""
        if g is None:
            if self.hold_g is not None and now - self.hold_last > GRACE:
                self.hold_g, self.fired = None, False
            return None
        if g != self.hold_g or now - self.hold_last > GRACE:
            self.hold_g, self.hold_t0, self.fired = g, now, False
        self.hold_last = now
        return now - self.hold_t0

    def update(self, hands: list, now: float | None = None) -> list:
        """hands: [hand_info(...), ...]. Returns a list of command dicts.
        Grab (2.6): a fist starting over a hologram picks THAT one ({"grab_at": (x, y)}),
        moving the fist nearer / further from the camera makes it bigger / smaller, and
        opening the hand drops it ({"release": True})."""
        out = self._update(hands, now)
        grabbing = self.last_one is not None and self.last_one[0] == "grab"
        if self.was_grab and not grabbing:
            out.append({"release": True})
            self.grab_size = None
        self.was_grab = grabbing
        return out

    def _update(self, hands: list, now: float | None = None) -> list:
        now = time.monotonic() if now is None else now
        out = []
        hands = sorted(self._match(hands, now), key=lambda h: h["palm"][0])
        out.append({"cursors": [(h["pt"][0], h["pt"][1], "pinch" if h["pinch"] else (h["g"] or "hand")) for h in hands]})
        if not hands:
            self._hold(None, now)
            self.last_one, self.last_two, self.mode = None, None, ""
            self.palm_hist.clear(); self.palm_still_since = self.both_down_since = None
            out.append({"hold": None})
            return out

        # ── two hands ──
        if len(hands) >= 2:
            a, b = hands[0], hands[1]
            d = _dist(a["pt"], b["pt"])
            two = None
            if a["pinch"] and b["pinch"]:
                two = "zoom"
            elif a["g"] == "Open_Palm" and b["g"] == "Open_Palm":
                two = "explode"
            if two and self.last_two and self.last_two[0] == two and self.last_two[1] > 0.02:
                ratio = d / self.last_two[1]
                if two == "zoom" and abs(ratio - 1) > 0.004:
                    out.append({"scale": max(0.85, min(1.18, ratio))})
                if two == "explode" and abs(d - self.last_two[1]) > 0.003:
                    out.append({"explode": max(-0.3, min(0.3, (d - self.last_two[1]) * 3.0))})
            self.last_two = (two, d) if two else None
            if a["g"] == "Thumb_Down" and b["g"] == "Thumb_Down":
                self.both_down_since = self.both_down_since or now
                p = (now - self.both_down_since) / 1.0
                out.append({"hold": {"label": "👎👎  REMOVE", "p": min(1.0, p)}})
                if p >= 1.0 and self._ready("remove", now, 2.0):
                    out.append({"op": "remove_selected"}); out.append({"feedback": "👎👎  REMOVED"})
                self._reset_hold()                 # don't let the one-hand thumb-down fire too
                return out
            self.both_down_since = None
            if two:
                self.mode = two
                self.last_one = None
                out.append({"mode": LABELS[two]}); out.append({"hold": None})
                return out
        else:
            self.last_two, self.both_down_since = None, None

        # ── one hand: the one doing something (a resting second hand never steals control) ──
        h = (next((x for x in hands if x["pinch"]), None)
             or next((x for x in hands if x["g"] == "Closed_Fist"), None)
             or next((x for x in hands if x["g"] in HOLD_ACTIONS), None)
             or next((x for x in hands if x["g"]), None) or hands[0])
        g = h["g"]
        mode = "pinch" if h["pinch"] else ("grab" if g == "Closed_Fist" else None)
        if mode == "grab" and not (self.last_one and self.last_one[0] == "grab"):
            out.append({"grab_at": (h["pt"][0], h["pt"][1])})       # pick up the hologram under the fist
            self.grab_size = h.get("size")
        elif mode == "grab" and self.grab_size and h.get("size"):
            r = h["size"] / self.grab_size                          # nearer the camera = bigger hand = bigger hologram
            if abs(r - 1) > 0.025:
                out.append({"scale": max(0.88, min(1.14, r ** 1.4))})
                self.grab_size = h["size"]
        if mode and self.last_one and self.last_one[0] == mode and self.last_one[1] == h["tid"]:
            dx = h["pt"][0] - self.last_one[2][0]
            dy = h["pt"][1] - self.last_one[2][1]
            if abs(dx) + abs(dy) > JUMP:                       # tracking jumped — re-anchor
                dx = dy = 0.0
            if abs(dx) + abs(dy) > 0.0015:
                out.append({"dyaw": dx * 7.0, "dpitch": dy * 5.0} if mode == "pinch" else {"move": (dx * 1.2, dy * 1.2)})
        self.last_one = (mode, h["tid"], h["pt"]) if mode else None
        if mode:
            self._reset_hold()
            self.palm_hist.clear(); self.palm_still_since = None
            self.mode = mode
            out.append({"mode": LABELS[mode]}); out.append({"hold": None})
            return out

        # open palm: swipe (fast sideways) or hold still (spin toggle)
        if g == "Open_Palm":
            self._reset_hold()
            x, y = h["palm"]
            self.palm_hist.append((now, x, y))
            while self.palm_hist and now - self.palm_hist[0][0] > 0.4:
                self.palm_hist.popleft()
            t0, x0, _ = self.palm_hist[0]
            if now - t0 > 0.06:
                travel = x - x0
                if abs(travel) >= SWIPE_DIST and abs(travel) / (now - t0) >= SWIPE_SPEED and self._ready("swipe", now, 0.6):
                    out.append({"op": "select", "dir": 1 if travel > 0 else -1})
                    out.append({"feedback": "👋  NEXT" if travel > 0 else "👋  PREVIOUS"})
                    self.palm_hist.clear(); self.palm_still_since = None
                    out.append({"hold": None})
                    return out
            xs = [p[1] for p in self.palm_hist]; ys = [p[2] for p in self.palm_hist]
            if max(xs) - min(xs) < 0.05 and max(ys) - min(ys) < 0.05:
                self.palm_still_since = self.palm_still_since or now
                p = (now - self.palm_still_since) / 1.0
                if p >= 1.0:
                    if self._ready("spin", now, 1.8):
                        out.append({"op": "spin_toggle"}); out.append({"feedback": "✋  SPIN ON / OFF"})
                    out.append({"hold": None})
                elif p > 0.25:
                    out.append({"hold": {"label": "✋  SPIN ON / OFF", "p": p}})
            else:
                self.palm_still_since = None
                out.append({"hold": None})
            self.mode = "palm"
            out.append({"mode": "✋ PALM"})
            return out
        self.palm_hist.clear(); self.palm_still_since = None

        t = self._hold(g if g in HOLD_ACTIONS else None, now)
        self.mode = NAMES.get(g, "") if g else ""
        if self.mode:
            out.append({"mode": self.mode})
        if t is None:
            if self.hold_g is not None and not self.fired:     # brief drop-out: keep the ring where it was
                out.append({"hold": {"label": HOLD_ACTIONS[self.hold_g],
                                     "p": min(0.99, (self.hold_last - self.hold_t0) / max(HOLD, 1e-3))}})
            else:
                out.append({"hold": None})
            return out
        g = self.hold_g
        if not self.fired:
            p = t / HOLD if HOLD > 0 else 1.0
            if p < 1.0:
                out.append({"hold": {"label": HOLD_ACTIONS[g], "p": p}})
                return out
        out.append({"hold": None})
        if g == "Thumb_Up" and self._ready("shape", now, REPEAT):
            out += [{"op": "shape", "dir": 1}, {"feedback": "👍  NEXT SHAPE"}]
        elif g == "Thumb_Down" and self._ready("shape", now, REPEAT):
            out += [{"op": "shape", "dir": -1}, {"feedback": "👎  PREVIOUS SHAPE"}]
        elif g == "Victory" and not self.fired and self._ready("color", now, 0.8):
            out += [{"op": "next_color"}, {"feedback": "✌  NEXT COLOUR"}]
        elif g == "ILoveYou" and not self.fired and self._ready("scheme", now, 0.8):
            out += [{"op": "next_scheme"}, {"feedback": "🤟  NEXT COLOUR SCHEME"}]
        elif g == "Pointing_Up" and not self.fired and self._ready("all", now, 1.0):
            out += [{"op": "select_all"}, {"feedback": "☝  ALL / ONE"}]
        self.fired = True
        return out


# ── a smoother for the general gesture control (actions/gesture_control.py) ──
class SignSmoother:
    """Votes the sign over the last few frames and reports a sign ONCE when it
    becomes steady — tolerant of MediaPipe's frame-to-frame flicker."""

    def __init__(self, frames: int = 5, need: int = 3):
        self.hist = deque(maxlen=frames)
        self.need = need
        self.current = None

    def feed(self, sign):
        """Returns the sign the moment it becomes steady, else None."""
        self.hist.append(sign)
        c = Counter(s for s in self.hist if s)
        steady = None
        if c:
            best, k = c.most_common(1)[0]
            if k >= self.need:
                steady = best
        if steady is None and not any(self.hist):
            self.current = None
        if steady and steady != self.current:
            self.current = steady
            return steady
        return None
