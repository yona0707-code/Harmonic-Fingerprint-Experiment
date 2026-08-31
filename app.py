"""Streamlit introduction and sound check for a music-emotion study."""

import math
import struct
import traceback
import uuid
import wave
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
import streamlit as st
import streamlit.components.v1 as components

from database import save_completed_experiment
from musical_personality import PERSONALITIES, calculate_musical_personality


APP_DIR = Path(__file__).resolve().parent
SOUND_CHECK_PATH = APP_DIR / "sound_check.wav"
KAERU_SOUNDS = (
    ("Sound A", "basic_major", "kaeru_basic_major.wav"),
    ("Sound B", "basic_minor", "kaeru_basic_minor.wav"),
    ("Sound C", "seventh_major", "kaeru_seventh_rich_major.wav"),
    ("Sound D", "seventh_minor", "kaeru_seventh_rich_minor.wav"),
    ("Sound E", "ninth_major", "kaeru_ninth_rich_major.wav"),
    ("Sound F", "ninth_minor", "kaeru_minor_ninth.wav"),
    ("Sound G", "diminished_seventh", "kaeru_diminished_seventh.wav"),
)

EMOTIONS = (
    "Anxious",
    "Mysterious",
    "Sad",
    "Excited",
    "Peaceful",
    "Joyful",
    "Uncomfortable",
    "Neutral",
    "Other",
)


def scroll_to_top() -> None:
    """Scroll Streamlit's main page container to the top in the browser."""
    components.html(
        """
        <script>
            const main = window.parent.document.querySelector(
                '[data-testid="stMain"]'
            );
            if (main) {
                main.scrollTo({ top: 0, left: 0, behavior: 'auto' });
            }
            window.parent.scrollTo({ top: 0, left: 0, behavior: 'auto' });
        </script>
        """,
        height=0,
    )


