#!/usr/bin/env python3
"""Generate piano versions of the controlled-harmony Kaeru no Uta stimulus."""

from __future__ import annotations

import math
import shutil
import struct
import subprocess
import tempfile
import wave
from pathlib import Path


SAMPLE_RATE = 44_100
TEMPO_BPM = 112
SECONDS_PER_BEAT = 60.0 / TEMPO_BPM
ACCOMPANIMENT_LEVEL = 0.63
PPQ = 480
PROGRAM = 0  # General MIDI Acoustic Grand Piano
ROOT = Path(__file__).resolve().parent
SOUNDFONT = ROOT / "GeneralUser-GS.sf2"

NOTE_MIDI = {
    "G2": 43,
    "A2": 45,
    "C3": 48,
    "D3": 50,
    "Eb3": 51,
    "E3": 52,
    "F3": 53,
    "F#3": 54,
    "Gb3": 54,
    "G3": 55,
    "G#3": 56,
    "Ab3": 56,
    "A3": 57,
    "Bb3": 58,
    "B3": 59,
    "C4": 60,
    "Db4": 61,
    "D4": 62,
    "Eb4": 63,
    "E4": 64,
    "F4": 65,
    "F#4": 66,
    "G4": 67,
    "G#4": 68,
    "Ab4": 68,
    "A4": 69,
    "Bb4": 70,
    "B4": 71,
    "C5": 72,
    "D5": 74,
}

CHORDS = {
    "C": ("C3", "E3", "G3"),
    "F": ("F3", "A3", "C4"),
    "G": ("G3", "B3", "D4"),
}

# Controlled minor counterpart to CHORDS. Roots, fifths, voicing, and register
# are unchanged; only each major third is lowered by one semitone.
MINOR_CHORDS = {
    "C": ("C3", "Eb3", "G3"),
    "F": ("F3", "Ab3", "C4"),
    "G": ("G3", "Bb3", "D4"),
}

DIMINISHED_SEVENTH_CHORDS = {
    "C": ("C3", "Eb3", "Gb3", "A3"),
    "F": ("F3", "Ab3", "B3", "D4"),
    "G": ("G3", "Bb3", "Db4", "E4"),
}

# The original seventh-rich condition is the source of truth. Tuple order and
# octaves are deliberately preserved exactly from the original implementation.
SEVENTH_RICH_MAJOR_CHORDS = {
    "Cmaj7": ("C3", "E3", "G3", "B3"),
    "E7": ("E3", "G#3", "B3", "D4"),
    "Am7": ("A2", "C3", "E3", "G3"),
    "C7": ("C3", "E3", "G3", "Bb3"),
    "F": ("F3", "A3", "C4"),
    "Dm7": ("D3", "F3", "A3", "C4"),
    "G": ("G3", "B3", "D4"),
    "C": ("C3", "E3", "G3"),
}

# Corresponding minor harmony: lower only major thirds. Chords already minor
# in the original rich progression remain untouched.
SEVENTH_RICH_MINOR_CHORDS = {
    "Cmaj7": ("C3", "Eb3", "G3", "B3"),
    "E7": ("E3", "G3", "B3", "D4"),
    "Am7": ("A2", "C3", "E3", "G3"),
    "C7": ("C3", "Eb3", "G3", "Bb3"),
    "F": ("F3", "Ab3", "C4"),
    "Dm7": ("D3", "F3", "A3", "C4"),
    "G": ("G3", "Bb3", "D4"),
    "C": ("C3", "Eb3", "G3"),
}

# Ninth-rich is mechanically the corresponding seventh-rich tuple plus one
# ninth. Nothing in the source voicing is reordered, removed, doubled, or moved.
RICH_NINTH_BY_CHORD = {
    "Cmaj7": "D4", "E7": "F#4", "Am7": "B3", "C7": "D4",
    "F": "G4", "Dm7": "E4", "G": "A4", "C": "D4",
}
NINTH_RICH_MAJOR_CHORDS = {
    name: notes + (RICH_NINTH_BY_CHORD[name],)
    for name, notes in SEVENTH_RICH_MAJOR_CHORDS.items()
}
NINTH_RICH_MINOR_CHORDS = {
    name: notes + (RICH_NINTH_BY_CHORD[name],)
    for name, notes in SEVENTH_RICH_MINOR_CHORDS.items()
}

ARRANGEMENT_BEATS = 32

# One entry per beat; ``None`` means the notated quarter rest. Harmony is kept
# separate so later conditions can replace chord tones without changing timing.
HARMONY_BY_MEASURE = (
    ("C", None, "C", None),
    ("C", "G", "C", None),
    ("C", None, "C", None),
    ("C", "F", "C", None),
    (None, "C", None, "C"),
    (None, "C", None, "C"),
    ("C", "G", "C", "F"),
    ("C", "G", "C", None),
)

# This condition changes chord identity only. Its pattern of attacks and rests
# is identical to HARMONY_BY_MEASURE. Bar 8 places G on its first two attacks
# and C on its final attack, preserving the arrangement's rhythmic structure.
RICH_HARMONY_BY_MEASURE = (
    ("Cmaj7", None, "Cmaj7", None),
    ("E7", "E7", "E7", None),
    ("Am7", None, "Am7", None),
    ("C7", "C7", "C7", None),
    (None, "F", None, "F"),
    (None, "F", None, "F"),
    ("Dm7", "Dm7", "Dm7", "Dm7"),
    ("G", "G", "C", None),
)

