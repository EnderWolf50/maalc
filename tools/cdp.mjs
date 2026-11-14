// A Chrome DevTools Protocol connection over Node's global WebSocket (Node 22 or later, no packages), shared by
// tools/gui_shots.mjs (a headless Edge, flat sessions) and tools/gui_devtools.mjs (the settings window's WebView2 page).

/** A CDP connection: `send` a command (to a flat session when `sessionId` is given), wait `once` for an event, `on` to hear
 * every one, `evaluate` an expression in the page. */
export class Cdp {
  /** A connection to a DevTools WebSocket URL (a browser's or a page's). */
  static async connect(url) {
    const ws = new WebSocket(url);
    await new Promise((resolve, reject) => {
      ws.onopen = resolve;
      ws.onerror = () => reject(new Error(`cannot connect to ${url}`));
    });
    return new Cdp(ws);
  }

  constructor(ws) {
    this.ws = ws;
    this.next = 0;
    this.pending = new Map();
    this.waiters = [];
    this.listeners = [];
    ws.onmessage = (e) => {
      const m = JSON.parse(e.data);
      if (m.id !== undefined && this.pending.has(m.id)) {
        const p = this.pending.get(m.id);
        this.pending.delete(m.id);
        if (m.error) p.reject(new Error(`${p.method}: ${m.error.message}`));
        else p.resolve(m.result);
      } else if (m.method) {
        for (const l of this.listeners) if (l.method === m.method) l.fn(m.params, m.sessionId);
        this.waiters = this.waiters.filter((w) => !(w.method === m.method && w.sessionId === m.sessionId && (w.resolve(m.params), true)));
      }
    };
    ws.onclose = () => {
      for (const p of this.pending.values()) p.reject(new Error(`${p.method}: the DevTools connection closed`));
      this.pending.clear();
    };
  }

  send(method, params = {}, sessionId) {
    const id = ++this.next;
    this.ws.send(JSON.stringify({ id, method, params, sessionId }));
    return new Promise((resolve, reject) => this.pending.set(id, { resolve, reject, method }));
  }

  once(method, sessionId, ms = 15000) {
    return new Promise((resolve, reject) => {
      const w = { method, sessionId, resolve };
      this.waiters.push(w);
      setTimeout(() => reject(new Error(`timed out waiting for ${method}`)), ms);
    });
  }

  on(method, fn) {
    this.listeners.push({ method, fn });
  }

  /** The expression's value (a Promise awaited); a page exception throws with its description. */
  async evaluate(expression, sessionId) {
    const r = await this.send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true }, sessionId);
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description ?? r.exceptionDetails.text);
    return r.result.value;
  }
}