def create_sound_check(path: Path) -> None:
    """Create a neutral, mono A4 sine tone if the file is not already present."""
    if path.exists():
        return

    sample_rate = 44_100
    duration_seconds = 1.0
    frequency_hz = 440.0
    amplitude = 0.25  # Comfortable level with plenty of headroom.
    fade_samples = int(sample_rate * 0.02)  # 20 ms fades prevent clicks.
    frame_count = int(sample_rate * duration_seconds)

    frames = bytearray()
    for index in range(frame_count):
        fade = 1.0
        if index < fade_samples:
            fade = index / fade_samples
        elif index >= frame_count - fade_samples:
            fade = (frame_count - 1 - index) / fade_samples

        sample = amplitude * fade * math.sin(
            2.0 * math.pi * frequency_hz * index / sample_rate
        )
        frames.extend(struct.pack("<h", round(sample * 32_767)))

    # Write to a temporary sibling first, so an interrupted write cannot leave a
    # partially created sound-check file behind.
    temporary_path = path.with_suffix(".tmp")
    try:
        with wave.open(str(temporary_path), "wb") as audio_file:
            audio_file.setnchannels(1)
            audio_file.setsampwidth(2)
            audio_file.setframerate(sample_rate)
            audio_file.writeframes(frames)
        temporary_path.replace(path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def reset_experiment() -> None:
    """Remove this app's participant state so it can start again cleanly."""
    st.session_state.clear()
    st.session_state.page = "introduction"


def go_back_to_previous_page() -> None:
    """Move back one visible step while keeping earlier answers editable."""
    page = st.session_state.get("page", "introduction")

    if page == "sound_check":
        st.session_state.page = "introduction"
    elif page == "kaeru_listening":
        st.session_state.page = "sound_check"
    elif page == "background_questionnaire":
        st.session_state.background_draft = {
            key: value
            for key, value in st.session_state.items()
            if key.startswith("background_") and key != "background_draft"
        }
        st.session_state.page = "kaeru_listening"

    st.session_state.scroll_to_top = True


def show_back_button() -> None:
    """Show a consistent previous-page control on every app view."""
    st.button(
        "Go back to previous page",
        disabled=st.session_state.get("page", "introduction") == "introduction",
        on_click=go_back_to_previous_page,
        use_container_width=True,
    )


def start_listening_comparison() -> None:
    """Start the seven-condition Kaeru listening session."""
    st.session_state.responses = []
    st.session_state.experiment_type = "kaeru_harmony"
    submission_key = "kaeru_harmony_submission_id"
    st.session_state.setdefault(submission_key, str(uuid.uuid4()))
    st.session_state.submission_id = st.session_state[submission_key]
    st.session_state.data_saved = st.session_state.get("kaeru_harmony_saved", False)
    st.session_state.save_attempted = False
    st.session_state.pop("database_error", None)
    st.session_state.pop("save_error", None)
    st.session_state.pop("save_traceback", None)
    # Remove old trial and questionnaire widget values without affecting
    # consent or listening-device data.
    for key in list(st.session_state):
        if key.startswith("sound_") or key.startswith("comparison_"):
            del st.session_state[key]
    st.session_state.comparison_answers = {}
    st.session_state.page = "kaeru_listening"


def display_emotion(response: dict) -> str:
    """Return the participant's custom label when they selected Other."""
    if response["emotion"] == "Other":
        return response.get("other_emotion", "").strip() or "Other"
    return response["emotion"]


def render_emotional_map(fingerprint: dict) -> None:
    """Render the seven Kaeru ratings without revealing their conditions."""
    figure, axis = plt.subplots(figsize=(6, 5))
    for response in sorted(fingerprint["responses"], key=lambda item: item["trial_number"]):
        axis.scatter(response["pleasantness"], response["tension"], s=65)
        axis.annotate(
            response["sound_label"],
            (response["pleasantness"], response["tension"]),
            xytext=(5, 6),
            textcoords="offset points",
            fontsize=9,
        )
    axis.axvline(4, color="grey", linewidth=1, alpha=0.6)
    axis.axhline(4, color="grey", linewidth=1, alpha=0.6)
    axis.set_xlim(1, 7)
    axis.set_ylim(1, 7)
    axis.set_xticks(range(1, 8))
    axis.set_yticks(range(1, 8))
    axis.set_xlabel("Unpleasant ← Pleasantness → Pleasant")
    axis.set_ylabel("Relaxed ← Tension → Tense")
    axis.grid(alpha=0.15)
    figure.tight_layout()
    st.pyplot(figure, use_container_width=True)
    plt.close(figure)


def show_introduction() -> None:
    show_back_button()
    st.title("Can Music Read You?")
    st.subheader("Discover your Harmonic Fingerprint")

    st.write("Listen to a series of short harmonies and describe how they feel to you.")
    st.write(
        "This experiment explores whether people with different musical and "
        "cultural backgrounds interpret harmony differently."
    )

    st.markdown(
        """
        - The experiment will eventually take around 3–4 minutes.
        - There are no correct or incorrect answers.
        - Headphones or earphones are recommended.
        - Participants may stop at any time.
        - We will not ask for your name or contact details. Your responses will only be used for this study.
        """
    )

    st.checkbox(
        "I understand the information above and agree to take part.",
        key="consent_input",
    )

    if st.button("Continue to sound check", use_container_width=True):
        if st.session_state.consent_input:
            st.session_state.consent = True
            st.session_state.page = "sound_check"
            st.rerun()
        else:
            st.warning("Consent is required before continuing to the sound check.")


def show_sound_check() -> None:
    show_back_button()
    st.title("Sound check")
    st.write("Set your volume to a comfortable level, then play the sound below.")

    try:
        create_sound_check(SOUND_CHECK_PATH)
        st.audio(str(SOUND_CHECK_PATH), format="audio/wav")
    except (OSError, wave.Error) as error:
        st.error(f"The sound-check audio could not be prepared: {error}")
        st.info("Check that this app has permission to write files in its folder, then reload.")
        return

    st.radio(
        "Could you hear the sound properly?",
        ("Yes", "No"),
        index=None,
        key="heard_clearly_input",
    )

    if st.session_state.heard_clearly_input == "No":
        st.warning("Please adjust your volume and play the sound again.")

    if st.button("Start", use_container_width=True):
        if st.session_state.heard_clearly_input is None:
            st.warning("Please confirm whether you could hear the sound properly.")
        elif st.session_state.heard_clearly_input == "No":
            st.warning("Please adjust your volume and play the sound again.")
        else:
            st.session_state.heard_clearly = st.session_state.heard_clearly_input
            start_listening_comparison()
            st.rerun()


def show_kaeru_listening() -> None:
    """Collect all seven chord-condition ratings and direct comparisons."""
    for response in st.session_state.get("responses", []):
        prefix = f"kaeru_sound_{response['trial_number']}"
        for field in (
            "pleasantness", "relaxation", "emotion", "other_emotion", "familiarity"
        ):
            st.session_state.setdefault(f"{prefix}_{field}", response.get(field, ""))
    saved = st.session_state.get("comparison_answers", {})
    for widget_suffix, answer_key in (
        ("preferred", "preferred_sound"),
        ("most_tense", "most_tense_sound"),
        ("most_complex", "most_complex_sound"),
        ("most_familiar", "most_familiar_sound"),
        ("overall_association", "overall_association"),
    ):
        default = saved.get(answer_key, "")
        if widget_suffix != "overall_association":
            default = default or None
        st.session_state.setdefault(f"kaeru_comparison_{widget_suffix}", default)

    show_back_button()
    st.title("Kaeru listening experiment")
    st.header("Same Progression, Different Chord Quality")
    st.write("All seven sounds contain chords only; there is no melody part.")
    st.write(
        "Listen to each version as many times as you like and compare how they feel to you."
    )
    st.write("There are no correct or incorrect answers.")

    completed_conditions = 0
    for trial_number in range(1, len(KAERU_SOUNDS) + 1):
        prefix = f"kaeru_sound_{trial_number}"
        required_values = (
            st.session_state.get(f"{prefix}_pleasantness"),
            st.session_state.get(f"{prefix}_relaxation"),
            st.session_state.get(f"{prefix}_emotion"),
            st.session_state.get(f"{prefix}_familiarity"),
        )
        emotion = st.session_state.get(f"{prefix}_emotion")
        other_complete = (
            emotion != "Other"
            or bool((st.session_state.get(f"{prefix}_other_emotion") or "").strip())
        )
        if all(value is not None for value in required_values) and other_complete:
            completed_conditions += 1
    st.progress(
        completed_conditions / len(KAERU_SOUNDS),
        text=f"{completed_conditions} of {len(KAERU_SOUNDS)} conditions completed",
    )
    for sound_label, _, audio_filename in KAERU_SOUNDS:
        st.subheader(sound_label)
        audio_path = APP_DIR / audio_filename
        if not audio_path.is_file():
            st.error("A required sound is unavailable. Please contact the researcher.")
            return
        st.audio(str(audio_path), format="audio/wav")

    st.header("Your responses")
    for trial_number, (sound_label, _, _) in enumerate(KAERU_SOUNDS, start=1):
        prefix = f"kaeru_sound_{trial_number}"
        st.subheader(sound_label)
        st.radio(
            "How pleasant or unpleasant did this sound feel to you?",
            range(1, 8), index=None, horizontal=True, key=f"{prefix}_pleasantness",
            captions=["Very unpleasant", "", "", "Neither", "", "", "Very pleasant"],
        )
        st.radio(
            "How tense or relaxed did this sound feel to you?",
            range(1, 8), index=None, horizontal=True, key=f"{prefix}_relaxation",
            captions=["Very tense", "", "", "Neither", "", "", "Very relaxed"],
        )
        emotion = st.radio(
            "Which emotion best matches this sound?", EMOTIONS, index=None,
            key=f"{prefix}_emotion",
        )
        if emotion == "Other":
            st.text_input(
                "Please describe the emotion in one or two words.", max_chars=50,
                key=f"{prefix}_other_emotion",
            )
        st.radio(
            "How familiar did this version sound to you?",
            range(1, 8), index=None, horizontal=True, key=f"{prefix}_familiarity",
            captions=["Very unfamiliar", "", "", "Neither", "", "", "Very familiar"],
        )
        st.divider()

    labels = tuple(label for label, _, _ in KAERU_SOUNDS)
    st.subheader("Compare the sounds")
    st.radio(
        "Which version did you like the most?",
        (*labels, "No clear preference"), index=None, key="kaeru_comparison_preferred",
    )
    st.radio(
        "Which version felt the most tense?",
        (*labels, "They felt about the same"), index=None,
        key="kaeru_comparison_most_tense",
    )
    st.radio(
        "Which version sounded the most emotionally complex?",
        (*labels, "They felt about the same"), index=None,
        key="kaeru_comparison_most_complex",
    )
    st.radio(
        "Which version sounded the most familiar?",
        (*labels, "They felt about the same"), index=None,
        key="kaeru_comparison_most_familiar",
    )
    st.text_area(
        "Did any of the versions give you a particularly strong feeling, image, or association?",
        help=("Optional — you can mention the sound label, for example: “Sound C felt "
              "dreamy” or “Sound D reminded me of a movie soundtrack.”"),
        max_chars=400, key="kaeru_comparison_overall_association",
    )

    if st.button("Continue", type="primary", use_container_width=True):
        missing = []
        responses = []
        for trial_number, (sound_label, condition_key, audio_filename) in enumerate(
            KAERU_SOUNDS, start=1
        ):
            prefix = f"kaeru_sound_{trial_number}"
            values = {
                field: st.session_state.get(f"{prefix}_{field}")
                for field in ("pleasantness", "relaxation", "emotion", "familiarity")
            }
            other = st.session_state.get(f"{prefix}_other_emotion", "").strip()
            if any(value is None for value in values.values()):
                missing.append(sound_label)
            elif values["emotion"] == "Other" and not other:
                missing.append(f"{sound_label} Other emotion description")
            responses.append({
                "experiment_type": "kaeru_harmony",
                "condition_key": condition_key,
                "trial_number": trial_number,
                "sound_label": sound_label,
                "audio_filename": audio_filename,
                **values,
                "tension": 8 - values["relaxation"] if values["relaxation"] else None,
                "other_emotion": other if values["emotion"] == "Other" else "",
            })
        comparisons = {
            "preferred_sound": st.session_state.get("kaeru_comparison_preferred"),
            "most_tense_sound": st.session_state.get("kaeru_comparison_most_tense"),
            "most_complex_sound": st.session_state.get("kaeru_comparison_most_complex"),
            "most_familiar_sound": st.session_state.get("kaeru_comparison_most_familiar"),
            "overall_association": st.session_state.get(
                "kaeru_comparison_overall_association", ""
            ).strip(),
        }
        for key, label in (
            ("preferred_sound", "the favourite-version comparison"),
            ("most_tense_sound", "the most-tense comparison"),
            ("most_complex_sound", "the emotional-complexity comparison"),
            ("most_familiar_sound", "the familiarity comparison"),
        ):
            if not comparisons[key]:
                missing.append(label)
        if missing:
            st.warning(
                "Please complete all required responses. Missing: "
                + ", ".join(missing) + "."
            )
        else:
            st.session_state.responses = responses
            st.session_state.comparison_answers = comparisons
            st.session_state.kaeru_comparison_answers = comparisons
            st.session_state.kaeru_responses = responses
            st.session_state.page = "background_questionnaire"
            st.session_state.save_attempted = False
            st.session_state.scroll_to_top = True
            st.rerun()


def show_background_questionnaire() -> None:
    """Collect the participant's background answers in one validated form."""
    if len(st.session_state.get("kaeru_responses", [])) != len(KAERU_SOUNDS):
        st.session_state.page = "kaeru_listening"
        st.rerun()

    for widget_key, draft_value in st.session_state.get(
        "background_draft", {}
    ).items():
        st.session_state.setdefault(widget_key, draft_value)

    show_back_button()
    st.title("A little about you")
    st.write(
        "These questions help us explore whether musical and cultural experiences "
        "are connected to how people respond to harmony."
    )
    st.write("We will not ask for your name or contact details.")

    with st.form("background_questionnaire"):
        age_range = st.selectbox(
            "What is your age range?",
            (
                "Select one", "Under 13", "13–15", "16–18", "19–24", "25–34",
                "35–44", "45–54", "55–64", "65 or older", "Prefer not to say",
            ),
            key="background_age_range",
        )
        grew_up_countries = st.text_input(
            "Which country or countries did you mainly grow up in?",
            help=(
                "Think about where you spent most of your childhood, especially "
                "between ages 0 and 12."
            ),
            key="background_grew_up_countries",
        )
        current_country = st.text_input(
            "Which country do you currently live in?",
            key="background_current_country",
        )
        music_training_years = st.selectbox(
            "How many years of formal musical training have you had?",
            (
                "Select one", "None", "Less than 1 year", "1–3 years", "4–7 years",
                "8 years or more",
            ),
            help=(
                "Formal musical training may include instrument lessons, singing "
                "lessons, music theory classes, or structured music education."
            ),
            key="background_music_training_years",
        )
        musical_activities = st.multiselect(
            "Which musical activities have you done?",
            (
                "Played an instrument", "Singing", "Music theory",
                "Composing or producing music",
                "Performed in a band, orchestra, or ensemble", "None",
            ),
            key="background_musical_activities",
        )
        music_genres = st.multiselect(
            "Which types of music do you regularly listen to?",
            (
                "Pop", "Rock or metal", "Classical", "Jazz", "Hip-hop or R&B",
                "Electronic", "Film, anime, or video-game music",
                "Traditional or folk music", "Religious music", "Other",
            ),
            key="background_music_genres",
        )
        other_music_genre = ""
        if "Other" in music_genres:
            other_music_genre = st.text_input(
                "What other type of music do you listen to?",
                key="background_other_music_genre",
            )
        weekly_listening_hours = st.selectbox(
            "Approximately how many hours of music do you listen to each week?",
            (
                "Select one", "Less than 1 hour", "1–3 hours", "4–7 hours",
                "8–14 hours", "15 hours or more",
            ),
            key="background_weekly_listening_hours",
        )
        current_mood = st.selectbox(
            "How would you describe your current mood?",
            ("Select one", "Very negative", "Negative", "Neutral", "Positive", "Very positive"),
            key="background_current_mood",
        )
        hearing_difficulty = st.selectbox(
            "Do you have any difficulty hearing music or everyday sounds?",
            ("Select one", "No", "Yes", "Unsure", "Prefer not to say"),
            key="background_hearing_difficulty",
        )
        listening_device = st.selectbox(
            "What are you using to listen to the sounds?",
            ("Select one", "Headphones", "Earphones", "Device speakers", "External speakers", "Other"),
            key="background_listening_device",
        )
        recruitment_source = st.selectbox(
            "How did you find this experiment?",
            (
                "Select one", "Friend or family", "School",
                "Music teacher or music community", "Social media",
                "Online community", "Other",
            ),
            key="background_recruitment_source",
        )
        other_recruitment_source = ""
        if recruitment_source == "Other":
            other_recruitment_source = st.text_input(
                "Please briefly describe how you found it.",
                key="background_other_recruitment_source",
            )

        submitted = st.form_submit_button(
            "See my results", type="primary", use_container_width=True
        )

    if submitted:
        missing_answers = []
        if age_range == "Select one":
            missing_answers.append("your age range")
        if not grew_up_countries.strip():
            missing_answers.append("where you mainly grew up")
        if not current_country.strip():
            missing_answers.append("your current country")
        if music_training_years == "Select one":
            missing_answers.append("your formal musical training")
        if not musical_activities:
            missing_answers.append("at least one musical activity")
        if not music_genres:
            missing_answers.append("at least one type of music")
        if "Other" in music_genres and not other_music_genre.strip():
            missing_answers.append("the other type of music")
        if weekly_listening_hours == "Select one":
            missing_answers.append("your weekly listening time")
        if current_mood == "Select one":
            missing_answers.append("your current mood")
        if hearing_difficulty == "Select one":
            missing_answers.append("hearing difficulty")
        if listening_device == "Select one":
            missing_answers.append("your listening device")
        if recruitment_source == "Select one":
            missing_answers.append("how you found the experiment")
        if recruitment_source == "Other" and not other_recruitment_source.strip():
            missing_answers.append("how you found the experiment")

        none_with_other_activity = (
            "None" in musical_activities and len(musical_activities) > 1
        )
        if none_with_other_activity:
            st.warning(
                "Please select ‘None’ by itself, or remove it and keep your other "
                "musical activities."
            )
        elif missing_answers:
            st.warning("Please complete: " + ", ".join(missing_answers) + ".")
        else:
            st.session_state.background_answers = {
                "age_range": age_range,
                "grew_up_countries": grew_up_countries.strip(),
                "current_country": current_country.strip(),
                "music_training_years": music_training_years,
                "musical_activities": musical_activities,
                "music_genres": music_genres,
                "other_music_genre": (
                    other_music_genre.strip() if "Other" in music_genres else ""
                ),
                "weekly_listening_hours": weekly_listening_hours,
                "current_mood": current_mood,
                "hearing_difficulty": hearing_difficulty,
                "recruitment_source": recruitment_source,
                "other_recruitment_source": (
                    other_recruitment_source.strip()
                    if recruitment_source == "Other" else ""
                ),
                "listening_device": listening_device,
            }
            complete_listening_data = (
                len(st.session_state.get("kaeru_responses", [])) == len(KAERU_SOUNDS)
                and st.session_state.get("kaeru_comparison_answers", {}).get(
                    "most_tense_sound"
                )
                and st.session_state.get("kaeru_comparison_answers", {}).get(
                    "preferred_sound"
                )
                and st.session_state.get("kaeru_comparison_answers", {}).get(
                    "most_complex_sound"
                )
                and st.session_state.get("kaeru_comparison_answers", {}).get(
                    "most_familiar_sound"
                )
            )
            if not complete_listening_data:
                st.error(
                    "Your listening answers are incomplete. Please return to the listening page "
                    "and complete the required questions."
                )
                return
            st.session_state.page = "save_completed_experiment"
            st.session_state.save_attempted = False
            st.session_state.scroll_to_top = True
            st.rerun()


def attempt_database_save() -> None:
    """Save the Kaeru experiment once, retaining answers on failure."""
    st.session_state.save_attempted = True
    st.session_state.setdefault("kaeru_harmony_submission_id", str(uuid.uuid4()))
    try:
        if not st.session_state.get("kaeru_harmony_saved", False):
            save_completed_experiment(
                st.session_state.participant_id,
                st.session_state.background_answers,
                st.session_state.kaeru_responses,
                st.session_state.kaeru_comparison_answers,
                "kaeru_harmony",
                st.session_state.kaeru_harmony_submission_id,
            )
            st.session_state.kaeru_harmony_saved = True
    except Exception as exc:  # Supabase may raise API, auth, or transport errors.
        st.session_state.data_saved = False
        st.session_state.save_error = repr(exc)
        st.session_state.save_traceback = traceback.format_exc()
        print("DATABASE SAVE ERROR:", repr(exc))
        traceback.print_exc()
    else:
        st.session_state.data_saved = True
        st.session_state.save_error = None
        st.session_state.save_traceback = None
        st.session_state.page = "musical_personality"
        st.session_state.scroll_to_top = True
        st.rerun()


def show_database_save() -> None:
    """Save silently, showing only a participant-friendly error if needed."""
    if st.session_state.get("data_saved", False):
        st.session_state.page = "musical_personality"
        st.rerun()
    if not st.session_state.get("save_attempted", False):
        attempt_database_save()

    st.error(
        "We had a problem submitting your responses. Your answers are still here."
    )
    if st.button("Try again", type="primary", use_container_width=True):
        attempt_database_save()
    with st.expander("Development/debug details", expanded=False):
        if st.session_state.get("save_error"):
            st.write("Error:")
            st.code(st.session_state.save_error)
        if st.session_state.get("save_traceback"):
            st.write("Full traceback:")
            st.code(st.session_state.save_traceback)


def show_musical_personality_result() -> bool:
    """Render the participant result from the seven Kaeru responses."""
    kaeru_responses = st.session_state.get("kaeru_responses", [])
    kaeru_comparison = st.session_state.get("kaeru_comparison_answers", {})
    if len(kaeru_responses) != len(KAERU_SOUNDS):
        return False

    try:
        result = calculate_musical_personality(kaeru_responses, kaeru_comparison)
    except (KeyError, TypeError, ValueError) as error:
        st.error("Your result could not be calculated from the saved answers.")
        with st.expander("Development/debug details", expanded=False):
            st.code(f"{type(error).__name__}: {error}")
        return True

    main = result["main_personality"]
    secondary = result["secondary_personality"]
    profile = PERSONALITIES[main]

    st.title("Your Musical Personality")
    st.header(f"{profile['emoji']} {main}")
    st.subheader(f"“{profile['headline']}”")
    st.write(profile["description"])

    st.markdown("### Your Harmonic Match")
    st.markdown(f"## {result['harmonic_match']}")
    st.write(
        f"**Secondary trait:**  \n"
        f"{PERSONALITIES[secondary]['emoji']} {secondary}"
    )

    kaeru_fingerprint = calculate_kaeru_fingerprint(kaeru_responses)
    all_emotions = Counter(
        display_emotion(item) for item in kaeru_responses
    )
    favourite_emotion = sorted(
        all_emotions, key=lambda emotion: (-all_emotions[emotion], emotion)
    )[0]
    tension_tolerance = result["dimensions"]["tension_tolerance_score"]
    if tension_tolerance >= 60:
        tension_relationship = "Enjoys some tension"
    elif tension_tolerance <= 35:
        tension_relationship = "Prefers resolution"
    else:
        tension_relationship = "Mostly tension-neutral"
    richness = result["dimensions"]["richness_score"]
    simplicity = result["dimensions"]["simplicity_score"]
    if richness - simplicity >= 12:
        harmony_preference = "Rich"
    elif simplicity - richness >= 12:
        harmony_preference = "Simple"
    else:
        harmony_preference = "Mixed"

    st.subheader("Your Listening Snapshot")
    st.write(f"**Favourite harmony:** {result['harmonic_match']}")
    st.write(f"**Most common emotion:** {favourite_emotion}")
    st.write(f"**Tension relationship:** {tension_relationship}")
    st.write(f"**Harmony preference:** {harmony_preference}")

    st.subheader("What were you actually hearing?")
    condition_names = (
        "Basic Major", "Basic Minor", "Seventh Rich Major",
        "Seventh Rich Minor", "Ninth Rich Major", "Ninth Rich Minor",
        "Diminished Seventh",
    )
    for (sound_label, _, _), condition_name in zip(KAERU_SOUNDS, condition_names):
        st.write(f"**{sound_label} — {condition_name}**")

    with st.expander("See my detailed listening results", expanded=False):
        st.markdown("#### Same Progression, Different Chord Quality")
        pleasant_col, tension_col, familiar_col = st.columns(3)
        pleasant_col.metric(
            "Overall Pleasantness", f"{kaeru_fingerprint['pleasantness']:.1f} / 7"
        )
        tension_col.metric(
            "Overall Tension", f"{kaeru_fingerprint['tension']:.1f} / 7"
        )
        familiar_col.metric(
            "Overall Familiarity", f"{kaeru_fingerprint['familiarity']:.1f} / 7"
        )
        st.markdown("##### What stood out in your responses?")
        for observation in generate_kaeru_observations(
            kaeru_fingerprint, kaeru_comparison
        ):
            st.markdown(f"- {observation}")
        st.markdown("##### Your direct comparison")
        st.write(
            f"**Favourite:** {kaeru_comparison.get('preferred_sound', 'Not answered')}"
        )
        st.write(
            f"**Most tense:** {kaeru_comparison.get('most_tense_sound', 'Not answered')}"
        )
        st.write(
            "**Most emotionally complex:** "
            f"{kaeru_comparison.get('most_complex_sound', 'Not answered')}"
        )
        st.write(
            "**Most familiar:** "
            f"{kaeru_comparison.get('most_familiar_sound', 'Not answered')}"
        )
        st.markdown("##### Emotional Sound Map")
        render_emotional_map(kaeru_fingerprint)
        st.markdown("##### Familiarity Ratings")
        render_familiarity_chart(kaeru_fingerprint["responses"])

        st.markdown("#### Individual ratings")
        st.markdown("##### Same Progression, Different Chord Quality")
        for response in kaeru_fingerprint["responses"]:
            st.write(
                f"**{response['sound_label']}:** pleasantness "
                f"{response['pleasantness']} / 7, tension {response['tension']} / 7, "
                f"familiarity {response['familiarity']} / 7, "
                f"emotion {display_emotion(response)}"
            )
        st.markdown("#### Direct comparison answers")
        st.markdown("##### Same Progression, Different Chord Quality")
        st.write(
            f"**Favourite:** {kaeru_comparison.get('preferred_sound', 'Not answered')}"
        )
        st.write(
            f"**Most tense:** {kaeru_comparison.get('most_tense_sound', 'Not answered')}"
        )
        st.write(
            "**Most emotionally complex:** "
            f"{kaeru_comparison.get('most_complex_sound', 'Not answered')}"
        )
        st.write(
            "**Most familiar:** "
            f"{kaeru_comparison.get('most_familiar_sound', 'Not answered')}"
        )

    with st.expander("Development/debug details", expanded=False):
        st.markdown("#### Hidden dimensions")
        st.json({key: round(value, 2) for key, value in result["dimensions"].items()})
        st.markdown("#### Musical Personality scores")
        st.json({key: round(value, 2) for key, value in result["scores"].items()})
        st.write(f"**Main personality:** {main}")
        st.write(f"**Secondary personality:** {secondary}")
        st.write(f"**Harmonic match:** {result['harmonic_match']}")

    st.divider()
    st.write(
        "This is a playful interpretation of your responses in this experiment, "
        "not a psychological assessment."
    )
    st.button(
        "Return to the beginning", use_container_width=True, on_click=reset_experiment
    )
    return True


def calculate_kaeru_fingerprint(responses: list[dict]) -> dict:
    """Summarize same-melody ratings without interpreting personality."""
    enriched = [
        {**response, "tension": 8 - response["relaxation"]}
        for response in responses
    ]
    emotion_counts = Counter(display_emotion(item) for item in enriched)
    highest_count = max(emotion_counts.values())
    return {
        "responses": enriched,
        "pleasantness": sum(item["pleasantness"] for item in enriched) / len(enriched),
        "tension": sum(item["tension"] for item in enriched) / len(enriched),
        "familiarity": sum(item["familiarity"] for item in enriched) / len(enriched),
        "common_emotions": [
            emotion for emotion, count in emotion_counts.items() if count == highest_count
        ],
    }


def generate_kaeru_observations(fingerprint: dict, comparison: dict) -> list[str]:
    """Generate two or three cautious observations from this participant's data."""
    responses = fingerprint["responses"]
    by_label = {item["sound_label"]: item for item in responses}
    observations = []
    favourite = comparison["preferred_sound"]
    familiar = comparison["most_familiar_sound"]
    if favourite in by_label and favourite == familiar:
        observations.append(
            f"{favourite} was both your favourite and the version you found most familiar."
        )
    tensions = [item["tension"] for item in responses]
    tense_item = max(responses, key=lambda item: item["tension"])
    if max(tensions) - min(tensions) >= 2:
        observations.append(
            f"You rated {tense_item['sound_label']} as considerably more tense than at least one other version."
        )
    pleasantness = [item["pleasantness"] for item in responses]
    emotions = {display_emotion(item) for item in responses}
    if max(pleasantness) - min(pleasantness) <= 1 and len(emotions) > 1:
        observations.append(
            "You gave similar pleasantness ratings to all seven versions, even though their emotional descriptions differed."
        )
    if favourite in by_label and familiar in by_label and favourite != familiar:
        observations.append(
            "In these seven versions, familiarity and preference did not directly match."
        )
    if len(observations) < 2:
        most_pleasant = max(responses, key=lambda item: item["pleasantness"])
        observations.append(
            f"You gave {most_pleasant['sound_label']} your highest pleasantness rating."
        )
    if len(observations) < 2:
        observations.append(
            f"You associated {responses[0]['sound_label']} with {display_emotion(responses[0])}."
        )
    return observations[:3]


def render_familiarity_chart(responses: list[dict]) -> None:
    figure, axis = plt.subplots(figsize=(6, 3))
    ordered = sorted(responses, key=lambda item: item["trial_number"])
    axis.bar(
        [item["sound_label"] for item in ordered],
        [item["familiarity"] for item in ordered],
        color="#5b8ff9",
    )
    axis.set_ylim(1, 7)
    axis.set_yticks(range(1, 8))
    axis.set_ylabel("Familiarity")
    axis.grid(axis="y", alpha=0.15)
    figure.tight_layout()
    st.pyplot(figure, use_container_width=True)
    plt.close(figure)


st.set_page_config(
    page_title="Can Music Read You?",
    page_icon="🎵",
    layout="centered",
)

# Run the browser-side scroll once, immediately after a completed trial advances.
if st.session_state.pop("scroll_to_top", False):
    scroll_to_top()

# A single session-state value controls the view; no separate browser pages are used.
if "page" not in st.session_state:
    st.session_state.page = "introduction"
if "participant_id" not in st.session_state:
    st.session_state.participant_id = str(uuid.uuid4())
if "data_saved" not in st.session_state:
    st.session_state.data_saved = False
st.session_state.setdefault("kaeru_harmony_saved", False)
if "consent" not in st.session_state:
    st.session_state.consent = False
if "heard_clearly" not in st.session_state:
    st.session_state.heard_clearly = None
if st.session_state.page == "sound_check":
    show_sound_check()
elif st.session_state.page == "kaeru_listening":
    show_kaeru_listening()
elif st.session_state.page == "background_questionnaire":
    show_background_questionnaire()
elif st.session_state.page == "save_completed_experiment":
    show_database_save()
elif st.session_state.page == "musical_personality":
    if not show_musical_personality_result():
        st.session_state.page = "kaeru_listening"
        st.rerun()
else:
    show_introduction()
