#!/usr/bin/env python3
"""Generate controlled-harmony versions of the Kaeru no Uta stimulus."""

from __future__ import annotations

import math
import wave
from array import array
from pathlib import Path


SAMPLE_RATE = 44_100
SAMPLE_WIDTH = 2  # 16-bit PCM
CHANNELS = 1
TEMPO_BPM = 112
SECONDS_PER_BEAT = 60.0 / TEMPO_BPM
FADE_SECONDS = 0.008
TARGET_PEAK = 0.90
MELODY_LEVEL = 0.75
ACCOMPANIMENT_LEVEL = 0.63

# The same neutral, mildly piano-like additive timbre is used for every voice.
PARTIALS = ((1, 1.0), (2, 0.20), (3, 0.08), (4, 0.03))

NOTE_MIDI = {
    "G2": 43,
    "A2": 45,
    "C3": 48,
    "D3": 50,
    "E3": 52,
    "F3": 53,
    "F#3": 54,
    "G3": 55,
    "G#3": 56,
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
    "B4": 71,
    "C5": 72,
    "D5": 74,
}

CHORDS = {
    "C": ("C3", "E3", "G3"),
    "F": ("F3", "A3", "C4"),
    "G": ("G3", "B3", "D4"),
}

DIMINISHED_SEVENTH_CHORDS = {
    **CHORDS,
    "Bdim7": ("B3", "D4", "F4", "Ab4"),
    "Edim7": ("E3", "G3", "Bb3", "Db4"),
    "F#dim7": ("F#3", "A3", "C4", "Eb4"),
}

SEVENTH_CHORDS = {
    "C": ("C3", "E3", "G3", "B3"),
    "F": ("F3", "A3", "C4", "E4"),
    "G": ("G3", "B3", "D4", "F4"),
}

RICH_CHORDS = {
    "Cmaj7": ("C3", "E3", "G3", "B3"),
    "E7": ("E3", "G#3", "B3", "D4"),
    "Am7": ("A2", "C3", "E3", "G3"),
    "C7": ("C3", "E3", "G3", "Bb3"),
    "F": ("F3", "A3", "C4"),
    "Dm7": ("D3", "F3", "A3", "C4"),
    "G": ("G3", "B3", "D4"),
    "C": ("C3", "E3", "G3"),
}

# Consistent open ninth-chord voicings: root, fifth, seventh, ninth, third.
# The upper tones are spread above the bass/fifth to keep the five-note
# accompaniment clear while retaining every chord-defining tone.
NINTH_CHORDS = {
    "Cmaj9": ("C3", "G3", "B3", "D4", "E4"),
    "E9": ("E3", "B3", "D4", "F#4", "G#4"),
    "Am9": ("A2", "E3", "G3", "B3", "C4"),
    "C9": ("C3", "G3", "Bb3", "D4", "E4"),
    "Fmaj9": ("F3", "C4", "E4", "G4", "A4"),
    "Dm9": ("D3", "A3", "C4", "E4", "F4"),
    "G9": ("G2", "D3", "F3", "A3", "B3"),
}

# Controlled ninth-chord condition derived directly from the basic triads.
# Each voicing consistently uses root, seventh, ninth, third, then fifth in the
# upper register. The tuple order is root, fifth, seventh, ninth, third so the
# chord construction remains easy to audit. The names remain C/F/G so the
# control's HARMONY_BY_MEASURE is reused without any timing/progression changes.
NINTHS_FROM_BASIC_CHORDS = {
    "C": ("C3", "G4", "B3", "D4", "E4"),       # Cmaj9
    "F": ("F3", "C5", "E4", "G4", "A4"),       # Fmaj9
    "G": ("G3", "D5", "F4", "A4", "B4"),       # G9
}

NINTHS_FROM_BASIC_NAMES = {
    "C": "Cmaj9",
    "F": "Fmaj9",
    "G": "G9",
}

