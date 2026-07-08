# FocusFlow — Session Notes (2026-07-02 / 2026-07-03)

## What We Built

FocusFlow is an ADHD task manager app. The source was provided as a zip (`/Users/koushik/Downloads/focusflow.zip`). Over this session we:

1. Extracted and understood the codebase
2. Set up the full local dev stack (FastAPI backend + Supabase DB + Gemini AI)
3. Fixed multiple bugs and added features iteratively

---

## Stack

| Layer | Service | Notes |
|---|---|---|
| Backend | FastAPI (Python) | Port 8000 |
| Database | Supabase PostgreSQL | Free tier |
| AI | Google Gemini 2.5 Flash | OpenAI-compatible endpoint |
| Frontend | Vanilla JS (ES modules) | Port 3000 via `python3 -m http.server 3000` |

---

## How to Start the App Locally

```bash
# Terminal 1 — Backend
cd /Users/koushik/focusflow/backend
source venv/bin/activate
uvicorn app.main:app --reload

# Terminal 2 — Frontend
cd /Users/koushik/focusflow/frontend
python3 -m http.server 3000
```

Then open: http://localhost:3000

> **Important:** The frontend uses ES modules (`type="module"`) which the browser blocks on `file://`. It MUST be served via HTTP.

---

## Credentials & Config

All secrets are in `/Users/koushik/focusflow/backend/.env` (gitignored):

```
DATABASE_URL=postgresql://postgres:%23Sambitusesfocusflowv12026@db.hstkhoijkrwvjbewfnha.supabase.co:5432/postgres
GEMINI_API_KEY=<your-key-from-aistudio.google.com>
FRONTEND_URL=*
```

> The `#` in the Supabase password is URL-encoded as `%23` — this is intentional and necessary.

---

## Database (Supabase)

Three tables exist in the project: `users`, `tasks`, `completions`.

### Schema additions made this session (via SQLAlchemy migrations):

```sql
-- Added to tasks table
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS task_type VARCHAR(20) NOT NULL DEFAULT 'one-time';

-- Added to completions table
ALTER TABLE completions ADD COLUMN IF NOT EXISTS progress VARCHAR(3) NOT NULL DEFAULT '100';
```

These ran automatically on server start via the migration block in `app/main.py`.

---

## Key Files & What They Do

### Backend

| File | Purpose |
|---|---|
| `app/main.py` | FastAPI entry point; runs DB migrations on startup |
| `app/models/models.py` | SQLAlchemy ORM: `User`, `Task`, `Completion` |
| `app/schemas/schemas.py` | Pydantic request/response shapes |
| `app/routes/tasks.py` | All task endpoints including `/toggle` for recording progress |
| `app/services/ai_service.py` | Calls Gemini via OpenAI-compatible API |

### Frontend

| File | Purpose |
|---|---|
| `src/utils/state.js` | Mini pub/sub state manager (`getState`, `setState`, `subscribe`) |
| `src/utils/api.js` | All fetch calls to the backend |
| `src/components/tasks.js` | Task list UI (table layout, add/edit/delete) |
| `src/components/calendar.js` | Calendar grid, day modal, streak stats |
| `src/components/explore.js` | AI chat panel |
| `styles/main.css` | All styling |

---

## Features Built / Changed This Session

### Task Types
- Added `task_type` field: `"one-time"` or `"repetitive"`
- Repetitive tasks: toggled on the calendar per-day; never marked globally complete
- One-time tasks: progress recorded as 0–100%; marked globally complete when any day reaches 100%

### Progress Recording
- `POST /tasks/{user_id}/{task_id}/toggle` accepts `{ date, progress? }`
- `progress=null` → binary toggle (repetitive)
- `progress=0–100` → set percentage (one-time)

### Calendar
- Mini cells show: repetitive → checkbox + name; one-time → name only (no bar)
- Clicking a cell opens the day modal
- Day modal: repetitive = click-to-toggle row; one-time = slider + Save button
- Progress bar removed from mini cells (was cluttered)

