#!/usr/bin/env python3
"""Generate controlled WAV stimuli for a diminished-seventh experiment."""

from __future__ import annotations

import math
import wave
from array import array
from pathlib import Path


SAMPLE_RATE = 44_100
SAMPLE_WIDTH = 2  # 16-bit PCM
CHANNELS = 1
TONIC_DURATION = 2.5
DIMINISHED_DURATION = 2.5
PAUSE_DURATION = 0.2
FADE_DURATION = 0.010
TARGET_PEAK = 0.90
CHORD_PEAK = 0.80

# Fixed, neutral spectrum for every note: fundamental plus very quiet overtones.
PARTIALS = ((1, 1.0), (2, 0.08), (3, 0.025))

NOTE_MIDI = {
    "C4": 60,
    "Eb4": 63,
    "E4": 64,
    "G4": 67,
    "B3": 59,
    "D4": 62,
    "F4": 65,
    "Ab4": 68,
}

C_MAJOR = ("C4", "E4", "G4")
C_MINOR = ("C4", "Eb4", "G4")
B_DIMINISHED_SEVENTH = ("B3", "D4", "F4", "Ab4")


def frequency(note: str) -> float:
    """Return equal-tempered frequency with A4 fixed at 440 Hz."""
    return 440.0 * 2.0 ** ((NOTE_MIDI[note] - 69) / 12.0)


def chord(notes: tuple[str, ...], duration: float) -> list[float]:
    """Synthesize a chord with deterministic phases and click-free fades."""
    frame_count = round(duration * SAMPLE_RATE)
    fade_frames = round(FADE_DURATION * SAMPLE_RATE)
    frequencies = tuple(frequency(note) for note in notes)
    samples: list[float] = []

    for frame in range(frame_count):
        time = frame / SAMPLE_RATE
        value = 0.0
        for hz in frequencies:
            for harmonic, amplitude in PARTIALS:
                value += amplitude * math.sin(2.0 * math.pi * hz * harmonic * time)
        value /= len(frequencies)

        # Raised-cosine fades reach exactly zero at both segment boundaries.
        if frame < fade_frames:
            envelope = 0.5 - 0.5 * math.cos(math.pi * frame / fade_frames)
        elif frame >= frame_count - fade_frames:
            remaining = frame_count - 1 - frame
            envelope = 0.5 - 0.5 * math.cos(math.pi * remaining / fade_frames)
        else:
            envelope = 1.0
        samples.append(value * envelope)

    # Calibrate every chord to a fixed peak so chord identity does not cause
    # clip-level gain differences. This also keeps the shared diminished chord
    # sample-identical in all four stimuli after final normalization.
    peak = max(abs(sample) for sample in samples)
    gain = CHORD_PEAK / peak
    return [sample * gain for sample in samples]


def silence(duration: float) -> list[float]:
    return [0.0] * round(duration * SAMPLE_RATE)


def make_clip(tonic: tuple[str, ...], resolved: bool) -> list[float]:
    samples = chord(tonic, TONIC_DURATION)
    samples.extend(silence(PAUSE_DURATION))
    samples.extend(chord(B_DIMINISHED_SEVENTH, DIMINISHED_DURATION))
    if resolved:
        samples.extend(silence(PAUSE_DURATION))
        samples.extend(chord(tonic, TONIC_DURATION))
    return samples


def normalize(samples: list[float]) -> list[float]:
    peak = max(abs(sample) for sample in samples)
    if peak == 0.0:
        return samples
    gain = TARGET_PEAK / peak
    return [sample * gain for sample in samples]


def write_wav(path: Path, samples: list[float]) -> None:
    pcm = array(
        "h",
        (round(max(-1.0, min(1.0, sample)) * 32767) for sample in samples),
    )
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(CHANNELS)
        wav_file.setsampwidth(SAMPLE_WIDTH)
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(pcm.tobytes())


def main() -> None:
    output_dir = Path(__file__).resolve().parent
    clips = {
        "major_resolved.wav": (C_MAJOR, True),
        "minor_resolved.wav": (C_MINOR, True),
        "major_unresolved.wav": (C_MAJOR, False),
        "minor_unresolved.wav": (C_MINOR, False),
    }
    for filename, (tonic, resolved) in clips.items():
        write_wav(output_dir / filename, normalize(make_clip(tonic, resolved)))
        print(f"Created {filename}")


if __name__ == "__main__":
    main()