# Eight 4/4 measures transcribed from the control-condition score. ``None`` is
# an explicit rest, retained here so the score rhythm remains easy to audit and
# reuse in later harmony conditions.
MELODY = (
    ("C4", 1), ("D4", 1), ("E4", 1), ("F4", 1),
    ("E4", 1), ("D4", 1), ("C4", 1), (None, 1),
    ("E4", 1), ("F4", 1), ("G4", 1), ("A4", 1),
    ("G4", 1), ("F4", 1), ("E4", 1), (None, 1),
    ("C4", 1), (None, 1), ("C4", 1), (None, 1),
    ("C4", 1), (None, 1), ("C4", 1), (None, 1),
    ("C4", 0.5), ("C4", 0.5), ("D4", 0.5), ("D4", 0.5),
    ("E4", 0.5), ("E4", 0.5), ("F4", 0.5), ("F4", 0.5),
    ("E4", 1), ("D4", 1), ("C4", 1), (None, 1),
)

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

NINTH_HARMONY_BY_MEASURE = (
    ("Cmaj9", None, "Cmaj9", None),
    ("E9", "E9", "E9", None),
    ("Am9", None, "Am9", None),
    ("C9", "C9", "C9", None),
    (None, "Fmaj9", None, "Fmaj9"),
    (None, "Fmaj9", None, "Fmaj9"),
    ("Dm9", "Dm9", "G9", "G9"),
    ("Cmaj9", "Cmaj9", "Cmaj9", None),
)

# Harmony-only experimental condition. Every tuple retains the control's four
# beat slots exactly; only selected existing chord attacks are substituted.
DIMINISHED_SEVENTH_HARMONY_BY_MEASURE = (
    ("C", None, "C", None),
    ("C", "Bdim7", "C", None),
    ("C", None, "C", None),
    ("Edim7", "F", "C", None),
    (None, "C", None, "C"),
    (None, "C", None, "C"),
    ("F#dim7", "G", "C", "F"),
    ("C", "Bdim7", "C", None),
)

ACCOMPANIMENT_OPTIONS = {
    "basic_triads": (CHORDS, HARMONY_BY_MEASURE),
    "ninths_from_basic": (NINTHS_FROM_BASIC_CHORDS, HARMONY_BY_MEASURE),
    "legacy_sevenths": (SEVENTH_CHORDS, HARMONY_BY_MEASURE),
    "sevenths_rich": (RICH_CHORDS, RICH_HARMONY_BY_MEASURE),
    "ninths": (NINTH_CHORDS, NINTH_HARMONY_BY_MEASURE),
    "diminished_sevenths": (
        DIMINISHED_SEVENTH_CHORDS,
        DIMINISHED_SEVENTH_HARMONY_BY_MEASURE,
    ),
}


def frequency(note: str) -> float:
    """Equal-tempered frequency with A4 fixed at 440 Hz."""
    return 440.0 * 2.0 ** ((NOTE_MIDI[note] - 69) / 12.0)


