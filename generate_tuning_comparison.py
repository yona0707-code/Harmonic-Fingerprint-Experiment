#!/usr/bin/env python3
"""Generate controlled ET/Pythagorean left-hand piano stimuli.

Requires FluidSynth and GeneralUser-GS.sf2 in this directory.  The MIDI files
use three channels (one per chord tone), allowing each simultaneous note to
receive its own pitch bend while retaining exactly the same piano preset.
"""

from __future__ import annotations

import math
import shutil
import struct
import subprocess
import wave
from fractions import Fraction
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOUNDFONT = ROOT / "GeneralUser-GS.sf2"
SAMPLE_RATE = 44_100
TEMPO_BPM = 80
PPQ = 480
BAR_TICKS = 4 * PPQ
VELOCITY = 72
PROGRAM = 0  # General MIDI Acoustic Grand Piano

# Root-position left-hand voicings. Bars 9--16 are bars 1--8 transposed by an
# augmented fourth (six MIDI semitones), including C# major's notated E# on the
# fixed keyboard's F key.
C_MAJOR_BLOCK = ((48, 52, 55), (41, 45, 48), (43, 47, 50), (48, 52, 55))
CHORDS = C_MAJOR_BLOCK * 2 + tuple(
    tuple(note + 6 for note in chord) for chord in C_MAJOR_BLOCK * 2
)

# One fixed, 12-pitch chain of pure 3:2 fifths, F through A#. Ratios are octave
# reduced relative to C. This is never changed when the passage reaches F#.
PYTHAGOREAN_RATIOS = {
    0: Fraction(1, 1),             # C
    1: Fraction(2187, 2048),       # C#
    2: Fraction(9, 8),             # D
    3: Fraction(19683, 16384),     # D#
    4: Fraction(81, 64),           # E
    5: Fraction(4, 3),             # F (not retuned as E#)
    6: Fraction(729, 512),         # F#
    7: Fraction(3, 2),             # G
    8: Fraction(6561, 4096),       # G#
    9: Fraction(27, 16),           # A
    10: Fraction(59049, 32768),    # A#
    11: Fraction(243, 128),        # B
}


def variable_length(value: int) -> bytes:
    """Encode a nonnegative integer as a MIDI variable-length quantity."""
    out = [value & 0x7F]
    value >>= 7
    while value:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    return bytes(reversed(out))


