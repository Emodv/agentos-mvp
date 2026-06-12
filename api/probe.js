// Diagnostic probe: checks the L2Agent Railway API server-side so the
// dashboard (and operators) can see backend health without CORS or
// client network issues. Probes a fixed host only — not an open proxy.
const BASE = "https://agentos-mvp-production-f4e9.up.railway.app";

module.exports = async (req, res) => {
  const headers = {};
  if (req.headers["x-api-key"]) headers["X-API-Key"] = req.headers["x-api-key"];

  const results = {};
  for (const path of ["/healthz", "/v1/stats"]) {
    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 8000);
      const r = await fetch(BASE + path, { headers, signal: controller.signal });
      clearTimeout(timer);
      const text = await r.text();
      results[path] = { status: r.status, body: text.slice(0, 600) };
    } catch (e) {
      results[path] = { error: String(e) };
    }
  }

  res.setHeader("Content-Type", "application/json");
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.status(200).json({ target: BASE, checked_at: new Date().toISOString(), results });
};
