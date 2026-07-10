"""
music_service.py — Knowledge graph operations for the music recommendation engine.

GRAPH MODEL
-----------
Nodes:
  User         — the person using the app (central node, one per user)
  MusicArtist  — an artist they've listened to (or a seed artist)
  Genre        — a genre tag (virtual node, not a DB table — derived from artist.genres)

Edges (all stored in DB with weights):
  User  → MusicArtist    user_artist_stats.play_count   (how often they play this artist)
  Artist → Genre         artist.genres list             (what genres the artist belongs to)
  Artist ↔ Artist        artist_similarity.score        (how similar two artists are)

HOW RECOMMENDATIONS WORK (two paths combined)
----------------------------------------------
Path 1 — Graph hop (content-based):
  Your played artists → find similar artists (via artist_similarity) → recommend unheard ones

Path 2 — Collaborative filtering:
  Other users → compute taste similarity (cosine of genre vectors) → recommend their top artists

Both paths produce candidate artists with scores. The scores are summed and the
top 10 are returned. This hybrid approach works better than either method alone:
  - Graph hop works when you have listening history
  - Collaborative filtering kicks in when similar users have listened to more

Data Science parallel: think of _taste_vector() as creating a TF-IDF-style feature
vector per user (genres weighted by play count × recency). Cosine similarity between
two users' vectors tells us how alike their musical taste is.
"""

import math
import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.models.music_models import MusicArtist, MusicSong, UserArtistStat, UserSongStat, ArtistSimilarity
from app.services.music_seed import SEED_ARTISTS_BY_GENRE, SEED_GENRES


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _cosine(vec_a: dict, vec_b: dict) -> float:
    """
    Compute cosine similarity between two sparse vectors represented as dicts.
    Each dict maps a genre name to a weight: {"Pop": 3.5, "R&B": 1.2, ...}

    Cosine similarity measures the angle between two vectors (0 = nothing in
    common, 1 = identical direction). Unlike raw dot product, it's normalised
    by vector length — so a user who plays 100 Pop songs and a user who plays
    10 Pop songs still get a similarity of 1.0 (same taste, different volume).

    Why "sparse"? Most users haven't listened to all genres. Instead of a
    fixed-length array of zeros (dense), we only store genres that have non-zero
    weight — much more memory-efficient.
    """
    dot    = sum(vec_a.get(k, 0) * vec_b.get(k, 0) for k in vec_a)
    norm_a = math.sqrt(sum(v ** 2 for v in vec_a.values()))
    norm_b = math.sqrt(sum(v ** 2 for v in vec_b.values()))
    if not norm_a or not norm_b:
        return 0.0   # one vector is all zeros — no similarity possible
    return dot / (norm_a * norm_b)


def _recency_weight(last_played: datetime | None) -> float:
    """
    Give higher weight to recently played artists using exponential decay.

    Formula: e^(-0.023 × days_ago)
    At 0 days: weight = 1.0 (full weight)
    At 30 days: weight ≈ 0.5 (half-life)
    At 90 days: weight ≈ 0.125 (very low)

    Why decay? A band you listened to obsessively 6 months ago but haven't
    touched since probably doesn't reflect your current taste as well as
    something you played last week. This makes recommendations feel timely.

    The constant 0.023 ≈ ln(2)/30 — chosen to give a half-life of 30 days.
    """
    if not last_played:
        return 1.0
    days_ago = (datetime.now(timezone.utc) - last_played.replace(tzinfo=timezone.utc)).days
    return math.exp(-0.023 * days_ago)


def _taste_vector(user_id: str, db: Session) -> dict:
    """
    Build a genre-weighted taste vector for a user.

    For each artist the user has played:
      weight = play_count × recency_weight
      for each genre of that artist: add weight to that genre's total

    Result: {"Pop": 8.3, "R&B": 4.1, "Soul": 2.0, ...}
    This is the user's "taste fingerprint" — used for cosine similarity
    between users (collaborative filtering).

    Data Science parallel: similar to a TF-IDF document vector, but for music
    taste instead of word frequency.
    """
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


# =============================================================================
# SEED / INITIALISE
# =============================================================================

