"""
music_service.py — Knowledge graph operations.

Graph model:
  Nodes : User, MusicArtist, Genre (virtual)
  Edges :
    User  → MusicArtist   (user_artist_stats.play_count)
    MusicArtist → Genre   (artist.genres list, virtual)
    MusicArtist ↔ MusicArtist  (artist_similarity.score)
    User  ↔ User          (cosine similarity, computed on-the-fly)
"""

import math
import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.models.music_models import MusicArtist, MusicSong, UserArtistStat, UserSongStat, ArtistSimilarity
from app.services.music_seed import SEED_ARTISTS_BY_GENRE, SEED_GENRES


# ── Helpers ──────────────────────────────────────────────────────────────────

def _cosine(vec_a: dict, vec_b: dict) -> float:
    """Cosine similarity between two {key: weight} dicts."""
    dot = sum(vec_a.get(k, 0) * vec_b.get(k, 0) for k in vec_a)
    norm_a = math.sqrt(sum(v ** 2 for v in vec_a.values()))
    norm_b = math.sqrt(sum(v ** 2 for v in vec_b.values()))
    if not norm_a or not norm_b:
        return 0.0
    return dot / (norm_a * norm_b)


def _recency_weight(last_played: datetime | None) -> float:
    """More recent = higher weight (half-life ~30 days)."""
    if not last_played:
        return 1.0
    days_ago = (datetime.now(timezone.utc) - last_played.replace(tzinfo=timezone.utc)).days
    return math.exp(-0.023 * days_ago)   # e^(-ln2/30 * days) ≈ half-life 30 days


def _taste_vector(user_id: str, db: Session) -> dict:
    """Build a genre-weighted taste vector for a user."""
    stats = db.query(UserArtistStat).filter(UserArtistStat.user_id == user_id).all()
    vec: dict[str, float] = {}
    for stat in stats:
        artist = db.query(MusicArtist).get(stat.artist_id)
        if not artist:
            continue
        weight = stat.play_count * _recency_weight(stat.last_played)
        for genre in (artist.genres or []):
            vec[genre] = vec.get(genre, 0) + weight
    return vec


# ── Seed / initialise ────────────────────────────────────────────────────────

def ensure_seed_artists(db: Session):
    """Insert seed artists + pre-compute genre-based similarity. Idempotent."""
    # collect all artists across all genres
    name_to_genres: dict[str, list[str]] = {}
    name_to_related: dict[str, list[str]] = {}

    for genre, artists in SEED_ARTISTS_BY_GENRE.items():
        for a in artists:
            name = a["name"]
            name_to_genres.setdefault(name, [])
            if genre not in name_to_genres[name]:
                name_to_genres[name].append(genre)
            name_to_related[name] = a.get("related", [])

    # upsert artists
    name_to_id: dict[str, str] = {}
    for name, genres in name_to_genres.items():
        existing = db.query(MusicArtist).filter(MusicArtist.name == name).first()
        if existing:
            name_to_id[name] = existing.id
        else:
            obj = MusicArtist(id=str(uuid.uuid4()), name=name, genres=genres, is_seed="true")
            db.add(obj)
            db.flush()
            name_to_id[name] = obj.id
    db.commit()

    # pre-compute similarity from shared genres (only between seed artists)
    all_names = list(name_to_genres.keys())
    for i, na in enumerate(all_names):
        for nb in all_names[i + 1:]:
            shared = len(set(name_to_genres[na]) & set(name_to_genres[nb]))
            total  = len(set(name_to_genres[na]) | set(name_to_genres[nb]))
            genre_sim = shared / total if total else 0.0

            # boost if they explicitly appear in each other's related list
            related_boost = 0.0
            if nb in name_to_related.get(na, []) or na in name_to_related.get(nb, []):
                related_boost = 0.3

            score = min(1.0, genre_sim + related_boost)
            if score < 0.05:
                continue  # skip near-zero edges to keep graph sparse

            id_a, id_b = name_to_id[na], name_to_id[nb]
            # upsert both directions
            for (a, b) in [(id_a, id_b), (id_b, id_a)]:
                row = db.query(ArtistSimilarity).filter(
                    ArtistSimilarity.artist_a_id == a,
                    ArtistSimilarity.artist_b_id == b,
                ).first()
                if row:
                    row.score = score
                else:
                    db.add(ArtistSimilarity(artist_a_id=a, artist_b_id=b, score=score))

    db.commit()


# ── Preferences (onboarding) ────────────────────────────────────────────────

