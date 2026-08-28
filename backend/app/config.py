import os
from dataclasses import dataclass, field


def _bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    # Storage
    database_url: str = os.environ.get("DATABASE_URL", "sqlite:///./data/traffic.db")

    # Camera source
    # "mock"  -> synthetic camera list + synthetic vehicle motion, zero external deps
    # "live"  -> real DDOT MQTT camera registry + real video pulled per camera
    camera_mode: str = os.environ.get("CAMERA_MODE", "mock")

    # DDOT's public MQTT broker (an AWS Amazon MQ instance, MQTT-over-WebSocket
    # on port 61619). Host, port, transport, topic name, and credentials below
    # are verified against the source of the community ddotcli tool
    # (https://github.com/a10y/ddotcli/blob/master/pkg/ddot/ddot.go) -- the
    # username/password are published there as a public feed, not a secret.
    ddot_mqtt_host: str = os.environ.get(
        "DDOT_MQTT_HOST", "b-8c165eea-0974-40be-9e62-ad394d480541-1.mq.us-east-1.amazonaws.com"
    )
    ddot_mqtt_port: int = int(os.environ.get("DDOT_MQTT_PORT", "61619"))
    ddot_mqtt_transport: str = os.environ.get("DDOT_MQTT_TRANSPORT", "websockets")
    ddot_mqtt_ws_path: str = os.environ.get("DDOT_MQTT_WS_PATH", "/")
    ddot_mqtt_username: str = os.environ.get("DDOT_MQTT_USERNAME", "dcdot")
    ddot_mqtt_password: str = os.environ.get("DDOT_MQTT_PASSWORD", "cctvddotpublic")
    ddot_mqtt_camera_topic: str = os.environ.get("DDOT_MQTT_CAMERA_TOPIC", "DDOT/Camera")
    # Unlike the camera topic above, this one is *not* confirmed against
    # ddotcli's source -- it only appeared in secondary descriptions of the
    # feed. Treat DDOT-sourced ("external") incidents as best-effort.
    ddot_mqtt_incident_topic: str = os.environ.get("DDOT_MQTT_INCIDENT_TOPIC", "DDOT/Incidents")

    # Detection model (only used when camera_mode == "live")
    yolo_model: str = os.environ.get("YOLO_MODEL", "yolov8n.pt")
    detection_confidence: float = float(os.environ.get("DETECTION_CONFIDENCE", "0.35"))
    frame_sample_seconds: float = float(os.environ.get("FRAME_SAMPLE_SECONDS", "1.0"))

    # Snaps each camera's simulated vehicle motion to the nearest real street
    # (OpenStreetMap via Overpass), instead of a straight synthetic line.
    # Best-effort: any fetch failure just leaves those cameras on the
    # straight-line fallback, so this is safe to leave on everywhere.
    road_snap_enabled: bool = _bool("ROAD_SNAP_ENABLED", True)
    road_snap_radius_m: float = float(os.environ.get("ROAD_SNAP_RADIUS_M", "150"))
    road_snap_timeout_s: float = float(os.environ.get("ROAD_SNAP_TIMEOUT_S", "30"))
    # Persisted alongside the database (same volume in production) so a
    # redeploy doesn't need to re-query Overpass for cameras already matched.
    road_cache_path: str = os.environ.get("ROAD_CACHE_PATH", "./data/road_cache.json")

    # How many cameras to run pipelines for at once (keeps CPU/GPU load bounded)
    max_active_cameras: int = int(os.environ.get("MAX_ACTIVE_CAMERAS", "12"))

    # Congestion thresholds: vehicles observed within a camera's footprint
    congestion_light_threshold: int = int(os.environ.get("CONGESTION_LIGHT_THRESHOLD", "4"))
    congestion_moderate_threshold: int = int(os.environ.get("CONGESTION_MODERATE_THRESHOLD", "9"))
    congestion_heavy_threshold: int = int(os.environ.get("CONGESTION_HEAVY_THRESHOLD", "16"))

    # Incident detection: how far a metric must deviate from its rolling baseline
    incident_speed_drop_ratio: float = float(os.environ.get("INCIDENT_SPEED_DROP_RATIO", "0.4"))
    incident_count_spike_ratio: float = float(os.environ.get("INCIDENT_COUNT_SPIKE_RATIO", "2.0"))

    # History retention for raw samples (aggregation keeps longer)
    history_sample_interval_seconds: int = int(os.environ.get("HISTORY_SAMPLE_INTERVAL_SECONDS", "5"))

    cors_origins: list[str] = field(default_factory=lambda: os.environ.get(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(","))


settings = Settings()
