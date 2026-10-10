-- ══════════════════════════════════════════════════════════════════════
-- IPL DRAFT MIGRATION V2
-- 1. Reduce system teams: formula updated to (humans + 5) * 11
-- 2. Player eligibility: active/retired in 2020-2026 squads, AB de Villiers & Gayle eligible
-- 3. Batting order selection: schema and RPC functions
-- 4. Match simulation: squads ordered by confirmed batting order
-- ══════════════════════════════════════════════════════════════════════

-- 1. Schema Additions
alter table if exists ipl_tournament_teams 
  add column if not exists batting_order_confirmed boolean not null default false;

alter table if exists ipl_team_rosters 
  add column if not exists batting_order smallint check (batting_order between 1 and 11);

-- 2. Player Eligibility (2020-2026)
update ipl_players 
   set is_eligible = false 
 where last_ipl_season is not null 
   and last_ipl_season < 2020;

update ipl_players 
   set is_eligible = true, last_ipl_season = 2021 
 where slug in ('ab-de-villiers', 'chris-gayle') 
    or display_name in ('AB de Villiers', 'Chris Gayle');

-- 3. Required Pool Calculation (5 system teams)
create or replace function ipl_required_pool(p_humans int, p_margin int default 20) returns int
language sql immutable as $$ select greatest((p_humans + 5) * 11, 21 * p_humans) + p_margin $$;

-- 4. Team by ID Helper
create or replace function ipl_team_by_id(p_team_id bigint) returns jsonb
language sql stable security definer set search_path = public, ipl_private as $$
  select jsonb_build_object(
    'id', tm.id,
    'tournament_id', tm.tournament_id,
    'team_no', tm.team_no,
    'kind', tm.kind,
    'user_id', tm.user_id,
    'name', tm.name,
    'short_name', tm.short_name,
    'owner_name', tm.owner_name,
    'squad_complete', tm.squad_complete,
    'auto_draft', tm.auto_draft,
    'batting_order_confirmed', coalesce(tm.batting_order_confirmed, false)
  )
  from ipl_tournament_teams tm
  where tm.id = p_team_id;
$$;

-- 5. Batting Order State
create or replace function ipl_batting_order_state(p_team_id bigint) returns jsonb
language plpgsql stable security definer set search_path = public, ipl_private as $$
declare
  v_players jsonb;
  v_ordered jsonb;
  v_remaining jsonb;
begin
  select coalesce(jsonb_agg(
    jsonb_build_object(
      'id', p.id,
      'name', p.display_name,
      'role', p.role,
      'slot', r.slot,
      'batting_order', r.batting_order
    ) order by r.slot
  ), '[]'::jsonb)
  into v_players
  from ipl_team_rosters r
  join ipl_players p on p.id = r.player_id
  where r.team_id = p_team_id;

  select coalesce(jsonb_agg(
    jsonb_build_object(
      'id', p.id,
      'name', p.display_name,
      'role', p.role,
      'slot', r.slot,
      'batting_order', r.batting_order
    ) order by r.batting_order
  ), '[]'::jsonb)
  into v_ordered
  from ipl_team_rosters r
  join ipl_players p on p.id = r.player_id
  where r.team_id = p_team_id and r.batting_order is not null;

  select coalesce(jsonb_agg(
    jsonb_build_object(
      'pos', r.slot,
      'player', jsonb_build_object('id', p.id, 'name', p.display_name, 'role', p.role, 'slot', r.slot)
    ) order by r.slot
  ), '[]'::jsonb)
  into v_remaining
  from ipl_team_rosters r
  join ipl_players p on p.id = r.player_id
  where r.team_id = p_team_id and r.batting_order is null;

  return jsonb_build_object(
    'players', v_players,
    'ordered', v_ordered,
    'remaining', v_remaining
  );
end $$;

-- 6. Batting Order Pick
create or replace function ipl_batting_order_pick(p_team_id bigint, p_pos smallint) returns jsonb
language plpgsql security definer set search_path = public, ipl_private as $$
declare
  v_curr smallint;
  v_next smallint;
