/* Shared Pyodide worker and main-thread fallback for Playground and Challenge. */
(function () {
  "use strict";
  const SCRIPT_SRC = document.currentScript && document.currentScript.src;
  const DEFAULT_PYODIDE = "https://cdn.jsdelivr.net/npm/pyodide@0.29.5/";
  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const el = document.createElement("script");
      el.src = src;
      el.onload = resolve;
      el.onerror = () => reject(new Error("could not load " + src));
      document.head.appendChild(el);
    });
  }
  function assetURL(name) {
    return new URL("../playground/" + name, SCRIPT_SRC).href;
  }
  let bundlePromise;
  function ensureBundle() {
    if (window.OPULSE_BUNDLE) return Promise.resolve(window.OPULSE_BUNDLE);
    if (!bundlePromise) {
      bundlePromise = loadScript(assetURL("opulse_bundle.js"))
        .then(() => window.OPULSE_BUNDLE).catch((error) => { bundlePromise = null; throw error; });
    }
    return bundlePromise;
  }
  // ------------------------------------------------------------------ engine
  // One function serves both the worker and the main thread fallback. A "call" message names a
  // function of opulse.playground and its string arguments; the reply carries its JSON result.
  function engine(post, load) {
    let api = null;
    return async function (m) {
      try {
        if (m.type === "init") {
          post({ type: "progress", stage: "runtime" });
          await load(m.pyodide + "pyodide.js");
          const py = await loadPyodide({ indexURL: m.pyodide });
          post({ type: "progress", stage: "package" });
          const bin = atob(m.zip);
          const bytes = new Uint8Array(bin.length);
          for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
          py.unpackArchive(bytes.buffer, "zip", { extractDir: "/opulse_pkg" });
          py.runPython("import sys\nif '/opulse_pkg' not in sys.path: sys.path.insert(0, '/opulse_pkg')");
          api = py.pyimport("opulse.playground");
          post({ type: "ready", worlds: api.worlds_json(), python: py.runPython("import sys; sys.version.split()[0]") });
        } else if (m.type === "call") {
          const json = api[m.fn](...m.args);
          post({ type: "reply", id: m.id, json });
        }
      } catch (err) {
        post({ type: "fatal", id: m.id, message: String((err && err.message) || err) });
      }
    };
  }

  class Engine {
    constructor(pyodide, zip, listener) {
      this.pyodide = pyodide;
      this.zip = zip;
      this.listener = listener;
      this.mode = null;
      this.start();
    }
    start() {
      this.worker = null;
      try {
        const src = `const handle = (${engine.toString()})((m) => self.postMessage(m), async (u) => importScripts(u));\n` +
          "self.onmessage = (e) => handle(e.data);";
        const url = URL.createObjectURL(new Blob([src], { type: "text/javascript" }));
        this.worker = new Worker(url);
        this.mode = "worker";
        this.worker.onmessage = (e) => this.receive(e.data);
        this.worker.onerror = () => this.fallback();
        this.worker.postMessage({ type: "init", pyodide: this.pyodide, zip: this.zip });
      } catch (err) {
        this.fallback();
      }
    }
    fallback() {
      if (this.mode === "main") return;
      if (this.worker) this.worker.terminate();
      this.worker = null;
      this.mode = "main";
      this.handle = engine((m) => setTimeout(() => this.receive(m), 0), loadScript);
      this.handle({ type: "init", pyodide: this.pyodide, zip: this.zip });
    }
    receive(m) {
      if (m.type === "fatal" && !this.ready && this.mode === "worker") { this.fallback(); return; }
      if (m.type === "ready") this.ready = true;
      this.listener(m);
    }
    send(m) {
      if (this.worker) this.worker.postMessage(m);
      else if (this.handle) setTimeout(() => this.handle(m), 0);
    }
    restart() {
      if (this.mode !== "worker") return false;
      this.worker.terminate();
      this.ready = false;
      this.start();
      return true;
    }
  }

  window.OpulseRuntime = { Engine, ensureBundle, DEFAULT_PYODIDE };
})();
