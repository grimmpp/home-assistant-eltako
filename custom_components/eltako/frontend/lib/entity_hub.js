/**
 * Event hub for live entity states.
 *
 * A page which shows the state of an entity used to depend on the periodic reload of the
 * panel (`page.refreshMs`): the whole content was rendered again every few seconds, so
 * pressing "on" looked like nothing happened until the next tick. The hub replaces that
 * with a signal per entity - an element registers for the entity ids it displays and gets
 * called when exactly those change, so only that chip or that button is touched.
 *
 * Where the signal comes from:
 *   - Home Assistant sets a new `hass` object on the panel element on every state change,
 *   - the standalone shell (eltako_standalone/shell/shell.js) re-sets its own one after
 *     each pushed state event.
 * Both end up in `update()`. Unchanged entities keep their state object in both runtimes,
 * so comparing the object itself is enough to tell a real change from a new `hass`.
 */
export class EntityHub {
  /** @param {() => Record<string, any>} statesOf reads the current hass.states */
  constructor(statesOf) {
    this._statesOf = statesOf;
    /** @type {Map<string, Set<Function>>} entity id -> its listeners */
    this._listeners = new Map();
    /** @type {Map<string, any>} entity id -> the state its listeners were told about */
    this._seen = new Map();
  }

  /** Current state of an entity, or null while it does not exist (yet). */
  stateOf(entityId) {
    return (this._statesOf() || {})[entityId] || null;
  }

  /**
   * Listen to a set of entities. The callback gets `(entityId, state)` for every change,
   * one call per entity. Returns the unsubscribe function - a page has to call it before
   * it renders again, otherwise the listeners of the replaced dom stay behind.
   *
   * @param {string[]} entityIds
   * @param {(entityId: string, state: any) => void} callback
   * @returns {() => void}
   */
  subscribe(entityIds, callback) {
    const ids = [...new Set((entityIds || []).filter(Boolean))];
    for (const entityId of ids) {
      if (!this._listeners.has(entityId)) this._listeners.set(entityId, new Set());
      this._listeners.get(entityId).add(callback);
      // the caller renders the current state itself, so that one is not signalled again
      if (!this._seen.has(entityId)) this._seen.set(entityId, this.stateOf(entityId));
    }

    return () => {
      for (const entityId of ids) {
        const listeners = this._listeners.get(entityId);
        if (!listeners) continue;
        listeners.delete(callback);
        if (!listeners.size) {
          this._listeners.delete(entityId);
          this._seen.delete(entityId);
        }
      }
    };
  }

  /** A new state arrived: signal every watched entity which really changed. */
  update() {
    const states = this._statesOf() || {};
    for (const [entityId, listeners] of this._listeners) {
      const state = states[entityId] || null;
      if (state === this._seen.get(entityId)) continue;
      this._seen.set(entityId, state);
      for (const listener of [...listeners]) {
        try {
          listener(entityId, state);
        } catch (err) {
          console.error(`eltako: listener of ${entityId} failed`, err);
        }
      }
    }
  }
}