def pythagorean_frequency(midi_note: int) -> float:
    """Frequency for a MIDI key in the fixed C-referenced Pythagorean scale."""
    # Since A/C = 27/16, fixing A4=440 gives C4 = 440 * 16/27.
    c4_hz = 440.0 * 16.0 / 27.0
    octave = (midi_note // 12) - 5  # MIDI C4=60 lies in quotient octave 5
    return c4_hz * (2.0 ** octave) * float(PYTHAGOREAN_RATIOS[midi_note % 12])


def cents_from_et(midi_note: int) -> float:
    et_hz = 440.0 * 2.0 ** ((midi_note - 69) / 12.0)
    return 1200.0 * math.log2(pythagorean_frequency(midi_note) / et_hz)


def pitch_bend(cents: float) -> int:
    """Map cents to MIDI's 14-bit bend value (default +/-2 semitones)."""
    return max(0, min(16383, round(8192 + cents / 200.0 * 8192)))


def make_midi(path: Path, pythagorean: bool) -> None:
    # Format 0, one event stream. Three channels provide independent bends.
    events: list[tuple[int, int, bytes]] = []
    tempo_us = round(60_000_000 / TEMPO_BPM)
    events.append((0, 0, b"\xff\x51\x03" + tempo_us.to_bytes(3, "big")))
    events.append((0, 1, b"\xff\x58\x04\x04\x02\x18\x08"))  # 4/4
    for channel in range(3):
        events.append((0, 10 + channel, bytes((0xC0 | channel, PROGRAM))))
        events.append((0, 20 + channel, bytes((0xB0 | channel, 91, 0))))  # reverb
        events.append((0, 30 + channel, bytes((0xB0 | channel, 93, 0))))  # chorus

    for bar, chord in enumerate(CHORDS):
        start = bar * BAR_TICKS
        end = start + BAR_TICKS
        for channel, note in enumerate(chord):
            cents = cents_from_et(note) if pythagorean else 0.0
            bend = pitch_bend(cents)
            events.append((start, 40 + channel, bytes((0xE0 | channel, bend & 0x7F, bend >> 7))))
            events.append((start, 50 + channel, bytes((0x90 | channel, note, VELOCITY))))
            events.append((end, channel, bytes((0x80 | channel, note, 0))))

    events.append((len(CHORDS) * BAR_TICKS, 100, b"\xff\x2f\x00"))
    events.sort(key=lambda event: (event[0], event[1]))
    track = bytearray()
    prior_tick = 0
    for tick, _, payload in events:
        track += variable_length(tick - prior_tick) + payload
        prior_tick = tick
    header = b"MThd" + struct.pack(">IHHH", 6, 0, 1, PPQ)
    path.write_bytes(header + b"MTrk" + struct.pack(">I", len(track)) + track)


def render(midi_path: Path, wav_path: Path) -> None:
    fluidsynth = shutil.which("fluidsynth")
    if not fluidsynth:
        raise RuntimeError("FluidSynth is required (for macOS: brew install fluid-synth)")
    if not SOUNDFONT.exists():
        raise RuntimeError(f"Missing SoundFont: {SOUNDFONT}")
    subprocess.run(
        [fluidsynth, "-ni", "-R", "0", "-C", "0", "-r", str(SAMPLE_RATE),
         "-g", "0.7", "-F", str(wav_path), str(SOUNDFONT), str(midi_path)],
        check=True,
    )


def concatenate_ab(equal_path: Path, pyth_path: Path, output_path: Path) -> None:
    with wave.open(str(equal_path), "rb") as equal_wav, wave.open(str(pyth_path), "rb") as pyth_wav:
        params = equal_wav.getparams()
        if params[:4] != pyth_wav.getparams()[:4]:
            raise RuntimeError("Rendered WAV formats do not match")
        equal_frames = equal_wav.readframes(equal_wav.getnframes())
        pyth_frames = pyth_wav.readframes(pyth_wav.getnframes())
    silence = b"\x00" * SAMPLE_RATE * params.nchannels * params.sampwidth
    with wave.open(str(output_path), "wb") as out:
        out.setparams(params)
        out.writeframes(equal_frames + silence + pyth_frames)


def write_tuning_table(path: Path) -> None:
    names = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
    lines = [
        "# Fixed Pythagorean tuning used in the comparison", "",
        "Pure-fifth chain: `F–C–G–D–A–E–B–F#–C#–G#–D#–A#`.",
        "A4 is fixed at 440 Hz, hence C4 = 440 × 16/27 = 260.740741 Hz.",
        "The mapping is fixed for all 16 bars; F is not changed to E# in C# major.", "",
        "| Key | Ratio to C | Cents above C | Deviation from 12-TET |", "|---|---:|---:|---:|",
    ]
    c_offset = cents_from_et(60)
    for pc, name in enumerate(names):
        ratio = PYTHAGOREAN_RATIOS[pc]
        cents = 1200 * math.log2(float(ratio))
        deviation = cents - pc * 100 + c_offset
        lines.append(f"| {name} | {ratio.numerator}/{ratio.denominator} | {cents:.6f} | {deviation:+.6f} cents |")
    lines += ["", "Both files use program 0 (Acoustic Grand Piano), velocity 72, 80 BPM, no chorus/reverb, and identical events."]
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    equal_midi = ROOT / "left_hand_equal_temperament.mid"
    pyth_midi = ROOT / "left_hand_pythagorean.mid"
    equal_wav = ROOT / "left_hand_equal_temperament.wav"
    pyth_wav = ROOT / "left_hand_pythagorean.wav"
    make_midi(equal_midi, False)
    make_midi(pyth_midi, True)
    render(equal_midi, equal_wav)
    render(pyth_midi, pyth_wav)
    concatenate_ab(equal_wav, pyth_wav, ROOT / "left_hand_equal_vs_pythagorean_AB.wav")
    write_tuning_table(ROOT / "PYTHAGOREAN_TUNING.md")
    print("Generated MIDI, WAV, A/B comparison, and tuning documentation.")


if __name__ == "__main__":
    main()
