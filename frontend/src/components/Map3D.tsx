import { MapboxOverlay } from "@deck.gl/mapbox";
import { ColumnLayer, ScatterplotLayer } from "@deck.gl/layers";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef, useState } from "react";

import { LEVEL_COLOR, levelElevation, vehicleColor } from "../congestionColors";
import type { Camera, Congestion, VehiclePosition } from "../types";

const DC_CENTER: [number, number] = [-77.0369, 38.9072];

// Self-contained style with no external tile dependency -- used as a
// fallback if the real basemap style below fails to load (e.g. no outbound
// access to the tile provider), so the camera/vehicle/congestion layers on
// top always still render even without a basemap.
const BLANK_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  name: "Blank",
  sources: {},
  layers: [{ id: "background", type: "background", paint: { "background-color": "#0b1016" } }],
};

// OpenFreeMap (https://openfreemap.org) hosts free vector tiles with no API
// key and no usage cap. Set VITE_MAP_STYLE_URL to override (e.g. a MapTiler
// key) for 3D building extrusion.
const DEFAULT_STYLE_URL = "https://tiles.openfreemap.org/styles/liberty";

interface Props {
  cameras: Camera[];
  congestionByCamera: Record<string, Congestion>;
  vehicles: VehiclePosition[];
  selectedCameraId: string | null;
  onSelectCamera: (id: string) => void;
}

export default function Map3D({
  cameras,
  congestionByCamera,
  vehicles,
  selectedCameraId,
  onSelectCamera,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const overlayRef = useRef<MapboxOverlay | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!containerRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: import.meta.env.VITE_MAP_STYLE_URL || DEFAULT_STYLE_URL,
      center: DC_CENTER,
      zoom: 12.5,
      pitch: 55,
      bearing: -12,
      antialias: true,
    });
    mapRef.current = map;

    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");

    const overlay = new MapboxOverlay({ interleaved: true, layers: [] });
    overlayRef.current = overlay;
    map.addControl(overlay as unknown as maplibregl.IControl);

    map.on("load", () => setReady(true));

    // If the real basemap style can't be fetched (network policy, provider
    // outage), fall back to the blank style rather than leaving the map
    // stuck with no "load" event and no camera/vehicle layers ever rendered.
    let fellBack = false;
    map.on("error", (e) => {
      if (fellBack) return;
      const status = (e.error as { status?: number } | undefined)?.status;
      if (status !== undefined && status < 400) return;
      fellBack = true;
      console.warn("Basemap style failed to load; falling back to blank background.", e.error);
      map.setStyle(BLANK_STYLE);
    });

    return () => {
      map.remove();
      mapRef.current = null;
      overlayRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!ready || !overlayRef.current) return;

    const cameraLayer = new ScatterplotLayer<Camera>({
      id: "cameras",
      data: cameras,
      getPosition: (c) => [c.lon, c.lat],
      getRadius: 34,
      radiusUnits: "meters",
      radiusMinPixels: 4,
      radiusMaxPixels: 10,
      getFillColor: (c) => (c.id === selectedCameraId ? [79, 209, 255] : [220, 226, 233]),
      getLineColor: [10, 14, 20],
      lineWidthMinPixels: 1,
      stroked: true,
      pickable: true,
      onClick: (info) => {
        if (info.object) onSelectCamera((info.object as Camera).id);
      },
    });

    const congestionLayer = new ColumnLayer<Camera>({
      id: "congestion",
      data: cameras,
      diskResolution: 6,
      radius: 26,
      extruded: true,
      pickable: false,
      opacity: 0.55,
      getPosition: (c) => [c.lon, c.lat],
      getElevation: (c) => {
        const sample = congestionByCamera[c.id];
        return sample ? levelElevation(sample.level, sample.vehicle_count) : 2;
      },
      getFillColor: (c) => {
        const sample = congestionByCamera[c.id];
        return sample ? LEVEL_COLOR[sample.level] : [80, 90, 100];
      },
      updateTriggers: {
        getElevation: congestionByCamera,
        getFillColor: congestionByCamera,
      },
    });

    const vehicleLayer = new ScatterplotLayer<VehiclePosition>({
      id: "vehicles",
      data: vehicles,
      getPosition: (v) => [v.lon, v.lat],
      getRadius: 3,
      radiusUnits: "meters",
      radiusMinPixels: 2,
      radiusMaxPixels: 6,
      getFillColor: (v) => vehicleColor(v.vehicle_class),
      updateTriggers: {
        getPosition: vehicles,
      },
    });

    overlayRef.current.setProps({ layers: [congestionLayer, cameraLayer, vehicleLayer] });
  }, [ready, cameras, congestionByCamera, vehicles, selectedCameraId, onSelectCamera]);

  useEffect(() => {
    if (!ready || !selectedCameraId || !mapRef.current) return;
    const camera = cameras.find((c) => c.id === selectedCameraId);
    if (!camera) return;
    mapRef.current.flyTo({ center: [camera.lon, camera.lat], zoom: 16, pitch: 60, duration: 900 });
  }, [ready, selectedCameraId, cameras]);

  return <div ref={containerRef} style={{ position: "absolute", inset: 0 }} />;
}
