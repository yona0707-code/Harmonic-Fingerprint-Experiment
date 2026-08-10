"""Small regression cases for the musical-personality scoring model."""

import unittest

from musical_personality import calculate_musical_personality


FILES = (
    "major_resolved.wav", "major_unresolved.wav",
    "minor_resolved.wav", "minor_unresolved.wav",
)
LABELS = ("Sound A", "Sound B", "Sound C", "Sound D")


def responses(values, harmony=False):
    names = FILES if harmony else LABELS
    return [
        {
            "trial_number": index,
            "sound_label": LABELS[index - 1],
            "audio_filename": name if harmony else f"kaeru_{index}.wav",
            "pleasantness": value[0], "relaxation": 8 - value[1],
            "familiarity": value[2] if len(value) > 2 else None,
            "emotion": value[3] if len(value) > 3 else "Neutral",
            "other_emotion": "",
        }
        for index, (name, value) in enumerate(zip(names, values), 1)
    ]


class MusicalPersonalityTests(unittest.TestCase):
    def score(self, kaeru, harmony, favourite, complex_sound, familiar="Sound A"):
        return calculate_musical_personality(
            responses(harmony, harmony=True), responses(kaeru),
            {"preferred_sound": favourite, "most_complex_sound": complex_sound,
             "most_familiar_sound": familiar},
        )

    def assert_valid(self, result):
        for group in (result["dimensions"], result["scores"]):
            self.assertTrue(all(0 <= value <= 100 for value in group.values()))

    def test_six_expected_patterns(self):
        cases = (
            ([(7, 2, 7), (2, 5, 2), (2, 5, 2), (1, 7, 1)], [(6, 2), (2, 6), (6, 2), (2, 6)], "Sound A", "Sound D", "The Pure & Simple Listener"),
            ([(4, 3, 3), (7, 2, 5), (7, 2, 5), (2, 6, 2)], [(6, 2)] * 4, "Sound C", "Sound C", "The Harmonic Dreamer"),
            ([(3, 2, 3), (7, 6, 4), (7, 6, 4), (2, 7, 2)], [(5, 3), (3, 6), (5, 3), (3, 6)], "Sound B", "Sound C", "The Colour Seeker"),
            ([(4, 2, 3), (4, 3, 3), (5, 4, 3), (7, 7, 3)], [(4, 2), (7, 7), (4, 2), (7, 7)], "Sound D", "Sound D", "The Tension Seeker"),
            ([(1, 1, 2, "Sad"), (7, 7, 4, "Excited"), (2, 6, 3, "Anxious"), (6, 2, 5, "Peaceful")], [(1, 1, None, "Sad"), (7, 7, None, "Excited"), (2, 6, None, "Anxious"), (6, 2, None, "Peaceful")], "Sound B", "Sound B", "The Emotional Storyteller"),
            ([(6, 3, 5), (6, 3, 5), (6, 3, 5), (6, 3, 5)], [(6, 3)] * 4, "No clear preference", "They felt about the same", "The Open-Eared Explorer"),
        )
        for kaeru, harmony, favourite, complex_sound, expected in cases:
            with self.subTest(expected=expected):
                result = self.score(kaeru, harmony, favourite, complex_sound)
                self.assert_valid(result)
                self.assertEqual(result["main_personality"], expected)


if __name__ == "__main__":
    unittest.main()
