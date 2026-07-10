# =============================================================================
# music_schemas.py — Pydantic schemas for the music knowledge graph API.
#
# These define what JSON the music endpoints accept and return.
# See schemas.py for a general explanation of why schemas exist separately
# from ORM models.
# =============================================================================

from pydantic import BaseModel
from typing import Optional, List, Any


class ArtistOut(BaseModel):
    """Artist data sent to the frontend for display in lists and the graph."""
    id:         str
    name:       str
    genres:     List[str] = []
    play_count: int = 0
    model_config = {"from_attributes": True}


class SongOut(BaseModel):
    """Song data including which artist it belongs to and how many times played."""
    id:          str
    name:        str
    artist_id:   Optional[str] = None
    artist_name: str
    year:        Optional[int] = None
    genres:      List[str] = []
    play_count:  int = 0
    model_config = {"from_attributes": True}


class LogPlayRequest(BaseModel):
    """
    Sent when the user clicks "Log a Listen" for a song.

    We need the full song + artist info because we might need to create
    new rows in music_artists and music_songs if this is the first time
    this song/artist has been logged by anyone.

    mbid is the MusicBrainz recording ID — a globally unique ID for a
    specific recorded version of a song. Comes from the MusicBrainz search
    results shown in the "Log a Listen" UI.
    """
    song_name:   str
    artist_name: str
    year:        Optional[int] = None
    genres:      List[str] = []
    mbid:        Optional[str] = None


class SetPreferencesRequest(BaseModel):
    """
    Sent during onboarding when the user selects their favourite artists.
    Each name in the list gets inserted as a UserArtistStat row (play_count=1)
    so the recommendation engine has something to work with immediately.
    """
    artist_names: List[str]


# =============================================================================
# GRAPH DATA SCHEMAS
# Used by the D3.js force-directed graph visualisation on the Music tab.
# =============================================================================

class GraphNode(BaseModel):
    """
    One node in the graph.

    type controls colour/shape in the frontend:
      "user"        → the central "You" node
      "artist"      → an artist the user has played
      "genre"       → a genre tag node
      "recommended" → an artist suggested by the recommendation engine
    """
    id:         str
    label:      str
    type:       str
    genre:      Optional[str] = None  # primary genre (for colouring the node)
    size:       float = 10            # visual size — larger = more plays
    play_count: int = 0


class GraphLink(BaseModel):
    """
    One edge (connection) between two nodes.

    type controls how the edge is drawn (dashed, solid, colour, etc.):
      "played"   → User listened to this Artist
      "genre"    → Artist belongs to this Genre
      "similar"  → two Artists share genre fingerprint
      "peer"     → two Users have similar taste (collaborative filtering)
    """
    source: str    # node id
    target: str    # node id
    type:   str
    weight: float = 1.0  # line thickness in the visualisation


class GraphData(BaseModel):
    """Container returned by GET /music/{user_id}/graph."""
    nodes: List[GraphNode]
    links: List[GraphLink]


class RecommendationItem(BaseModel):
    """
    One recommended artist, as returned by GET /music/{user_id}/recommendations.

    reason is a human-readable sentence explaining WHY this was recommended
    (e.g., "Similar to Taylor Swift which you play a lot"). This is shown
    in the UI so the recommendation doesn't feel like a black box.
    """
    artist_id:   str
    artist_name: str
    genres:      List[str]
    score:       float   # higher = stronger recommendation
    reason:      str


class MBZSearchResult(BaseModel):
    """One result from the MusicBrainz song search proxy endpoint."""
    mbid:        str
    name:        str
    artist_name: str
    year:        Optional[int] = None