def ensure_seed_artists(db: Session):
    """
    Insert the curated list of seed artists and pre-compute their similarity scores.
    Called on every server startup. "Idempotent" — safe to run multiple times.

    WHY SEED ARTISTS?
    New users have no listening history, so there's nothing to recommend from.
    Seed artists are a hand-picked set of well-known musicians across genres,
    stored in music_seed.py. When a user picks favourites during onboarding,
    those are pulled from this seed list.

    SIMILARITY COMPUTATION
    For each pair of seed artists:
      1. Jaccard similarity of genre sets (shared_genres / total_genres)
      2. +0.3 boost if they appear in each other's "related" list in the seed data
      3. Clamp to max 1.0
      4. Skip if score < 0.05 (too weak — don't clutter the graph)
      5. Store BOTH directions (A→B and B→A) so queries are always one-directional
    """
    # Build a mapping: artist name → genres and related artists
    name_to_genres:  dict[str, list[str]] = {}
    name_to_related: dict[str, list[str]] = {}

    for genre, artists in SEED_ARTISTS_BY_GENRE.items():
        for a in artists:
            name = a["name"]
            name_to_genres.setdefault(name, [])
            if genre not in name_to_genres[name]:
                name_to_genres[name].append(genre)
            name_to_related[name] = a.get("related", [])

    # Upsert all artists — insert new ones, skip existing ones
    name_to_id: dict[str, str] = {}
    for name, genres in name_to_genres.items():
        existing = db.query(MusicArtist).filter(MusicArtist.name == name).first()
        if existing:
            name_to_id[name] = existing.id
        else:
            obj = MusicArtist(id=str(uuid.uuid4()), name=name, genres=genres, is_seed="true")
            db.add(obj)
            db.flush()   # flush so we can read obj.id before committing
            name_to_id[name] = obj.id
    db.commit()

    # Pre-compute pairwise similarity for all seed artists
    # O(n²) — fine for a small seed list (~100 artists), would need optimisation
    # for thousands of artists
    all_names = list(name_to_genres.keys())
    for i, na in enumerate(all_names):
        for nb in all_names[i + 1:]:   # i+1 avoids computing (A,B) and (B,A) twice
            shared    = len(set(name_to_genres[na]) & set(name_to_genres[nb]))
            total     = len(set(name_to_genres[na]) | set(name_to_genres[nb]))
            genre_sim = shared / total if total else 0.0

            # Explicit "related" links in the seed data boost the score
            related_boost = 0.0
            if nb in name_to_related.get(na, []) or na in name_to_related.get(nb, []):
                related_boost = 0.3

            score = min(1.0, genre_sim + related_boost)
            if score < 0.05:
                continue  # skip near-zero edges to keep the graph readable

            id_a, id_b = name_to_id[na], name_to_id[nb]
            # Store both directions so we can always query "similar to X" with a
            # simple WHERE artist_a_id = X filter
            for (a, b) in [(id_a, id_b), (id_b, id_a)]:
                row = db.query(ArtistSimilarity).filter(
                    ArtistSimilarity.artist_a_id == a,
                    ArtistSimilarity.artist_b_id == b,
                ).first()
                if row:
                    row.score = score   # update if already exists
                else:
                    db.add(ArtistSimilarity(artist_a_id=a, artist_b_id=b, score=score))

    db.commit()


# =============================================================================
# PREFERENCES (ONBOARDING)
# =============================================================================

def set_user_preferences(user_id: str, artist_names: list[str], db: Session):
    """
    Seed the user's taste graph with their selected favourite artists.

    Called once during onboarding when the user picks artists they like.
    Each selection creates a UserArtistStat row with play_count=1.
    This gives the recommendation engine something to start from immediately,
    even before the user has logged any actual listens.

    We only add if not already present (the user might re-run onboarding).
    """
    for name in artist_names:
        artist = db.query(MusicArtist).filter(MusicArtist.name == name).first()
        if not artist:
            # Artist not in seed list — create a new entry
            artist = MusicArtist(id=str(uuid.uuid4()), name=name, genres=[], is_seed="false")
            db.add(artist)
            db.flush()
        existing = db.query(UserArtistStat).filter_by(user_id=user_id, artist_id=artist.id).first()
        if not existing:
            db.add(UserArtistStat(user_id=user_id, artist_id=artist.id, play_count=1))
    db.commit()


# =============================================================================
# LOG A PLAY
# =============================================================================