def add_tone(
    mix: list[float], note: str, start_beat: float, beats: float, level: float
) -> None:
    """Add one deterministic tone with short raised-cosine edge fades."""
    start = round(start_beat * SECONDS_PER_BEAT * SAMPLE_RATE)
    end = round((start_beat + beats) * SECONDS_PER_BEAT * SAMPLE_RATE)
    frame_count = end - start
    fade_frames = min(round(FADE_SECONDS * SAMPLE_RATE), frame_count // 2)
    hz = frequency(note)

    for frame in range(frame_count):
        time = frame / SAMPLE_RATE
        value = sum(
            amplitude * math.sin(2.0 * math.pi * hz * harmonic * time)
            for harmonic, amplitude in PARTIALS
        ) / sum(amplitude for _, amplitude in PARTIALS)

        if frame < fade_frames:
            envelope = 0.5 - 0.5 * math.cos(math.pi * frame / fade_frames)
        elif frame >= frame_count - fade_frames:
            remaining = frame_count - 1 - frame
            envelope = 0.5 - 0.5 * math.cos(math.pi * remaining / fade_frames)
        else:
            envelope = 1.0
        mix[start + frame] += level * envelope * value


def build_melody() -> list[float]:
    """Render the shared melody independently of any harmony option."""
    total_beats = sum(beats for _, beats in MELODY)
    melody = [0.0] * round(total_beats * SECONDS_PER_BEAT * SAMPLE_RATE)
    beat = 0.0
    for note, duration in MELODY:
        if note is not None:
            add_tone(melody, note, beat, duration, MELODY_LEVEL)
        beat += duration
    return melody


def build_accompaniment(
    chords: dict[str, tuple[str, ...]],
    harmony_by_measure: tuple[tuple[str | None, ...], ...],
) -> list[float]:
    """Render chord tones using the arrangement's fixed attack/rest grid."""
    total_beats = sum(beats for _, beats in MELODY)
    accompaniment = [0.0] * round(total_beats * SECONDS_PER_BEAT * SAMPLE_RATE)
    for measure_index, measure in enumerate(harmony_by_measure):
        for beat_index, chord_name in enumerate(measure):
            if chord_name is None:
                continue
            start = measure_index * 4 + beat_index
            # Equal-power distribution makes ACCOMPANIMENT_LEVEL describe the
            # perceived level of the complete chord, rather than each note.
            chord_level = ACCOMPANIMENT_LEVEL / math.sqrt(len(chords[chord_name]))
            for note in chords[chord_name]:
                add_tone(accompaniment, note, start, 1, chord_level)
    return accompaniment


def build_mix(
    chords: dict[str, tuple[str, ...]],
    harmony_by_measure: tuple[tuple[str | None, ...], ...] = HARMONY_BY_MEASURE,
) -> list[float]:
    """Build an unnormalized mix from the shared melody and harmony timing."""
    melody = build_melody()
    accompaniment = build_accompaniment(chords, harmony_by_measure)
    return [
        melody_sample + chord_sample
        for melody_sample, chord_sample in zip(melody, accompaniment)
    ]


def render(
    chords: dict[str, tuple[str, ...]] = CHORDS,
    harmony_by_measure: tuple[tuple[str | None, ...], ...] = HARMONY_BY_MEASURE,
) -> list[float]:
    mix = build_mix(chords, harmony_by_measure)
    # Use the control stimulus's gain for every condition. Independently peak-
    # normalizing each harmony would change the otherwise identical melody level.
    control_mix = mix if chords is CHORDS else build_mix(CHORDS)
    control_peak = max(abs(sample) for sample in control_mix)
    gain = TARGET_PEAK / control_peak
    rendered = [sample * gain for sample in mix]
    # Dense five-note voicings can sum above full scale even though their
    # accompaniment uses the same equal-power level. If needed, apply one
    # uniform safety gain to the whole mix so the part-to-part balance remains
    # unchanged and no limiter or other dynamics processing is introduced.
    rendered_peak = max(abs(sample) for sample in rendered)
    if rendered_peak > 1.0:
        safety_gain = TARGET_PEAK / rendered_peak
        rendered = [sample * safety_gain for sample in rendered]
    return rendered


def write_wav(path: Path, samples: list[float]) -> None:
    pcm = array("h", (round(sample * 32767) for sample in samples))
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(CHANNELS)
        wav_file.setsampwidth(SAMPLE_WIDTH)
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(pcm.tobytes())


def main() -> None:
    output_options = {
        "kaeru_basic_triads.wav": "basic_triads",
        "kaeru_sevenths.wav": "legacy_sevenths",
        "kaeru_sevenths_rich.wav": "sevenths_rich",
        "kaeru_ninths.wav": "ninths",
        "kaeru_ninths_from_basic.wav": "ninths_from_basic",
        "kaeru_diminished_sevenths.wav": "diminished_sevenths",
    }
    output_dir = Path(__file__).resolve().parent
    total_beats = sum(beats for _, beats in MELODY)

    print(f"Tempo: {TEMPO_BPM} BPM")
    print(f"Duration: {total_beats * SECONDS_PER_BEAT:.6f} seconds")
    for filename, option in output_options.items():
        output_path = output_dir / filename
        if not output_path.exists():
            print(f"Skipped {filename} (not present)")
            continue
        chords, harmony = ACCOMPANIMENT_OPTIONS[option]
        samples = render(chords, harmony)
        write_wav(output_path, samples)
        peak = max(abs(sample) for sample in samples)
        print(
            f"Created {filename}: {len(samples)} frames, "
            f"{SAMPLE_RATE} Hz, peak {peak:.6f}"
        )


if __name__ == "__main__":
    main()
