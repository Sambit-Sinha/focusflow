from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.db.database import Base


def gen_uuid():
    return str(uuid.uuid4())


class MusicArtist(Base):
    __tablename__ = "music_artists"

    id       = Column(String, primary_key=True, default=gen_uuid)
    name     = Column(String(300), nullable=False, unique=True, index=True)
    genres   = Column(JSON, default=list)   # ["Pop", "R&B"]
    is_seed  = Column(String(5), default="true")  # "true" = from our seed list

    song_stats   = relationship("UserSongStat",   back_populates="artist", cascade="all, delete-orphan")
    artist_stats = relationship("UserArtistStat", back_populates="artist", cascade="all, delete-orphan")
    similar_a    = relationship("ArtistSimilarity", foreign_keys="ArtistSimilarity.artist_a_id", back_populates="artist_a", cascade="all, delete-orphan")
    similar_b    = relationship("ArtistSimilarity", foreign_keys="ArtistSimilarity.artist_b_id", back_populates="artist_b", cascade="all, delete-orphan")


class MusicSong(Base):
    __tablename__ = "music_songs"

    id          = Column(String, primary_key=True, default=gen_uuid)
    name        = Column(String(500), nullable=False)
    artist_id   = Column(String, ForeignKey("music_artists.id", ondelete="SET NULL"), nullable=True)
    artist_name = Column(String(300), nullable=False)
    year        = Column(Integer, nullable=True)
    genres      = Column(JSON, default=list)
    mbid        = Column(String(50), nullable=True)  # MusicBrainz recording ID

    stats = relationship("UserSongStat", back_populates="song", cascade="all, delete-orphan")


class UserArtistStat(Base):
    """Edge: User → Artist with play_count as weight."""
    __tablename__ = "user_artist_stats"

    user_id     = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    artist_id   = Column(String, ForeignKey("music_artists.id", ondelete="CASCADE"), primary_key=True)
    play_count  = Column(Integer, default=1)
    last_played = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    artist = relationship("MusicArtist", back_populates="artist_stats")


class UserSongStat(Base):
    """Edge: User → Song with play_count as weight."""
    __tablename__ = "user_song_stats"

    user_id     = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    song_id     = Column(String, ForeignKey("music_songs.id", ondelete="CASCADE"), primary_key=True)
    artist_id   = Column(String, ForeignKey("music_artists.id", ondelete="SET NULL"), nullable=True)
    play_count  = Column(Integer, default=1)
    last_played = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    song   = relationship("MusicSong",   back_populates="stats")
    artist = relationship("MusicArtist", back_populates="song_stats")


class ArtistSimilarity(Base):
    """Edge: Artist ↔ Artist similarity score (0–1)."""
    __tablename__ = "artist_similarity"

    artist_a_id = Column(String, ForeignKey("music_artists.id", ondelete="CASCADE"), primary_key=True)
    artist_b_id = Column(String, ForeignKey("music_artists.id", ondelete="CASCADE"), primary_key=True)
    score       = Column(Float, default=0.0)  # 0–1, higher = more similar

    artist_a = relationship("MusicArtist", foreign_keys=[artist_a_id], back_populates="similar_a")
    artist_b = relationship("MusicArtist", foreign_keys=[artist_b_id], back_populates="similar_b")
