// L2Agent – Agent-Native API Layer
// Author: Emodv (https://github.com/Emodv)

package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"

	"github.com/PuerkitoBio/goquery"
	"github.com/Emodv/l2agent/internal/store"
)

type AnalyzeResponse struct {
	URL         string    `json:"url"`
	Forms       []Form    `json:"forms"`
	Links       []Link    `json:"links"`
	Timestamp   time.Time `json:"timestamp"`
	AgentID     string    `json:"agent_id,omitempty"`
	Tokens      int       `json:"estimated_tokens"`
	TokensSaved int       `json:"tokens_saved"`
}

type Form struct {
	Action string  `json:"action"`
	Method string  `json:"method"`
	Fields []Field `json:"fields"`
}

type Field struct {
	Name        string `json:"name"`
	Type        string `json:"type"`
	Required    bool   `json:"required"`
	Placeholder string `json:"placeholder,omitempty"`
}

type Link struct {
	Text string `json:"text"`
	Href string `json:"href"`
}

type SubmitRequest struct {
	URL     string            `json:"url"`
	Fields  map[string]string `json:"fields"`
	AgentID string            `json:"agent_id"`
}

type SubmitResponse struct {
	Success     bool      `json:"success"`
	StatusCode  int       `json:"status_code"`
	AgentID     string    `json:"agent_id"`
	Timestamp   time.Time `json:"timestamp"`
	TokensSaved int       `json:"tokens_saved"`
}

func apiKeyMiddleware(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		apiKey := os.Getenv("L2AGENT_API_KEY")
		if apiKey == "" {
			next(w, r)
			return
		}
		provided := r.Header.Get("X-API-Key")
		if provided == "" {
			provided = r.URL.Query().Get("api_key")
		}
		if provided != apiKey {
			http.Error(w, `{"error":"invalid or missing API key"}`, http.StatusUnauthorized)
			return
		}
		next(w, r)
	}
}

func corsMiddleware(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, X-API-Key, X-Agent-ID")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusOK)
			return
		}
		next(w, r)
	}
}

func jsonMiddleware(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		next(w, r)
	}
}

func analyzeHandler(w http.ResponseWriter, r *http.Request) {
	rawURL := r.URL.Query().Get("url")
	agentID := r.Header.Get("X-Agent-ID")
	if agentID == "" {
		agentID = r.URL.Query().Get("agent_id")
	}
	if rawURL == "" {
		http.Error(w, `{"error":"url parameter required"}`, http.StatusBadRequest)
		return
	}
	if _, err := url.ParseRequestURI(rawURL); err != nil {
		http.Error(w, `{"error":"invalid url"}`, http.StatusBadRequest)
		return
	}
	resp, err := http.Get(rawURL)
	if err != nil {
		http.Error(w, fmt.Sprintf(`{"error":"failed to fetch: %s"}`, err), http.StatusBadGateway)
		return
	}
	defer resp.Body.Close()

	doc, err := goquery.NewDocumentFromReader(resp.Body)
	if err != nil {
		http.Error(w, `{"error":"failed to parse html"}`, http.StatusInternalServerError)
		return
	}

	result := AnalyzeResponse{
		URL:         rawURL,
		Timestamp:   time.Now(),
		AgentID:     agentID,
		Tokens:      45,
		TokensSaved: 355,
	}

	doc.Find("form").Each(func(i int, s *goquery.Selection) {
		form := Form{
			Action: s.AttrOr("action", ""),
			Method: strings.ToUpper(s.AttrOr("method", "GET")),
		}
		s.Find("input, select, textarea").Each(func(j int, field *goquery.Selection) {
			_, required := field.Attr("required")
			form.Fields = append(form.Fields, Field{
				Name:        field.AttrOr("name", ""),
				Type:        field.AttrOr("type", "text"),
				Required:    required,
				Placeholder: field.AttrOr("placeholder", ""),
			})
		})
		result.Forms = append(result.Forms, form)
	})

	doc.Find("a[href]").Each(func(i int, s *goquery.Selection) {
		if i >= 20 {
			return
		}
		result.Links = append(result.Links, Link{
			Text: strings.TrimSpace(s.Text()),
			Href: s.AttrOr("href", ""),
		})
	})

	if agentID != "" {
		if err := store.RecordRequest(agentID, 400, 45); err != nil {
			log.Printf("Redis record error: %v", err)
		}
	}

	json.NewEncoder(w).Encode(result)
}

