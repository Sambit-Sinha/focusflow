# =============================================================================
# music_models.py — Database tables for the music knowledge graph.
#
# The music feature is built around a graph data structure:
#   Nodes: Users, Artists, Genres (genres are virtual — not their own table)
#   Edges: User→Artist (user_artist_stats), Artist↔Artist (artist_similarity)
#
# This is a simplified version of what Spotify/Last.fm do internally.
# Instead of millions of listeners, we have a small personal graph per user.
#
# Data Science parallel: think of this as an adjacency-list representation
# of a weighted directed graph, stored in SQL tables.
# user_artist_stats.play_count is the edge weight: User → Artist.
# artist_similarity.score is the edge weight: Artist ↔ Artist.
# =============================================================================

from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.db.database import Base


def gen_uuid():
    return str(uuid.uuid4())


class MusicArtist(Base):
    """
    A music artist node in the graph.

    genres is stored as a JSON array (["Pop", "R&B"]) rather than a separate
    genres table to keep queries simple. We don't need to query "give me all
    artists with genre X" frequently — the genre list is mainly used to compute
    artist similarity scores during seeding.

    is_seed marks whether the artist came from our hand-picked seed list
    (music_seed.py) or was added by a user logging their own plays.
    """
    __tablename__ = "music_artists"

    id      = Column(String, primary_key=True, default=gen_uuid)
    name    = Column(String(300), nullable=False, unique=True, index=True)
    genres  = Column(JSON, default=list)    # ["Pop", "R&B", "Soul"]
    is_seed = Column(String(5), default="true")  # "true" or "false"

    # These relationships let SQLAlchemy load related rows automatically.
    # For example: artist.artist_stats gives all UserArtistStat rows for this artist.
    song_stats   = relationship("UserSongStat",   back_populates="artist", cascade="all, delete-orphan")
    artist_stats = relationship("UserArtistStat", back_populates="artist", cascade="all, delete-orphan")

    # ArtistSimilarity has TWO foreign keys pointing to music_artists (artist_a and artist_b).
    # SQLAlchemy needs foreign_keys=[...] to know which FK each relationship uses.
    similar_a = relationship("ArtistSimilarity", foreign_keys="ArtistSimilarity.artist_a_id", back_populates="artist_a", cascade="all, delete-orphan")
    similar_b = relationship("ArtistSimilarity", foreign_keys="ArtistSimilarity.artist_b_id", back_populates="artist_b", cascade="all, delete-orphan")


class MusicSong(Base):
    """
    A song that a user has logged a play for.

    Songs are not pre-seeded — they're added to this table the first time
    any user logs a play for them (via the Log a Listen button).

    mbid = MusicBrainz recording ID. MusicBrainz is a free, open music
    database (like Wikipedia for music). The ID lets us uniquely identify
    a specific recording (not just any song with that title).
    """
    __tablename__ = "music_songs"

    id          = Column(String, primary_key=True, default=gen_uuid)
    name        = Column(String(500), nullable=False)

    # artist_id can be NULL (ON DELETE SET NULL) — if the artist row is
    # deleted, the song stays but loses its artist_id link. We keep artist_name
    # as a plain string for exactly this fallback: we can still show the name
    # even if the foreign key is gone.
    artist_id   = Column(String, ForeignKey("music_artists.id", ondelete="SET NULL"), nullable=True)
    artist_name = Column(String(300), nullable=False)

    year   = Column(Integer, nullable=True)
    genres = Column(JSON, default=list)
    mbid   = Column(String(50), nullable=True)

    stats = relationship("UserSongStat", back_populates="song", cascade="all, delete-orphan")


class UserArtistStat(Base):
    """
    Edge: User → Artist (with weight = play_count).

    This is the primary signal for recommendations. The more a user plays
    an artist, the stronger the edge, and the more that artist's genre
    fingerprint influences what gets recommended.

    PRIMARY KEY (user_id, artist_id) enforces one row per pair. When the
    user plays the artist again, we UPDATE play_count += 1 rather than
    INSERT a new row.
    """
    __tablename__ = "user_artist_stats"

    user_id     = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    artist_id   = Column(String, ForeignKey("music_artists.id", ondelete="CASCADE"), primary_key=True)
    play_count  = Column(Integer, default=1)
    # onupdate=func.now() automatically updates this timestamp whenever
    # the row is modified — so last_played stays accurate without manual code.
    last_played = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    artist = relationship("MusicArtist", back_populates="artist_stats")


class UserSongStat(Base):
    """
    Edge: User → Song (with weight = play_count).

    Tracks which specific songs a user has listened to and how many times.
    Used for the "Your Stats" panel (top songs list).
    """
    __tablename__ = "user_song_stats"

    user_id     = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    song_id     = Column(String, ForeignKey("music_songs.id", ondelete="CASCADE"), primary_key=True)
    artist_id   = Column(String, ForeignKey("music_artists.id", ondelete="SET NULL"), nullable=True)
    play_count  = Column(Integer, default=1)
    last_played = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    song   = relationship("MusicSong",   back_populates="stats")
    artist = relationship("MusicArtist", back_populates="song_stats")


class ArtistSimilarity(Base):
    """
    Edge: Artist ↔ Artist (with weight = similarity score 0–1).

    Stored in BOTH directions (A→B and B→A) so queries are always
    "give me all artists similar to X" with a simple filter on artist_a_id,
    rather than needing to check both columns.

    Score is computed from shared genres (Jaccard similarity) + a boost if
    the artists appear in each other's "related" list in music_seed.py.

    Score 1.0 = identical genre fingerprint.
    Score 0.0 = no genres in common.
    Edges below 0.05 are not stored to keep the graph sparse.
    """
    __tablename__ = "artist_similarity"

    artist_a_id = Column(String, ForeignKey("music_artists.id", ondelete="CASCADE"), primary_key=True)
    artist_b_id = Column(String, ForeignKey("music_artists.id", ondelete="CASCADE"), primary_key=True)
    score       = Column(Float, default=0.0)

    artist_a = relationship("MusicArtist", foreign_keys=[artist_a_id], back_populates="similar_a")
    artist_b = relationship("MusicArtist", foreign_keys=[artist_b_id], back_populates="similar_b")