begin
  select batting_order into v_curr from ipl_team_rosters where team_id = p_team_id and slot = p_pos;
  if not found then
    return jsonb_build_object('status', 'NOT_FOUND');
  end if;
  if v_curr is not null then
    return jsonb_build_object('status', 'ALREADY');
  end if;

  select coalesce(max(batting_order), 0) + 1 into v_next
  from ipl_team_rosters
  where team_id = p_team_id;

  if v_next > 11 then
    return jsonb_build_object('status', 'FULL');
  end if;

  update ipl_team_rosters
     set batting_order = v_next
   where team_id = p_team_id and slot = p_pos;

  if v_next = 11 then
    return jsonb_build_object('status', 'LAST', 'order', v_next);
  end if;

  return jsonb_build_object('status', 'OK', 'order', v_next);
end $$;

-- 7. Batting Order Undo
create or replace function ipl_batting_order_undo(p_team_id bigint) returns void
language plpgsql security definer set search_path = public, ipl_private as $$
declare
  v_max smallint;
begin
  select max(batting_order) into v_max from ipl_team_rosters where team_id = p_team_id;
  if v_max is not null then
    update ipl_team_rosters set batting_order = null where team_id = p_team_id and batting_order = v_max;
  end if;
end $$;

-- 8. Batting Order Reset
create or replace function ipl_batting_order_reset(p_team_id bigint) returns void
language sql security definer set search_path = public, ipl_private as $$
  update ipl_team_rosters set batting_order = null where team_id = p_team_id;
  update ipl_tournament_teams set batting_order_confirmed = false where id = p_team_id;
$$;

-- 9. Batting Order Confirm
create or replace function ipl_batting_order_confirm(p_team_id bigint) returns jsonb
language plpgsql security definer set search_path = public, ipl_private as $$
declare
  v_cnt int;
begin
  select count(*) into v_cnt from ipl_team_rosters where team_id = p_team_id and batting_order is not null;
  if v_cnt < 11 then
    return jsonb_build_object('status', 'INCOMPLETE', 'count', v_cnt);
  end if;
  update ipl_tournament_teams set batting_order_confirmed = true where id = p_team_id;
  return jsonb_build_object('status', 'OK');
end $$;

-- 10. Batting Order Auto Assign (Ratings Sort)
create or replace function ipl_batting_order_auto_assign(p_team_id bigint) returns void
language plpgsql security definer set search_path = public, ipl_private as $$
begin
  with ranked as (
    select r.id, row_number() over (
      order by coalesce(tr.batting_rating, 50) * 0.7 + coalesce(tr.power_hitting, 50) * 0.3 desc, r.slot
    ) as rn
    from ipl_team_rosters r
    left join ipl_private.ipl_tournament_ratings tr
           on tr.tournament_id = r.tournament_id and tr.player_id = r.player_id
    where r.team_id = p_team_id
  )
  update ipl_team_rosters ro
     set batting_order = rk.rn
    from ranked rk
   where ro.id = rk.id;

  update ipl_tournament_teams set batting_order_confirmed = true where id = p_team_id;
end $$;

-- 11. Batting Order Set Explicit Order
create or replace function ipl_batting_order_set_order(p_team_id bigint, p_player_ids text[]) returns void
language plpgsql security definer set search_path = public, ipl_private as $$
declare
  i int;
begin
  for i in 1 .. array_length(p_player_ids, 1) loop
    update ipl_team_rosters
       set batting_order = i
     where team_id = p_team_id and player_id = (p_player_ids[i])::uuid;
  end loop;
  update ipl_tournament_teams set batting_order_confirmed = true where id = p_team_id;
end $$;

-- 12. Teams Pending Batting Order
create or replace function ipl_teams_pending_batting_order(p_tid bigint) returns jsonb
language sql stable security definer set search_path = public, ipl_private as $$
  select coalesce(jsonb_agg(ipl_team_json(tm)), '[]'::jsonb)
    from ipl_tournament_teams tm
   where tm.tournament_id = p_tid
     and tm.kind = 'HUMAN'
     and tm.squad_complete = true
     and coalesce(tm.batting_order_confirmed, false) = false;
