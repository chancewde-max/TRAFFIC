import { useEffect, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { api } from "../api/client";
import type { HistoryPoint } from "../types";

interface Props {
  cameraId: string | null;
}

const REFRESH_MS = 15_000;

export default function HistoryChart({ cameraId }: Props) {
  const [points, setPoints] = useState<HistoryPoint[]>([]);

  useEffect(() => {
    if (!cameraId) {
      setPoints([]);
      return;
    }

    let cancelled = false;

    async function load() {
      try {
        const data = await api.history(cameraId!, 3);
        if (!cancelled) setPoints(data);
      } catch {
        // history is a nice-to-have; ignore transient errors
      }
    }

    load();
    const interval = setInterval(load, REFRESH_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [cameraId]);

  if (!cameraId) {
    return <p className="empty-hint">Select a camera to see its recent trend.</p>;
  }

  if (points.length < 2) {
    return <p className="empty-hint">Collecting history for this camera…</p>;
  }

  const data = points.map((p) => ({
    time: new Date(p.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    vehicles: p.vehicle_count,
  }));

  return (
    <ResponsiveContainer width="100%" height={140}>
      <LineChart data={data} margin={{ top: 4, right: 8, left: -24, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1f2b38" />
        <XAxis dataKey="time" tick={{ fontSize: 10, fill: "#8b98a5" }} minTickGap={30} />
        <YAxis tick={{ fontSize: 10, fill: "#8b98a5" }} allowDecimals={false} />
        <Tooltip
          contentStyle={{ background: "#121a24", border: "1px solid #1f2b38", fontSize: 12 }}
          labelStyle={{ color: "#8b98a5" }}
        />
        <Line type="monotone" dataKey="vehicles" stroke="#4fd1ff" dot={false} strokeWidth={2} />
      </LineChart>
    </ResponsiveContainer>
  );
}
