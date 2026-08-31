"""Regression cases for the Kaeru-only musical-personality scoring model."""

import unittest

from musical_personality import calculate_musical_personality


LABELS = tuple(f"Sound {letter}" for letter in "ABCDEFG")


def responses(values):
    return [
        {
            "trial_number": index,
            "sound_label": label,
            "audio_filename": f"kaeru_{index}.wav",
            "pleasantness": value[0],
            "relaxation": 8 - value[1],
            "familiarity": value[2],
            "emotion": value[3] if len(value) > 3 else "Neutral",
            "other_emotion": "",
        }
        for index, (label, value) in enumerate(zip(LABELS, values), 1)
    ]


class MusicalPersonalityTests(unittest.TestCase):
    def test_result_is_valid_for_seven_conditions(self):
        result = calculate_musical_personality(
            responses([
                (6, 2, 7), (5, 3, 6), (6, 3, 5), (5, 4, 4),
                (7, 3, 5), (6, 4, 4), (3, 7, 2),
            ]),
            {
                "preferred_sound": "Sound E",
                "most_complex_sound": "Sound G",
                "most_familiar_sound": "Sound A",
            },
        )
        for group in (result["dimensions"], result["scores"]):
            self.assertTrue(all(0 <= value <= 100 for value in group.values()))
        self.assertIn(result["main_personality"], result["scores"])
        self.assertEqual(result["harmonic_match"], "Ninth Rich Major")

    def test_requires_exactly_seven_conditions(self):
        with self.assertRaisesRegex(ValueError, "seven responses"):
            calculate_musical_personality(responses([(4, 4, 4)] * 6), {})


if __name__ == "__main__":
    unittest.main()