$$;

-- 13. Engine Squads with Confirmed Lineup Order
create or replace function ipl_engine_squads(p_tid bigint) returns jsonb
language sql stable security definer set search_path = public, ipl_private as $$
  select coalesce(jsonb_agg(jsonb_build_object(
      'team_id', tm.id, 'team_no', tm.team_no, 'name', tm.name, 'short_name', tm.short_name, 'kind', tm.kind,
      'players', (select coalesce(jsonb_agg(jsonb_build_object(
                    'id', p.id, 'name', p.display_name, 'role', p.role, 'bowling_type', p.bowling_type,
                    'batting_style', p.batting_style, 'slot', r.slot,
                    'batting_order', r.batting_order,
                    'ratings', to_jsonb(tr) - 'tournament_id' - 'player_id') order by coalesce(r.batting_order, r.slot)), '[]'::jsonb)
                    from ipl_team_rosters r
                    join ipl_players p on p.id = r.player_id
                    left join ipl_private.ipl_tournament_ratings tr
                           on tr.tournament_id = r.tournament_id and tr.player_id = r.player_id
                   where r.team_id = tm.id)) order by tm.team_no), '[]'::jsonb)
    from ipl_tournament_teams tm where tm.tournament_id = p_tid
$$;

-- 14. State Transitions: Flexible Transitions Between Drafting, System Generation, and Fixtures
create or replace function ipl_valid_transition(p_old text, p_new text) returns boolean
language sql immutable as $$
  select case
    when p_old = p_new then true
    when p_old in ('COMPLETED','CANCELLED') then false
    when p_new = 'CANCELLED' then true
    when p_new = 'FAILED_RECOVERABLE' then p_old <> 'LOBBY'
    when p_old = 'FAILED_RECOVERABLE' then p_new in ('DRAFTING','SYSTEM_TEAM_GENERATION','FIXTURE_GENERATION',
         'LEAGUE_RUNNING','LEAGUE_COMPLETED','PLAYOFF_ELIMINATOR','PLAYOFF_QUALIFIER_1',
         'PLAYOFF_QUALIFIER_2','PLAYOFF_FINAL')
    when p_old = 'LOBBY'                  then p_new in ('DRAFTING', 'SYSTEM_TEAM_GENERATION')
    when p_old = 'SYSTEM_TEAM_GENERATION' then p_new in ('DRAFTING', 'FIXTURE_GENERATION')
    when p_old = 'DRAFTING'               then p_new in ('SYSTEM_TEAM_GENERATION', 'FIXTURE_GENERATION')
    when p_old = 'FIXTURE_GENERATION'     then p_new = 'LEAGUE_RUNNING'
    when p_old = 'LEAGUE_RUNNING'         then p_new = 'LEAGUE_COMPLETED'
    when p_old = 'LEAGUE_COMPLETED'       then p_new = 'PLAYOFF_ELIMINATOR'
    when p_old = 'PLAYOFF_ELIMINATOR'     then p_new = 'PLAYOFF_QUALIFIER_1'
    when p_old = 'PLAYOFF_QUALIFIER_1'    then p_new = 'PLAYOFF_QUALIFIER_2'
    when p_old = 'PLAYOFF_QUALIFIER_2'    then p_new = 'PLAYOFF_FINAL'
    when p_old = 'PLAYOFF_FINAL'          then p_new = 'COMPLETED'
    else false end
$$;

