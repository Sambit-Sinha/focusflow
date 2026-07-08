from pydantic import BaseModel
from typing import Optional, List, Any


class ArtistOut(BaseModel):
    id: str
    name: str
    genres: List[str] = []
    play_count: int = 0
    model_config = {"from_attributes": True}


class SongOut(BaseModel):
    id: str
    name: str
    artist_id: Optional[str] = None
    artist_name: str
    year: Optional[int] = None
    genres: List[str] = []
    play_count: int = 0
    model_config = {"from_attributes": True}


class LogPlayRequest(BaseModel):
    song_name: str
    artist_name: str
    year: Optional[int] = None
    genres: List[str] = []
    mbid: Optional[str] = None       # MusicBrainz recording ID


class SetPreferencesRequest(BaseModel):
    artist_names: List[str]          # selected from seed list


class GraphNode(BaseModel):
    id: str
    label: str
    type: str        # "user" | "artist" | "genre"
    genre: Optional[str] = None
    size: float = 10
    play_count: int = 0


class GraphLink(BaseModel):
    source: str
    target: str
    type: str        # "played" | "genre" | "similar" | "peer"
    weight: float = 1.0


class GraphData(BaseModel):
    nodes: List[GraphNode]
    links: List[GraphLink]


class RecommendationItem(BaseModel):
    artist_id: str
    artist_name: str
    genres: List[str]
    score: float
    reason: str      # human-readable explanation


class MBZSearchResult(BaseModel):
    mbid: str
    name: str
    artist_name: str
    year: Optional[int] = None
