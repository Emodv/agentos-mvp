// Agent OS MVP - MCP Gateway with Full Agent Tracking
// Co-Founder & Author: Emodv

package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
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

const (
	tokenLimitPerAgent = 10000
	rateLimitPerMin    = 60
	tokenResetWindow   = 24 * time.Hour
)

var agentState = internal.NewAgentState()

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

	if !agentState.RateLimit(agentID, rateLimitPerMin) {
		sendError(id, -32003, "rate limit exceeded")
		internal.Audit(agentID, "rate_limited", "tools/call")
		return
	}

	skill := registry.Get(params.Name)
	if skill == nil {
		sendError(id, -32001, "Tool not found")
		internal.Audit(agentID, "tool_not_found", params.Name)
		return
	}

	output, err := skill.Execute(params.Arguments)
	if err != nil {
		sendError(id, -32002, err.Error())
		internal.Audit(agentID, "tool_error", params.Name+": "+err.Error())
		return
	}

	tokensUsed := len(output.Text) / 4
	if tokensUsed < 1 {
		tokensUsed = 1
	}

	agentState.AddUsage(agentID, tokensUsed)
	agentState.ResetIfNeeded(agentID, tokenResetWindow)

	currentUsage := agentState.GetUsage(agentID)
	if currentUsage > tokenLimitPerAgent {
		internal.Audit(agentID, "budget_warning", fmt.Sprintf("exceeded soft limit: %d/%d tokens", currentUsage, tokenLimitPerAgent))
	}

	internal.Audit(agentID, "tools.call", fmt.Sprintf("skill=%s tokens=%d total=%d", params.Name, tokensUsed, currentUsage))

	sendResult(id, map[string]interface{}{
		"content": []map[string]string{
			{"type": "text", "text": output.Text},
		},
		"structured_output": output.Structured,
		"metadata": map[string]interface{}{
			"agent_id":     agentID,
			"tokens_used":  tokensUsed,
			"total_tokens": currentUsage,
			"rate_limit":   rateLimitPerMin,
			"token_limit":  tokenLimitPerAgent,
		},
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
