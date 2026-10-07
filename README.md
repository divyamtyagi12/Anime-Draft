# 🎴 ANIME DRAFT — Telegram multiplayer draft-tournament bot

Lobby in a **group**, drafting and battles in each player's **DM**.
Franchises: **Re:ZERO · Black Clover · Death Note · Ben 10** (81 characters, 6 categories). Ben 10 includes the main cast, villains and Omnitrix aliens as draftable cards.

Python 3.12 · python-telegram-bot (async) · Supabase/PostgreSQL · long polling (webhook-ready).

## Game flow
1. `/start` in a group → lobby (⚔️ JOIN / 🚪 LEAVE / 🔥 FORCE START). 3–8 players. Joining requires having pressed Start in the bot's DM.
2. FORCE START (host/admin) → every player is DM-checked, the lobby locks, and each player drafts 6 characters (5 random offers per category). Progress (✅/⏳, never characters) is shown in the group.
3. Round-robin league: each match = 6 clashes, fought privately with live-edited DM cards and a scorecard to both players. The group only gets the standings table (edited in place after each round).
4. Top two → Grand Final (4+ clashes wins; 3-3 → 🔥 Ultimate Tiebreaker on whole-team strength). Champion announced in the group.

Scoring: win 3 / draw 1 / loss 0. Ranking: points → clash difference → clashes won → head-to-head → deterministic random.

## Project layout
```
bot.py            entry point (polling / webhook, recovery, commands)
config.py         env-based settings (no secrets in code)
database/         schema.sql (tables + atomic RPCs), seed_characters.sql, client.py, seed.py
repositories/     all Supabase queries
models/           Character, CharacterCatalog
game/             categories, battle engine, draft offers, tournament/ranking (pure logic)
services/         lobby, draft, match, league, final, table, recovery, images, telegram I/O
handlers/         Telegram commands & callbacks
utils/            messages (all text), logging with secret redaction
data/             characters.py (stats), image_urls.json (artwork)
tests/            unit tests for engine/data/messages
```

## 1. Supabase setup
1. Create a project at supabase.com.
2. **SQL Editor → paste `database/schema.sql` → Run.** (Re-runnable.)
3. Characters are upserted automatically on bot start (`AUTO_SEED=true`). Alternatives: run `database/seed_characters.sql` in the SQL Editor, or `python -m scripts.seed_characters`.
4. **Project Settings → API**: copy the *Project URL* and the **`service_role` key**.
   - `SUPABASE_KEY` must be the **service_role** key. RLS is enabled with no policies, so the anon key cannot work (by design — it also can't read your data).
   - It is a server-side secret: never put it in a frontend, a Telegram message, or Git.

## 2. Telegram / BotFather setup
1. `@BotFather` → `/newbot` → copy the token.
2. `/setjoingroups` → Enable. (Privacy mode can stay ON; the bot only needs commands and buttons.)
3. Commands (the bot also sets these itself on startup; `/setcommands` is optional):
```
start - Create a game (group) / register (DM)
help - Show commands
rules - How the game works
team - Show your drafted team (DM)
draft - Resend your current draft prompt (DM)
table - League standings
status - Current game status
cancelgame - Cancel the game (host/admin)
```
4. Add the bot to your group. Every player must open the bot privately and press **Start** once.

## 3. Run locally
```bash
python3.12 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # fill TELEGRAM_BOT_TOKEN, SUPABASE_URL, SUPABASE_KEY
python bot.py
```
Optional env vars are documented in `.env.example` (MIN_PLAYERS, MAX_PLAYERS, CLASH_DELAY, DRAFT_TIMEOUT_MINUTES, OWNER_IDS…).

## 4. Testing
```bash
pip install -r requirements-dev.txt && pytest          # or: python -m tests.run_all (no pytest needed)
```
Unit tests cover round-robin generation, ranking/tiebreaks, battle fairness, draft offers (incl. worst-case pool exhaustion), data validation, and message rendering.

Manual end-to-end test: you need 3 Telegram accounts (or set `MIN_PLAYERS=2` and use 2). Suggested checklist: join twice (rejected), join without DM start (prompted), non-host FORCE START (rejected), double-tap a draft button, kill the bot mid-draft / mid-league and restart (it resumes), `/cancelgame`, `/table`, `/status`, `/team`. Set `CLASH_DELAY=0.5` for faster runs.

## 5. Artwork
No artwork ships with the bot (I can't verify image rights/URLs). Put direct image URLs in `data/image_urls.json` (`{"reinhard": "https://…"}`), or reply to a photo with `/setimage reinhard` (user ids in `OWNER_IDS` only). After the first successful send the Telegram `file_id` is cached in Supabase. The draft shows an album only when all five offered characters have artwork; otherwise it's text-only. Everything image-related lives in `services/images.py`.

## 6. Tuning characters
Edit `data/characters.py` (ratings 1–100, eligible categories, abilities) and restart; stats are re-synced. Ratings are judgement calls — Death Note characters are Intelligence-only on purpose. Battle constants (±5 % clash randomness, tiebreak formula) are at the top of `game/battle.py`.

## Reliability design
- **Everything important lives in Supabase**; a restart resumes drafts (prompts re-sent if lost), the league (orphaned matches reset, undelivered scorecards sent) and unannounced finals.
- **Atomic transitions** via Postgres functions with row locks: join/leave, LOBBY→DRAFTING, DRAFTING→LEAGUE, LEAGUE→FINAL, and `finish_match` (points awarded once). Unique constraints stop duplicate joins, double picks, duplicate finals, and a second lobby per group. Matches are claimed `PENDING→RUNNING` with a conditional update.
- Every callback is answered; stale buttons get a friendly message; Telegram rate limits (`AIORateLimiter` + RetryAfter handling), blocked users, deleted messages and Supabase network failures are handled per-player so one failure never crashes the bot.
- Idle drafters are auto-picked after `DRAFT_TIMEOUT_MINUTES`.
- Logs redact the token/keys (and httpx URL logging is silenced).

## Deployment notes
- **Run exactly one instance** (the league runner is an in-process task guarded by DB state; two instances would fight over polling anyway).
- Webhook: set `RUN_MODE=webhook`, `WEBHOOK_URL=https://your.domain`, a non-guessable `WEBHOOK_PATH`, a random `WEBHOOK_SECRET`, and put TLS in front (reverse proxy) forwarding to `WEBHOOK_PORT`.
- Docker sketch: `FROM python:3.12-slim`, `COPY . /app`, `pip install -r requirements.txt`, `CMD ["python","bot.py"]`; pass secrets as env vars (Railway/Fly/Render/systemd) — never bake `.env` into an image.
- Back up the Supabase project as usual; game history stays in `games/matches/match_clashes`.
