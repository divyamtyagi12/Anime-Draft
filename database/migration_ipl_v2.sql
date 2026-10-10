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
