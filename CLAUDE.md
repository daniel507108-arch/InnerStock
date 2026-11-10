# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

InnerStock is a trading-journal and portfolio app. Users log trades (or sync them from Wealthsimple through SnapTrade), and every manual trade needs a written thesis, a conviction score and a review date. The app shows holdings and P&L from live yfinance prices, brings trades back for grading when their review date arrives, flags behaviour patterns such as FOMO, and offers a Claude-backed advisor chat plus per-ticker news sentiment and bull/bear summaries.

- `Backend/`: FastAPI + SQLAlchemy + SQLite (`innerstock.db`)
- `Frontend/`: React 19 + Vite, plain JS/JSX (no TypeScript), Recharts for charts

## Commands

Backend (run from `Backend/`, with the venv in `Backend/venv` activated):
```
pip install -r requirements.txt
python init_db.py                 # apply all Alembic migrations (= alembic upgrade head)
uvicorn main:app --reload         # serves on http://127.0.0.1:8000, Swagger at /docs
```
Copy `Backend/.env.example` to `Backend/.env`. `ANTHROPIC_API_KEY` and `JWT_SECRET_KEY` are required; `DATABASE_URL` (defaults to local SQLite) and the `SNAPTRADE_*` keys are optional.

Schema changes go through Alembic (run from `Backend/`):
```
alembic revision --autogenerate -m "describe change"   # then review/edit the generated file
alembic upgrade head
alembic check                                        # models and migrations agree?
```
`env.py` uses the app's own engine (`database.DATABASE_URL`) and `render_as_batch=True` because SQLite can't ALTER most things in place. Migration `0001` is a baseline that also upgrades pre-Alembic databases in place (creates missing tables, adds missing columns), so existing local DBs never need deleting.

Frontend (run from `Frontend/`):
```
npm install
npm run dev       # http://localhost:5173
npm run build
npm run lint
```

Backend tests (run from `Backend/`):
```
pip install -r requirements-dev.txt
python -m pytest                                   # whole suite
python -m pytest tests/test_holdings.py -k rebuy   # single file / test
```
Tests use a fresh in-memory SQLite DB per test and stub out yfinance (`prices` fixture replaces `get_or_fetch_price`) and the FOMO check; the `history` fixture fakes daily closes for the grading scorecard (`grading.fetch_daily_closes`, keyed by ticker, missing ticker = no data). `conftest.py` sets fake `JWT_SECRET_KEY`/`ANTHROPIC_API_KEY` and blanks the `SNAPTRADE_*` vars so no real API can be hit; brokerage tests use the `fake_snaptrade` fixture in `test_snaptrade_sync.py`. `test_migrations.py` fails if `models.py` changes without a matching migration. Use the `alice`/`bob` fixtures and `log_trade()` helper from `tests/conftest.py`. When adding a user-scoped route, add it to the isolation tests in `test_data_isolation.py`.

CI (`.github/workflows/ci.yml`, runs on PRs to `main`) runs `py_compile` and pytest with Python 3.14 and `npm run build` with Node 20.

## Architecture

