// Agent OS MVP - Skill Registry
// Co-Founder & Author: Emodv (https://github.com/Emodv)

package skills

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"time"
)

type Skill struct {
	Name        string
	Description string
	InputSchema interface{}
	Execute     func(args map[string]interface{}) (*Result, error)
}

type Result struct {
	Text       string
	Structured interface{}
}

type Registry struct {
	skills map[string]*Skill
}

var httpClient = &http.Client{Timeout: 15 * time.Second}

func proxyURL() string {
	if u := os.Getenv("PROXY_URL"); u != "" {
		return u
	}
	return "http://localhost:8080"
}

func NewRegistry() *Registry {
	r := &Registry{skills: make(map[string]*Skill)}

	r.Register(&Skill{
		Name:        "web_analyze",
		Description: "Extract all forms and clickable elements from a URL",
		InputSchema: map[string]interface{}{
			"type": "object",
			"properties": map[string]interface{}{
				"url": map[string]string{"type": "string", "description": "The URL to analyze"},
			},
			"required": []string{"url"},
		},
		Execute: func(args map[string]interface{}) (*Result, error) {
			targetURL, ok := args["url"].(string)
			if !ok || targetURL == "" {
				return nil, fmt.Errorf("missing or invalid url argument")
			}

			endpoint := proxyURL() + "/v1/analyze?" + url.Values{"url": {targetURL}}.Encode()
			resp, err := httpClient.Get(endpoint)
			if err != nil {
				return nil, fmt.Errorf("proxy unreachable: %w", err)
			}
			defer resp.Body.Close()

			body, err := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
			if err != nil {
				return nil, fmt.Errorf("reading proxy response: %w", err)
			}
			if resp.StatusCode != http.StatusOK {
				return nil, fmt.Errorf("proxy returned %d: %s", resp.StatusCode, string(body))
			}

			var structured interface{}
			if err := json.Unmarshal(body, &structured); err != nil {
				return nil, fmt.Errorf("invalid JSON from proxy: %w", err)
			}

			return &Result{
				Text:       string(body),
				Structured: structured,
			}, nil
		},
	})

	r.Register(&Skill{
		Name:        "web_submit",
		Description: "Submit a form on a webpage",
		InputSchema: map[string]interface{}{
			"type": "object",
			"properties": map[string]interface{}{
				"url":     map[string]string{"type": "string", "description": "The page URL containing the form"},
				"form_id": map[string]string{"type": "string", "description": "The form ID from web_analyze (e.g. form_0)"},
				"values": map[string]interface{}{
					"type":                 "object",
					"description":          "Field name → value pairs to submit",
					"additionalProperties": map[string]string{"type": "string"},
				},
			},
			"required": []string{"url", "form_id", "values"},
		},
		Execute: func(args map[string]interface{}) (*Result, error) {
			targetURL, _ := args["url"].(string)
			formID, _ := args["form_id"].(string)
			rawValues, _ := args["values"].(map[string]interface{})

			if targetURL == "" || formID == "" {
				return nil, fmt.Errorf("url and form_id are required")
			}

			values := make(map[string]string)
			for k, v := range rawValues {
				if s, ok := v.(string); ok {
					values[k] = s
				}
			}

			payload := map[string]interface{}{
				"url":     targetURL,
				"form_id": formID,
				"values":  values,
			}
			body, err := json.Marshal(payload)
			if err != nil {
				return nil, fmt.Errorf("encoding request: %w", err)
			}

			resp, err := httpClient.Post(proxyURL()+"/v1/submit", "application/json", bytes.NewReader(body))
			if err != nil {
				return nil, fmt.Errorf("proxy unreachable: %w", err)
			}
			defer resp.Body.Close()

			respBody, err := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
			if err != nil {
				return nil, fmt.Errorf("reading proxy response: %w", err)
			}
			if resp.StatusCode != http.StatusOK {
				return nil, fmt.Errorf("proxy returned %d: %s", resp.StatusCode, string(respBody))
			}

			var structured interface{}
			json.Unmarshal(respBody, &structured)

			return &Result{
				Text:       string(respBody),
				Structured: structured,
			}, nil
		},
	})

	return r
}

func (r *Registry) Register(s *Skill) {
	r.skills[s.Name] = s
}

func (r *Registry) Get(name string) *Skill {
	return r.skills[name]
}

func (r *Registry) List() []*Skill {
	list := []*Skill{}
	for _, s := range r.skills {
		list = append(list, s)
	}
	return list
}
