const STORAGE_KEY = "simulator.workspace.session";
const SESSION_VERSION = 1;

export function loadWorkspaceSession(storage = globalThis.localStorage) {
  try {
    const raw = storage?.getItem(STORAGE_KEY);
    if (!raw) return null;
    const payload = JSON.parse(raw);
    if (!payload || payload.version !== SESSION_VERSION || typeof payload !== "object") return null;
    return payload;
  } catch (error) {
    console.warn("Could not restore simulator workspace session.", error);
    return null;
  }
}

export function saveWorkspaceSession(session, storage = globalThis.localStorage) {
  try {
    storage?.setItem(STORAGE_KEY, JSON.stringify({
      ...session,
      version: SESSION_VERSION,
      saved_at: new Date().toISOString(),
    }));
    return true;
  } catch (error) {
    console.warn("Could not persist simulator workspace session.", error);
    return false;
  }
}

export function clearWorkspaceSession(storage = globalThis.localStorage) {
  try {
    storage?.removeItem(STORAGE_KEY);
  } catch (error) {
    console.warn("Could not clear simulator workspace session.", error);
  }
}
