"""Client for DDOT's public MQTT broker.

DDOT (District Department of Transportation) runs a live camera/incident feed
on a public AWS Amazon MQ instance over MQTT-over-WebSocket (wss://, port
61619). The broker host, transport, topic name, and credentials below are
verified against the source of the community-maintained ddotcli project
(https://github.com/a10y/ddotcli/blob/master/pkg/ddot/ddot.go) -- the
username/password are published there as a public feed, not a private secret.

This module is optional: if paho-mqtt isn't installed, or the broker can't be
reached (outbound access to it may simply be blocked by network policy in a
given environment), callers fall back to the bundled seed camera list.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
from typing import Any
from urllib.parse import urlparse

from .config import settings

logger = logging.getLogger(__name__)

try:
    import paho.mqtt.client as mqtt
except ImportError:  # pragma: no cover - optional dependency
    mqtt = None


def _new_client() -> "mqtt.Client":
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        transport=settings.ddot_mqtt_transport,
    )
    client.username_pw_set(settings.ddot_mqtt_username, settings.ddot_mqtt_password)
    client.tls_set()
    if settings.ddot_mqtt_transport == "websockets":
        client.ws_set_options(path=settings.ddot_mqtt_ws_path)

    # Best-effort: route through an HTTP CONNECT proxy if one is configured
    # (e.g. HTTPS_PROXY) and PySocks is installed. paho-mqtt's raw sockets
    # otherwise bypass HTTP(S)_PROXY entirely, which fails outright in
    # environments that only permit egress through such a proxy.
    proxy_url = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if proxy_url:
        try:
            import socks

            parsed = urlparse(proxy_url)
            client.proxy_set(
                proxy_type=socks.HTTP,
                proxy_addr=parsed.hostname,
                proxy_port=parsed.port or 443,
            )
        except ImportError:
            logger.debug("HTTPS_PROXY set but PySocks not installed; connecting directly")

    return client


def _parse_camera_payload(data: Any) -> list[dict[str, Any]] | None:
    """The real DDOT/Camera payload is a JSON object keyed by small integer
    strings ("0", "1", ...), each value describing one camera. Also accepts a
    plain list, defensively, in case the shape ever changes."""

    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        entries = [v for k, v in data.items() if isinstance(v, dict)]
        return entries or None
    return None


def fetch_camera_snapshot(timeout: float = 10.0) -> list[dict[str, Any]] | None:
    """Connect briefly, wait for one payload on the camera topic, disconnect."""

    if mqtt is None:
        return None

    result_q: "queue.Queue[list[dict]]" = queue.Queue(maxsize=1)

    def on_connect(client, userdata, flags, rc, properties=None):
        if rc == 0:
            client.subscribe(settings.ddot_mqtt_camera_topic)
        else:
            logger.warning("DDOT MQTT connect failed with rc=%s", rc)

    def on_message(client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return
        cameras = _parse_camera_payload(data)
        if cameras:
            try:
                result_q.put_nowait(cameras)
            except queue.Full:
                pass

    client = _new_client()
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(settings.ddot_mqtt_host, settings.ddot_mqtt_port, keepalive=30)
    except Exception:
        logger.exception("Failed to connect to DDOT MQTT broker")
        return None

    client.loop_start()
    try:
        return result_q.get(timeout=timeout)
    except queue.Empty:
        return None
    finally:
        client.loop_stop()
        client.disconnect()


class IncidentListener:
    """Runs a background thread subscribed to DDOT's incident topic and pushes
    parsed incident dicts onto a thread-safe queue for the async worker to
    drain. Best-effort: the incident topic name isn't confirmed the way the
    camera topic is (see config.py)."""

    def __init__(self) -> None:
        self.queue: "queue.Queue[dict]" = queue.Queue()
        self._client = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if mqtt is None:
            return

        def on_connect(client, userdata, flags, rc, properties=None):
            if rc == 0:
                client.subscribe(settings.ddot_mqtt_incident_topic)

        def on_message(client, userdata, msg):
            try:
                data = json.loads(msg.payload.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return
            self.queue.put(data)

        self._client = _new_client()
        self._client.on_connect = on_connect
        self._client.on_message = on_message
        try:
            self._client.connect(settings.ddot_mqtt_host, settings.ddot_mqtt_port, keepalive=30)
        except Exception:
            logger.exception("Failed to connect to DDOT MQTT broker for incidents")
            return
        self._thread = threading.Thread(target=self._client.loop_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._client is not None:
            self._client.disconnect()
