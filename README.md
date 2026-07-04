# FocusFlow — ADHD Task Manager

Full-stack app with FastAPI backend, Vanilla JS frontend, Supabase DB, and Groq AI (free Llama 3.3 70B).

## Stack

| Layer | Tech | Cost |
|-------|------|------|
| Frontend | Vanilla HTML/CSS/JS | Free (Netlify) |
| Backend | FastAPI (Python) | Free (Render) |
| Database | Supabase PostgreSQL | Free tier |
| AI | Groq API (Llama 3.3 70B) | Free tier |
| Hosting (BE) | Render | Free tier |
| Hosting (FE) | Netlify | Free tier |

## Local Setup

### 1. Get your free API keys

- **Supabase**: https://supabase.com → New project → Settings → Database → get `DATABASE_URL`
- **Groq**: https://console.groq.com → API Keys → Create (free, no card needed)

### 2. Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env      # fill in your keys
python -m app.db.init_db  # creates tables in Supabase
uvicorn app.main:app --reload --port 8000
```

### 3. Frontend

```bash
cd frontend
# Edit src/utils/api.js — set BASE_URL to http://localhost:8000
# Open index.html directly in browser, OR:
npx serve .
```

## Deploy

### Backend → Render

1. Push backend/ to a GitHub repo
2. Render → New Web Service → connect repo
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. Add environment variables from .env

### Frontend → Netlify

1. Edit `frontend/src/utils/api.js` — set `BASE_URL` to your Render URL
2. Drag and drop `frontend/` folder to Netlify → Deploy

## Project Structure

```
focusflow/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI app, CORS
│   │   ├── db/
│   │   │   ├── database.py  # SQLAlchemy engine + session
│   │   │   └── init_db.py   # Creates tables
│   │   ├── models/
│   │   │   └── models.py    # SQLAlchemy ORM models
│   │   ├── schemas/
│   │   │   └── schemas.py   # Pydantic schemas
│   │   ├── routes/
│   │   │   ├── users.py     # POST /users/login
│   │   │   ├── tasks.py     # CRUD /tasks
│   │   │   └── explore.py   # POST /explore/chat
│   │   └── services/
│   │       └── ai_service.py # Groq API calls
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── index.html
    ├── src/
    │   ├── utils/api.js     # All fetch calls
    │   ├── components/      # Tasks, Calendar, Explore UI
    │   └── main.js          # App entry point
    └── styles/
        └── main.css
```