def set_user_preferences(user_id: str, artist_names: list[str], db: Session):
    """
    Seed the graph with artists the user selected at onboarding.
    Each selection = 1 play (so the graph has something to work with immediately).
    """
    for name in artist_names:
        artist = db.query(MusicArtist).filter(MusicArtist.name == name).first()
        if not artist:
            artist = MusicArtist(id=str(uuid.uuid4()), name=name, genres=[], is_seed="false")
            db.add(artist)
            db.flush()
        existing = db.query(UserArtistStat).filter_by(user_id=user_id, artist_id=artist.id).first()
        if not existing:
            db.add(UserArtistStat(user_id=user_id, artist_id=artist.id, play_count=1))
    db.commit()


# ── Log a play ───────────────────────────────────────────────────────────────

def log_play(user_id: str, song_name: str, artist_name: str,
             year: int | None, genres: list[str], mbid: str | None, db: Session) -> dict:
    """Record a play event. Returns updated stats."""
    # ensure artist exists
    artist = db.query(MusicArtist).filter(MusicArtist.name == artist_name).first()
    if not artist:
        artist = MusicArtist(id=str(uuid.uuid4()), name=artist_name, genres=genres or [], is_seed="false")
        db.add(artist)
        db.flush()
    elif genres and not artist.genres:
        artist.genres = genres

    # ensure song exists
    song = db.query(MusicSong).filter(
        MusicSong.name == song_name, MusicSong.artist_id == artist.id
    ).first()
    if not song:
        song = MusicSong(
            id=str(uuid.uuid4()), name=song_name, artist_id=artist.id,
            artist_name=artist_name, year=year, genres=genres or [], mbid=mbid,
        )
        db.add(song)
        db.flush()

    # update user → song edge
    song_stat = db.query(UserSongStat).filter_by(user_id=user_id, song_id=song.id).first()
    if song_stat:
        song_stat.play_count += 1
        song_stat.last_played = datetime.now(timezone.utc)
    else:
        db.add(UserSongStat(user_id=user_id, song_id=song.id, artist_id=artist.id, play_count=1))

    # update user → artist edge
    artist_stat = db.query(UserArtistStat).filter_by(user_id=user_id, artist_id=artist.id).first()
    if artist_stat:
        artist_stat.play_count += 1
        artist_stat.last_played = datetime.now(timezone.utc)
    else:
        db.add(UserArtistStat(user_id=user_id, artist_id=artist.id, play_count=1))

    # recompute artist similarity with new artist vs user's existing artists (incremental)
    _update_artist_similarity(artist, db)

    db.commit()
    return {"song": song_name, "artist": artist_name, "play_count": (song_stat.play_count if song_stat else 1)}


def _update_artist_similarity(new_artist: MusicArtist, db: Session):
    """Incrementally add similarity edges for a newly-logged artist."""
    if not new_artist.genres:
        return
    all_artists = db.query(MusicArtist).filter(MusicArtist.id != new_artist.id).all()
    for other in all_artists:
        if not other.genres:
            continue
        shared = len(set(new_artist.genres) & set(other.genres))
        total  = len(set(new_artist.genres) | set(other.genres))
        score  = shared / total if total else 0.0
        if score < 0.05:
            continue
        for (a, b) in [(new_artist.id, other.id), (other.id, new_artist.id)]:
            row = db.query(ArtistSimilarity).filter_by(artist_a_id=a, artist_b_id=b).first()
            if row:
                row.score = max(row.score, score)
            else:
                db.add(ArtistSimilarity(artist_a_id=a, artist_b_id=b, score=score))


# ── Graph data ───────────────────────────────────────────────────────────────

def get_graph_data(user_id: str, db: Session) -> dict:
    """
    Returns nodes + links for D3.js force-directed graph.
    Scope: this user's played artists + similar artists + genre nodes.
    """
    nodes, links = [], []
    seen_nodes: set[str] = set()

    # User node
    nodes.append({"id": f"u-{user_id}", "label": "You", "type": "user", "size": 20, "play_count": 0})
    seen_nodes.add(f"u-{user_id}")

    # User's played artists
    user_stats = db.query(UserArtistStat).filter(UserArtistStat.user_id == user_id).all()
    played_ids = {s.artist_id for s in user_stats}

    for stat in user_stats:
        artist = db.query(MusicArtist).get(stat.artist_id)
        if not artist:
            continue
        nid = f"a-{artist.id}"
        size = 8 + min(stat.play_count, 20) * 0.8   # 8–24
        primary_genre = (artist.genres or ["?"])[0]

        if nid not in seen_nodes:
            nodes.append({"id": nid, "label": artist.name, "type": "artist",
                          "genre": primary_genre, "size": size, "play_count": stat.play_count})
            seen_nodes.add(nid)

        links.append({"source": f"u-{user_id}", "target": nid,
                      "type": "played", "weight": math.log1p(stat.play_count)})

        # Genre nodes
        for genre in (artist.genres or [])[:2]:   # max 2 genres per artist to keep graph clean
            gnid = f"g-{genre}"
            if gnid not in seen_nodes:
                nodes.append({"id": gnid, "label": genre, "type": "genre", "size": 6, "play_count": 0})
                seen_nodes.add(gnid)
            links.append({"source": nid, "target": gnid, "type": "genre", "weight": 0.5})

    # Similar artist nodes (not played by user yet)
    for artist_id in list(played_ids):
        sims = db.query(ArtistSimilarity).filter(
            ArtistSimilarity.artist_a_id == artist_id,
            ArtistSimilarity.score >= 0.3,
        ).order_by(ArtistSimilarity.score.desc()).limit(3).all()

        for sim in sims:
            if sim.artist_b_id in played_ids:
                continue   # user already knows this one — skip (already drawn)
            sim_artist = db.query(MusicArtist).get(sim.artist_b_id)
            if not sim_artist:
                continue
            snid = f"a-{sim_artist.id}"
            if snid not in seen_nodes:
                primary_genre = (sim_artist.genres or ["?"])[0]
                nodes.append({"id": snid, "label": sim_artist.name, "type": "recommended",
                              "genre": primary_genre, "size": 6, "play_count": 0})
                seen_nodes.add(snid)
            # draw similarity edge between known and recommended artist
            known_nid = f"a-{artist_id}"
            links.append({"source": known_nid, "target": snid,
                          "type": "similar", "weight": sim.score})

    return {"nodes": nodes, "links": links}