### Backend
- **Most logic lives in `Backend/main.py`**: nearly every route, the Pydantic request models, the price cache and the Claude calls. `models.py` holds the ORM tables, `auth.py` handles bcrypt and JWT (HS256, 7-day tokens), `database.py` builds the engine from `DATABASE_URL`, and `deps.py` holds the shared `get_db`/`get_current_user` dependencies. New route groups go in their own module with an `APIRouter` included from `main.py` (e.g. `brokerage.py`), importing dependencies from `deps.py` rather than `main`.
- **Imports are flat** (`from models import ...`), so the backend has to be run from inside `Backend/`.
- **Auth**: protected routes take `current_user: User = Depends(get_current_user)` (from `deps.py`), which uses an `HTTPBearer` token. Any route touching user data must filter by `current_user.id`. Public routes such as `/stock/{ticker}`, `/sentiment/{ticker}` and `/bullbear/{ticker}` take no user.
- **Migrations**: every model change needs an Alembic migration in `migrations/versions/` (see Commands). Each developer keeps their own gitignored `innerstock.db`, upgraded with `python init_db.py`.
- **Price data**: always go through `get_or_fetch_price(ticker, db)` rather than calling yfinance directly. It reads the `PriceCache` table (TTL `PRICE_CACHE_TTL_SECONDS` = 45s), falls back to stale cache when yfinance fails, and uses `regularMarketPrice` when `currentPrice` is missing (ETFs such as `VFV.TO`). Tickers are upper-cased.
- **Canadian tickers**: `.TO` (TSX) tickers are first-class. Trade times are treated as US/Eastern. Sentiment tells TSX ETFs apart from CDRs using yfinance `quoteType`; never guess a US ticker by stripping `.TO` (see the comments in `get_sentiment`).
- **Claude usage**: one module-level `claude_client`.
  - Sentiment and bull/bear use `claude-sonnet-4-6`. Sentiment results are cached in `SentimentCache` for 60 minutes, and ETFs with no news get a permanent `"unavailable"` marker.
  - `/chat` uses `claude-haiku-4-5-20251001`. Every call rebuilds a system prompt with `build_advisor_context` (profile, holdings, stats), sends the last 40 `ChatMessage` rows, and stores each user message before calling Claude.
  - Each call prints its token usage and estimated cost to the terminal. If you change models, update the pricing constants.
