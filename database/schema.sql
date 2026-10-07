-- ════════════════════════════════════════════════════════════════════
--  ANIME DRAFT — Supabase / PostgreSQL schema
--  Paste this whole file into: Supabase Dashboard → SQL Editor → Run.
--  Idempotent: safe to run again.
--  The bot connects with the *service_role* key; RLS is enabled with NO
--  policies so the public anon key can read/write nothing.
-- ════════════════════════════════════════════════════════════════════

-- ───────────── users / groups ─────────────
create table if not exists users (
  id          bigint primary key,                 -- Telegram user id
  username    text,
  first_name  text        not null default '',
  dm_started  boolean     not null default false, -- has opened the bot privately
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create table if not exists groups (
  id          bigint primary key,                 -- Telegram chat id
  title       text,
  created_at  timestamptz not null default now()
);

-- ───────────── characters ─────────────
create table if not exists characters (
  id             text primary key,                -- slug, e.g. 'reinhard'
  name           text not null,
  series         text not null check (series in ('Re:ZERO', 'Black Clover', 'Death Note', 'Ben 10')),
  image_url      text,
  image_file_id  text,                            -- cached Telegram file_id
  attack         smallint not null check (attack between 1 and 100),
  defense        smallint not null check (defense between 1 and 100),
  tanking        smallint not null check (tanking between 1 and 100),
  speed          smallint not null check (speed between 1 and 100),
  healing        smallint not null check (healing between 1 and 100),
  intelligence   smallint not null check (intelligence between 1 and 100),
  rarity         text not null check (rarity in ('COMMON', 'RARE', 'EPIC', 'LEGENDARY')),
  abilities      jsonb not null default '[]'::jsonb,
  description    text not null default '',
  active         boolean not null default true
);

-- Migration for databases created before a franchise was added: refresh the series check.
alter table characters drop constraint if exists characters_series_check;
alter table characters add constraint characters_series_check
  check (series in ('Re:ZERO', 'Black Clover', 'Death Note', 'Ben 10'));

create table if not exists character_categories (
  character_id  text not null references characters(id) on delete cascade,
  category      text not null check (category in
                  ('ATTACK', 'DEFENSE', 'TANKING', 'SPEED', 'HEALING', 'INTELLIGENCE')),
  primary key (character_id, category)
);
create index if not exists idx_character_categories_category on character_categories(category);

-- ───────────── games ─────────────
create table if not exists games (
  id                  bigint generated always as identity primary key,
  group_id            bigint not null references groups(id),
  host_id             bigint not null references users(id),
  status              text   not null default 'LOBBY'
                        check (status in ('LOBBY','DRAFTING','LEAGUE','FINAL','COMPLETED','CANCELLED')),
  min_players         smallint not null default 3,
  max_players         smallint not null default 8,
  lobby_message_id    bigint,
  progress_message_id bigint,
  table_message_id    bigint,
  champion_user_id    bigint references users(id),
  final_announced     boolean not null default false,
  draft_deadline      timestamptz,
  created_at          timestamptz not null default now(),
  started_at          timestamptz,
  completed_at        timestamptz
);
create index if not exists idx_games_status on games(status);
create index if not exists idx_games_group  on games(group_id, id desc);
-- Only ONE unfinished game per group (prevents duplicate lobbies under races)
create unique index if not exists uq_games_one_active_per_group
  on games(group_id) where status in ('LOBBY','DRAFTING','LEAGUE','FINAL');

create table if not exists game_players (
  id            bigint generated always as identity primary key,
  game_id       bigint not null references games(id) on delete cascade,
  user_id       bigint not null references users(id),
  display_name  text   not null,
  draft_done    boolean not null default false,
  joined_at     timestamptz not null default now(),
  unique (game_id, user_id)                       -- no duplicate joins
);
create index if not exists idx_game_players_game on game_players(game_id);
create index if not exists idx_game_players_user on game_players(user_id, id desc);

-- ───────────── drafting ─────────────
-- The five characters offered to a player for a category (kept so a restart
-- shows the same offer and old buttons keep working).
create table if not exists draft_offers (
  id              bigint generated always as identity primary key,
  game_player_id  bigint not null references game_players(id) on delete cascade,
  category        text   not null,
  character_ids   text[] not null,
  created_at      timestamptz not null default now(),
  unique (game_player_id, category)
);

create table if not exists draft_choices (
  id              bigint generated always as identity primary key,
  game_player_id  bigint not null references game_players(id) on delete cascade,
  category        text   not null,
  character_id    text   not null references characters(id),
  auto_picked     boolean not null default false,
  picked_at       timestamptz not null default now(),
  unique (game_player_id, category),              -- one pick per category (no double click)
  unique (game_player_id, character_id)           -- same character can't fill two slots
);
create index if not exists idx_draft_choices_player on draft_choices(game_player_id);

create table if not exists teams (
  id              bigint generated always as identity primary key,
  game_player_id  bigint not null unique references game_players(id) on delete cascade,
  attack_id       text not null references characters(id),
  defense_id      text not null references characters(id),
  tanking_id      text not null references characters(id),
  speed_id        text not null references characters(id),
  healing_id      text not null references characters(id),
  intelligence_id text not null references characters(id),
  locked_at       timestamptz not null default now()
);

-- ───────────── matches ─────────────
create table if not exists matches (
  id            bigint generated always as identity primary key,
  game_id       bigint not null references games(id) on delete cascade,
  stage         text   not null check (stage in ('LEAGUE','FINAL')),
  round_no      smallint not null default 0,
  p1_id         bigint not null references game_players(id),
  p2_id         bigint not null references game_players(id),
  status        text   not null default 'PENDING' check (status in ('PENDING','RUNNING','DONE')),
  p1_score      smallint,
  p2_score      smallint,
  winner_id     bigint references game_players(id),   -- null = draw
  tiebreak_used boolean not null default false,
  tiebreak_p1   numeric(8,3),
  tiebreak_p2   numeric(8,3),
  notified      boolean not null default false,        -- scorecards delivered to DMs
  started_at    timestamptz,
  finished_at   timestamptz,
  check (p1_id <> p2_id),
  unique (game_id, stage, p1_id, p2_id)
);
create index if not exists idx_matches_game on matches(game_id, stage, round_no);
create unique index if not exists uq_matches_one_final on matches(game_id) where stage = 'FINAL';

create table if not exists match_clashes (
  id               bigint generated always as identity primary key,
  match_id         bigint not null references matches(id) on delete cascade,
  clash_no         smallint not null,
  category         text not null,
  p1_character_id  text not null references characters(id),
  p2_character_id  text not null references characters(id),
  p1_rating        smallint not null,
  p2_rating        smallint not null,
  p1_score         numeric(8,3) not null,
  p2_score         numeric(8,3) not null,
  winner_side      smallint not null check (winner_side in (1, 2)),
  unique (match_id, category)
);
create index if not exists idx_match_clashes_match on match_clashes(match_id);

create table if not exists standings (
  id               bigint generated always as identity primary key,
  game_id          bigint not null references games(id) on delete cascade,
  game_player_id   bigint not null references game_players(id) on delete cascade,
  played           integer not null default 0,
  wins             integer not null default 0,
  draws            integer not null default 0,
  losses           integer not null default 0,
  clashes_won      integer not null default 0,
  clashes_lost     integer not null default 0,
  clash_difference integer generated always as (clashes_won - clashes_lost) stored,
  points           integer not null default 0,
  unique (game_id, game_player_id)
);
create index if not exists idx_standings_rank
  on standings(game_id, points desc, clash_difference desc, clashes_won desc);

-- ════════════════ atomic game operations (called via RPC) ════════════════
-- Row locks (FOR UPDATE) make these safe under simultaneous button presses.

create or replace function join_game(p_game_id bigint, p_user_id bigint, p_name text)
returns text language plpgsql as $$
declare g games%rowtype; cnt int;
begin
  select * into g from games where id = p_game_id for update;
  if not found or g.status <> 'LOBBY' then return 'CLOSED'; end if;
  if exists (select 1 from game_players where game_id = p_game_id and user_id = p_user_id) then
    return 'ALREADY';
  end if;
  select count(*) into cnt from game_players where game_id = p_game_id;
  if cnt >= g.max_players then return 'FULL'; end if;
  insert into game_players (game_id, user_id, display_name) values (p_game_id, p_user_id, p_name);
  return 'OK';
end $$;

create or replace function leave_game(p_game_id bigint, p_user_id bigint)
returns text language plpgsql as $$
declare g games%rowtype;
begin
  select * into g from games where id = p_game_id for update;
  if not found or g.status <> 'LOBBY' then return 'CLOSED'; end if;
  delete from game_players where game_id = p_game_id and user_id = p_user_id;
  if found then return 'OK'; end if;
  return 'NOT_IN';
end $$;

-- LOBBY -> DRAFTING (exactly one caller wins; others get false)
create or replace function begin_draft(p_game_id bigint, p_deadline timestamptz)
returns boolean language plpgsql as $$
declare g games%rowtype; cnt int;
begin
  select * into g from games where id = p_game_id for update;
  if not found or g.status <> 'LOBBY' then return false; end if;
  select count(*) into cnt from game_players where game_id = p_game_id;
  if cnt < g.min_players then return false; end if;
  update games set status = 'DRAFTING', started_at = now(), draft_deadline = p_deadline
   where id = p_game_id;
  return true;
end $$;

-- DRAFTING -> LEAGUE once every player is done (exactly one caller wins)
create or replace function begin_league(p_game_id bigint)
returns boolean language plpgsql as $$
declare g games%rowtype;
begin
  select * into g from games where id = p_game_id for update;
  if not found or g.status <> 'DRAFTING' then return false; end if;
  if exists (select 1 from game_players where game_id = p_game_id and not draft_done) then
    return false;
  end if;
  update games set status = 'LEAGUE' where id = p_game_id;
  insert into standings (game_id, game_player_id)
    select game_id, id from game_players where game_id = p_game_id
  on conflict do nothing;
  return true;
end $$;

-- LEAGUE -> FINAL; creates the single final match. Idempotent for recovery.
create or replace function begin_final(p_game_id bigint, p_p1 bigint, p_p2 bigint)
returns jsonb language plpgsql as $$
declare g games%rowtype; mid bigint;
begin
  select * into g from games where id = p_game_id for update;
  if not found then return null; end if;
  if g.status = 'FINAL' then
    select id into mid from matches where game_id = p_game_id and stage = 'FINAL';
    return jsonb_build_object('match_id', mid, 'created', false);
  end if;
  if g.status <> 'LEAGUE' then return null; end if;
  if exists (select 1 from matches where game_id = p_game_id and stage = 'LEAGUE' and status <> 'DONE') then
    return null;
  end if;
  update games set status = 'FINAL' where id = p_game_id;
  insert into matches (game_id, stage, round_no, p1_id, p2_id)
    values (p_game_id, 'FINAL', 0, p_p1, p_p2) returning id into mid;
  return jsonb_build_object('match_id', mid, 'created', true);
end $$;

-- Persist a finished match + award points EXACTLY once.
-- p_winner_side: 1 / 2 / 0 (draw, league only).
create or replace function finish_match(
  p_match_id bigint, p_clashes jsonb, p_winner_side int,
  p_tb1 numeric default null, p_tb2 numeric default null
) returns boolean language plpgsql as $$
declare m matches%rowtype; s1 int; s2 int; wid bigint;
begin
  select * into m from matches where id = p_match_id for update;
  if not found or m.status = 'DONE' then return false; end if;
  if m.stage = 'FINAL' and p_winner_side not in (1, 2) then
    raise exception 'A final needs a winner';
  end if;

  insert into match_clashes
    (match_id, clash_no, category, p1_character_id, p2_character_id,
     p1_rating, p2_rating, p1_score, p2_score, winner_side)
  select p_match_id, x.clash_no, x.category, x.p1_character_id, x.p2_character_id,
         x.p1_rating, x.p2_rating, x.p1_score, x.p2_score, x.winner_side
    from jsonb_to_recordset(p_clashes) as x(
      clash_no int, category text, p1_character_id text, p2_character_id text,
      p1_rating int, p2_rating int, p1_score numeric, p2_score numeric, winner_side int);

  select count(*) filter (where winner_side = 1), count(*) filter (where winner_side = 2)
    into s1, s2 from match_clashes where match_id = p_match_id;

  wid := case p_winner_side when 1 then m.p1_id when 2 then m.p2_id else null end;

  update matches set status = 'DONE', p1_score = s1, p2_score = s2, winner_id = wid,
         tiebreak_used = (p_tb1 is not null), tiebreak_p1 = p_tb1, tiebreak_p2 = p_tb2,
         finished_at = now()
   where id = p_match_id;

  if m.stage = 'LEAGUE' then
    update standings set
      played = played + 1,
      wins   = wins   + (case when p_winner_side = 1 then 1 else 0 end),
      draws  = draws  + (case when p_winner_side = 0 then 1 else 0 end),
      losses = losses + (case when p_winner_side = 2 then 1 else 0 end),
      clashes_won  = clashes_won  + s1,
      clashes_lost = clashes_lost + s2,
      points = points + (case p_winner_side when 1 then 3 when 0 then 1 else 0 end)
     where game_player_id = m.p1_id;
    update standings set
      played = played + 1,
      wins   = wins   + (case when p_winner_side = 2 then 1 else 0 end),
      draws  = draws  + (case when p_winner_side = 0 then 1 else 0 end),
      losses = losses + (case when p_winner_side = 1 then 1 else 0 end),
      clashes_won  = clashes_won  + s2,
      clashes_lost = clashes_lost + s1,
      points = points + (case p_winner_side when 2 then 3 when 0 then 1 else 0 end)
     where game_player_id = m.p2_id;
  else
    update games set status = 'COMPLETED', completed_at = now(),
           champion_user_id = (select user_id from game_players where id = wid)
     where id = m.game_id and status = 'FINAL';
  end if;
  return true;
end $$;

-- ════════════════ security: RLS on, RPCs only for service_role ════════════════
alter table users                enable row level security;
alter table groups               enable row level security;
alter table characters           enable row level security;
alter table character_categories enable row level security;
alter table games                enable row level security;
alter table game_players         enable row level security;
alter table draft_offers         enable row level security;
alter table draft_choices        enable row level security;
alter table teams                enable row level security;
alter table matches              enable row level security;
alter table match_clashes        enable row level security;
alter table standings            enable row level security;

revoke all on function join_game(bigint, bigint, text)            from public, anon, authenticated;
revoke all on function leave_game(bigint, bigint)                 from public, anon, authenticated;
revoke all on function begin_draft(bigint, timestamptz)           from public, anon, authenticated;
revoke all on function begin_league(bigint)                       from public, anon, authenticated;
revoke all on function begin_final(bigint, bigint, bigint)        from public, anon, authenticated;
revoke all on function finish_match(bigint, jsonb, int, numeric, numeric) from public, anon, authenticated;
grant execute on function join_game(bigint, bigint, text)            to service_role;
grant execute on function leave_game(bigint, bigint)                 to service_role;
grant execute on function begin_draft(bigint, timestamptz)           to service_role;
grant execute on function begin_league(bigint)                       to service_role;
grant execute on function begin_final(bigint, bigint, bigint)        to service_role;
grant execute on function finish_match(bigint, jsonb, int, numeric, numeric) to service_role;
