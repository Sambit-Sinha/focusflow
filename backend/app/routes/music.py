import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.models import User
from app.schemas.music_schemas import LogPlayRequest, SetPreferencesRequest
from app.services import music_service

router = APIRouter(prefix="/music", tags=["music"])

MBZ_BASE   = "https://musicbrainz.org/ws/2"
MBZ_HEADERS = {
    "User-Agent": "UnPocoLoco/1.0 (soumik.pal@klinic.live)",
    "Accept": "application/json",
}


def get_user_or_404(user_id: str, db: Session):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


# ── Seed / onboarding ────────────────────────────────────────────────────────

@router.get("/genres")
def list_genres():
    return music_service.get_all_genres()


@router.get("/seed-artists")
def seed_artists():
    return music_service.get_seed_artists_by_genre()


@router.post("/{user_id}/preferences")
def set_preferences(user_id: str, payload: SetPreferencesRequest, db: Session = Depends(get_db)):
    get_user_or_404(user_id, db)
    music_service.set_user_preferences(user_id, payload.artist_names, db)
    return {"set": len(payload.artist_names)}


# ── Play logging ─────────────────────────────────────────────────────────────

@router.post("/{user_id}/play")
def log_play(user_id: str, payload: LogPlayRequest, db: Session = Depends(get_db)):
    get_user_or_404(user_id, db)
    result = music_service.log_play(
        user_id    = user_id,
        song_name  = payload.song_name,
        artist_name= payload.artist_name,
        year       = payload.year,
        genres     = payload.genres,
        mbid       = payload.mbid,
        db         = db,
    )
    return result


# ── Graph data ────────────────────────────────────────────────────────────────

@router.get("/{user_id}/graph")
def get_graph(user_id: str, db: Session = Depends(get_db)):
    get_user_or_404(user_id, db)
    return music_service.get_graph_data(user_id, db)


# ── Recommendations ──────────────────────────────────────────────────────────

@router.get("/{user_id}/recommendations")
def get_recommendations(user_id: str, db: Session = Depends(get_db)):
    get_user_or_404(user_id, db)
    return music_service.get_recommendations(user_id, db)


# ── MusicBrainz search proxy ─────────────────────────────────────────────────

@router.get("/search")
def search_songs(q: str):
    """Proxy to MusicBrainz recording search. Returns up to 10 results."""
    if not q or len(q.strip()) < 2:
        return []
    try:
        url = f"{MBZ_BASE}/recording/"
        resp = httpx.get(url, params={"query": q, "fmt": "json", "limit": 10},
                         headers=MBZ_HEADERS, timeout=8)
        resp.raise_for_status()
        data = resp.json()
        results = []
        for rec in data.get("recordings", []):
            artist_credit = rec.get("artist-credit", [])
            artist_name = artist_credit[0]["name"] if artist_credit else "Unknown"
            year = None
            date = rec.get("first-release-date", "") or rec.get("date", "")
            if date and len(date) >= 4:
                try:
                    year = int(date[:4])
                except ValueError:
                    pass
            results.append({
                "mbid":        rec.get("id", ""),
                "name":        rec.get("title", ""),
                "artist_name": artist_name,
                "year":        year,
            })
        return results
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"MusicBrainz error: {e}")


@router.get("/{user_id}/stats")
def get_stats(user_id: str, db: Session = Depends(get_db)):
    """Return user's top artists and top songs for the profile panel."""
    from app.models.music_models import UserArtistStat, UserSongStat, MusicArtist, MusicSong
    get_user_or_404(user_id, db)

    top_artists = (
        db.query(UserArtistStat)
        .filter(UserArtistStat.user_id == user_id)
        .order_by(UserArtistStat.play_count.desc())
        .limit(8).all()
    )
    top_songs = (
        db.query(UserSongStat)
        .filter(UserSongStat.user_id == user_id)
        .order_by(UserSongStat.play_count.desc())
        .limit(8).all()
    )

    artists_out = []
    for s in top_artists:
        a = db.query(MusicArtist).get(s.artist_id)
        if a:
            artists_out.append({"name": a.name, "genres": a.genres, "play_count": s.play_count})

    songs_out = []
    for s in top_songs:
        sg = db.query(MusicSong).get(s.song_id)
        if sg:
            songs_out.append({"name": sg.name, "artist": sg.artist_name, "play_count": s.play_count})

    return {"top_artists": artists_out, "top_songs": songs_out}
