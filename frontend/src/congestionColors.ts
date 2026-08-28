import type { CongestionLevel } from "./types";

export const LEVEL_COLOR: Record<CongestionLevel, [number, number, number]> = {
  free: [46, 204, 113],
  light: [244, 208, 63],
  moderate: [230, 126, 34],
  heavy: [231, 76, 60],
};

export const LEVEL_ORDER: CongestionLevel[] = ["free", "light", "moderate", "heavy"];

export function levelElevation(level: CongestionLevel, vehicleCount: number): number {
  const base = { free: 4, light: 10, moderate: 20, heavy: 34 }[level];
  return base + Math.min(vehicleCount, 30);
}

const VEHICLE_COLOR: Record<string, [number, number, number]> = {
  car: [79, 209, 255],
  truck: [255, 159, 67],
  bus: [199, 125, 255],
  motorcycle: [255, 255, 255],
};

export function vehicleColor(vehicleClass: string): [number, number, number] {
  return VEHICLE_COLOR[vehicleClass] ?? VEHICLE_COLOR.car;
}
