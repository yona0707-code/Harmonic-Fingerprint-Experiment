"""Participant-level scoring for the combined harmony listening result."""

from __future__ import annotations

from statistics import mean
from typing import Any


PERSONALITIES = {
    "The Pure & Simple Listener": {
        "emoji": "🌱",
        "headline": "Clarity speaks to you.",
        "description": (
            "In these experiments, you seemed most comfortable when the harmony "
            "stayed clear and grounded. Adding more notes did not automatically make "
            "the music more appealing to you — sometimes simplicity carried the feeling best."
        ),
    },
    "The Harmonic Dreamer": {
        "emoji": "🌙",
        "headline": "You hear colour where others might hear complexity.",
        "description": (
            "Richer harmony seemed to add atmosphere without creating much discomfort "
            "for you. Seventh and ninth chords felt more like colour and warmth than "
            "musical clutter."
        ),
    },
    "The Colour Seeker": {
        "emoji": "🎨",
        "headline": "You notice what extra notes do to a melody.",
        "description": (
            "You were drawn to harmonies that changed the character of the music. "
            "Richer chords caught your attention, even when they also made the sound "
            "less settled or more complex."
        ),
    },
    "The Tension Seeker": {
        "emoji": "⚡",
        "headline": "A little instability doesn’t scare your ears.",
        "description": (
            "You noticed harmonic tension, but tension did not automatically make the "
            "music unpleasant. Suspense and instability sometimes seemed to add to the "
            "experience rather than take away from it."
        ),
    },
    "The Emotional Storyteller": {
        "emoji": "🎭",
        "headline": "For you, harmony changes the story.",
        "description": (
            "Small changes in harmony produced noticeably different emotional reactions "
            "in your responses. The melody could stay the same, but changing the chords "
            "changed what the music seemed to say."
        ),
    },
    "The Open-Eared Explorer": {
        "emoji": "🌊",
        "headline": "You don’t need harmony to behave one particular way.",
        "description": (
            "You responded positively to several different harmonic styles rather than "
            "locking onto one clear favourite. Simple, colourful, and tense harmony "
            "could each work for you in different ways."
        ),
    },
}

HARMONIC_MATCHES = {
    "Sound A": "Basic Triads",
    "Sound B": "Seventh Chords",
    "Sound C": "Ninth Chords",
    "Sound D": "Diminished Seventh Harmony",
}


def clamp(value: float) -> float:
    """Keep a calculated score within its participant-facing 0–100 range."""
    return max(0.0, min(100.0, value))


def enjoyed_tension(pleasantness: float, tension: float) -> float:
    """Score tension only when it co-occurs with above-midpoint pleasantness."""
    tension_factor = max(0.0, tension - 4) / 3
    pleasant_factor = max(0.0, pleasantness - 4) / 3
    return clamp(tension_factor * pleasant_factor * 100)


def _emotion(response: dict[str, Any]) -> str:
    if response.get("emotion") == "Other":
        return response.get("other_emotion", "").strip() or "Other"
    return response.get("emotion", "")


def _variation_score(responses: list[dict[str, Any]]) -> float:
    pleasantness = [item["pleasantness"] for item in responses]
    tensions = [8 - item["relaxation"] for item in responses]
    unique_emotions = len({_emotion(item) for item in responses})
    return clamp(
        0.4 * ((max(pleasantness) - min(pleasantness)) / 6 * 100)
        + 0.4 * ((max(tensions) - min(tensions)) / 6 * 100)
        + 0.2 * ((unique_emotions - 1) / 3 * 100)
    )


