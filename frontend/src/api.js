// Small fetch wrapper: JSON in/out, readable errors that carry the server's request ID.
export class ApiError extends Error {
  constructor(message, status, requestId, details) {
    super(message);
    this.status = status;
    this.requestId = requestId;
    this.details = details;
  }
}

async function request(method, path, body) {
  let res;
  const isForm = body instanceof FormData;
  try {
    res = await fetch(`/api${path}`, {
      method,
      headers: body && !isForm ? { "Content-Type": "application/json" } : {},
      body: isForm ? body : body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError("Can't reach the server. Check your connection and try again.", 0);
  }
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new ApiError(data.error || `Request failed (${res.status})`, res.status, data.request_id || res.headers.get("X-Request-ID"), data.details);
  }
  return data;
}

export const api = {
  get: (p) => request("GET", p),
  post: (p, b) => request("POST", p, b ?? {}),
  patch: (p, b) => request("PATCH", p, b),
  put: (p, b) => request("PUT", p, b),
  del: (p) => request("DELETE", p),
  /** Upload one file as multipart/form-data (field name "file"). */
  upload: (p, file) => { const fd = new FormData(); fd.append("file", file); return request("POST", p, fd); },
};

export const fmtDate = (d) => (d ? new Date(d.length === 10 ? d + "T00:00:00" : d).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "—");
export const fmtDateTime = (d) => (d ? new Date(d).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "—");
export const today = () => new Date().toISOString().slice(0, 10);