# ── Recommendations ──────────────────────────────────────────────────────────

def get_recommendations(user_id: str, db: Session) -> list[dict]:
    """
    Hybrid recommendations:
      1. Graph hop  : User→Artist→similar→unheard artist
      2. Collaborative: other users with similar taste → their top artists
    """
    user_stats   = {s.artist_id: s.play_count for s in
                    db.query(UserArtistStat).filter(UserArtistStat.user_id == user_id).all()}
    played_ids   = set(user_stats.keys())
    user_vec     = _taste_vector(user_id, db)

    candidates: dict[str, dict] = {}  # artist_id → {score, reasons}

    # — Path 1: graph hop via similarity edges —
    for artist_id, play_count in user_stats.items():
        sims = db.query(ArtistSimilarity).filter(
            ArtistSimilarity.artist_a_id == artist_id,
            ArtistSimilarity.score >= 0.2,
        ).order_by(ArtistSimilarity.score.desc()).limit(5).all()

        source_artist = db.query(MusicArtist).get(artist_id)
        for sim in sims:
            if sim.artist_b_id in played_ids:
                continue
            score = sim.score * math.log1p(play_count)
            reason = f"Similar to {source_artist.name if source_artist else '?'} which you play a lot"
            if sim.artist_b_id not in candidates:
                candidates[sim.artist_b_id] = {"score": score, "reasons": [reason]}
            else:
                candidates[sim.artist_b_id]["score"] += score
                candidates[sim.artist_b_id]["reasons"].append(reason)

    # — Path 2: collaborative filtering —
    all_user_ids = [
        r[0] for r in db.execute(
            text("SELECT DISTINCT user_id FROM user_artist_stats WHERE user_id != :uid"),
            {"uid": user_id}
        ).fetchall()
    ]

    best_peers: list[tuple[str, float]] = []
    for other_id in all_user_ids:
        other_vec = _taste_vector(other_id, db)
        sim = _cosine(user_vec, other_vec)
        if sim > 0.2:
            best_peers.append((other_id, sim))

    best_peers.sort(key=lambda x: x[1], reverse=True)

    for peer_id, peer_sim in best_peers[:5]:
        peer_stats = db.query(UserArtistStat).filter(UserArtistStat.user_id == peer_id).all()
        for stat in peer_stats:
            if stat.artist_id in played_ids:
                continue
            score = peer_sim * math.log1p(stat.play_count) * 0.8
            reason = f"Loved by users with taste similar to yours"
            if stat.artist_id not in candidates:
                candidates[stat.artist_id] = {"score": score, "reasons": [reason]}
            else:
                candidates[stat.artist_id]["score"] += score

    # build output
    recs = []
    for artist_id, data in sorted(candidates.items(), key=lambda x: x[1]["score"], reverse=True)[:10]:
        artist = db.query(MusicArtist).get(artist_id)
        if not artist:
            continue
        recs.append({
            "artist_id":   artist.id,
            "artist_name": artist.name,
            "genres":      artist.genres or [],
            "score":       round(data["score"], 3),
            "reason":      data["reasons"][0],
        })

    return recs


# ── Seed genres list ─────────────────────────────────────────────────────────

def get_all_genres() -> list[str]:
    return SEED_GENRES


def get_seed_artists_by_genre() -> dict:
    """Return {genre: [name, ...]} for the onboarding UI."""
    return {
        genre: [a["name"] for a in artists]
        for genre, artists in SEED_ARTISTS_BY_GENRE.items()
    }
