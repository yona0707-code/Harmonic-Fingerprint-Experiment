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
SOUNDS = (
    ("Sound A", "major_resolved.wav"),
    ("Sound B", "major_unresolved.wav"),
    ("Sound C", "minor_resolved.wav"),
    ("Sound D", "minor_unresolved.wav"),
)
KAERU_SOUNDS = (
    ("Sound A", "kaeru_basic_triads.wav"),
    ("Sound B", "kaeru_sevenths.wav"),
    ("Sound C", "kaeru_ninths_from_basic.wav"),
    ("Sound D", "kaeru_diminished_sevenths.wav"),
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
    elif page == "listening_comparison":
        st.session_state.page = "sound_check"
    elif page == "part_one_complete":
        st.session_state.page = "listening_comparison"
    elif page == "kaeru_listening":
        st.session_state.page = "part_one_complete"
    elif page == "background_questionnaire":
        st.session_state.background_draft = {
            key: value
            for key, value in st.session_state.items()
            if key.startswith("background_") and key != "background_draft"
        }
        st.session_state.page = "kaeru_listening"
    elif page == "harmonic_fingerprint":
        st.session_state.page = "background_questionnaire"
    elif page == "kaeru_fingerprint":
        st.session_state.page = "background_questionnaire"

    st.session_state.scroll_to_top = True


def show_back_button() -> None:
    """Show a consistent previous-page control on every app view."""
    st.button(
        "Go back to previous page",
        disabled=st.session_state.get("page", "introduction") == "introduction",
        on_click=go_back_to_previous_page,
        use_container_width=True,
    )


def start_listening_comparison(experiment_type: str = "diminished_context") -> None:
    """Start a comparative listening session in the fixed Sound A–D order."""
    st.session_state.responses = []
    st.session_state.experiment_type = experiment_type
    submission_key = f"{experiment_type}_submission_id"
    st.session_state.setdefault(submission_key, str(uuid.uuid4()))
    st.session_state.submission_id = st.session_state[submission_key]
    st.session_state.data_saved = st.session_state.get(f"{experiment_type}_saved", False)
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
    st.session_state.page = (
        "kaeru_listening" if experiment_type == "kaeru_harmony"
        else "listening_comparison"
    )


def show_part_one_complete() -> None:
    """Bridge the listening sections without showing an interim result."""
    show_back_button()
    st.title("Part 1 complete")
    st.write("Next, you’ll hear the same melody with different accompaniments.")
    if st.button("Continue to Part 2", type="primary", use_container_width=True):
        start_listening_comparison("kaeru_harmony")
        st.rerun()


def display_emotion(response: dict) -> str:
    """Return the participant's custom label when they selected Other."""
    if response["emotion"] == "Other":
        return response.get("other_emotion", "").strip() or "Other"
    return response["emotion"]


def calculate_harmonic_fingerprint(responses: list[dict]) -> dict:
    """Calculate participant-only summaries from the four listening responses."""
    enriched = [
        {**response, "tension": 8 - response["relaxation"]}
        for response in responses
    ]

    def averages(selected: list[dict]) -> dict:
        return {
            "pleasantness": sum(item["pleasantness"] for item in selected) / len(selected),
            "tension": sum(item["tension"] for item in selected) / len(selected),
        }

    major = [item for item in enriched if item["audio_filename"].startswith("major_")]
    minor = [item for item in enriched if item["audio_filename"].startswith("minor_")]
    resolved = [
        item for item in enriched
        if item["audio_filename"].endswith("_resolved.wav")
    ]
    unresolved = [
        item for item in enriched
        if item["audio_filename"].endswith("_unresolved.wav")
    ]
    emotion_counts = Counter(display_emotion(item) for item in enriched)
    highest_count = max(emotion_counts.values())

    return {
        "responses": enriched,
        "overall": averages(enriched),
        "major": averages(major),
        "minor": averages(minor),
        "resolved": averages(resolved),
        "unresolved": averages(unresolved),
        "common_emotions": [
            emotion for emotion, count in emotion_counts.items()
            if count == highest_count
        ],
        "emotion_counts": emotion_counts,
    }


def choose_fingerprint_title(fingerprint: dict) -> str:
    """Choose a descriptive title using simple, participant-only rules."""
    pleasantness = fingerprint["overall"]["pleasantness"]
    tension = fingerprint["overall"]["tension"]
    emotions = fingerprint["emotion_counts"]
    mysterious_is_most_common = (
        emotions.get("Mysterious", 0) > 0
        and emotions["Mysterious"] == max(emotions.values())
    )

    if tension >= 5 and pleasantness >= 4:
        return "The Suspense Interpreter"
    if mysterious_is_most_common:
        return "The Mystery Seeker"
    if tension >= 5 and pleasantness < 4:
        return "The Dramatic Listener"
    if tension <= 3:
        return "The Calm Interpreter"
    if abs(pleasantness - 4) <= 0.75 and abs(tension - 4) <= 0.75:
        return "The Balanced Observer"
    return "The Emotional Explorer"


def comparison_sentence(
    fingerprint: dict, first_key: str, second_key: str, comparison_name: str
) -> str:
    """Describe a two-condition comparison using the 0.75 readability threshold."""
    first = fingerprint[first_key]
    second = fingerprint[second_key]
    pleasantness_difference = first["pleasantness"] - second["pleasantness"]
    tension_difference = first["tension"] - second["tension"]

    if comparison_name == "major_minor":
        if abs(pleasantness_difference) < 0.75 and abs(tension_difference) < 0.75:
            return "Your responses to major and minor were very similar."
        if abs(tension_difference) >= abs(pleasantness_difference):
            more_tense = "major" if tension_difference > 0 else "minor"
            return f"In this experiment, the {more_tense} sounds felt noticeably more tense to you."
        more_pleasant = "major" if pleasantness_difference > 0 else "minor"
        return f"In this experiment, the {more_pleasant} sounds felt noticeably more pleasant to you."

    if abs(pleasantness_difference) < 0.75 and abs(tension_difference) < 0.75:
        return "Whether the harmony resolved made little difference to your ratings."
    if abs(tension_difference) >= abs(pleasantness_difference):
        more_tense = "resolved" if tension_difference > 0 else "unresolved"
        return f"The {more_tense} endings created noticeably more tension for you."
    more_pleasant = "resolved" if pleasantness_difference > 0 else "unresolved"
    return f"The {more_pleasant} sounds felt noticeably more pleasant to you."


def generate_result_description(fingerprint: dict) -> str:
    """Create a cautious short description that changes with the ratings."""
    pleasantness = fingerprint["overall"]["pleasantness"]
    tension = fingerprint["overall"]["tension"]
    if tension >= 5:
        tension_phrase = "fairly tense"
    elif tension <= 3:
        tension_phrase = "fairly relaxed"
    else:
        tension_phrase = "neither strongly tense nor strongly relaxed"
    if pleasantness >= 5:
        pleasantness_phrase = "generally pleasant"
    elif pleasantness <= 3:
        pleasantness_phrase = "generally unpleasant"
    else:
        pleasantness_phrase = "not strongly pleasant or unpleasant"

    return (
        f"You experienced these four sounds as {tension_phrase} and {pleasantness_phrase}. "
        f"{comparison_sentence(fingerprint, 'major', 'minor', 'major_minor')} "
        f"{comparison_sentence(fingerprint, 'resolved', 'unresolved', 'resolution')}"
    )


def generate_key_findings(fingerprint: dict) -> list[str]:
    """Return three readable findings without treating small differences as meaningful."""
    findings = [
        comparison_sentence(fingerprint, "major", "minor", "major_minor"),
        comparison_sentence(fingerprint, "resolved", "unresolved", "resolution"),
    ]
    counts = fingerprint["emotion_counts"]
    if max(counts.values()) > 1:
        repeated = ", ".join(fingerprint["common_emotions"])
        findings.append(f"You selected {repeated} more than once across the four sounds.")
    elif len(counts) == 4:
        findings.append("You chose a different emotional association for each sound.")
    return findings


def render_emotional_map(fingerprint: dict) -> None:
    """Render the four participant ratings without revealing conditions."""
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
            start_listening_comparison("diminished_context")
            st.rerun()


def show_listening_comparison() -> None:
    """Collect intentional comparative judgments with freely replayable sounds."""
    # Restore saved answers when navigating back from the questionnaire. Streamlit
    # may remove widget state while those widgets are not rendered.
    for response in st.session_state.get("responses", []):
        prefix = f"sound_{response['trial_number']}"
        for field in ("pleasantness", "relaxation", "emotion", "other_emotion"):
            st.session_state.setdefault(f"{prefix}_{field}", response.get(field, ""))
    saved_comparison = st.session_state.get("comparison_answers", {})
    st.session_state.setdefault(
        "comparison_most_tense", saved_comparison.get("most_tense_sound")
    )
    st.session_state.setdefault(
        "comparison_preferred", saved_comparison.get("preferred_sound")
    )
    st.session_state.setdefault(
        "comparison_overall_association", saved_comparison.get("overall_association", "")
    )
    show_back_button()
    st.title("Part 1 of 2")
    st.header("Harmony and Resolution")
    st.write(
        "Listen to the four sounds below. You may replay them as many times as "
        "you like and switch between them before answering."
    )
    st.write(
        "There are no correct or incorrect answers. Focus on how each sound feels to you."
    )
    for sound_label, audio_filename in SOUNDS:
        audio_path = APP_DIR / audio_filename
        st.subheader(sound_label)
        if not audio_path.is_file():
            st.error("A required sound is unavailable. Please contact the researcher.")
            return
        st.audio(str(audio_path), format="audio/wav")

    st.header("Your responses")
    for trial_number, (sound_label, _) in enumerate(SOUNDS, start=1):
        prefix = f"sound_{trial_number}"
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
        st.divider()

    st.subheader("Compare the sounds")
    st.radio(
        "Which sound felt the most tense?",
        (*[label for label, _ in SOUNDS], "They felt about the same"),
        index=None, key="comparison_most_tense",
    )
    st.radio(
        "Which sound did you like the most?",
        (*[label for label, _ in SOUNDS], "No clear preference"),
        index=None, key="comparison_preferred",
    )
    st.text_area(
        "Did any of the sounds give you a particularly strong image, memory, or feeling?",
        help=("Optional — you can mention the sound label if you want, for example "
              "“Sound C reminded me of a suspenseful movie scene.”"),
        max_chars=400, key="comparison_overall_association",
    )

    if st.button("Continue", type="primary", use_container_width=True):
        missing = []
        responses = []
        for trial_number, (sound_label, audio_filename) in enumerate(SOUNDS, start=1):
            prefix = f"sound_{trial_number}"
            pleasantness = st.session_state.get(f"{prefix}_pleasantness")
            relaxation = st.session_state.get(f"{prefix}_relaxation")
            emotion = st.session_state.get(f"{prefix}_emotion")
            other = st.session_state.get(f"{prefix}_other_emotion", "").strip()
            if pleasantness is None or relaxation is None or emotion is None:
                missing.append(sound_label)
            elif emotion == "Other" and not other:
                missing.append(f"{sound_label} Other emotion description")
            responses.append({
                "trial_number": trial_number, "sound_label": sound_label,
                "audio_filename": audio_filename, "pleasantness": pleasantness,
                "relaxation": relaxation, "emotion": emotion,
                "other_emotion": other if emotion == "Other" else "",
            })
        if st.session_state.get("comparison_most_tense") is None:
            missing.append("the most-tense comparison")
        if st.session_state.get("comparison_preferred") is None:
            missing.append("the favourite-sound comparison")
        if missing:
            st.warning("Please complete all required responses. Missing: " + ", ".join(missing) + ".")
        else:
            st.session_state.responses = responses
            st.session_state.comparison_answers = {
                "most_tense_sound": st.session_state.comparison_most_tense,
                "preferred_sound": st.session_state.comparison_preferred,
                "overall_association": st.session_state.get(
                    "comparison_overall_association", ""
                ).strip(),
            }
            # Preserve this completed section while the existing save flow runs;
            # the second section can then contribute to one combined result.
            st.session_state.harmony_responses = responses
            st.session_state.harmony_comparison_answers = dict(
                st.session_state.comparison_answers
            )
            st.session_state.page = "part_one_complete"
            st.session_state.scroll_to_top = True
            st.rerun()


def show_kaeru_listening() -> None:
    """Collect all four same-melody ratings and direct comparisons."""
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
    st.title("Part 2 of 2")
    st.header("Same Melody, Different Harmony")
    st.write("The melody is the same in all four sounds, but the accompaniment changes.")
    st.write(
        "Listen to each version as many times as you like and compare how they feel to you."
    )
    st.write("There are no correct or incorrect answers.")

    for sound_label, audio_filename in KAERU_SOUNDS:
        st.subheader(sound_label)
        audio_path = APP_DIR / audio_filename
        if not audio_path.is_file():
            st.error("A required sound is unavailable. Please contact the researcher.")
            return
        st.audio(str(audio_path), format="audio/wav")

    st.header("Your responses")
    for trial_number, (sound_label, _) in enumerate(KAERU_SOUNDS, start=1):
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

    labels = tuple(label for label, _ in KAERU_SOUNDS)
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
        for trial_number, (sound_label, audio_filename) in enumerate(KAERU_SOUNDS, start=1):
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
    if (
        len(st.session_state.get("harmony_responses", [])) != 4
        or len(st.session_state.get("kaeru_responses", [])) != 4
    ):
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
                len(st.session_state.get("harmony_responses", [])) == 4
                and len(st.session_state.get("kaeru_responses", [])) == 4
                and all(
                    st.session_state.get(key, {}).get("most_tense_sound")
                    and st.session_state.get(key, {}).get("preferred_sound")
                    for key in (
                        "harmony_comparison_answers",
                        "kaeru_comparison_answers",
                    )
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
                    "Your listening answers are incomplete. Please return to Part 2 "
                    "and complete the required questions."
                )
                return
            st.session_state.page = "save_completed_experiment"
            st.session_state.save_attempted = False
            st.session_state.scroll_to_top = True
            st.rerun()


def attempt_database_save() -> None:
    """Save each section once, retaining answers and partial-save state on failure."""
    st.session_state.save_attempted = True
    for experiment_type in ("diminished_context", "kaeru_harmony"):
        st.session_state.setdefault(
            f"{experiment_type}_submission_id", str(uuid.uuid4())
        )
    try:
        for experiment_type, response_key, comparison_key in (
            ("diminished_context", "harmony_responses", "harmony_comparison_answers"),
            ("kaeru_harmony", "kaeru_responses", "kaeru_comparison_answers"),
        ):
            saved_key = f"{experiment_type}_saved"
            if st.session_state.get(saved_key, False):
                continue
            save_completed_experiment(
                st.session_state.participant_id,
                st.session_state.background_answers,
                st.session_state[response_key],
                st.session_state[comparison_key],
                experiment_type,
                st.session_state[f"{experiment_type}_submission_id"],
            )
            st.session_state[saved_key] = True
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
    """Render the combined reward once both independently saved sections exist."""
    harmony_responses = st.session_state.get("harmony_responses", [])
    kaeru_responses = st.session_state.get("kaeru_responses", [])
    harmony_comparison = st.session_state.get("harmony_comparison_answers", {})
    kaeru_comparison = st.session_state.get("kaeru_comparison_answers", {})
    if len(harmony_responses) != 4 or len(kaeru_responses) != 4:
        return False

    try:
        result = calculate_musical_personality(
            harmony_responses, kaeru_responses, kaeru_comparison
        )
    except (KeyError, TypeError, ValueError) as error:
        st.error("Your combined result could not be calculated from the saved answers.")
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
    harmony_fingerprint = calculate_harmonic_fingerprint(harmony_responses)
    all_emotions = Counter(
        display_emotion(item) for item in harmony_responses + kaeru_responses
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
    st.write("**Sound A — Basic Triads**  \nSimple C, F and G chords.")
    st.write(
        "**Sound B — Seventh Chords**  \n"
        "Extra notes add more harmonic colour."
    )
    st.write(
        "**Sound C — Ninth Chords**  \n"
        "The harmony is extended further, creating an even richer sound."
    )
    st.write(
        "**Sound D — Diminished Seventh Harmony**  \n"
        "Unstable chords briefly increase tension before resolving."
    )

    with st.expander("See my detailed listening results", expanded=False):
        st.markdown("#### Same Melody, Different Harmony")
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

        st.markdown("#### Harmony and Resolution")
        resolved_col, unresolved_col = st.columns(2)
        resolved_col.metric(
            "Resolved pleasantness",
            f"{harmony_fingerprint['resolved']['pleasantness']:.1f} / 7",
        )
        resolved_col.metric(
            "Resolved tension", f"{harmony_fingerprint['resolved']['tension']:.1f} / 7"
        )
        unresolved_col.metric(
            "Unresolved pleasantness",
            f"{harmony_fingerprint['unresolved']['pleasantness']:.1f} / 7",
        )
        unresolved_col.metric(
            "Unresolved tension",
            f"{harmony_fingerprint['unresolved']['tension']:.1f} / 7",
        )
        render_emotional_map(harmony_fingerprint)

        st.markdown("#### Individual ratings")
        st.markdown("##### Same Melody, Different Harmony")
        for response in kaeru_fingerprint["responses"]:
            st.write(
                f"**{response['sound_label']}:** pleasantness "
                f"{response['pleasantness']} / 7, tension {response['tension']} / 7, "
                f"familiarity {response['familiarity']} / 7, "
                f"emotion {display_emotion(response)}"
            )
        st.markdown("##### Harmony and Resolution")
        for response in harmony_fingerprint["responses"]:
            st.write(
                f"**{response['sound_label']}:** pleasantness "
                f"{response['pleasantness']} / 7, tension {response['tension']} / 7, "
                f"emotion {display_emotion(response)}"
            )
        st.markdown("#### Direct comparison answers")
        st.markdown("##### Same Melody, Different Harmony")
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
        st.markdown("##### Harmony and Resolution")
        st.write(
            "**Favourite:** "
            f"{harmony_comparison.get('preferred_sound', 'Not answered')}"
        )
        st.write(
            "**Most tense:** "
            f"{harmony_comparison.get('most_tense_sound', 'Not answered')}"
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


def show_harmonic_fingerprint() -> None:
    """Display the participant's Harmonic Fingerprint and collapsed raw details."""
    responses = st.session_state.get("responses", [])
    if len(responses) != len(SOUNDS):
        st.session_state.page = "listening_comparison"
        st.rerun()
    if "background_answers" not in st.session_state:
        st.session_state.page = "background_questionnaire"
        st.rerun()

    if show_musical_personality_result():
        return

    show_back_button()
    fingerprint = calculate_harmonic_fingerprint(responses)
    st.title("Your Harmonic Fingerprint")
    st.header(choose_fingerprint_title(fingerprint))
    st.write(generate_result_description(fingerprint))

    st.subheader("What stood out in your responses?")
    for finding in generate_key_findings(fingerprint):
        st.markdown(f"- {finding}")

    pleasantness_column, tension_column = st.columns(2)
    pleasantness_column.metric(
        "Pleasantness", f"{fingerprint['overall']['pleasantness']:.1f} / 7"
    )
    tension_column.metric("Tension", f"{fingerprint['overall']['tension']:.1f} / 7")
    common_emotions = fingerprint["common_emotions"]
    emotion_label = (
        "Most common emotion"
        if len(common_emotions) == 1
        else "Most common emotions"
    )
    st.write(f"**{emotion_label}:** {', '.join(common_emotions)}")

    comparison_answers = st.session_state.get("comparison_answers", {})
    st.subheader("Your direct comparison")
    st.write(f"**Most tense:** {comparison_answers.get('most_tense_sound', 'Not answered')}")
    st.write(f"**Favourite:** {comparison_answers.get('preferred_sound', 'Not answered')}")

    st.subheader("Your Emotional Sound Map")
    render_emotional_map(fingerprint)

    st.subheader("Major and minor")
    major_column, minor_column = st.columns(2)
    with major_column:
        st.markdown("#### Major")
        st.write(f"Pleasantness: {fingerprint['major']['pleasantness']:.1f} / 7")
        st.write(f"Tension: {fingerprint['major']['tension']:.1f} / 7")
    with minor_column:
        st.markdown("#### Minor")
        st.write(f"Pleasantness: {fingerprint['minor']['pleasantness']:.1f} / 7")
        st.write(f"Tension: {fingerprint['minor']['tension']:.1f} / 7")
    st.write(comparison_sentence(fingerprint, "major", "minor", "major_minor"))

    st.subheader("Resolution")
    resolved_column, unresolved_column = st.columns(2)
    with resolved_column:
        st.markdown("#### Resolved")
        st.write(f"Pleasantness: {fingerprint['resolved']['pleasantness']:.1f} / 7")
        st.write(f"Tension: {fingerprint['resolved']['tension']:.1f} / 7")
    with unresolved_column:
        st.markdown("#### Unresolved")
        st.write(f"Pleasantness: {fingerprint['unresolved']['pleasantness']:.1f} / 7")
        st.write(f"Tension: {fingerprint['unresolved']['tension']:.1f} / 7")
    st.write(comparison_sentence(fingerprint, "resolved", "unresolved", "resolution"))

    st.subheader("Your emotional associations")
    for response in sorted(responses, key=lambda item: item["trial_number"]):
        st.write(f"**{response['sound_label']}** — {display_emotion(response)}")

    st.divider()
    st.write(
        "This Harmonic Fingerprint describes your responses during this listening "
        "experiment. It is not a personality or psychological diagnosis."
    )
    st.write(
        "As more people take part, future versions of the experiment may allow "
        "you to compare your responses with other listeners."
    )

    background_labels = {
        "age_range": "Age range",
        "grew_up_countries": "Country or countries mainly grew up in",
        "current_country": "Current country",
        "music_training_years": "Formal musical training",
        "musical_activities": "Musical activities",
        "music_genres": "Regularly listened-to music",
        "other_music_genre": "Other type of music",
        "weekly_listening_hours": "Weekly listening time",
        "current_mood": "Current mood",
        "hearing_difficulty": "Hearing difficulty",
        "recruitment_source": "How the experiment was found",
        "other_recruitment_source": "Other recruitment source",
        "listening_device": "Listening device",
    }
    with st.expander("Development details", expanded=False):
        st.write(f"**Participant ID:** {st.session_state.participant_id}")
        st.write(f"**Database saved:** {st.session_state.data_saved}")
        st.subheader("Listening responses")
        for response in sorted(
            fingerprint["responses"], key=lambda item: item["trial_number"]
        ):
            st.markdown(f"#### {response['sound_label']}")
            st.write(f"**Actual audio filename:** {response['audio_filename']}")
            st.write(f"**Pleasantness:** {response['pleasantness']}")
            st.write(f"**Relaxation:** {response['relaxation']}")
            st.write(f"**Calculated tension:** {response['tension']}")
            st.write(f"**Emotion:** {response['emotion']}")
            st.write(f"**Other emotion:** {response['other_emotion'] or 'Not provided'}")
        st.subheader("Comparison answers")
        st.write(f"**Most tense:** {comparison_answers.get('most_tense_sound', 'Not answered')}")
        st.write(f"**Favourite:** {comparison_answers.get('preferred_sound', 'Not answered')}")
        st.write(
            "**Overall association:** "
            f"{comparison_answers.get('overall_association') or 'Not provided'}"
        )
        st.subheader("Background questionnaire answers")
        for key, label in background_labels.items():
            value = st.session_state.background_answers.get(key, "")
            if isinstance(value, list):
                value = ", ".join(value)
            st.write(f"**{label}:** {value or 'Not provided'}")

    if st.button(
        "Continue to Same Melody, Different Harmony",
        type="primary",
        use_container_width=True,
    ):
        start_listening_comparison("kaeru_harmony")
        st.rerun()

    st.button(
        "Return to the beginning",
        use_container_width=True,
        on_click=reset_experiment,
    )


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
        "pleasantness": sum(item["pleasantness"] for item in enriched) / 4,
        "tension": sum(item["tension"] for item in enriched) / 4,
        "familiarity": sum(item["familiarity"] for item in enriched) / 4,
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
            "You gave similar pleasantness ratings to all four versions, even though their emotional descriptions differed."
        )
    if favourite in by_label and familiar in by_label and favourite != familiar:
        observations.append(
            "In these four versions, familiarity and preference did not directly match."
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


def show_kaeru_fingerprint() -> None:
    responses = st.session_state.get("responses", [])
    if len(responses) != 4:
        st.session_state.page = "kaeru_listening"
        st.rerun()
    if "background_answers" not in st.session_state:
        st.session_state.page = "background_questionnaire"
        st.rerun()

    if show_musical_personality_result():
        return

    show_back_button()
    fingerprint = calculate_kaeru_fingerprint(responses)
    comparison = st.session_state.get("comparison_answers", {})
    st.title("Your Harmony Fingerprint")
    pleasant_col, tension_col, familiar_col = st.columns(3)
    pleasant_col.metric("Overall Pleasantness", f"{fingerprint['pleasantness']:.1f} / 7")
    tension_col.metric("Overall Tension", f"{fingerprint['tension']:.1f} / 7")
    familiar_col.metric("Overall Familiarity", f"{fingerprint['familiarity']:.1f} / 7")
    st.write(f"**Most common emotion:** {fingerprint['common_emotions'][0]}")

    st.subheader("What stood out in your responses?")
    for observation in generate_kaeru_observations(fingerprint, comparison):
        st.markdown(f"- {observation}")

    st.subheader("Your direct comparison")
    st.write(f"**Favourite:** {comparison.get('preferred_sound', 'Not answered')}")
    st.write(f"**Most tense:** {comparison.get('most_tense_sound', 'Not answered')}")
    st.write(f"**Most emotionally complex:** {comparison.get('most_complex_sound', 'Not answered')}")
    st.write(f"**Most familiar:** {comparison.get('most_familiar_sound', 'Not answered')}")

    st.subheader("Your Emotional Sound Map")
    render_emotional_map(fingerprint)
    st.subheader("Your Familiarity Ratings")
    render_familiarity_chart(fingerprint["responses"])

    with st.expander("Development details", expanded=False):
        st.write("**Internal mapping**")
        for sound_label, filename in KAERU_SOUNDS:
            st.write(f"{sound_label} → {filename}")
        st.write(f"**Participant UUID:** {st.session_state.participant_id}")
        st.write(f"**Supabase saved status:** {st.session_state.data_saved}")
        st.subheader("Listening responses")
        for response in fingerprint["responses"]:
            st.markdown(f"#### {response['sound_label']}")
            st.write(f"**Pleasantness:** {response['pleasantness']}")
            st.write(f"**Relaxation:** {response['relaxation']}")
            st.write(f"**Calculated tension:** {response['tension']}")
            st.write(f"**Familiarity:** {response['familiarity']}")
            st.write(f"**Emotion:** {display_emotion(response)}")
        st.subheader("Comparison answers")
        st.json(comparison)
        st.subheader("Background answers")
        st.json(st.session_state.background_answers)

    if st.button(
        "Continue to Harmony and Resolution",
        type="primary",
        use_container_width=True,
    ):
        start_listening_comparison("diminished_context")
        st.rerun()
    st.button("Return to the beginning", use_container_width=True, on_click=reset_experiment)


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
for experiment_type in ("diminished_context", "kaeru_harmony"):
    st.session_state.setdefault(f"{experiment_type}_saved", False)
if "consent" not in st.session_state:
    st.session_state.consent = False
if "heard_clearly" not in st.session_state:
    st.session_state.heard_clearly = None
if st.session_state.page == "sound_check":
    show_sound_check()
elif st.session_state.page == "listening_comparison":
    show_listening_comparison()
elif st.session_state.page == "part_one_complete":
    show_part_one_complete()
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
