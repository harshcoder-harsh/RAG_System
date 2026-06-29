export function getApiBaseUrl() {
  // Always use the configured API URL (set via NEXT_PUBLIC_API_URL env var)
  const envUrl = process.env.NEXT_PUBLIC_API_URL;
  if (envUrl && envUrl.trim().length > 0) {
    return envUrl.replace(/\/$/, "");
  }

  // Fallback for local dev
  return "http://127.0.0.1:8000";
}
