const STORAGE_KEY = "simulator.workspace.session";
const SESSION_VERSION = 2;

function readStored(storage) {
  const raw = storage?.getItem(STORAGE_KEY);
  if (!raw) return null;
  const payload = JSON.parse(raw);
  return payload && typeof payload === "object" ? payload : null;
}

function sameJson(left, right) {
  try {
    return JSON.stringify(left ?? null) === JSON.stringify(right ?? null);
  } catch {
    return false;
  }
}

function normalizeLoadedSession(payload) {
  if (!payload) return null;
  if (![1, SESSION_VERSION].includes(payload.version)) return null;

  const migrated = { ...payload, version: SESSION_VERSION };
  if (migrated.isNew) return migrated;

  const hasUnsavedExistingDraft = !!migrated.draft
    && !!migrated.baseline
    && !sameJson(migrated.draft, migrated.baseline);

  const recovery = hasUnsavedExistingDraft
    ? {
        simulation_id: migrated.selectedId || migrated.draft?.simulation_id || null,
        draft: migrated.draft,
        baseline: migrated.baseline,
        sourcePreview: migrated.sourcePreview || null,
        saved_at: migrated.saved_at || null,
      }
    : (migrated.recovery || null);

  // Backend reality is authoritative for existing simulations. The workspace
  // may remember where the user was, but it must never repaint a cached
  // definition as though it were the current live definition. Existing
  // unsaved work is retained separately as recovery data for a future
  // explicit recovery UX instead of being auto-applied.
  return {
    ...migrated,
    draft: null,
    baseline: null,
    sourcePreview: null,
    recovery,
  };
}

export function loadWorkspaceSession(storage = globalThis.localStorage) {
  try {
    return normalizeLoadedSession(readStored(storage));
  } catch (error) {
    console.warn("Could not restore simulator workspace session.", error);
    return null;
  }
}

export function saveWorkspaceSession(session, storage = globalThis.localStorage) {
  try {
    const previous = normalizeLoadedSession(readStored(storage));
    storage?.setItem(STORAGE_KEY, JSON.stringify({
      ...session,
      recovery: session.recovery ?? previous?.recovery ?? null,
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
