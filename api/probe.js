// Diagnostic probe: checks the L2Agent Railway API server-side so the
// dashboard (and operators) can see backend health without CORS or
// client network issues. Probes a fixed host only — not an open proxy.
// With ?bench=1 it also runs a live token-savings benchmark against a
// fixed set of real-world pages.
const BASE = "https://agentos-mvp-production-f4e9.up.railway.app";

const BENCH_URLS = [
  "https://httpbin.org/forms/post",
  "https://en.wikipedia.org/wiki/Web_scraping",
  "https://news.ycombinator.com/",
];

async function fetchJSON(url, headers) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 8000);
  try {
    const r = await fetch(url, { headers, signal: controller.signal });
    const text = await r.text();
    return { status: r.status, text };
  } finally {
    clearTimeout(timer);
  }
}

module.exports = async (req, res) => {
  const headers = {};
  if (req.headers["x-api-key"]) headers["X-API-Key"] = req.headers["x-api-key"];

  const out = { target: BASE, checked_at: new Date().toISOString(), results: {} };

  if (req.query && req.query.bench) {
    const settled = await Promise.allSettled(
      BENCH_URLS.map((u) =>
        fetchJSON(BASE + "/v1/analyze?url=" + encodeURIComponent(u), headers)
      )
    );
    out.benchmark = settled.map((s, i) => {
      if (s.status === "rejected") return { url: BENCH_URLS[i], error: String(s.reason) };
      try {
        const data = JSON.parse(s.value.text);
        return {
          url: BENCH_URLS[i],
          http_status: s.value.status,
          title: data.title,
          forms: (data.forms || []).length,
          links: (data.links || []).length,
          meta: data.meta,
        };
      } catch {
        return { url: BENCH_URLS[i], http_status: s.value.status, body: s.value.text.slice(0, 300) };
      }
    });
  } else {
    for (const path of ["/healthz", "/v1/stats"]) {
      try {
        const r = await fetchJSON(BASE + path, headers);
        out.results[path] = { status: r.status, body: r.text.slice(0, 600) };
      } catch (e) {
        out.results[path] = { error: String(e) };
      }
    }
  }

  res.setHeader("Content-Type", "application/json");
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.status(200).json(out);
};
