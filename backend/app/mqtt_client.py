"""Thin client for DDOT's public MQTT broker.

DDOT (District Department of Transportation) publishes a live camera/incident
feed over MQTT for public consumption. The broker address and credentials
below are the ones documented by the community-maintained ddotcli project
(https://github.com/a10y/ddotcli); the username/password are published in
plaintext there as a public feed, not a private secret.

This module is optional: if paho-mqtt isn't installed, or the broker can't be
reached (e.g. outbound MQTT is blocked by network policy), callers fall back
to the bundled seed camera list. Set DDOT_MQTT_HOST to enable this for real.
"""

from __future__ import annotations

import json
import queue
import threading
from typing import Any

from .config import settings

try:
    import paho.mqtt.client as mqtt
except ImportError:  # pragma: no cover - optional dependency
    mqtt = None


def fetch_camera_snapshot(timeout: float = 8.0) -> list[dict[str, Any]] | None:
    """Connect briefly, wait for one payload on the camera topic, disconnect."""

    if mqtt is None or not settings.ddot_mqtt_host:
        return None

    result_q: "queue.Queue[list[dict]]" = queue.Queue(maxsize=1)

    def on_connect(client, userdata, flags, rc, properties=None):
        if rc == 0:
            client.subscribe(settings.ddot_mqtt_camera_topic)

    def on_message(client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return
        cameras = data if isinstance(data, list) else data.get("cameras", data.get("Cameras"))
        if cameras:
            try:
                result_q.put_nowait(cameras)
            except queue.Full:
                pass

    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(settings.ddot_mqtt_username, settings.ddot_mqtt_password)
    client.tls_set()
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect_async(settings.ddot_mqtt_host, settings.ddot_mqtt_port, keepalive=30)
    client.loop_start()
    try:
        return result_q.get(timeout=timeout)
    except queue.Empty:
        return None
    finally:
        client.loop_stop()
        client.disconnect()


class IncidentListener:
    """Runs a background thread subscribed to DDOT/Incidents and pushes parsed
    incident dicts onto a thread-safe queue for the async worker to drain."""

    def __init__(self) -> None:
        self.queue: "queue.Queue[dict]" = queue.Queue()
        self._client = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if mqtt is None or not settings.ddot_mqtt_host:
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

        self._client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self._client.username_pw_set(settings.ddot_mqtt_username, settings.ddot_mqtt_password)
        self._client.tls_set()
        self._client.on_connect = on_connect
        self._client.on_message = on_message
        self._client.connect_async(settings.ddot_mqtt_host, settings.ddot_mqtt_port, keepalive=30)
        self._thread = threading.Thread(target=self._client.loop_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._client is not None:
            self._client.disconnect()
