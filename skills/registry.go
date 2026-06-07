// Agent OS MVP - Skill Registry
// Co-Founder & Author: Emodv (https://github.com/Emodv)

package skills

import (
	"fmt"
)

type Skill struct {
	Name         string
	Description  string
	InputSchema  interface{}
	Execute      func(args map[string]interface{}) (*Result, error)
}

type Result struct {
	Text       string
	Structured interface{}
}

type Registry struct {
	skills map[string]*Skill
}

func NewRegistry() *Registry {
	r := &Registry{skills: make(map[string]*Skill)}
	// Built-in web analyze skill
	r.Register(&Skill{
		Name:        "web_analyze",
		Description: "Extract forms and clickables from a URL",
		InputSchema: map[string]interface{}{
			"type": "object",
			"properties": map[string]interface{}{
				"url": map[string]string{"type": "string"},
			},
			"required": []string{"url"},
		},
		Execute: func(args map[string]interface{}) (*Result, error) {
			url, ok := args["url"].(string)
			if !ok {
				return nil, fmt.Errorf("missing url")
			}
			// Call proxy's analyze endpoint (mock for MVP)
			return &Result{
				Text:       fmt.Sprintf("Analyzed %s", url),
				Structured: map[string]string{"status": "ok"},
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
