"""
core/whistle.py — Whistle detector (whistle → JARVIS shuts down).

A whistle is an almost pure tone between ~500 and 4,500 Hz that lasts. So a
frame counts as "whistle" when, in that band:
  • one narrow peak holds most of the energy  (tonality — speech has many harmonics)
  • the band holds most of the frame's energy  (speech/music sit mostly lower)
  • it's clearly louder than the room's background
and it fires when that continues for min_seconds (default 0.7 s) with a steady
or smoothly gliding pitch (a tune of separate notes — e.g. music — doesn't count). Beeps and alarms (perfectly steady machine tones), claps, talking and noise
don't trigger it.
Settings: "whistle_shutdown": false to turn off, "whistle_seconds": 0.7.
"""
import numpy as np


class WhistleDetector:
    def __init__(self, rate: int = 16000, min_seconds: float = 0.7, lo: float = 500.0, hi: float = 4500.0,
                 tonality: float = 0.55, band_share: float = 0.6):
        self.rate, self.n, self.hop = rate, 1024, 512
        self.win = np.hanning(self.n).astype(np.float32)
        f = np.fft.rfftfreq(self.n, 1.0 / rate)
        self.band = (f >= lo) & (f <= hi)
        self.freqs = f
        self.need = max(3, int(min_seconds * rate / self.hop))
        self.tonality, self.band_share = tonality, band_share
        self.buf = np.zeros(0, np.float32)
        self.bg = 0.005
        self.run, self.last_f, self.cool, self.jumps = 0, None, 0, 0
        self.hist = []                       # (precise pitch, loudness) during the current run

    def _machine_tone(self) -> bool:
        """Electronic beeps hold an exact pitch and volume; a human whistle always
        wobbles a little (pitch jitter of a few Hz, breath changes the loudness)."""
        h = np.array(self.hist[-self.need:])
        if len(h) < 3:
            return False
        f = h[:, 0]
        # measured: machine beeps ≈ 0.005 % pitch wobble, a very steady human whistle ≈ 0.2 %
        return float(np.std(f)) < 0.0006 * float(np.mean(f))

    def feed(self, frames) -> bool:
        x = np.asarray(frames)
        x = (x.astype(np.float32) / 32768.0) if x.dtype == np.int16 else x.astype(np.float32)
        self.buf = np.concatenate([self.buf, x.reshape(-1)])
        fired = False
        while len(self.buf) >= self.n:
            fr = self.buf[: self.n]
            self.buf = self.buf[self.hop:]
            if self.cool:
                self.cool -= 1
                continue
            rms = float(np.sqrt(np.mean(fr * fr)) + 1e-9)
            spec = np.abs(np.fft.rfft(fr * self.win)) ** 2
            total = float(spec.sum()) + 1e-12
            band = spec[self.band]
            bsum = float(band.sum()) + 1e-12
            k = int(np.argmax(band))
            peak = float(band[max(0, k - 5): k + 6].sum())     # ±78 Hz: allows a wobbly whistle
            freq = float(self.freqs[self.band][k])
            # sub-bin pitch (parabolic fit) — precise enough to tell a human from a machine
            if 0 < k < len(band) - 1:
                a, b, c = np.log(band[k - 1] + 1e-12), np.log(band[k] + 1e-12), np.log(band[k + 1] + 1e-12)
                den = a - 2 * b + c
                fine = freq + (0.5 * (a - c) / den if den else 0.0) * (self.freqs[1] - self.freqs[0])
            else:
                fine = freq
            tonal = (rms > max(0.012, self.bg * 4) and peak / bsum > self.tonality and bsum / total > self.band_share)
            step = abs(freq - self.last_f) / self.last_f if (tonal and self.last_f) else 0.0
            if tonal and step < 0.35:
                self.run += 1
                self.hist.append((fine, rms))
                if self.last_f and abs(freq - self.last_f) > max(0.06 * self.last_f, 90.0):
                    self.jumps += 1                        # a separate note (a tune), not a glide/wobble
                    if self.jumps > 1:                     # 2+ notes → a melody (music), not a whistle
                        self.run, self.jumps = 1, 0
                self.last_f = freq
            elif tonal:
                self.run, self.last_f, self.jumps = 1, freq, 0   # pitch jumped: start counting again
                self.hist = [(fine, rms)]
            else:
                self.run, self.last_f, self.jumps = 0, None, 0
                self.hist = []
                self.bg = 0.995 * self.bg + 0.005 * rms   # learn the room's background level
            if self.run >= self.need:
                if self._machine_tone():
                    self.run, self.hist = 0, []          # alarm / timer / beep: perfectly steady → ignore
                    continue
                fired = True
                self.run, self.last_f, self.jumps, self.cool = 0, None, 0, int(2.0 * self.rate / self.hop)
                self.hist = []
        return fired