def _rank_personalities(
    scores: dict[str, float], dimensions: dict[str, float]
) -> list[str]:
    """Rank scores, applying the requested deterministic rules to near ties."""
    remaining = set(scores)
    ranking: list[str] = []
    rule_order = (
        ("The Tension Seeker", dimensions["tension_tolerance_score"] >= 65),
        ("The Emotional Storyteller", dimensions["emotional_sensitivity_score"] >= 65),
        (
            "The Harmonic Dreamer",
            dimensions["richness_score"] >= 60
            and dimensions["rich_comfort_score"] > dimensions["rich_stimulation_score"],
        ),
        (
            "The Colour Seeker",
            dimensions["richness_score"] >= 60
            and dimensions["rich_stimulation_score"] >= dimensions["rich_comfort_score"],
        ),
        ("The Pure & Simple Listener", dimensions["simplicity_score"] >= 65),
        (
            "The Open-Eared Explorer",
            dimensions["openness_score"]
            >= max(
                dimensions["richness_score"],
                dimensions["simplicity_score"],
                dimensions["rich_comfort_score"],
                dimensions["rich_stimulation_score"],
                dimensions["tension_tolerance_score"],
                dimensions["emotional_sensitivity_score"],
            ),
        ),
    )
    while remaining:
        best_score = max(scores[name] for name in remaining)
        near_tie = {name for name in remaining if best_score - scores[name] <= 2}
        chosen = next(
            (name for name, condition in rule_order if condition and name in near_tie),
            None,
        )
        if chosen is None:
            chosen = sorted(near_tie, key=lambda name: (-scores[name], name))[0]
        ranking.append(chosen)
        remaining.remove(chosen)
    return ranking


