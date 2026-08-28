import datetime as dt

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from .db import Base


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Camera(Base):
    __tablename__ = "cameras"

    id = Column(String, primary_key=True)  # DDOT camera id, or "seed-###" for fallback data
    name = Column(String, nullable=False)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    bearing_deg = Column(Float, nullable=False, default=0.0)  # compass heading the camera faces
    stream_url = Column(String, nullable=True)  # HLS playlist, when known
    snapshot_url = Column(String, nullable=True)
    source = Column(String, nullable=False, default="seed")  # "ddot_mqtt" | "seed"
    active = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    congestion_samples = relationship("CongestionSample", back_populates="camera")
    incidents = relationship("Incident", back_populates="camera")


class VehicleTrackSample(Base):
    """A single tracked-vehicle observation, sampled at HISTORY_SAMPLE_INTERVAL_SECONDS.

    We persist samples (not every raw frame) to keep the history table small while
    still supporting per-camera trend charts. Live per-frame positions are streamed
    over the WebSocket and are not all persisted.
    """

    __tablename__ = "vehicle_track_samples"

    id = Column(Integer, primary_key=True, autoincrement=True)
    camera_id = Column(String, ForeignKey("cameras.id"), nullable=False, index=True)
    track_id = Column(Integer, nullable=False)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    speed_mps = Column(Float, nullable=True)
    vehicle_class = Column(String, nullable=False, default="car")
    ts = Column(DateTime(timezone=True), default=utcnow, index=True)


class CongestionSample(Base):
    __tablename__ = "congestion_samples"

    id = Column(Integer, primary_key=True, autoincrement=True)
    camera_id = Column(String, ForeignKey("cameras.id"), nullable=False, index=True)
    vehicle_count = Column(Integer, nullable=False)
    avg_speed_mps = Column(Float, nullable=True)
    level = Column(String, nullable=False)  # free | light | moderate | heavy
    ts = Column(DateTime(timezone=True), default=utcnow, index=True)

    camera = relationship("Camera", back_populates="congestion_samples")


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    camera_id = Column(String, ForeignKey("cameras.id"), nullable=False, index=True)
    kind = Column(String, nullable=False)  # speed_drop | count_spike | external
    severity = Column(String, nullable=False, default="minor")  # minor | major
    description = Column(String, nullable=False)
    ts = Column(DateTime(timezone=True), default=utcnow, index=True)

    camera = relationship("Camera", back_populates="incidents")