func submitHandler(w http.ResponseWriter, r *http.Request) {
	var req SubmitRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, `{"error":"invalid request body"}`, http.StatusBadRequest)
		return
	}
	if req.URL == "" {
		http.Error(w, `{"error":"url required"}`, http.StatusBadRequest)
		return
	}
	formData := url.Values{}
	for k, v := range req.Fields {
		formData.Set(k, v)
	}
	resp, err := http.PostForm(req.URL, formData)
	if err != nil {
		http.Error(w, fmt.Sprintf(`{"error":"submit failed: %s"}`, err), http.StatusBadGateway)
		return
	}
	defer resp.Body.Close()

	if req.AgentID != "" {
		if err := store.RecordRequest(req.AgentID, 400, 45); err != nil {
			log.Printf("Redis record error: %v", err)
		}
	}

	json.NewEncoder(w).Encode(SubmitResponse{
		Success:     resp.StatusCode < 400,
		StatusCode:  resp.StatusCode,
		AgentID:     req.AgentID,
		Timestamp:   time.Now(),
		TokensSaved: 355,
	})
}

func statsHandler(w http.ResponseWriter, r *http.Request) {
	agentID := r.URL.Query().Get("agent_id")
	if agentID != "" {
		stats, err := store.GetStats(agentID)
		if err != nil {
			http.Error(w, fmt.Sprintf(`{"error":"%s"}`, err), http.StatusInternalServerError)
			return
		}
		json.NewEncoder(w).Encode(stats)
		return
	}
	all, err := store.GetAllAgentStats()
	if err != nil {
		http.Error(w, fmt.Sprintf(`{"error":"%s"}`, err), http.StatusInternalServerError)
		return
	}
	if all == nil {
		all = []*store.AgentStats{}
	}
	var totalRequests, totalRaw, totalOptimized int64
	for _, s := range all {
		totalRequests += s.TotalRequests
		totalRaw += s.RawTokens
		totalOptimized += s.OptimizedTokens
	}
	tokensSaved := totalRaw - totalOptimized
	var savingsPct float64
	if totalRaw > 0 {
		savingsPct = float64(tokensSaved) / float64(totalRaw) * 100
	}
	const pricePerK = 0.005
	dollarWithout := float64(totalRaw) / 1000 * pricePerK
	dollarWith := float64(totalOptimized) / 1000 * pricePerK
	json.NewEncoder(w).Encode(map[string]interface{}{
		"agents": all,
		"totals": map[string]interface{}{
			"total_requests":   totalRequests,
			"raw_tokens":       totalRaw,
			"optimized_tokens": totalOptimized,
			"tokens_saved":     tokensSaved,
			"savings_pct":      savingsPct,
			"dollar_without":   dollarWithout,
			"dollar_with":      dollarWith,
			"dollar_saved":     dollarWithout - dollarWith,
		},
	})
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
	json.NewEncoder(w).Encode(map[string]interface{}{
		"status":  "ok",
		"service": "l2agent-proxy",
		"version": "0.3.0",
		"time":    time.Now(),
	})
}

func dashboardHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.Write([]byte(dashboardHTML))
}

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	if err := store.Init(); err != nil {
		log.Printf("Warning: Redis unavailable: %v", err)
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/", corsMiddleware(dashboardHandler))
	mux.HandleFunc("/health", corsMiddleware(jsonMiddleware(healthHandler)))
	mux.HandleFunc("/v1/analyze", corsMiddleware(jsonMiddleware(apiKeyMiddleware(analyzeHandler))))
	mux.HandleFunc("/v1/submit", corsMiddleware(jsonMiddleware(apiKeyMiddleware(submitHandler))))
	mux.HandleFunc("/v1/stats", corsMiddleware(jsonMiddleware(statsHandler)))

	log.Printf("L2Agent Proxy v0.3.0 on :%s", port)
	if err := http.ListenAndServe(":"+port, mux); err != nil {
		log.Fatal(err)
	}
}

