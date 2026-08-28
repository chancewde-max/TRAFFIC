import { useEffect, useMemo, useRef, useState } from "react";

import type { Camera, Congestion, Incident, LiveMessage, VehiclePosition } from "../types";
import { WS_BASE } from "./client";

interface TrackState {
  camera_id: string;
  track_id: number;
  vehicle_class: string;
  heading_deg: number;
  fromLat: number;
  fromLon: number;
  toLat: number;
  toLon: number;
  fromTs: number;
  toTs: number;
}

const ANIMATION_FPS = 20;
// Assumed spacing between two vehicle-batch updates for the same camera; used
// to interpolate smooth motion between the (roughly 0.5-1s apart) samples we
// actually receive from the backend.
const INTERP_WINDOW_MS = 900;

export function useLiveFeed() {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [congestionByCamera, setCongestionByCamera] = useState<Record<string, Congestion>>({});
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [connected, setConnected] = useState(false);
  const [tick, setTick] = useState(0);

  const tracksRef = useRef<Map<string, TrackState>>(new Map());

  useEffect(() => {
    let cancelled = false;
    let retryDelay = 1000;
    let ws: WebSocket | null = null;

    function connect() {
      ws = new WebSocket(`${WS_BASE}/ws/live`);

      ws.onopen = () => {
        retryDelay = 1000;
        setConnected(true);
      };

      ws.onmessage = (ev: MessageEvent<string>) => {
        const msg: LiveMessage = JSON.parse(ev.data);

        if (msg.type === "init") {
          setCameras(msg.cameras);
          setCongestionByCamera(Object.fromEntries(msg.congestion.map((c) => [c.camera_id, c])));
          setIncidents(msg.incidents);
        } else if (msg.type === "vehicles") {
          const now = performance.now();
          const seen = new Set<string>();
          for (const p of msg.positions) {
            const key = `${p.camera_id}:${p.track_id}`;
            seen.add(key);
            const prev = tracksRef.current.get(key);
            tracksRef.current.set(key, {
              camera_id: p.camera_id,
              track_id: p.track_id,
              vehicle_class: p.vehicle_class,
              heading_deg: p.heading_deg,
              fromLat: prev ? prev.toLat : p.lat,
              fromLon: prev ? prev.toLon : p.lon,
              toLat: p.lat,
              toLon: p.lon,
              fromTs: now,
              toTs: now + INTERP_WINDOW_MS,
            });
          }
          for (const [key, tr] of tracksRef.current) {
            if (tr.camera_id === msg.camera_id && !seen.has(key)) {
              tracksRef.current.delete(key);
            }
          }
        } else if (msg.type === "congestion") {
          setCongestionByCamera((prev) => ({ ...prev, [msg.camera_id]: msg }));
        } else if (msg.type === "incident") {
          setIncidents((prev) => [msg, ...prev].slice(0, 100));
        }
      };

      ws.onclose = () => {
        setConnected(false);
        if (cancelled) return;
        setTimeout(connect, retryDelay);
        retryDelay = Math.min(retryDelay * 1.5, 10000);
      };

      ws.onerror = () => ws?.close();
    }

    connect();

    let raf = 0;
    let lastFrame = 0;
    const frameInterval = 1000 / ANIMATION_FPS;
    function loop(now: number) {
      if (now - lastFrame >= frameInterval) {
        lastFrame = now;
        setTick((t) => t + 1);
      }
      raf = requestAnimationFrame(loop);
    }
    raf = requestAnimationFrame(loop);

    return () => {
      cancelled = true;
      ws?.close();
      cancelAnimationFrame(raf);
    };
  }, []);

  const animatedVehicles = useMemo<VehiclePosition[]>(() => {
    const now = performance.now();
    const out: VehiclePosition[] = [];
    for (const tr of tracksRef.current.values()) {
      const span = Math.max(1, tr.toTs - tr.fromTs);
      const t = Math.min(1, Math.max(0, (now - tr.fromTs) / span));
      out.push({
        camera_id: tr.camera_id,
        track_id: tr.track_id,
        lat: tr.fromLat + (tr.toLat - tr.fromLat) * t,
        lon: tr.fromLon + (tr.toLon - tr.fromLon) * t,
        heading_deg: tr.heading_deg,
        speed_mps: null,
        vehicle_class: tr.vehicle_class,
      });
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tick]);

  return { cameras, congestionByCamera, incidents, animatedVehicles, connected };
}
