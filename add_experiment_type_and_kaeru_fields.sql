-- Run this migration once in the Supabase SQL editor for an existing project.
-- It preserves existing participants/responses and treats them as the original
-- diminished-context experiment.

create extension if not exists pgcrypto;

alter table public.responses
    add column if not exists experiment_type text,
    add column if not exists familiarity integer,
    add column if not exists submission_id uuid;

update public.responses
set experiment_type = 'diminished_context'
where experiment_type is null;

alter table public.responses
    alter column experiment_type set default 'diminished_context',
    alter column experiment_type set not null;

create table if not exists public.experiment_submissions (
    submission_id uuid primary key,
    participant_id uuid not null references public.participants(participant_id),
    experiment_type text not null,
    most_tense_sound text not null,
    preferred_sound text not null,
    most_complex_sound text,
    most_familiar_sound text,
    overall_association text,
    created_at timestamptz not null default now(),
    constraint experiment_submissions_type_check
        check (experiment_type in ('diminished_context', 'kaeru_harmony'))
);

-- Give every pre-migration response set a submission record, copying the old
-- participant-level comparison answers without deleting them.
insert into public.experiment_submissions (
    submission_id, participant_id, experiment_type, most_tense_sound,
    preferred_sound, overall_association
)
select
    gen_random_uuid(), p.participant_id, 'diminished_context',
    coalesce(p.most_tense_sound, 'Not recorded'),
    coalesce(p.preferred_sound, 'Not recorded'),
    p.overall_association
from public.participants p
where exists (
    select 1 from public.responses r where r.participant_id = p.participant_id
)
and not exists (
    select 1 from public.experiment_submissions s
    where s.participant_id = p.participant_id
      and s.experiment_type = 'diminished_context'
);

update public.responses r
set submission_id = s.submission_id
from public.experiment_submissions s
where r.submission_id is null
  and r.participant_id = s.participant_id
  and s.experiment_type = 'diminished_context';

alter table public.responses
    alter column submission_id set not null;

alter table public.responses
    drop constraint if exists responses_participant_trial_unique;
alter table public.responses
    drop constraint if exists responses_submission_id_fkey;
alter table public.responses
    add constraint responses_submission_id_fkey
        foreign key (submission_id)
        references public.experiment_submissions(submission_id),
    add constraint responses_submission_trial_unique
        unique (submission_id, trial_number),
    add constraint responses_experiment_type_check
        check (experiment_type in ('diminished_context', 'kaeru_harmony')),
    add constraint responses_familiarity_check
        check (familiarity is null or familiarity between 1 and 7);

alter table public.experiment_submissions enable row level security;
revoke all on table public.experiment_submissions from anon, authenticated;
grant insert on table public.experiment_submissions to anon, authenticated;

drop policy if exists "Public app can insert experiment submissions"
on public.experiment_submissions;
create policy "Public app can insert experiment submissions"
on public.experiment_submissions for insert to anon, authenticated with check (true);

-- Replace the original two-argument function with the multi-experiment version.
drop function if exists public.save_completed_experiment(jsonb, jsonb);
create or replace function public.save_completed_experiment(
    p_participant jsonb,
    p_submission jsonb,
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
        audio_filename, pleasantness, relaxation, tension, emotion,
        other_emotion, familiarity
    )
    select
        item.submission_id, item.participant_id, item.experiment_type,
        item.trial_number, item.audio_filename, item.pleasantness,
        item.relaxation, item.tension, item.emotion, item.other_emotion,
        item.familiarity
    from jsonb_to_recordset(p_responses) as item(
        submission_id uuid, participant_id uuid, experiment_type text,
        trial_number integer, audio_filename text, pleasantness integer,
        relaxation integer, tension integer, emotion text,
        other_emotion text, familiarity integer
    )
    on conflict (submission_id, trial_number) do nothing;
end;
$$;

revoke all on function public.save_completed_experiment(jsonb, jsonb, jsonb)
from public;
grant execute on function public.save_completed_experiment(jsonb, jsonb, jsonb)
to anon, authenticated;