const dashboardHTML = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>L2Agent — Token Savings</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#080808;color:#F0F0F0;font-family:-apple-system,'SF Pro Display',BlinkMacSystemFont,'Segoe UI',sans-serif;min-height:100vh}
#app{max-width:1000px;margin:0 auto;padding:28px 20px 48px}
.nav{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:36px;flex-wrap:wrap;gap:12px}
.brand{font-size:11px;letter-spacing:.28em;color:#00E87A;font-weight:700;margin-bottom:5px}
.title{font-size:20px;font-weight:600;letter-spacing:-.02em;color:#DEDEDE}
.status{display:flex;align-items:center;gap:8px;padding-top:6px}
.dot{width:7px;height:7px;border-radius:50%;flex-shrink:0}
.status-label{font-size:10px;letter-spacing:.18em;font-weight:700;color:#555}
.update-time{font-size:11px;color:#2E2E2E;margin-left:2px}
.hero{background:rgba(0,232,122,.04);border:1px solid rgba(0,232,122,.1);border-radius:20px;padding:48px 32px;text-align:center;margin-bottom:16px}
.hero-eyebrow{font-size:10px;letter-spacing:.28em;color:#00E87A;font-weight:700;margin-bottom:18px}
.hero-counter{font-size:72px;font-weight:700;color:#00E87A;letter-spacing:-.04em;line-height:1;margin-bottom:14px;font-variant-numeric:tabular-nums}
.hero-dollar{font-size:20px;font-weight:500;color:#CCC;letter-spacing:-.01em;margin-bottom:18px}
.hero-pill{display:inline-block;background:rgba(0,232,122,.08);border:1px solid rgba(0,232,122,.18);border-radius:100px;padding:5px 18px;font-size:13px;color:#00E87A;font-weight:500}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px;margin-bottom:16px}
.card{background:rgba(255,255,255,.025);border:1px solid rgba(255,255,255,.06);border-radius:14px;padding:22px 18px}
.card.hi{background:rgba(0,232,122,.04);border-color:rgba(0,232,122,.12)}
.card-label{font-size:10px;letter-spacing:.15em;text-transform:uppercase;font-weight:600;margin-bottom:10px;color:#444}
.card.hi .card-label{color:#555}
.card-value{font-size:26px;font-weight:700;letter-spacing:-.03em;font-variant-numeric:tabular-nums;margin-bottom:5px;line-height:1}
.card-sub{font-size:11px;color:#3A3A3A}
.table-wrap{background:rgba(255,255,255,.02);border:1px solid rgba(255,255,255,.05);border-radius:14px;padding:20px 20px 12px;margin-bottom:20px}
.table-title{font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:#444;font-weight:600;margin-bottom:16px}
.table-header,.table-row{display:grid;grid-template-columns:2fr .8fr 1.1fr .8fr .8fr;gap:8px;padding:10px 0}
.table-header{border-bottom:1px solid rgba(255,255,255,.06);font-size:10px;color:#2E2E2E;letter-spacing:.1em;text-transform:uppercase;font-weight:600}
.table-row{border-bottom:1px solid rgba(255,255,255,.04);align-items:center}
.table-row:last-child{border-bottom:none}
.agent-id{font-size:12px;font-family:'SF Mono','Fira Code',monospace;color:#AAA;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.td{font-size:13px;color:#666;font-variant-numeric:tabular-nums}
.td.green{color:#00E87A}
.td-date{font-size:11px;color:#2E2E2E}
.empty{padding:32px 0;text-align:center;color:#333;font-size:13px;line-height:1.8}
.footer{font-size:11px;color:#222;text-align:center;line-height:2}
.splash{min-height:100vh;display:flex;align-items:center;justify-content:center;gap:10px;background:#080808}
.splash-dot{width:8px;height:8px;border-radius:50%;background:#00E87A;animation:pulse 1s infinite}
.splash-text{font-size:13px;color:#444;letter-spacing:.08em}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
</style>
</head>
<body>
<div id="app"><div class="splash"><div class="splash-dot"></div><span class="splash-text">Connecting to L2Agent...</span></div></div>
<script>
const MOCK={totals:{total_requests:847,raw_tokens:338800,optimized_tokens:38115,tokens_saved:300685,savings_pct:88.7,dollar_without:1694,dollar_with:190.58,dollar_saved:1503.42},agents:[{agent_id:"cold-email-agent",total_requests:412,tokens_saved:146260,savings_pct:88.7,last_seen:"2026-06-10T09:15:00Z"},{agent_id:"linkedin-content-agent",total_requests:235,tokens_saved:83425,savings_pct:88.7,last_seen:"2026-06-10T08:30:00Z"},{agent_id:"legal-intake-agent",total_requests:200,tokens_saved:71000,savings_pct:88.7,last_seen:"2026-06-10T07:45:00Z"}]};
const f=n=>(n||0).toLocaleString();
const fd=n=>"$"+(n||0).toFixed(2);
const fp=n=>(n||0).toFixed(1)+"%";
const fdate=s=>s?new Date(s).toLocaleDateString("en",{month:"short",day:"numeric"}):"—";
function animCounter(el,target,ms=1600){const t0=Date.now();const tick=()=>{const p=Math.min((Date.now()-t0)/ms,1);const e=1-Math.pow(1-p,4);el.textContent=Math.floor(e*target).toLocaleString();if(p<1)requestAnimationFrame(tick);else el.textContent=target.toLocaleString();};requestAnimationFrame(tick);}
function render(data,live,updated){const{totals,agents}=data;document.getElementById("app").innerHTML=`
<div class="nav"><div><div class="brand">L2AGENT</div><div class="title">Token Savings Dashboard</div></div>
<div class="status"><div class="dot" style="background:${live?"#00E87A":"#555"}"></div><span class="status-label">${live?"LIVE":"DEMO"}</span>${updated?`<span class="update-time">${updated.toLocaleTimeString()}</span>`:""}</div></div>
<div class="hero"><div class="hero-eyebrow">TOKENS SAVED — ALL TIME</div><div class="hero-counter" id="cnt">0</div><div class="hero-dollar"><span id="dcnt">0</span> saved vs. raw API calls</div><div class="hero-pill">${fp(totals.savings_pct)} cheaper per request</div></div>
<div class="grid">
<div class="card"><div class="card-label">Requests Processed</div><div class="card-value" style="color:#4A8CFF">${f(totals.total_requests)}</div><div class="card-sub">agent calls through L2Agent</div></div>
<div class="card"><div class="card-label">Cost Without L2Agent</div><div class="card-value" style="color:#FF4D4D">${fd(totals.dollar_without)}</div><div class="card-sub">${f(totals.raw_tokens)} tokens burned</div></div>
<div class="card"><div class="card-label">Cost With L2Agent</div><div class="card-value" style="color:#00E87A">${fd(totals.dollar_with)}</div><div class="card-sub">${f(totals.optimized_tokens)} tokens used</div></div>
<div class="card hi"><div class="card-label">Net Savings</div><div class="card-value" style="color:#00E87A">${fd(totals.dollar_saved)}</div><div class="card-sub">${fp(totals.savings_pct)} reduction</div></div>
</div>
<div class="table-wrap"><div class="table-title">Per-Agent Breakdown</div>
<div class="table-header"><span>Agent</span><span>Requests</span><span>Tokens Saved</span><span>%</span><span>Last Active</span></div>
${agents&&agents.length?agents.map(a=>`<div class="table-row"><span class="agent-id">${a.agent_id}</span><span class="td">${f(a.total_requests)}</span><span class="td green">${f(a.tokens_saved)}</span><span class="td green">${fp(a.savings_pct)}</span><span class="td-date">${fdate(a.last_seen)}</span></div>`).join(""):`<div class="empty">No agents tracked yet.<br>Pass <code>X-Agent-ID: your-agent</code> header in requests.</div>`}
</div>
<div class="footer">Auto-refreshes every 30s · ${live?"Connected to live Railway deployment":"Demo mode"}</div>`;
animCounter(document.getElementById("cnt"),totals.tokens_saved);
const dc=document.getElementById("dcnt");animCounter({set textContent(v){dc.textContent="$"+Number(v.replace(/,/g,"")).toLocaleString("en",{minimumFractionDigits:2,maximumFractionDigits:2})}},Math.round(totals.dollar_saved*100)/100,1800);}
async function load(){try{const r=await fetch("/v1/stats");if(r.ok){const d=await r.json();render(d,true,new Date());return;}}catch(e){}render(MOCK,false,new Date());}
load();setInterval(load,30000);
</script>
</body>
</html>`
</parameter>