### Streak Logic
- Streak = consecutive days going back from today where ANY task had ANY progress > 0
- This counts both repetitive completions and partial one-time progress
- Stats cards: Streak, Done Today, This Month

### Task Table
- Replaced card layout with borderless table
- Columns: checkbox | Task | Category | Date Added | Last Worked | Type | Actions
- Inline edit: click ✎ → row expands with name input + category select + type select
- Stale badges: repetitive with no work in 3 days → amber `⚡ Going stale`; one-time created 3+ days ago and incomplete → grey `⏳ Overdue`

### Bugs Fixed
- `#` in Supabase password broke database URL (fixed with `%23` URL encoding)
- ES module `file://` loading blocked by browser (fixed with HTTP server)
- AI chat reply not fully shown (fixed with `requestAnimationFrame` scroll)
- Streak not updating in real time (fixed — see below)

### Streak Real-Time Fix (Applied at End of Session)
Three changes:

1. **`state.js`**: Wrapped each listener in try-catch so if `renderTasks` throws, `renderCal` still runs
2. **`calendar.js`**: Added explicit `renderStreaks()` call directly inside both `calToggle()` and `calSetProgress()` after `setState` — belt-and-suspenders
3. **`calendar.js` + `main.css`**: Removed mini progress bar (`cal-mini-prog` / `cal-mini-fill`) from calendar mini-cells entirely

---

## Remaining Things To Do

### High Priority
- [ ] **Test streak fix end-to-end**: Hard-refresh browser (`Cmd+Shift+R`), mark tasks on the calendar, verify streak counter updates immediately without page reload
- [ ] **Test one-time task progress flow**: Set 60% → streak ticks up; set 100% → task marked complete in task list

### Medium Priority
- [ ] **Deploy backend to Render**: Use `render.yaml` already in the project; change `BASE_URL` in `frontend/src/utils/api.js` to the Render URL after deploy
- [ ] **Deploy frontend to Netlify**: Point to the `frontend/` folder; set `BASE_URL` to the Render backend URL
- [ ] **Environment variable for BASE_URL**: Currently hardcoded as `http://localhost:8000` in `api.js` — should use an env-aware value for production

### Nice to Have
- [ ] **"Last Worked" column only for repetitive tasks**: Currently shown for all — for one-time tasks it's less meaningful; consider showing "Progress" (%) instead
- [ ] **Mobile layout**: The table may overflow on small screens — could collapse columns or switch to cards on mobile
- [ ] **Filter by task type**: Add "Repetitive" and "One-time" filter buttons alongside the existing category filters
- [ ] **Streak freeze / grace day**: Option to not break a streak if the user misses one day (common in habit apps like Duolingo)
- [ ] **Onboarding**: New users land on an empty task list — a short onboarding message or sample tasks would help

---

## Architecture Notes (for reference)

### State flow
```
user action
  → api.js fetch → backend returns updated task
  → setState({ tasks: [...] })        ← updates central state
  → listeners fire:
      renderTasks()                   ← rebuilds task table
      renderCal()                     ← rebuilds calendar grid + calls renderStreaks()
  → renderStreaks() also called explicitly in calToggle/calSetProgress
```

### Why ES modules need an HTTP server
The browser enforces CORS/same-origin on `import` statements. When you open an HTML file directly (`file://`), `import` from another local file is blocked by default. Serving from `localhost:3000` bypasses this.

### Why `#` must be `%23` in DATABASE_URL
In a URL, `#` marks the start of a "fragment" (like `page.html#section`). Everything after it is ignored. So the password `#Sambit...` would be interpreted as an empty password + a fragment. URL-encoding the `#` as `%23` tells the parser to treat it as a literal character.

---

# Session Notes — 2026-07-08

## What We Built This Session

### 1. Streak Fix (verified)
- Confirmed 7-day streak (Jul 2–8) was correct by querying Supabase directly
- Clarified that `streakDays()` walks backward from today, so logging on a future date does NOT move the streak — this is correct behaviour

