-- Run this migration once on an existing Supabase project.
alter table public.participants
    add column if not exists most_tense_sound text,
    add column if not exists preferred_sound text,
    add column if not exists overall_association text;

-- Replace the atomic save function so the new participant fields are persisted.
create or replace function public.save_completed_experiment(
    p_participant jsonb,
    p_responses jsonb
)
returns void
language plpgsql
security invoker
set search_path = ''
as $$
begin
    if jsonb_typeof(p_responses) <> 'array'
       or jsonb_array_length(p_responses) <> 4 then
        raise exception 'A completed experiment requires exactly four responses';
    end if;

    insert into public.participants (
        participant_id, age_range, grew_up_countries, current_country,
        music_training_years, musical_activities, music_genres,
        other_music_genre, weekly_listening_hours, current_mood,
        hearing_difficulty, recruitment_source, other_recruitment_source,
        listening_device, most_tense_sound, preferred_sound, overall_association
    ) values (
        (p_participant->>'participant_id')::uuid,
        p_participant->>'age_range',
        p_participant->>'grew_up_countries',
        p_participant->>'current_country',
        p_participant->>'music_training_years',
        array(select jsonb_array_elements_text(p_participant->'musical_activities')),
        array(select jsonb_array_elements_text(p_participant->'music_genres')),
        p_participant->>'other_music_genre',
        p_participant->>'weekly_listening_hours',
        p_participant->>'current_mood',
        p_participant->>'hearing_difficulty',
        p_participant->>'recruitment_source',
        p_participant->>'other_recruitment_source',
        p_participant->>'listening_device',
        p_participant->>'most_tense_sound',
        p_participant->>'preferred_sound',
        p_participant->>'overall_association'
    );

    insert into public.responses (
        participant_id, trial_number, audio_filename, pleasantness,
        relaxation, tension, emotion, other_emotion, written_association
    )
    select
        (p_participant->>'participant_id')::uuid,
        item.trial_number, item.audio_filename, item.pleasantness,
        item.relaxation, item.tension, item.emotion, item.other_emotion,
        item.written_association
    from jsonb_to_recordset(p_responses) as item(
        participant_id uuid, trial_number integer, audio_filename text,
        pleasantness integer, relaxation integer, tension integer,
        emotion text, other_emotion text, written_association text
    );
end;
$$;

revoke all on function public.save_completed_experiment(jsonb, jsonb) from public;
grant execute on function public.save_completed_experiment(jsonb, jsonb)
to anon, authenticated;