def log_play(user_id: str, song_name: str, artist_name: str,
             year: int | None, genres: list[str], mbid: str | None, db: Session) -> dict:
    """
    Record that the user listened to a song. Updates three things:
      1. The song row (create if doesn't exist)
      2. user_song_stats — their play count for this song
      3. user_artist_stats — their play count for this artist

    Also incrementally updates artist similarity edges when a new artist
    is encountered (so recommendations improve in real-time).
    """
    # Step 1: Ensure the artist exists
    artist = db.query(MusicArtist).filter(MusicArtist.name == artist_name).first()
    if not artist:
        artist = MusicArtist(id=str(uuid.uuid4()), name=artist_name, genres=genres or [], is_seed="false")
        db.add(artist)
        db.flush()
    elif genres and not artist.genres:
        # If we now know the genres for an artist we didn't have them for, update
        artist.genres = genres

    # Step 2: Ensure the song exists
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

    # Step 3: Update user → song edge (increment play count or create)
    song_stat = db.query(UserSongStat).filter_by(user_id=user_id, song_id=song.id).first()
    if song_stat:
        song_stat.play_count += 1
        song_stat.last_played = datetime.now(timezone.utc)
    else:
        db.add(UserSongStat(user_id=user_id, song_id=song.id, artist_id=artist.id, play_count=1))

    # Step 4: Update user → artist edge (increment play count or create)
    artist_stat = db.query(UserArtistStat).filter_by(user_id=user_id, artist_id=artist.id).first()
    if artist_stat:
        artist_stat.play_count += 1
        artist_stat.last_played = datetime.now(timezone.utc)
    else:
        db.add(UserArtistStat(user_id=user_id, artist_id=artist.id, play_count=1))

    # Step 5: Incrementally update similarity edges for this artist vs all others
    _update_artist_similarity(artist, db)

    db.commit()
    return {"song": song_name, "artist": artist_name, "play_count": (song_stat.play_count if song_stat else 1)}


def _update_artist_similarity(new_artist: MusicArtist, db: Session):
    """
    When a new artist is added (or encountered for the first time), compute
    their similarity to all existing artists and add/update edges.

    This is the "online learning" part of the system — the graph grows
    incrementally as new data arrives, rather than needing a full recompute.
    Only skips pairs with score < 0.05 to keep the graph sparse.
    """
    if not new_artist.genres:
        return  # can't compute similarity without genre information
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
                row.score = max(row.score, score)  # keep the higher score
            else:
                db.add(ArtistSimilarity(artist_a_id=a, artist_b_id=b, score=score))


# =============================================================================
# GRAPH DATA (for D3.js visualisation)
# =============================================================================

def get_graph_data(user_id: str, db: Session) -> dict:
    """
    Build the graph JSON for the D3.js force-directed visualisation.

    Returns nodes (things) and links (connections between things).
    Three types of nodes: the user, their played artists, and genre tags.
    Two extra node types: recommended artists (similar but unplayed).

    Node sizes are proportional to play count (bigger = listened more).
    Link weights become line thickness in the frontend.

    We cap genres to 2 per artist to avoid cluttering the visualisation.
    """
    nodes, links = [], []
    seen_nodes: set[str] = set()  # track which node IDs we've already added

    # Central "You" node
    nodes.append({"id": f"u-{user_id}", "label": "You", "type": "user", "size": 20, "play_count": 0})
    seen_nodes.add(f"u-{user_id}")

    user_stats = db.query(UserArtistStat).filter(UserArtistStat.user_id == user_id).all()
    played_ids = {s.artist_id for s in user_stats}

    for stat in user_stats:
        artist = db.query(MusicArtist).get(stat.artist_id)
        if not artist:
            continue
        nid = f"a-{artist.id}"
        # Node size: 8 (minimum) + up to 16 more based on play count, capped at 24
        size = 8 + min(stat.play_count, 20) * 0.8
        primary_genre = (artist.genres or ["?"])[0]

        if nid not in seen_nodes:
            nodes.append({"id": nid, "label": artist.name, "type": "artist",
                          "genre": primary_genre, "size": size, "play_count": stat.play_count})
            seen_nodes.add(nid)

        # Edge: User → Artist (weight = log of play count, so 10 plays isn't
        # 10× thicker than 1 play — logarithm keeps sizes visually reasonable)
        links.append({"source": f"u-{user_id}", "target": nid,
                      "type": "played", "weight": math.log1p(stat.play_count)})

        # Genre nodes — at most 2 per artist to keep the graph readable
        for genre in (artist.genres or [])[:2]:
            gnid = f"g-{genre}"
            if gnid not in seen_nodes:
                nodes.append({"id": gnid, "label": genre, "type": "genre", "size": 6, "play_count": 0})
                seen_nodes.add(gnid)
            links.append({"source": nid, "target": gnid, "type": "genre", "weight": 0.5})

    # Add recommended artists (similar to played, but not yet played by this user)
    for artist_id in list(played_ids):
        sims = db.query(ArtistSimilarity).filter(
            ArtistSimilarity.artist_a_id == artist_id,
            ArtistSimilarity.score >= 0.3,   # only include strong similarity (≥30%)
        ).order_by(ArtistSimilarity.score.desc()).limit(3).all()  # top 3 similar per played artist

        for sim in sims:
            if sim.artist_b_id in played_ids:
                continue   # already played — already in the graph
            sim_artist = db.query(MusicArtist).get(sim.artist_b_id)
            if not sim_artist:
                continue
            snid = f"a-{sim_artist.id}"
            if snid not in seen_nodes:
                primary_genre = (sim_artist.genres or ["?"])[0]
                nodes.append({"id": snid, "label": sim_artist.name, "type": "recommended",
                              "genre": primary_genre, "size": 6, "play_count": 0})
                seen_nodes.add(snid)
            # Edge: known artist → recommended artist (shows the connection)
            links.append({"source": f"a-{artist_id}", "target": snid,
                          "type": "similar", "weight": sim.score})

    return {"nodes": nodes, "links": links}


