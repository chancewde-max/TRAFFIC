import datetime as dt

from pydantic import BaseModel, ConfigDict


class CameraOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    lat: float
    lon: float
    bearing_deg: float
    stream_url: str | None
    snapshot_url: str | None
    source: str
    active: int


class VehiclePosition(BaseModel):
    """Live per-frame vehicle position, streamed over WebSocket (not persisted per-frame)."""

    camera_id: str
    track_id: int
    lat: float
    lon: float
    heading_deg: float
    speed_mps: float | None = None
    vehicle_class: str = "car"


class CongestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    camera_id: str
    vehicle_count: int
    avg_speed_mps: float | None
    level: str
    ts: dt.datetime


class IncidentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    camera_id: str
    kind: str
    severity: str
    description: str
    ts: dt.datetime


class HistoryPoint(BaseModel):
    ts: dt.datetime
    vehicle_count: float
    avg_speed_mps: float | None
