"""
core/clap.py — Double-clap detector.

A clap is a very sudden, very short, loud sound: the level jumps many times
above the room's background noise within a few milliseconds and dies away fast.
Speech rises more slowly, so it's mostly ignored. Two claps between 0.15 and
0.9 seconds apart = a double clap.

Used by clap_launcher.py and the boot screen (clap twice → start JARVIS) and
main.py (one clap → mute, two claps → unmute).
"""
import numpy as np


class ClapDetector:
    def __init__(self, rate: int = 16000, threshold: float = 0.30, onset_ratio: float = 5.0,
                 bg_ratio: float = 7.0, min_gap: float = 0.15, max_gap: float = 0.9):
        self.rate = rate
        self.win = max(1, rate // 100)          # 10 ms windows
        self.threshold, self.onset_ratio, self.bg_ratio = threshold, onset_ratio, bg_ratio
        self.min_gap, self.max_gap = min_gap, max_gap
        self.bg = 0.01                           # running background level (RMS)
        self.prev_rms = 0.01
        self.t = 0.0                             # seconds of audio seen
        self.last_clap = -10.0
        self.first = None
        self.decay_check = None                  # (time, peak_rms) of a candidate clap
        self._buf = np.zeros(0, dtype=np.float32)

    def feed(self, frames) -> bool:
        """Feed audio (int16 or float, any shape). Returns True on a double clap."""
        return self.feed_events(frames) == "double"

    def feed_events(self, frames):
        """Like feed(), but returns "double", "single" (one clap and no second one
        within max_gap seconds) or None."""
        x = np.asarray(frames)
        x = (x.astype(np.float32) / 32768.0) if x.dtype == np.int16 else x.astype(np.float32)
        self._buf = np.concatenate([self._buf, x.reshape(-1)])
        fired = None
        while len(self._buf) >= self.win:
            w, self._buf = self._buf[:self.win], self._buf[self.win:]
            now = self.t
            self.t += self.win / self.rate
            peak = float(np.max(np.abs(w)))
            rms = float(np.sqrt(np.mean(w * w)) + 1e-6)

            # confirm a candidate clap only if it died away quickly (~40 ms later)
            if self.decay_check is not None and now - self.decay_check[0] >= 0.04:
                cand_t, cand_rms = self.decay_check
                self.decay_check = None
                if rms < cand_rms * 0.45:            # sharp decay → a real clap
                    if self.first is not None and self.min_gap <= cand_t - self.first <= self.max_gap:
                        self.first = None
                        fired = "double"
                    else:
                        self.first = cand_t
                    self.last_clap = cand_t

            sudden = rms > self.prev_rms * self.onset_ratio and rms > self.bg * self.bg_ratio
            if (peak >= self.threshold and sudden and self.decay_check is None
                    and now - self.last_clap > self.min_gap * 0.7):
                self.decay_check = (now, rms)
            elif self.decay_check is None:
                self.bg = 0.995 * self.bg + 0.005 * rms   # learn the room's noise level
            if self.first is not None and now - self.first > self.max_gap:
                self.first = None
                fired = fired or "single"          # one clap, and no second one came
            self.prev_rms = rms
        return fired