### 2. One-Time Task Date Ranges

**Goal:** Allow users to assign a `from_date` and `to_date` to any one-time task. The task only appears on the calendar within that window, and disappears after reaching 100%.

**Backend changes:**
- Added `from_date` and `to_date` VARCHAR(10) columns to the `tasks` table (migration runs on startup in `app/main.py`)
- Added fields to `TaskCreate`, `TaskUpdate`, `TaskOut` schemas in `schemas.py`
- Fixed `update_task()` in `routes/tasks.py` — now uses Pydantic v2's `model_fields_set` to distinguish "explicitly sent null (clear the date)" from "field not sent at all":
  ```python
  sent = payload.model_fields_set
  if "from_date" in sent: task.from_date = payload.from_date
  if "to_date"   in sent: task.to_date   = payload.to_date
  ```

**Frontend changes:**
- `calendar.js` — `isOneTimeVisibleOnDate(task, dateStr)`: hides a one-time task if before `from_date`, after `to_date`, or already hit 100% on an earlier date
- `state.js` — `progressImprovedOnDate(task, dateStr)`: returns true only if the % actually went up vs the prior recorded day (stagnant 50%→50% does not count as progress)
- `streakDays()` updated to use `progressImprovedOnDate` instead of bare `progressOnDate > 0`
- `tasks.js` — date pickers shown inline in the task-add row (only for one-time type); also inline in the edit row alongside category/type selects
- `index.html` — added `#task-date-range` div with `task-from-date` and `task-to-date` inputs
- `api.js` — `createTask()` now accepts and sends `fromDate` / `toDate`

**Bug fixed:** Date inputs in the edit row were not editable when placed in a sub-div below the controls. Fixed by moving them inline into `.edit-controls` on the same row as selects and buttons.

---

### 3. Knowledge Graph Music Recommendation Engine

**New "Music" tab** replaces the old Recommendations tab. Goal: build an Obsidian-style knowledge graph that learns from listening habits and gives personalised recommendations.

**New database tables (auto-created on startup):**

| Table | Purpose |
|---|---|
| `music_artists` | All artists (seed + user-discovered), with genres as JSON |
| `music_songs` | Songs logged by users |
| `user_artist_stats` | (user, artist) play count + last played timestamp |
| `user_song_stats` | (user, song) play count + last played timestamp |
| `artist_similarity` | Bidirectional pre-computed similarity scores between artists |

**Seed data (`app/services/music_seed.py`):**
- 132 artists across 16 genres loaded idempotently on startup
- Similarity pre-computed: Jaccard on shared genres + related-artist boost (max 0.3 score)
- Stored bidirectionally in `artist_similarity` table

**Recommendation engine (`app/services/music_service.py`):**
- `_cosine(vec_a, vec_b)` — manual cosine similarity, no sklearn dependency
- `_recency_weight(last_played)` — exponential decay, half-life 30 days
- `_taste_vector(user_id, db)` — genre-weighted vector per user
- `_update_artist_similarity()` — called on each `log_play` to keep graph fresh
- Hybrid recommendations: graph-hop (traverse similar artists) + collaborative filtering (cosine similarity between user taste vectors)

**New API routes (`/music/...`):**
- `GET /music/genres` — list all genres
- `GET /music/seed-artists` — artists grouped by genre (for onboarding UI)
- `POST /music/{user_id}/preferences` — save onboarding picks
- `POST /music/{user_id}/play` — log a listen, updates graph live
- `GET /music/{user_id}/graph` — D3-ready `{ nodes, links }` payload
- `GET /music/{user_id}/recommendations` — personalised artist list
- `GET /music/search?q=` — MusicBrainz proxy (backend-side to avoid CORS + centralise rate limiting)
- `GET /music/{user_id}/stats` — top 8 artists + top 8 songs

