const launcher = window.SIMULATOR_LAUNCHER_CONFIG || {};
const industrialPort = Number(launcher.industrial_web_port || 8000);
const API_BASE = `http://${location.hostname || "localhost"}:${industrialPort}`;

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {}),
    },
  });
  if (response.status === 204) return null;
  const text = await response.text();
  let payload = null;
  if (text) {
    try { payload = JSON.parse(text); }
    catch { payload = text; }
  }
  if (!response.ok) {
    const detail = payload?.detail ?? payload?.error ?? payload ?? `${response.status} ${response.statusText}`;
    const message = typeof detail === "string" ? detail : JSON.stringify(detail);
    throw new Error(message);
  }
  return payload;
}

function json(method, body) {
  return { method, body: JSON.stringify(body) };
}

export const simulatorApi = {
  baseUrl: API_BASE,
  health: () => request("/api/health"),
  capabilities: () => request("/api/v2/capabilities"),
  runtime: () => request("/api/v2/runtime"),
  interfaces: () => request("/api/v2/interfaces"),

  listSimulations: () => request("/api/v2/simulations"),
  getSimulation: (id) => request(`/api/v2/simulations/${encodeURIComponent(id)}`),
  previewSimulation: (definition) => request("/api/v2/simulations/preview", json("POST", definition)),
  createSimulation: (definition) => request("/api/v2/simulations", json("POST", definition)),
  replaceSimulation: (id, definition) => request(`/api/v2/simulations/${encodeURIComponent(id)}`, json("PUT", definition)),
  deleteSimulation: (id) => request(`/api/v2/simulations/${encodeURIComponent(id)}`, { method: "DELETE" }),
  startSimulation: (id) => request(`/api/v2/simulations/${encodeURIComponent(id)}/start`, { method: "POST" }),
  pauseSimulation: (id) => request(`/api/v2/simulations/${encodeURIComponent(id)}/pause`, { method: "POST" }),
  resumeSimulation: (id) => request(`/api/v2/simulations/${encodeURIComponent(id)}/resume`, { method: "POST" }),
  stopSimulation: (id) => request(`/api/v2/simulations/${encodeURIComponent(id)}/stop`, { method: "POST" }),
  restartSimulation: (id) => request(`/api/v2/simulations/${encodeURIComponent(id)}/restart`, { method: "POST" }),
  resetCursor: (id) => request(`/api/v2/simulations/${encodeURIComponent(id)}/reset-cursor`, { method: "POST" }),
  seekSimulation: (id, position) => request(`/api/v2/simulations/${encodeURIComponent(id)}/seek?position=${encodeURIComponent(position)}`, { method: "POST" }),
  snapshot: (id) => request(`/api/v2/simulations/${encodeURIComponent(id)}/snapshot`),

  files: () => request("/api/csv/files"),
  fileMetadata: (filename, source) => request(`/api/csv/files/${encodeURIComponent(filename)}/metadata?source=${encodeURIComponent(source)}`),
  datasets: () => request("/api/datasets"),
  generators: () => request("/api/generators"),
  generatorSpec: (domainId) => request(`/api/generators/${encodeURIComponent(domainId)}/spec`),
};
