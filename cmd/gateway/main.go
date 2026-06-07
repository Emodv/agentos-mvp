// Agent OS MVP - MCP Gateway with Agent Tracking
// Co-Founder & Author: Emodv

package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/Emodv/agentos-mvp/internal"
	"github.com/Emodv/agentos-mvp/skills"
)

type JSONRPCRequest struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      int             `json:"id"`
	Method  string          `json:"method"`
	Params  json.RawMessage `json:"params"`
}

type Tool struct {
	Name        string      `json:"name"`
	Description string      `json:"description"`
	InputSchema interface{} `json:"inputSchema"`
}

type CallParams struct {
	Name      string                 `json:"name"`
	Arguments map[string]interface{} `json:"arguments"`
	AgentID   string                 `json:"agent_id,omitempty"`
}

var agentState = internal.NewAgentState()
const tokenLimitPerAgent = 10000   // soft limit
const rateLimitPerMin = 60

func main() {
	scanner := bufio.NewScanner(os.Stdin)
	skillRegistry := skills.NewRegistry()

	for scanner.Scan() {
		line := scanner.Text()
		var req JSONRPCRequest
		if err := json.Unmarshal([]byte(line), &req); err != nil {
			sendError(req.ID, -32700, "Parse error")
			continue
		}

		switch req.Method {
		case "tools/list":
			handleListTools(req.ID, skillRegistry)
		case "tools/call":
			handleCallTool(req.ID, req.Params, skillRegistry)
		default:
			sendError(req.ID, -32601, "Method not found")
		}
	}
}

func handleListTools(id int, registry *skills.Registry) {
	tools := []Tool{}
	for _, skill := range registry.List() {
		tools = append(tools, Tool{
			Name:        skill.Name,
			Description: skill.Description,
			InputSchema: skill.InputSchema,
		})
	}
	result := map[string]interface{}{"tools": tools}
	sendResult(id, result)
}

func handleCallTool(id int, paramsRaw json.RawMessage, registry *skills.Registry) {
	var params CallParams
	if err := json.Unmarshal(paramsRaw, &params); err != nil {
		sendError(id, -32602, "Invalid params")
		return
	}

	agentID := params.AgentID
	if agentID == "" {
		agentID = "anonymous"
	}

	// Rate limiting
	if !agentState.RateLimit(agentID, rateLimitPerMin) {
		sendError(id, -32003, "rate limit exceeded")
		internal.Audit(agentID, "rate_limited", "tools/call")
		return
	}

	skill := registry.Get(params.Name)
	if skill == nil {
		sendError(id, -32001, "Tool not found")
		return
	}

	// Execute skill
	output, err := skill.Execute(params.Arguments)
	if err != nil {
		sendError(id, -32002, err.Error())
		internal.Audit(agentID, "tool_error", params.Name+": "+err.Error())
		return
	}

	// Estimate tokens used (rough: 1 token per 4 chars of output text)
	tokensUsed := len(output.Text) / 4
	agentState.AddUsage(agentID, tokensUsed)
	agentState.ResetIfNeeded(agentID, 24*time.Hour) // daily reset

	// Soft budget warning
	if agentState.GetUsage(agentID) > tokenLimitPerAgent {
		internal.Audit(agentID, "budget_warning", fmt.Sprintf("used %d tokens", agentState.GetUsage(agentID)))
	}

	internal.Audit(agentID, "tools.call", params.Name)

	sendResult(id, map[string]interface{}{
		"content": []map[string]string{
			{"type": "text", "text": output.Text},
		},
		"structured_output": output.Structured,
	})
}

func sendResult(id int, result interface{}) {
	resp := map[string]interface{}{
		"jsonrpc": "2.0",
		"id":      id,
		"result":  result,
	}
	out, _ := json.Marshal(resp)
	fmt.Println(string(out))
}

func sendError(id int, code int, message string) {
	resp := map[string]interface{}{
		"jsonrpc": "2.0",
		"id":      id,
		"error":   map[string]interface{}{"code": code, "message": message},
	}
	out, _ := json.Marshal(resp)
	fmt.Println(string(out))
}
