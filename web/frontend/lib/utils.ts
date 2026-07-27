import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatAnchor(anchor: number, modality: "pdf" | "video" | "audio"): string {
  if (modality === "video" || modality === "audio") {
    const totalSeconds = Math.floor(anchor);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${minutes}:${seconds.toString().padStart(2, "0")}`;
  }
  return `P.${Math.floor(anchor)}`;
}