-- 15. Create Fixtures: Updated for 5 System Teams (7 to 13 Total Teams)
create or replace function ipl_create_fixtures(p_tid bigint, p_fixtures jsonb) returns jsonb
language plpgsql security definer set search_path = public, ipl_private as $$
declare t ipl_tournaments%rowtype; n int; expected int; cnt int; f jsonb;
begin
  select * into t from ipl_tournaments where id = p_tid for update;
  if not found then return jsonb_build_object('status', 'NOT_FOUND'); end if;
  if t.state = 'LEAGUE_RUNNING' or exists (select 1 from ipl_fixtures where tournament_id = p_tid) then
    return jsonb_build_object('status', 'OK', 'already', true);
  end if;
  if t.state <> 'FIXTURE_GENERATION' then return jsonb_build_object('status', 'BAD_STATE', 'state', t.state); end if;
  select count(*) into n from ipl_tournament_teams where tournament_id = p_tid;
  if n < 7 or n > 13 then return jsonb_build_object('status', 'BAD_TEAM_COUNT', 'teams', n); end if;
  expected := n * (n - 1);
  cnt := jsonb_array_length(p_fixtures);
  if cnt <> expected then return jsonb_build_object('status', 'BAD_FIXTURE_COUNT', 'have', cnt, 'need', expected); end if;
  for f in select * from jsonb_array_elements(p_fixtures) loop
    insert into ipl_fixtures (tournament_id, stage, match_no, matchday, leg, home_team_id, away_team_id)
    values (p_tid, 'LEAGUE', (f->>'match_no')::int, (f->>'matchday')::int, (f->>'leg')::smallint,
            (f->>'home')::bigint, (f->>'away')::bigint);
  end loop;
  if (select count(distinct (least(home_team_id, away_team_id), greatest(home_team_id, away_team_id)))
        from ipl_fixtures where tournament_id = p_tid) <> n * (n - 1) / 2 then
    raise exception 'fixture list does not cover every pair';
  end if;
  insert into ipl_standings (tournament_id, team_id)
    select p_tid, id from ipl_tournament_teams where tournament_id = p_tid on conflict do nothing;
  update ipl_tournaments set state = 'LEAGUE_RUNNING', league_started_at = now() where id = p_tid;
  return jsonb_build_object('status', 'OK', 'fixtures', cnt, 'teams', n);
end $$;

-- 16. System Teams Generation (Allow During DRAFTING or SYSTEM_TEAM_GENERATION)
create or replace function ipl_begin_system_teams(p_tid bigint, p_franchises jsonb) returns jsonb
language plpgsql security definer set search_path = public, ipl_private as $$
declare t ipl_tournaments%rowtype; h int; f jsonb; i int := 0;
begin
  select * into t from ipl_tournaments where id = p_tid for update;
  if not found then return jsonb_build_object('status', 'NOT_FOUND'); end if;
  if t.state not in ('DRAFTING', 'SYSTEM_TEAM_GENERATION') then return jsonb_build_object('status', 'BAD_STATE', 'state', t.state); end if;
  select count(*) into h from ipl_tournament_teams where tournament_id = p_tid and kind = 'HUMAN';
  for f in select * from jsonb_array_elements(p_franchises) loop
    i := i + 1;
    insert into ipl_tournament_teams (tournament_id, team_no, kind, franchise_code, name, short_name)
    values (p_tid, h + i, 'SYSTEM', f->>'code', f->>'name', f->>'code')
    on conflict do nothing;
  end loop;
  return jsonb_build_object('status', 'OK', 'teams', i);
end $$;

-- 17. System Team Offers and Picks (Allow During DRAFTING or SYSTEM_TEAM_GENERATION)
create or replace function ipl_open_offer(p_team_id bigint, p_force_roles jsonb default null)
returns jsonb language plpgsql security definer set search_path = public, ipl_private as $$
declare tm ipl_tournament_teams%rowtype; t ipl_tournaments%rowtype; o ipl_draft_offers%rowtype;
        n int; ids uuid[]; extra uuid; dl timestamptz; oid bigint;
