-- Run once in the Supabase SQL editor after the existing Kaeru migration.
-- This is additive: existing submissions and responses are preserved.

alter table public.responses
    add column if not exists condition_key text;

alter table public.responses
    drop constraint if exists responses_condition_key_check;
alter table public.responses
    add constraint responses_condition_key_check check (
        condition_key is null or condition_key in (
            'basic_major', 'basic_minor', 'seventh_major', 'seventh_minor',
            'ninth_major', 'ninth_minor', 'diminished_seventh'
        )
    );

drop function if exists public.save_completed_experiment(jsonb, jsonb, jsonb);

create or replace function public.save_completed_experiment(
    p_participant jsonb,
    p_submission jsonb,
    p_responses jsonb
)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
    if p_submission->>'experiment_type' <> 'kaeru_harmony'
       or jsonb_typeof(p_responses) <> 'array'
       or jsonb_array_length(p_responses) <> 7 then
        raise exception 'A completed Kaeru experiment requires exactly seven responses';
    end if;

    insert into public.participants (
        participant_id, age_range, grew_up_countries, current_country,
        music_training_years, musical_activities, music_genres,
        other_music_genre, weekly_listening_hours, current_mood,
        hearing_difficulty, recruitment_source, other_recruitment_source,
        listening_device
    ) values (
        (p_participant->>'participant_id')::uuid,
        p_participant->>'age_range', p_participant->>'grew_up_countries',
        p_participant->>'current_country', p_participant->>'music_training_years',
        array(select jsonb_array_elements_text(p_participant->'musical_activities')),
        array(select jsonb_array_elements_text(p_participant->'music_genres')),
        p_participant->>'other_music_genre',
        p_participant->>'weekly_listening_hours', p_participant->>'current_mood',
        p_participant->>'hearing_difficulty', p_participant->>'recruitment_source',
        p_participant->>'other_recruitment_source', p_participant->>'listening_device'
    ) on conflict (participant_id) do nothing;

    insert into public.experiment_submissions (
        submission_id, participant_id, experiment_type, most_tense_sound,
        preferred_sound, most_complex_sound, most_familiar_sound,
        overall_association
    ) values (
        (p_submission->>'submission_id')::uuid,
        (p_submission->>'participant_id')::uuid,
        p_submission->>'experiment_type', p_submission->>'most_tense_sound',
        p_submission->>'preferred_sound', p_submission->>'most_complex_sound',
        p_submission->>'most_familiar_sound', p_submission->>'overall_association'
    ) on conflict (submission_id) do nothing;

    insert into public.responses (
        submission_id, participant_id, experiment_type, trial_number,
        audio_filename, condition_key, pleasantness, relaxation, tension,
        emotion, other_emotion, familiarity
    )
    select
        item.submission_id, item.participant_id, item.experiment_type,
        item.trial_number, item.audio_filename, item.condition_key,
        item.pleasantness, item.relaxation, item.tension, item.emotion,
        item.other_emotion, item.familiarity
    from jsonb_to_recordset(p_responses) as item(
        submission_id uuid, participant_id uuid, experiment_type text,
        trial_number integer, audio_filename text, condition_key text,
        pleasantness integer, relaxation integer, tension integer,
        emotion text, other_emotion text, familiarity integer
    )
    on conflict (submission_id, trial_number) do nothing;
end;
$$;

revoke all on function public.save_completed_experiment(jsonb, jsonb, jsonb)
from public;
grant execute on function public.save_completed_experiment(jsonb, jsonb, jsonb)
to anon, authenticated;