# =============================================================================
# RECOMMENDATIONS
# =============================================================================

def get_recommendations(user_id: str, db: Session) -> list[dict]:
    """
    Hybrid recommendation system combining two signals:

    PATH 1 — Content-based (graph hop):
      For each artist you've played, find similar unheard artists via
      artist_similarity edges. Score = similarity × log(how much you
      played the source artist). More listening → stronger signal.

    PATH 2 — Collaborative filtering:
      Find other users whose taste vector (genre weights) is similar to yours.
      Recommend what THEY listen to that you haven't heard yet.
      Score scaled by peer similarity (0–1) × their play count × 0.8.

    Both paths add to the same candidates dict — scores accumulate across
    paths so an artist recommended by BOTH paths scores higher and rises
    to the top.

    Returns the top 10 candidates, sorted by combined score.
    """
    # Build current user's play history and taste vector
    user_stats  = {s.artist_id: s.play_count for s in
                   db.query(UserArtistStat).filter(UserArtistStat.user_id == user_id).all()}
    played_ids  = set(user_stats.keys())
    user_vec    = _taste_vector(user_id, db)

    candidates: dict[str, dict] = {}  # artist_id → {"score": float, "reasons": [str]}

    # ── Path 1: graph hop via similarity edges ──
    for artist_id, play_count in user_stats.items():
        sims = db.query(ArtistSimilarity).filter(
            ArtistSimilarity.artist_a_id == artist_id,
            ArtistSimilarity.score >= 0.2,  # minimum meaningful similarity
        ).order_by(ArtistSimilarity.score.desc()).limit(5).all()

        source_artist = db.query(MusicArtist).get(artist_id)
        for sim in sims:
            if sim.artist_b_id in played_ids:
                continue  # skip artists already in the user's history
            score  = sim.score * math.log1p(play_count)  # stronger if you play the source a lot
            reason = f"Similar to {source_artist.name if source_artist else '?'} which you play a lot"
            if sim.artist_b_id not in candidates:
                candidates[sim.artist_b_id] = {"score": score, "reasons": [reason]}
            else:
                candidates[sim.artist_b_id]["score"] += score
                candidates[sim.artist_b_id]["reasons"].append(reason)

    # ── Path 2: collaborative filtering ──
    # Get all other users who have any listening history
    all_user_ids = [
        r[0] for r in db.execute(
            text("SELECT DISTINCT user_id FROM user_artist_stats WHERE user_id != :uid"),
            {"uid": user_id}
        ).fetchall()
    ]

    # Find peers with similar taste (cosine similarity > 0.2)
    best_peers: list[tuple[str, float]] = []
    for other_id in all_user_ids:
        other_vec = _taste_vector(other_id, db)
        sim = _cosine(user_vec, other_vec)
        if sim > 0.2:
            best_peers.append((other_id, sim))

    # Sort by similarity, take top 5 peers
    best_peers.sort(key=lambda x: x[1], reverse=True)

    for peer_id, peer_sim in best_peers[:5]:
        peer_stats = db.query(UserArtistStat).filter(UserArtistStat.user_id == peer_id).all()
        for stat in peer_stats:
            if stat.artist_id in played_ids:
                continue  # don't recommend what the user already knows
            score  = peer_sim * math.log1p(stat.play_count) * 0.8  # 0.8 discount vs content-based
            reason = "Loved by users with taste similar to yours"
            if stat.artist_id not in candidates:
                candidates[stat.artist_id] = {"score": score, "reasons": [reason]}
            else:
                candidates[stat.artist_id]["score"] += score

    # Sort all candidates by combined score, return top 10
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
            "reason":      data["reasons"][0],  # show the strongest reason
        })

    return recs


# =============================================================================
# SEED GENRE / ARTIST HELPERS (used by onboarding UI)
# =============================================================================

def get_all_genres() -> list[str]:
    """Return the list of genre names for the onboarding genre picker."""
    return SEED_GENRES


def get_seed_artists_by_genre() -> dict:
    """
    Return {genre: [artist_name, ...]} for the onboarding artist picker.
    Strips out the internal 'related' metadata — the frontend only needs names.
    """
    return {
        genre: [a["name"] for a in artists]
        for genre, artists in SEED_ARTISTS_BY_GENRE.items()
    }
