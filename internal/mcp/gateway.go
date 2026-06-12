// Package mcp implements a stdio JSON-RPC gateway speaking the Model
// Context Protocol. Unlike a thin wrapper, tools here do the real
// work: analyze_url fetches and parses the page in-process and returns
// the structured JSON directly to the calling agent.
package mcp

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"strings"
	"time"

	"github.com/Emodv/l2agent/internal/analyzer"
	"github.com/Emodv/l2agent/internal/fetch"
	"github.com/Emodv/l2agent/internal/store"
)

const protocolVersion = "2024-11-05"

type request struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      json.RawMessage `json:"id,omitempty"`
	Method  string          `json:"method"`
	Params  json.RawMessage `json:"params,omitempty"`
}

type response struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      json.RawMessage `json:"id"`
	Result  interface{}     `json:"result,omitempty"`
	Error   *rpcError       `json:"error,omitempty"`
}

type rpcError struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
}

type tool struct {
	Name        string      `json:"name"`
	Description string      `json:"description"`
	InputSchema interface{} `json:"inputSchema"`
}

type Gateway struct {
	store store.Store
}

func NewGateway(st store.Store) *Gateway {
	return &Gateway{store: st}
}

// Run processes newline-delimited JSON-RPC messages from r until EOF.
func (g *Gateway) Run(r io.Reader, w io.Writer) error {
	scanner := bufio.NewScanner(r)
	scanner.Buffer(make([]byte, 0, 64*1024), 4*1024*1024)
	encoder := json.NewEncoder(w)

	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue
		}
		var req request
		if err := json.Unmarshal([]byte(line), &req); err != nil {
			encoder.Encode(errResponse(nil, -32700, "parse error"))
			continue
		}
		// Notifications (no id) get no response per JSON-RPC 2.0.
		if req.ID == nil {
			continue
		}
		encoder.Encode(g.handle(req))
	}
	return scanner.Err()
}

func (g *Gateway) handle(req request) response {
	switch req.Method {
	case "initialize":
		return ok(req.ID, map[string]interface{}{
			"protocolVersion": protocolVersion,
			"capabilities":    map[string]interface{}{"tools": map[string]bool{"listChanged": false}},
			"serverInfo":      map[string]string{"name": "l2agent", "version": "1.0.0"},
		})
	case "ping":
		return ok(req.ID, map[string]interface{}{})
	case "tools/list":
		return ok(req.ID, map[string]interface{}{"tools": tools()})
	case "tools/call":
		return g.handleToolCall(req)
	default:
		return errResponse(req.ID, -32601, "method not found: "+req.Method)
	}
}

func (g *Gateway) handleToolCall(req request) response {
	var params struct {
		Name      string                 `json:"name"`
		Arguments map[string]interface{} `json:"arguments"`
	}
	if err := json.Unmarshal(req.Params, &params); err != nil {
		return errResponse(req.ID, -32602, "invalid params")
	}
	agentID, _ := params.Arguments["agent_id"].(string)

	ctx, cancel := context.WithTimeout(context.Background(), 25*time.Second)
	defer cancel()

	switch params.Name {
	case "analyze_url":
		rawURL, _ := params.Arguments["url"].(string)
		if rawURL == "" {
			return errResponse(req.ID, -32602, "url is required")
		}
		return g.analyzeURL(ctx, req.ID, rawURL, agentID)

	case "submit_form":
		rawURL, _ := params.Arguments["url"].(string)
		fieldsArg, _ := params.Arguments["fields"].(map[string]interface{})
		if rawURL == "" || len(fieldsArg) == 0 {
			return errResponse(req.ID, -32602, "url and fields are required")
		}
		fields := make(map[string]string, len(fieldsArg))
		for k, v := range fieldsArg {
			fields[k] = fmt.Sprint(v)
		}
		body, status, err := fetch.PostForm(ctx, rawURL, fields)
		if err != nil {
			return toolError(req.ID, "submit failed: "+err.Error())
		}
		if agentID != "" {
			g.record(agentID, analyzer.EstimateTokens(string(body)), 50)
		}
		return toolText(req.ID, fmt.Sprintf(`{"success":%t,"status_code":%d}`,
			status >= 200 && status < 300, status))

	case "get_agent_stats":
		if agentID == "" {
			return errResponse(req.ID, -32602, "agent_id is required")
		}
		stats, err := g.store.GetStats(agentID)
		if err != nil {
			return toolError(req.ID, "stats lookup failed: "+err.Error())
		}
		out, _ := json.Marshal(stats)
		return toolText(req.ID, string(out))

	default:
		return errResponse(req.ID, -32601, "unknown tool: "+params.Name)
	}
}

