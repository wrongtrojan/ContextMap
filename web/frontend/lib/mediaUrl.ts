import { BASE_URL } from "./api-config";

/**
 * Build a playable media URL for <video>/<audio>.
 * Encodes path segments (Chinese filenames) and points /raw/... at the API
 * host so Range requests hit uvicorn directly.
 */
export function encodeMediaUrl(url: string): string {
  if (!url) return url;

  let path = url;
  let origin = "";

  try {
    if (/^https?:\/\//i.test(url)) {
      const parsed = new URL(url);
      origin = parsed.origin;
      path = `${parsed.pathname}${parsed.search}`;
    }
  } catch {
    // treat as path
  }

  const encodedPath = path
    .split("/")
    .map((seg) => {
      if (!seg) return seg;
      try {
        return encodeURIComponent(decodeURIComponent(seg));
      } catch {
        return encodeURIComponent(seg);
      }
    })
    .join("/");

  if (!origin && encodedPath.startsWith("/raw/")) {
    return `${BASE_URL}${encodedPath}`;
  }
  if (origin) {
    return `${origin}${encodedPath}`;
  }
  return encodedPath;
}
