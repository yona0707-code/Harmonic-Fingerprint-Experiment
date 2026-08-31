"""Supabase persistence for completed music-emotion experiments."""

from collections.abc import Mapping, Sequence
from typing import Any
import uuid

import streamlit as st
from supabase import Client, create_client


def get_supabase_client() -> Client:
    """Create a Supabase client using deployment secrets, never source code."""
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])


def save_completed_experiment(
    participant_id: str,
    background_answers: Mapping[str, Any],
    responses: Sequence[Mapping[str, Any]],
    comparison_answers: Mapping[str, Any],
    experiment_type: str = "kaeru_harmony",
    submission_id: str | None = None,
) -> None:
    """Insert one participant and exactly seven linked Kaeru responses."""
    if len(responses) != 7:
        raise ValueError("A completed Kaeru experiment must contain seven responses.")

    client = get_supabase_client()
    participant_row = {
        "participant_id": participant_id,
        "age_range": background_answers["age_range"],
        "grew_up_countries": background_answers["grew_up_countries"],
        "current_country": background_answers["current_country"],
        "music_training_years": background_answers["music_training_years"],
        "musical_activities": list(background_answers["musical_activities"]),
        "music_genres": list(background_answers["music_genres"]),
        "other_music_genre": background_answers.get("other_music_genre") or None,
        "weekly_listening_hours": background_answers["weekly_listening_hours"],
        "current_mood": background_answers["current_mood"],
        "hearing_difficulty": background_answers["hearing_difficulty"],
        "recruitment_source": background_answers["recruitment_source"],
        "other_recruitment_source": background_answers.get(
            "other_recruitment_source"
        ) or None,
        "listening_device": background_answers["listening_device"],
    }
    submission_row = {
        "submission_id": submission_id or str(uuid.uuid4()),
        "participant_id": participant_id,
        "experiment_type": experiment_type,
        "most_tense_sound": comparison_answers["most_tense_sound"],
        "preferred_sound": comparison_answers["preferred_sound"],
        "most_complex_sound": comparison_answers.get("most_complex_sound"),
        "most_familiar_sound": comparison_answers.get("most_familiar_sound"),
        "overall_association": comparison_answers.get("overall_association") or None,
    }
    response_rows = [
        {
            "submission_id": submission_row["submission_id"],
            "participant_id": participant_id,
            "experiment_type": experiment_type,
            "trial_number": response["trial_number"],
            "audio_filename": response["audio_filename"],
            "condition_key": response["condition_key"],
            "pleasantness": response["pleasantness"],
            "relaxation": response["relaxation"],
            "tension": 8 - response["relaxation"],
            "emotion": response["emotion"],
            "other_emotion": response.get("other_emotion") or None,
            "familiarity": response.get("familiarity"),
        }
        for response in responses
    ]

    # The database function inserts/reuses the participant and atomically creates
    # a distinct submission plus seven responses. A retry uses a fresh submission
    # UUID; this function is only called once per UI save attempt.
    client.rpc(
        "save_completed_experiment",
        {
            "p_participant": participant_row,
            "p_submission": submission_row,
            "p_responses": response_rows,
        },
    ).execute()
