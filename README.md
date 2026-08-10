# Can Music Read You?

**Can Music Read You?** is a Streamlit-based music-emotion study presented as a
short, playful musical personality test. Participants listen to eight harmony
clips, describe how each one feels, and receive a personalised **Musical
Personality** and **Harmonic Fingerprint** at the end.

Behind the playful result is an experiment about a serious question: do musical
and cultural backgrounds affect the way people experience harmony, tension,
resolution, and emotional colour?

## How the idea developed

### 1. The first idea: a small harmony experiment

The project began as a straightforward listening experiment. I made four short
clips that changed two musical features:

- major versus minor harmony;
- resolved versus unresolved endings.

Participants rated each anonymous Sound A–D for pleasantness, tension or
relaxation, and emotional association. They then compared the sounds directly.
The aim was to collect simple, useful data without telling participants which
musical condition they were hearing.

This first version worked as an experiment, but it felt too much like filling in
a research form. A participant gave their time and reactions, yet the experience
mostly benefited the researcher. There was not enough curiosity, reward, or
reason for the participant to enjoy reaching the end.

### 2. Trying a more controlled musical comparison

The next attempt kept one familiar melody constant and changed only its
accompaniment. I used **Kaeru no Uta** in four versions:

- basic triads;
- seventh chords;
- ninth chords;
- diminished seventh harmony.

Using the same melody made the contrast easier to hear: the tune remained
recognisable while the harmony became clearer, richer, dreamier, or more tense.
This section also added familiarity and emotional-complexity questions. That
produced a fuller picture than the original major/minor experiment alone, but a
page of ratings still did not automatically make the experience enjoyable.

### 3. From “experiment” to “personality test”

The turning point was to think about the participant's experience, not only the
data collection. I wanted people to finish with something that felt personal,
memorable, and fun. The app therefore became a two-part journey ending in a
playful musical personality result.

The final result combines both listening sections. It considers patterns such as
preference for simple or rich harmony, comfort with tension, variation in
emotional responses, and openness across different harmonic styles. It then
returns a profile such as **The Harmonic Dreamer**, **The Colour Seeker**, or
**The Tension Seeker**, together with a harmonic match and detailed listening
summary.

The personality-test format is an engagement layer around the experiment. It is
not a validated personality assessment or a psychological diagnosis. The result
only interprets how that participant responded to these particular sounds. This
balance is where the project ended up: the study can still collect structured
music-emotion data, while the participant receives an immediate and enjoyable
reason to take part.

## Participant journey

1. Read the study information and consent.
2. Complete a sound check.
3. Rate four major/minor, resolved/unresolved harmony clips.
4. Compare four versions of the same melody with different accompaniments.
5. Answer a short musical and cultural background questionnaire.
6. Receive a Musical Personality, harmonic match, and detailed listening
   snapshot.

There are no correct or incorrect listening answers. Participants can replay the
clips and move back to revise their responses before submission.

## Privacy and data design

The app does not ask for a participant's name or contact details. It generates a
random UUID and stores data in Supabase only after both listening sections and
the questionnaire have been completed.

Each listening section has its own submission and four linked response rows. The
`experiment_type` field distinguishes `diminished_context` from
`kaeru_harmony`. The participant-facing app can insert completed data but has no
database read policy.

## Setup

1. Install dependencies with `pip install -r requirements.txt`.
2. Create a Supabase project.
3. For a new project, run all of `supabase_schema.sql`, followed by
   `add_experiment_type_and_kaeru_fields.sql`, in the Supabase SQL editor.
4. For an existing project, run `add_comparison_answers.sql` if it has not
   already been applied, then run `add_experiment_type_and_kaeru_fields.sql`.
5. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`.
6. Add the project's Supabase URL and publishable/anon key to the copied file.
7. Run `streamlit run app.py`.

Never commit `.streamlit/secrets.toml` to GitHub. It is ignored by `.gitignore`.
Do not use a Supabase service-role key in this participant-facing app.

## Confirming a test submission

Complete the full participant journey. In Supabase's Table Editor, find the UUID
in `participants`, then filter `experiment_submissions` and `responses` by that
`participant_id`.

A completed journey should contain:

- one participant row;
- two experiment-submission rows, one for each `experiment_type`;
- eight response rows in total, four linked to each submission.

The personality result is calculated locally from the participant's listening
answers; it is not stored as a clinical or psychological profile.