def calculate_musical_personality(
    harmony_responses: list[dict[str, Any]],
    kaeru_responses: list[dict[str, Any]],
    kaeru_comparison: dict[str, Any],
) -> dict[str, Any]:
    """Calculate all dimensions, six traits, ranking, and harmonic match."""
    if len(harmony_responses) != 4 or len(kaeru_responses) != 4:
        raise ValueError("Both listening sections require exactly four responses.")

    kaeru = {item["sound_label"]: item for item in kaeru_responses}
    required_labels = {"Sound A", "Sound B", "Sound C", "Sound D"}
    if set(kaeru) != required_labels:
        raise ValueError("The same-melody responses must contain Sounds A, B, C, and D.")
    harmony = {item["audio_filename"]: item for item in harmony_responses}
    required_files = {
        "major_resolved.wav", "major_unresolved.wav",
        "minor_resolved.wav", "minor_unresolved.wav",
    }
    if set(harmony) != required_files:
        raise ValueError("The resolution responses do not match the four expected files.")

    p = {label: item["pleasantness"] for label, item in kaeru.items()}
    t = {label: 8 - item["relaxation"] for label, item in kaeru.items()}
    f = {label: item["familiarity"] for label, item in kaeru.items()}
    favourite = kaeru_comparison.get("preferred_sound")
    most_complex = kaeru_comparison.get("most_complex_sound")
    most_familiar = kaeru_comparison.get("most_familiar_sound")

    resolved = [harmony["major_resolved.wav"], harmony["minor_resolved.wav"]]
    unresolved = [harmony["major_unresolved.wav"], harmony["minor_unresolved.wav"]]
    resolved_p = mean(item["pleasantness"] for item in resolved)
    unresolved_p = mean(item["pleasantness"] for item in unresolved)
    resolved_t = mean(8 - item["relaxation"] for item in resolved)
    unresolved_t = mean(8 - item["relaxation"] for item in unresolved)

    rich_p = mean((p["Sound B"], p["Sound C"]))
    richness_score = 50 + (rich_p - p["Sound A"]) * 8.33
    if favourite in ("Sound B", "Sound C"):
        richness_score += 10
    if most_complex in ("Sound B", "Sound C"):
        richness_score += 5
    if favourite == "Sound A":
        richness_score -= 10
    richness_score = clamp(richness_score)

    simplicity_score = 100 - richness_score
    if favourite == "Sound A":
        simplicity_score += 10
    if most_familiar == "Sound A":
        simplicity_score += 5
    simplicity_score = clamp(simplicity_score)

    rich_tension = mean((t["Sound B"], t["Sound C"]))
    pleasant_component = (rich_p - 1) / 6 * 100
    relaxation_component = (7 - rich_tension) / 6 * 100
    rich_comfort_score = clamp(
        0.6 * pleasant_component + 0.4 * relaxation_component
    )
    rich_stimulation_score = 0.6 * pleasant_component + 0.4 * (
        (rich_tension - 1) / 6 * 100
    )
    if most_complex in ("Sound B", "Sound C"):
        rich_stimulation_score += 10
    rich_stimulation_score = clamp(rich_stimulation_score)

    tension_tolerance_score = mean(
        (
            enjoyed_tension(p["Sound D"], t["Sound D"]),
            enjoyed_tension(unresolved_p, unresolved_t),
        )
    )
    if favourite == "Sound D":
        tension_tolerance_score += 15
    if unresolved_p > resolved_p and unresolved_t > resolved_t:
        tension_tolerance_score += 10
    tension_tolerance_score = clamp(tension_tolerance_score)

    emotional_sensitivity_score = clamp(
        mean((_variation_score(kaeru_responses), _variation_score(harmony_responses)))
    )
    kaeru_average_p = mean(p.values())
    kaeru_p_range = max(p.values()) - min(p.values())
    openness_score = (
        0.65 * ((kaeru_average_p - 1) / 6 * 100)
        + 0.35 * (100 - kaeru_p_range / 6 * 100)
    )
    if favourite == "No clear preference":
        openness_score += 10
    openness_score = clamp(openness_score)

    dimensions = {
        "richness_score": richness_score,
        "simplicity_score": simplicity_score,
        "rich_comfort_score": rich_comfort_score,
        "rich_stimulation_score": rich_stimulation_score,
        "tension_tolerance_score": tension_tolerance_score,
        "emotional_sensitivity_score": emotional_sensitivity_score,
        "openness_score": openness_score,
    }
    scores = {
        "The Pure & Simple Listener": clamp(
            0.70 * simplicity_score
            + 0.20 * ((f["Sound A"] - 1) / 6 * 100)
            + 0.10 * (100 - emotional_sensitivity_score)
            + (10 if favourite == "Sound A" else 0)
        ),
        "The Harmonic Dreamer": clamp(
            0.50 * richness_score + 0.40 * rich_comfort_score + 0.10 * openness_score
            + (10 if favourite == "Sound C" else 5 if favourite == "Sound B" else 0)
        ),
        "The Colour Seeker": clamp(
            0.45 * richness_score + 0.40 * rich_stimulation_score
            + 0.15 * emotional_sensitivity_score
            + (10 if most_complex in ("Sound B", "Sound C") else 0)
        ),
        "The Tension Seeker": clamp(
            0.75 * tension_tolerance_score + 0.25 * emotional_sensitivity_score
            + (10 if favourite == "Sound D" else 0)
        ),
        "The Emotional Storyteller": clamp(
            0.80 * emotional_sensitivity_score + 0.20 * richness_score
        ),
        "The Open-Eared Explorer": clamp(
            0.80 * openness_score + 0.20 * tension_tolerance_score
            + (10 if favourite == "No clear preference" else 0)
        ),
    }
    ranking = _rank_personalities(scores, dimensions)

    harmonic_match = HARMONIC_MATCHES.get(favourite)
    if harmonic_match is None:
        highest = max(p.values())
        pleasantest = [label for label, value in p.items() if value == highest]
        harmonic_match = (
            HARMONIC_MATCHES[pleasantest[0]]
            if len(pleasantest) == 1
            else "Mixed / No single match"
        )

    main = ranking[0]
    return {
        "dimensions": dimensions,
        "scores": scores,
        "main_personality": main,
        "secondary_personality": ranking[1],
        "harmonic_match": harmonic_match,
        "share_text": (
            f"My Musical Personality is {PERSONALITIES[main]['emoji']} {main}.\n"
            f"My harmonic match: {harmonic_match}."
        ),
    }