**Frontend (`src/components/recommendations.js`):**
- D3 v7 force-directed graph: drag, zoom, tooltips per node type
- 3 sub-views: **Graph** / **For You** / **Your Stats**
- Onboarding modal: genre chips → artist chips → POST preferences
- Log modal: MusicBrainz search → select result → POST play
- Node colours: user=cyan, artist=genre colour, genre=dark, recommended=darker

---

### 4. Sporty Visual Redesign

**Design goal:** sharper, more energetic feel — less "soft productivity app", more "sports dashboard".

**New CSS design tokens:**

| Token | Before | After |
|---|---|---|
| `--accent` | `#7c6ef5` (purple) | `#00D4FF` (electric cyan) |
| `--radius` | `12px` | `4px` |
| `--radius-sm` | `8px` | `3px` |
| `--radius-xs` | `6px` | `2px` |
| `--bg` | `#0e0e12` | `#06060C` |

**Component changes:**

- **Tabs** — flat uppercase labels with a sharp 2px cyan underline + glow on active; no more rounded tab style
- **Logo** — cyan→blue gradient text; glowing pulsing cyan dot
- **Login card** — cyan top accent border, ambient shadow
- **Progress bar** — gradient: cyan left → orange right
- **Streak cards** — 40px bold scoreboard numbers; colour-coded top border (cyan / green / orange per card)
- **Buttons** — uppercase, black text on cyan, ambient glow; ghost button stays dark
- **Filter/nav badges** — uppercase, sharp corners, cyan when active
- **Tags** — each category has a coloured border now (not just background tint)
- **Task row hover** — faint cyan left border on checkbox cell + very subtle cyan background
- **Calendar cells** — sharper corners, cyan border + tint on today
- **Modals** — cyan top accent border, 80% black overlay
- **Slider thumb** — cyan with stronger glow
- **Music rec cards** — changed from horizontal rows → **2-column square grid**:
  - Coloured genre strip across the top of each card
  - Bold artist name, italic reason text
  - Genre tags + Log button in footer row
- **D3 graph** — user node changed from purple to cyan; tooltip uses cyan border + glow

---

## Updated File Map

```
focusflow/
├── backend/
│   └── app/
│       ├── main.py                    — startup, migrations, route wiring, seed call
│       ├── models/
│       │   ├── models.py              — Task (+ from_date, to_date), User, Completion
│       │   └── music_models.py        — MusicArtist, MusicSong, UserArtistStat, UserSongStat, ArtistSimilarity
│       ├── schemas/
│       │   ├── schemas.py             — TaskCreate/Update/Out (+ from_date, to_date)
│       │   └── music_schemas.py       — music Pydantic schemas
│       ├── routes/
│       │   ├── tasks.py               — CRUD; model_fields_set for partial updates
│       │   ├── music.py               — all /music/* endpoints + MusicBrainz proxy
│       │   └── explore.py             — AI coach chat
│       └── services/
│           ├── music_service.py       — recommendation engine, graph builder, cosine similarity
│           └── music_seed.py          — 132 seed artists × 16 genres + related lists
└── frontend/
    ├── index.html                     — tabs, panels, modals, D3 CDN script tag
    ├── styles/main.css                — full sporty design system (cyan palette, sharp radii)
    └── src/
        ├── main.js                    — boot, tab switching, login
        ├── utils/
        │   ├── api.js                 — fetch wrappers (createTask now takes fromDate/toDate)
        │   └── state.js               — state, streakDays(), progressImprovedOnDate()
        └── components/
            ├── tasks.js               — task table, add (with date pickers), inline edit
            ├── calendar.js            — month grid, isOneTimeVisibleOnDate(), day modal
            ├── recommendations.js     — D3 graph, 2-col rec grid, onboarding, log modal
            └── explore.js             — AI coach chat
```

---

## Pending / Next Up

- [ ] **Disable task completion for future dates** (mentioned during streak discussion)
- [ ] **Chatbot actions** — classify query → add to favourites / add to knowledge graph
- [ ] **Multi-user graph** — show connections between users with similar taste
- [ ] **Auth layer** — replace name-only login