- **Holdings math** (`/holdings`): processes trades in date order with moving-average cost basis (ACB). A separate tracker for today's buys keeps day gain/loss correct for shares bought today.
- **Trades**: manual trades go through `POST /trades` (`TradeCreate` requires a thesis, conviction, review date and `trade_time`). `Trade.source` is `manual`, `csv` (legacy rows from a removed CSV import) or `snaptrade`. Synced trades have no thesis, so `/trades/incomplete` lists them. Grading happens through `PATCH /trades/{id}/outcome`.
- **Grading** (`grading.py`): `GET /thesis-reviews/{id}/scorecard` gives a due trade's evidence - its return and the S&P 500's over the same days (currency-matched: `VFV.TO` for Canadian listings, `SPY` for US; S&P 500 funds are judged alone), best/worst since the trade, a price series, the FOMO check and a suggested grade. Returns are measured at the trade's `review_date` (not today) so waiting for a bounce doesn't change the verdict. `apply_grade` validates the outcome, requires `review_notes` when the grade flatly contradicts the suggestion (correct vs incorrect), and stores a snapshot (`graded_at`, `suggested_outcome`, `graded_return_pct`, `graded_benchmark_return_pct`) that `reasons_summary` turns into average return / vs-market per reason. All price history goes through `fetch_daily_closes` (10-min in-memory cache); fill prices far from the trade-day close are treated as a later stock split. `/thesis-reviews` itself does no price lookups.
- **Trade reasons / thesis inbox** (`thesis.py`, router under `/trades`): every trade needs a *why*. `Trade.reason_tags` holds fixed categories (comma-separated slugs from `BUY_REASONS` / `SELL_REASONS`; the frontend renders chips from `GET /trades/reasons`, so add new reasons there) and `thesis_written_at` records when the reason was written. Synced trades arrive without either and are listed by `GET /trades/needs-thesis`; `PUT /trades/thesis` answers one or many trades of the same side. Answers are final (409 on re-answer) and `dont_remember` is a valid answer that needs no thesis text. `reasons_summary` (counts, outcomes per reason, don't-remember rate, hindsight rate = written >7 days after the trade) feeds both the inbox page and the advisor's system prompt (`advisor_context_section`, `describe_trade_reason` in `build_advisor_context`).
- **Brokerage sync** (`snaptrade_sync.py`, routes in `brokerage.py`): `SNAPTRADE_KEY_TYPE` selects the mode. `personal`: one person's key, only the user matching `SNAPTRADE_OWNER_EMAIL` may use it (everyone else gets 403 / `available: false`). `commercial`: every user links their own brokerage; their SnapTrade user is registered on first Connect (never on page load, since SnapTrade bills per user) and stored in `snaptrade_users` with the secret encrypted by `secret_box.py` (`FIELD_ENCRYPTION_KEY`, which must never change in production). All SnapTrade calls go through `BrokerageSession`, which attaches the current user's credentials. The sync combines account *activities* (authoritative, refreshed by SnapTrade ~daily) with *recent orders* (real-time, last 24h). Each row stores `external_id` (`activity:<id>` / `order:<id>`, unique per user) so re-syncs never duplicate; an incoming record first tries to take over a matching existing row (same root symbol, ET date, action, quantity) so theses survive. Rows that can be taken over: manual/CSV rows, order rows (replaced by their activity), and rows from accounts marked `disconnected_at` (a reconnect or key switch gives accounts new ids; the new account also inherits the old one's `sync_enabled` by name). Quirks handled there: UTC timestamps → US/Eastern date/time, SnapTrade `.VN` → yfinance `.V`, sell units arrive negative, options are skipped, and US-stock prices arrive in CAD (converted with a yfinance USD/CAD rate). Only TFSA/PERSONAL accounts sync by default.

### Frontend
- **No router.** `App.jsx` switches screens with an `activeView` state string. The gating order is: no token → `AuthScreen`; no profile (`GET /profile` fails) → `SurveyScreen`; otherwise `Layout` plus the chosen view. A 401 from `/profile` clears the token. `SurveyScreen` doubles as the profile editor through `editMode`.
- **API calls go through `apiFetch` in `src/api.js`**, which uses `VITE_API_URL` (default `http://127.0.0.1:8000`, baked in at build time) and attaches the bearer token from `localStorage`. Don't call `fetch` directly.
- `refreshKey` in `App.jsx` is bumped after a trade is logged so the dashboard reloads. `BrokerageCard` (on the Dashboard) renders nothing unless `/brokerage/status` says `available`; it syncs on mount and every 5 minutes (the backend skips syncs within 2 minutes unless `force=true`) and bumps the Dashboard's `syncKey` to reload holdings.
- `Dashboard.jsx` and `SidebarWatchlist.jsx` poll every 60s (`PRICE_POLL_INTERVAL_MS`), paired with the backend's 45s price TTL. Keep the two numbers in step.
- `src/tickers.js` is a small hard-coded ticker list used for search autocomplete.
- Theme colours are CSS variables in `src/theme.css` (e.g. `var(--color-text-secondary)`).
- **CORS** allows `localhost:5173`/`5174` plus any origins in the backend's `ALLOWED_ORIGINS` env var (comma-separated) - the deployed frontend URL must be listed there.

## Conventions
- The codebase is heavily commented in plain language, explaining *why* each piece exists, including notes marked `NEW`. Keep that style when editing.
- `Backend/requirements.txt` is plain UTF-8 with exact pins (it was UTF-16 from a Windows `pip freeze`; converted so deploy builders can read it). Keep it UTF-8.

## Deployment
- `DATABASE_URL` selects the database (`database.normalize_database_url` maps `postgres://`/`postgresql://` to the psycopg 3 driver). Only set it to the hosted Postgres in the deployed environment, never in a local `.env`.
- Apply migrations to the hosted DB from a local shell with that URL set for the one command: `DATABASE_URL=<hosted url> alembic upgrade head`.
- `scripts/copy_database.py` copies the local SQLite data into an empty target (`TARGET_DATABASE_URL`): it migrates the target, refuses to write over existing data, keeps ids and resets Postgres id sequences.
- **Live on Vercel** as two projects deployed with the CLI (the GitHub repo can't be connected because it belongs to another account): frontend `innerstock` → https://innerstock.vercel.app (root `Frontend/`), backend `innerstock-api` → https://innerstock-api.vercel.app (root `Backend/`, served through `index.py`, which re-exports `main.app`). Deploy with `npx vercel deploy --prod` from inside each folder. Env vars live in each Vercel project (`npx vercel env ls`): backend has `DATABASE_URL` (Neon **pooled** URL), `JWT_SECRET_KEY` (separate from local), `ANTHROPIC_API_KEY`, `SNAPTRADE_*`, `ALLOWED_ORIGINS`; frontend has `VITE_API_URL`.
- Hosted data is Neon Postgres. Schema changes must be applied there too: `DATABASE_URL=<neon url> alembic upgrade head` before deploying code that needs them.
- `.vercelignore` files keep `.env`, `.env.local`, local databases and `venv/` out of Vercel CLI uploads.