ACCOMPANIMENT_OPTIONS = {
    "basic_major": (CHORDS, HARMONY_BY_MEASURE),
    "basic_triads_minor": (MINOR_CHORDS, HARMONY_BY_MEASURE),
    "seventh_rich_major": (SEVENTH_RICH_MAJOR_CHORDS, RICH_HARMONY_BY_MEASURE),
    "seventh_rich_minor": (SEVENTH_RICH_MINOR_CHORDS, RICH_HARMONY_BY_MEASURE),
    "ninth_rich_major": (NINTH_RICH_MAJOR_CHORDS, RICH_HARMONY_BY_MEASURE),
    "ninth_rich_minor": (NINTH_RICH_MINOR_CHORDS, RICH_HARMONY_BY_MEASURE),
    "diminished_sevenths": (
        DIMINISHED_SEVENTH_CHORDS,
        HARMONY_BY_MEASURE,
    ),
}


def variable_length(value: int) -> bytes:
    """Encode a nonnegative integer as a MIDI variable-length quantity."""
    out = [value & 0x7F]
    value >>= 7
    while value:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    return bytes(reversed(out))


def make_midi(
    path: Path,
    chords: dict[str, tuple[str, ...]],
    harmony_by_measure: tuple[tuple[str | None, ...], ...],
) -> None:
    """Write the chord accompaniment with no right-hand notes."""
    events: list[tuple[int, int, bytes]] = []
    tempo_us = round(60_000_000 / TEMPO_BPM)
    events.append((0, 0, b"\xff\x51\x03" + tempo_us.to_bytes(3, "big")))
    events.append((0, 1, b"\xff\x58\x04\x04\x02\x18\x08"))  # 4/4
    # Channel 1 is the left-hand accompaniment. Channel 0 is intentionally
    # unused so every Kaeru stimulus contains zero right-hand MIDI notes.
    events.append((0, 11, bytes((0xC1, PROGRAM))))

    for measure_index, measure in enumerate(harmony_by_measure):
        for beat_index, chord_name in enumerate(measure):
            if chord_name is None:
                continue
            start = (measure_index * 4 + beat_index) * PPQ
            end = start + PPQ
            # Equal-power distribution makes ACCOMPANIMENT_LEVEL describe the
            # perceived level of the complete chord, rather than each note.
            velocity = round(
                ACCOMPANIMENT_LEVEL / math.sqrt(len(chords[chord_name])) * 127
            )
            for note in chords[chord_name]:
                midi_note = NOTE_MIDI[note]
                events.append((start, 60, bytes((0x91, midi_note, velocity))))
                events.append((end, 30, bytes((0x81, midi_note, 0))))

    final_tick = ARRANGEMENT_BEATS * PPQ
    events.append((final_tick, 100, b"\xff\x2f\x00"))
    events.sort(key=lambda event: (event[0], event[1]))
    track = bytearray()
    prior_tick = 0
    for tick, _, payload in events:
        track += variable_length(tick - prior_tick) + payload
        prior_tick = tick
    header = b"MThd" + struct.pack(">IHHH", 6, 0, 1, PPQ)
    path.write_bytes(header + b"MTrk" + struct.pack(">I", len(track)) + track)


def render(midi_path: Path, wav_path: Path) -> None:
    """Render MIDI through the same acoustic-grand preset for every stimulus."""
    fluidsynth = shutil.which("fluidsynth")
    if not fluidsynth:
        raise RuntimeError("FluidSynth is required (for macOS: brew install fluid-synth)")
    if not SOUNDFONT.exists():
        raise RuntimeError(f"Missing SoundFont: {SOUNDFONT}")
    subprocess.run(
        [
            fluidsynth, "-ni", "-R", "0", "-C", "0", "-r", str(SAMPLE_RATE),
            "-g", "0.7", "-F", str(wav_path), str(SOUNDFONT), str(midi_path),
        ],
        check=True,
    )


def trim_to_arrangement(path: Path, total_beats: float) -> None:
    """Remove FluidSynth's added tail without changing the score duration."""
    frame_count = round(total_beats * SECONDS_PER_BEAT * SAMPLE_RATE)
    with wave.open(str(path), "rb") as source:
        params = source.getparams()
        frames = source.readframes(frame_count)
    with wave.open(str(path), "wb") as destination:
        destination.setparams(params)
        destination.writeframes(frames)


def main() -> None:
    output_options = {
        "kaeru_basic_major.wav": "basic_major",
        "kaeru_basic_minor.wav": "basic_triads_minor",
        "kaeru_seventh_rich_major.wav": "seventh_rich_major",
        "kaeru_seventh_rich_minor.wav": "seventh_rich_minor",
        "kaeru_ninth_rich_major.wav": "ninth_rich_major",
        "kaeru_ninth_rich_minor.wav": "ninth_rich_minor",
        "kaeru_diminished_seventh.wav": "diminished_sevenths",
    }
    total_beats = ARRANGEMENT_BEATS

    print(f"Tempo: {TEMPO_BPM} BPM")
    print(f"Duration: {total_beats * SECONDS_PER_BEAT:.6f} seconds")
    for filename, option in output_options.items():
        output_path = ROOT / filename
        chords, harmony = ACCOMPANIMENT_OPTIONS[option]
        with tempfile.TemporaryDirectory() as temp_dir:
            midi_path = Path(temp_dir) / "kaeru.mid"
            rendered_path = Path(temp_dir) / filename
            make_midi(midi_path, chords, harmony)
            render(midi_path, rendered_path)
            trim_to_arrangement(rendered_path, total_beats)
            rendered_path.replace(output_path)
        with wave.open(str(output_path), "rb") as wav_file:
            print(
                f"Created {filename}: {wav_file.getnframes()} frames, "
                f"{wav_file.getframerate()} Hz, acoustic grand piano"
            )


if __name__ == "__main__":
    main()