func (g *Gateway) analyzeURL(ctx context.Context, id json.RawMessage, rawURL, agentID string) response {
	body, status, err := fetch.Get(ctx, rawURL)
	if err != nil {
		return toolError(id, "fetch failed: "+err.Error())
	}
	if status != http.StatusOK {
		return toolError(id, fmt.Sprintf("upstream returned status %d", status))
	}
	html := string(body)
	page, err := analyzer.Analyze(strings.NewReader(html), rawURL)
	if err != nil {
		return toolError(id, "parse failed: "+err.Error())
	}
	draft, _ := json.Marshal(page)
	page.FillMeta(html, string(draft))
	out, _ := json.Marshal(page)

	if agentID != "" {
		g.record(agentID, page.Meta.RawTokens, page.Meta.OptimizedTokens)
	}
	return toolText(id, string(out))
}

func (g *Gateway) record(agentID string, raw, optimized int) {
	if err := g.store.RecordRequest(agentID, raw, optimized); err != nil {
		log.Printf("stats record failed for agent=%s: %v", agentID, err)
	}
}

func tools() []tool {
	return []tool{
		{
			Name: "analyze_url",
			Description: "Fetch a web page and return its structure (forms, fields, " +
				"buttons, links) as compact JSON, with measured token savings vs raw HTML.",
			InputSchema: schema(map[string]interface{}{
				"url":      prop("string", "The URL to analyze"),
				"agent_id": prop("string", "Optional agent identifier for usage tracking"),
			}, "url"),
		},
		{
			Name:        "submit_form",
			Description: "Submit form-encoded fields to a URL and return the result status.",
			InputSchema: schema(map[string]interface{}{
				"url": prop("string", "The form action URL"),
				"fields": map[string]interface{}{
					"type":        "object",
					"description": "Key-value pairs of form fields",
				},
				"agent_id": prop("string", "Optional agent identifier for usage tracking"),
			}, "url", "fields"),
		},
		{
			Name:        "get_agent_stats",
			Description: "Get measured token usage and savings stats for an agent.",
			InputSchema: schema(map[string]interface{}{
				"agent_id": prop("string", "The agent ID to look up"),
			}, "agent_id"),
		},
	}
}

func prop(typ, desc string) map[string]interface{} {
	return map[string]interface{}{"type": typ, "description": desc}
}

func schema(props map[string]interface{}, required ...string) map[string]interface{} {
	return map[string]interface{}{"type": "object", "properties": props, "required": required}
}

func ok(id json.RawMessage, result interface{}) response {
	return response{JSONRPC: "2.0", ID: id, Result: result}
}

func errResponse(id json.RawMessage, code int, msg string) response {
	return response{JSONRPC: "2.0", ID: id, Error: &rpcError{Code: code, Message: msg}}
}

func toolText(id json.RawMessage, text string) response {
	return ok(id, map[string]interface{}{
		"content": []map[string]interface{}{{"type": "text", "text": text}},
	})
}

func toolError(id json.RawMessage, msg string) response {
	return ok(id, map[string]interface{}{
		"content": []map[string]interface{}{{"type": "text", "text": msg}},
		"isError": true,
	})
}
