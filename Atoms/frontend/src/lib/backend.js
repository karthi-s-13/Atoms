const DEFAULT_BACKEND_PORT = "8000";
const DEV_PROXY_PORTS = new Set(["5173"]);

function stripTrailingSlash(value) {
  return String(value || "").replace(/\/+$/, "");
}

function normalizeOrigin(value) {
  const raw = stripTrailingSlash(value);
  if (!raw) {
    return "";
  }

  try {
    return new URL(raw).origin;
  } catch {
    try {
      return new URL(`http://${raw}`).origin;
    } catch {
      return "";
    }
  }
}

function resolveConfiguredOrigin() {
  return normalizeOrigin(
    import.meta.env.VITE_API_BASE_URL ||
    import.meta.env.VITE_BACKEND_ORIGIN ||
    import.meta.env.VITE_BACKEND_URL,
  );
}

function resolveBrowserOrigin() {
  const configuredOrigin = resolveConfiguredOrigin();
  if (configuredOrigin) {
    return configuredOrigin;
  }

  if (typeof window === "undefined") {
    return `http://localhost:${DEFAULT_BACKEND_PORT}`;
  }

  const { hostname, origin, port, protocol } = window.location;
  if (protocol === "file:") {
    return `http://localhost:${DEFAULT_BACKEND_PORT}`;
  }

  if (!port || port === DEFAULT_BACKEND_PORT || DEV_PROXY_PORTS.has(port)) {
    return origin;
  }

  if (hostname === "localhost" || hostname === "127.0.0.1") {
    const nextProtocol = protocol === "https:" ? "https:" : "http:";
    return `${nextProtocol}//${hostname}:${DEFAULT_BACKEND_PORT}`;
  }

  return origin;
}

export function getApiBaseUrl() {
  return resolveBrowserOrigin();
}

export function getBackendWsUrl(path) {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const baseUrl = new URL(getApiBaseUrl());
  baseUrl.protocol = baseUrl.protocol === "https:" ? "wss:" : "ws:";
  return new URL(normalizedPath, baseUrl).toString();
}
