// Agent OS MVP - HTML to API Proxy
// Co-Founder & Author: Emodv (https://github.com/Emodv)

package main

import (
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/url"
	"strings"

	"github.com/PuerkitoBio/goquery"
)

type AnalyzeResponse struct {
	URL        string      `json:"url"`
	Forms      []Form      `json:"forms"`
	Clickables []Clickable `json:"clickables"`
}

type Form struct {
	ID     string  `json:"id"`
	Action string  `json:"action"`
	Method string  `json:"method"`
	Fields []Field `json:"fields"`
}

type Field struct {
	Name     string `json:"name"`
	Type     string `json:"type"`
	Required bool   `json:"required"`
}

type Clickable struct {
	Selector string `json:"selector"`
	Text     string `json:"text"`
	Type     string `json:"type"`
}

func analyzeHandler(w http.ResponseWriter, r *http.Request) {
	targetURL := r.URL.Query().Get("url")
	if targetURL == "" {
		http.Error(w, "missing url", 400)
		return
	}
	resp, err := http.Get(targetURL)
	if err != nil {
		http.Error(w, err.Error(), 500)
		return
	}
	defer resp.Body.Close()

	doc, err := goquery.NewDocumentFromReader(resp.Body)
	if err != nil {
		http.Error(w, err.Error(), 500)
		return
	}

	forms := []Form{}
	doc.Find("form").Each(func(i int, s *goquery.Selection) {
		action, _ := s.Attr("action")
		method, _ := s.Attr("method")
		if method == "" {
			method = "GET"
		}
		fields := []Field{}
		s.Find("input, textarea, select").Each(func(j int, input *goquery.Selection) {
			name, _ := input.Attr("name")
			typ, _ := input.Attr("type")
			required := false
			if _, ok := input.Attr("required"); ok {
				required = true
			}
			if name != "" {
				fields = append(fields, Field{Name: name, Type: typ, Required: required})
			}
		})
		forms = append(forms, Form{
			ID:     fmt.Sprintf("form_%d", i),
			Action: action,
			Method: method,
			Fields: fields,
		})
	})

	clickables := []Clickable{}
	doc.Find("button, a.btn, input[type=submit]").Each(func(i int, s *goquery.Selection) {
		text := strings.TrimSpace(s.Text())
		// Create a simple selector: use text if not empty, else fallback to the element's node name
		selector := text
		if selector == "" {
			selector = s.Get(0).Data // tag name, e.g., "button"
		}
		typ := "button"
		if s.Is("a") {
			typ = "link"
		}
		clickables = append(clickables, Clickable{Selector: selector, Text: text, Type: typ})
	})

	respJSON := AnalyzeResponse{URL: targetURL, Forms: forms, Clickables: clickables}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(respJSON)
}

type SubmitRequest struct {
	URL    string            `json:"url"`
	FormID string            `json:"form_id"`
	Values map[string]string `json:"values"`
}

func submitHandler(w http.ResponseWriter, r *http.Request) {
	var req SubmitRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, err.Error(), 400)
		return
	}
	resp, err := http.Get(req.URL)
	if err != nil {
		http.Error(w, err.Error(), 500)
		return
	}
	defer resp.Body.Close()

	doc, err := goquery.NewDocumentFromReader(resp.Body)
	if err != nil {
		http.Error(w, err.Error(), 500)
		return
	}

	var targetAction, targetMethod string
	doc.Find("form").Each(func(i int, s *goquery.Selection) {
		if fmt.Sprintf("form_%d", i) == req.FormID {
			targetAction, _ = s.Attr("action")
			targetMethod, _ = s.Attr("method")
			if targetMethod == "" {
				targetMethod = "GET"
			}
		}
	})

	if targetAction == "" {
		http.Error(w, "form not found", 404)
		return
	}

	fullURL := req.URL
	if !strings.HasPrefix(targetAction, "http") {
		base, _ := url.Parse(req.URL)
		fullURL = base.ResolveReference(&url.URL{Path: targetAction}).String()
	}

	formData := url.Values{}
	for k, v := range req.Values {
		formData.Set(k, v)
	}

	var httpResp *http.Response
	if strings.ToUpper(targetMethod) == "POST" {
		httpResp, err = http.PostForm(fullURL, formData)
	} else {
		getURL := fullURL + "?" + formData.Encode()
		httpResp, err = http.Get(getURL)
	}
	if err != nil {
		http.Error(w, err.Error(), 500)
		return
	}
	defer httpResp.Body.Close()
	body, _ := io.ReadAll(httpResp.Body)

	result := map[string]interface{}{
		"success":          httpResp.StatusCode >= 200 && httpResp.StatusCode < 300,
		"status_code":      httpResp.StatusCode,
		"response_preview": string(body[:min(200, len(body))]),
	}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(result)
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func main() {
	// Health check endpoint required by Fly.io
	http.HandleFunc("/flycheck", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})

	// Agent OS proxy endpoints
	http.HandleFunc("/v1/analyze", analyzeHandler)
	http.HandleFunc("/v1/submit", submitHandler)

	log.Printf("Proxy listening on 0.0.0.0:8080")
	log.Fatal(http.ListenAndServe("0.0.0.0:8080", nil))
}
