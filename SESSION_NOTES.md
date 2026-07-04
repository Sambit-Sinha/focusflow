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
