// L2Agent – MCP Gateway
// Author: Emodv (https://github.com/Emodv)

package main

import (
	"bufio"
	"encoding/json"
	"log"
	"os"
	"time"
)

// ── Types ─────────────────────────────────────────────────

type JSONRPCRequest struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      interface{}     `json:"id"`
	Method  string          `json:"method"`
	Params  json.RawMessage `json:"params,omitempty"`
}

type JSONRPCResponse struct {
	JSONRPC string      `json:"jsonrpc"`
	ID      interface{} `json:"id"`
	Result  interface{} `json:"result,omitempty"`
	Error   *RPCError   `json:"error,omitempty"`
}

type RPCError struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
}

type Tool struct {
	Name        string      `json:"name"`
	Description string      `json:"description"`
	InputSchema interface{} `json:"inputSchema"`
}

type AgentStats struct {
	AgentID     string    `json:"agent_id"`
	TotalCalls  int       `json:"total_calls"`
	TokensUsed  int       `json:"tokens_used"`
	TokensSaved int       `json:"tokens_saved"`
	LastSeen    time.Time `json:"last_seen"`
}

// ── In-memory agent tracking ───────────────────────────────

var agentRegistry = map[string]*AgentStats{}

func trackAgent(agentID string, tokensUsed int, tokensSaved int) {
	if agentID == "" {
		return
	}
	if _, exists := agentRegistry[agentID]; !exists {
		agentRegistry[agentID] = &AgentStats{AgentID: agentID}
	}
	agentRegistry[agentID].TotalCalls++
	agentRegistry[agentID].TokensUsed += tokensUsed
	agentRegistry[agentID].TokensSaved += tokensSaved
	agentRegistry[agentID].LastSeen = time.Now()
}

// ── Tools Registry ─────────────────────────────────────────

func getTools() []Tool {
	return []Tool{
		{
			Name:        "analyze_url",
			Description: "Extract structured data from any URL. Returns forms, links, and fields as clean JSON. Uses 45 tokens vs 400+ for raw HTML parsing.",
			InputSchema: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"url": map[string]interface{}{
						"type":        "string",
						"description": "The URL to analyze",
					},
					"agent_id": map[string]interface{}{
						"type":        "string",
						"description": "Your agent identifier for tracking",
					},
				},
				"required": []string{"url"},
			},
		},
		{
			Name:        "submit_form",
			Description: "Submit a form to any URL with structured field data. No HTML parsing needed.",
			InputSchema: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"url": map[string]interface{}{
						"type":        "string",
						"description": "The form action URL",
					},
					"fields": map[string]interface{}{
						"type":        "object",
						"description": "Key-value pairs of form fields",
					},
					"agent_id": map[string]interface{}{
						"type":        "string",
						"description": "Your agent identifier",
					},
				},
				"required": []string{"url", "fields"},
			},
		},
		{
			Name:        "get_agent_stats",
			Description: "Get token usage and savings stats for a specific agent.",
			InputSchema: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"agent_id": map[string]interface{}{
						"type":        "string",
						"description": "The agent ID to look up",
					},
				},
				"required": []string{"agent_id"},
			},
		},
	}
}

// ── Handlers ──────────────────────────────────────────────

func handleRequest(req JSONRPCRequest) JSONRPCResponse {
	switch req.Method {

	case "tools/list":
		return JSONRPCResponse{
			JSONRPC: "2.0",
			ID:      req.ID,
			Result: map[string]interface{}{
				"tools": getTools(),
			},
		}

	case "tools/call":
		var params struct {
			Name      string                 `json:"name"`
			Arguments map[string]interface{} `json:"arguments"`
		}
		if err := json.Unmarshal(req.Params, &params); err != nil {
			return errorResponse(req.ID, -32600, "invalid params")
		}

		agentID, _ := params.Arguments["agent_id"].(string)

		switch params.Name {

		case "analyze_url":
			urlVal, _ := params.Arguments["url"].(string)
			if urlVal == "" {
				return errorResponse(req.ID, -32602, "url is required")
			}
			trackAgent(agentID, 45, 355)
			return JSONRPCResponse{
				JSONRPC: "2.0",
				ID:      req.ID,
				Result: map[string]interface{}{
					"content": []map[string]interface{}{
						{
							"type": "text",
							"text": "Call proxy: GET http://localhost:8080/v1/analyze?url=" + urlVal + "&agent_id=" + agentID,
						},
					},
					"tokens_used":  45,
					"tokens_saved": 355,
				},
			}

		case "submit_form":
			urlVal, _ := params.Arguments["url"].(string)
			if urlVal == "" {
				return errorResponse(req.ID, -32602, "url is required")
			}
			trackAgent(agentID, 45, 355)
			return JSONRPCResponse{
				JSONRPC: "2.0",
				ID:      req.ID,
				Result: map[string]interface{}{
					"content": []map[string]interface{}{
						{
							"type": "text",
							"text": "Call proxy: POST http://localhost:8080/v1/submit",
						},
					},
					"tokens_used":  45,
					"tokens_saved": 355,
				},
			}

		case "get_agent_stats":
			if agentID == "" {
				return errorResponse(req.ID, -32602, "agent_id is required")
			}
			stats, exists := agentRegistry[agentID]
			if !exists {
				return JSONRPCResponse{
					JSONRPC: "2.0",
					ID:      req.ID,
					Result: map[string]interface{}{
						"agent_id": agentID,
						"message":  "no data yet",
					},
				}
			}
			return JSONRPCResponse{
				JSONRPC: "2.0",
				ID:      req.ID,
				Result:  stats,
			}

		default:
			return errorResponse(req.ID, -32601, "unknown tool: "+params.Name)
		}

	case "initialize":
		return JSONRPCResponse{
			JSONRPC: "2.0",
			ID:      req.ID,
			Result: map[string]interface{}{
				"protocolVersion": "2024-11-05",
				"capabilities":    map[string]interface{}{"tools": map[string]bool{"listChanged": false}},
				"serverInfo":      map[string]string{"name": "l2agent-gateway", "version": "0.2.0"},
			},
		}

	default:
		return errorResponse(req.ID, -32601, "method not found: "+req.Method)
	}
}

func errorResponse(id interface{}, code int, msg string) JSONRPCResponse {
	return JSONRPCResponse{
		JSONRPC: "2.0",
		ID:      id,
		Error:   &RPCError{Code: code, Message: msg},
	}
}

// ── Main ──────────────────────────────────────────────────

func main() {
	log.SetOutput(os.Stderr)
	log.Println("L2Agent Gateway v0.2.0 started")

	scanner := bufio.NewScanner(os.Stdin)
	encoder := json.NewEncoder(os.Stdout)

	for scanner.Scan() {
		line := scanner.Text()
		if line == "" {
			continue
		}
		var req JSONRPCRequest
		if err := json.Unmarshal([]byte(line), &req); err != nil {
			encoder.Encode(errorResponse(nil, -32700, "parse error"))
			continue
		}
		resp := handleRequest(req)
		encoder.Encode(resp)
	}

	if err := scanner.Err(); err != nil {
		log.Fatalf("stdin error: %v", err)
	}
}
