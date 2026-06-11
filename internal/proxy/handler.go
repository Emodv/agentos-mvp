## 🛠️ Step 1: Create `internal/proxy/handler.go`

Create a new file:

```
internal/proxy/handler.go
```

Paste the following code into it:

```go
package proxy

import (
	"encoding/json"
	"net/http"
	"strings"

	"github.com/PuerkitoBio/goquery"
)

// ScrapeRequest defines the incoming JSON payload.
type ScrapeRequest struct {
	URL string `json:"url"`
}

// Form represents an HTML form.
type Form struct {
	Action string   `json:"action"`
	Method string   `json:"method"`
	Inputs []string `json:"inputs"`
}

// ScrapeResponse is returned to the AI agent.
type ScrapeResponse struct {
	Title   string   `json:"title"`
	Forms   []Form   `json:"forms"`
	Buttons []string `json:"buttons"`
	Links   []string `json:"links"`
}

// ScrapeHandler converts HTML into structured JSON.
func ScrapeHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "only POST allowed", http.StatusMethodNotAllowed)
		return
	}

	var req ScrapeRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	if req.URL == "" {
		http.Error(w, "missing url", http.StatusBadRequest)
		return
	}

	doc, err := goquery.NewDocument(req.URL)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	resp := ScrapeResponse{
		Title:   strings.TrimSpace(doc.Find("title").First().Text()),
		Forms:   extractForms(doc),
		Buttons: extractButtons(doc),
		Links:   extractLinks(doc),
	}

	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Access-Control-Allow-Origin", "*")

	json.NewEncoder(w).Encode(resp)
}

func extractForms(doc *goquery.Document) []Form {
	var forms []Form

	doc.Find("form").Each(func(i int, s *goquery.Selection) {
		action, _ := s.Attr("action")
		method, _ := s.Attr("method")

		if method == "" {
			method = "GET"
		}

		var inputs []string

		s.Find("input, textarea, select").Each(func(i int, input *goquery.Selection) {
			if name, ok := input.Attr("name"); ok && name != "" {
				inputs = append(inputs, name)
			}
		})

		forms = append(forms, Form{
			Action: action,
			Method: strings.ToUpper(method),
			Inputs: inputs,
		})
	})

	return forms
}

func extractButtons(doc *goquery.Document) []string {
	var buttons []string

	doc.Find("button").Each(func(i int, s *goquery.Selection) {
		text := strings.TrimSpace(s.Text())
		if text != "" {
			buttons = append(buttons, text)
		}
	})

	doc.Find("input[type='submit'], input[type='button']").Each(func(i int, s *goquery.Selection) {
		if value, ok := s.Attr("value"); ok && value != "" {
			buttons = append(buttons, value)
		}
	})

	return buttons
}

func extractLinks(doc *goquery.Document) []string {
	var links []string

	doc.Find("a[href]").Each(func(i int, s *goquery.Selection) {
		href, ok := s.Attr("href")
		if !ok {
			return
		}

		if strings.HasPrefix(href, "http") || strings.HasPrefix(href, "/") {
			links = append(links, href)
		}
	})

	return links
}
```

---

## 🛠️ Step 2: Update `cmd/proxy/main.go`

Replace the file with:

```go
package main

import (
	"log"
	"net/http"

	"github.com/Emodv/l2agent/internal/proxy"
)

func main() {
	http.HandleFunc("/scrape", proxy.ScrapeHandler)

	log.Println("L2Agent proxy listening on :8080")

	log.Fatal(http.ListenAndServe(":8080", nil))
}
```

---

## 🧪 Test

```bash
curl -X POST http://localhost:8080/scrape \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com"}'
```

Expected response:

```json
{
  "title": "Example Domain",
  "forms": [],
  "buttons": [],
  "links": [
    "https://www.iana.org/domains/example"
  ]
}
```