begin
  select * into tm from ipl_tournament_teams where id = p_team_id;
  if not found then return jsonb_build_object('status', 'NO_TEAM'); end if;
  select * into t from ipl_tournaments where id = tm.tournament_id for update;
  if tm.kind = 'HUMAN' and t.state <> 'DRAFTING' then return jsonb_build_object('status', 'CLOSED'); end if;
  if tm.kind = 'SYSTEM' and t.state not in ('DRAFTING', 'SYSTEM_TEAM_GENERATION') then return jsonb_build_object('status', 'CLOSED'); end if;

  select * into o from ipl_draft_offers where team_id = p_team_id and status = 'OPEN';
  if found then
    return ipl_offer_json(o.id) || jsonb_build_object('status', 'OPEN', 'picks_done', o.round_no - 1);
  end if;

  select count(*) into n from ipl_draft_picks where team_id = p_team_id;
  if n >= 11 then return jsonb_build_object('status', 'DONE', 'picks_done', n); end if;

  select array_agg(id) into ids from (
    select pl.player_id as id
      from ipl_tournament_pool pl
     where pl.tournament_id = t.id
       and not exists (select 1 from ipl_team_rosters r where r.tournament_id = t.id and r.player_id = pl.player_id)
       and not exists (select 1 from ipl_player_reservations x where x.tournament_id = t.id and x.player_id = pl.player_id)
     order by random() limit 11) s;
  if ids is null or cardinality(ids) < 11 then
    return jsonb_build_object('status', 'POOL_EXHAUSTED', 'available', coalesce(cardinality(ids), 0));
  end if;

  if p_force_roles is not null and tm.kind = 'SYSTEM' and not exists (
       select 1 from ipl_players p where p.id = any(ids) and p.role in (select jsonb_array_elements_text(p_force_roles))) then
    select pl.player_id into extra
      from ipl_tournament_pool pl join ipl_players p on p.id = pl.player_id
     where pl.tournament_id = t.id and p.role in (select jsonb_array_elements_text(p_force_roles))
       and not exists (select 1 from ipl_team_rosters r where r.tournament_id = t.id and r.player_id = pl.player_id)
       and not exists (select 1 from ipl_player_reservations x where x.tournament_id = t.id and x.player_id = pl.player_id)
     order by random() limit 1;
    if extra is not null then ids[11] := extra; end if;
  end if;

  dl := now() + make_interval(secs => t.draft_seconds);
  insert into ipl_draft_offers (tournament_id, team_id, round_no, deadline_at)
  values (t.id, p_team_id, n + 1, dl) returning id into oid;
  insert into ipl_draft_offer_candidates (offer_id, position, player_id)
    select oid, row_number() over (order by random()), x from unnest(ids) x;
  insert into ipl_player_reservations (tournament_id, player_id, team_id, offer_id, expires_at)
    select t.id, x, p_team_id, oid, dl + interval '30 seconds' from unnest(ids) x;
  return ipl_offer_json(oid) || jsonb_build_object('status', 'OPEN', 'picks_done', n);
end $$;

-- 18. Complete System Teams
create or replace function ipl_complete_system_teams(p_tid bigint) returns jsonb
language plpgsql security definer set search_path = public, ipl_private as $$
declare t ipl_tournaments%rowtype; bad int;
begin
  select * into t from ipl_tournaments where id = p_tid for update;
  if not found then return jsonb_build_object('status', 'NOT_FOUND'); end if;
  if t.state = 'FIXTURE_GENERATION' then return jsonb_build_object('status', 'OK', 'already', true); end if;
  if t.state not in ('DRAFTING', 'SYSTEM_TEAM_GENERATION') then return jsonb_build_object('status', 'BAD_STATE', 'state', t.state); end if;
  select count(*) into bad from ipl_tournament_teams tm
   where tm.tournament_id = p_tid and (select count(*) from ipl_team_rosters r where r.team_id = tm.id) <> 11;
  if bad > 0 then return jsonb_build_object('status', 'INCOMPLETE', 'teams', bad); end if;
  update ipl_tournament_teams set squad_complete = true where tournament_id = p_tid and not squad_complete;
  if t.state = 'SYSTEM_TEAM_GENERATION' then
    update ipl_tournaments set state = 'FIXTURE_GENERATION' where id = p_tid;
  end if;
  return jsonb_build_object('status', 'OK');
end $$;
