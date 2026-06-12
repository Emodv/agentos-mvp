// Package analyzer converts raw HTML into a compact, structured
// representation that AI agents can consume with far fewer tokens.
package analyzer

import (
	"io"
	"net/url"
	"strings"

	"github.com/PuerkitoBio/goquery"
)

// PageData is the structured representation of a web page.
type PageData struct {
	URL     string   `json:"url"`
	Title   string   `json:"title"`
	Forms   []Form   `json:"forms"`
	Buttons []string `json:"buttons,omitempty"`
	Links   []Link   `json:"links,omitempty"`
	Meta    Meta     `json:"meta"`
}

// Meta carries honest, measured token accounting for the conversion.
type Meta struct {
	RawTokens       int     `json:"raw_tokens_est"`
	OptimizedTokens int     `json:"optimized_tokens_est"`
	TokensSaved     int     `json:"tokens_saved_est"`
	SavingsPct      float64 `json:"savings_pct"`
	Note            string  `json:"note"`
}

type Form struct {
	Action string  `json:"action"`
	Method string  `json:"method"`
	Fields []Field `json:"fields"`
}

type Field struct {
	Name        string `json:"name"`
	Type        string `json:"type"`
	Required    bool   `json:"required,omitempty"`
	Placeholder string `json:"placeholder,omitempty"`
	Value       string `json:"value,omitempty"`
}

type Link struct {
	Text string `json:"text"`
	Href string `json:"href"`
}

const (
	maxLinks   = 50
	maxButtons = 25
	tokenNote  = "estimates use ~4 chars/token; raw = original HTML, optimized = this JSON"
)

// EstimateTokens approximates LLM token count using the common
// ~4 characters per token heuristic. It is an estimate, not a
// tokenizer, and is labeled as such in the API output.
func EstimateTokens(s string) int {
	n := len(s) / 4
	if n < 1 && len(s) > 0 {
		n = 1
	}
	return n
}

// Analyze parses HTML from r and extracts forms, buttons and links.
// baseURL is used to resolve relative hrefs and form actions.
func Analyze(r io.Reader, baseURL string) (*PageData, error) {
	doc, err := goquery.NewDocumentFromReader(r)
	if err != nil {
		return nil, err
	}

	base, _ := url.Parse(baseURL)

	page := &PageData{
		URL:   baseURL,
		Title: strings.TrimSpace(doc.Find("title").First().Text()),
		Forms: []Form{},
	}

	doc.Find("form").Each(func(_ int, s *goquery.Selection) {
		form := Form{
			Action: resolveRef(base, s.AttrOr("action", "")),
			Method: strings.ToUpper(s.AttrOr("method", "GET")),
			Fields: []Field{},
		}
		s.Find("input, select, textarea").Each(func(_ int, in *goquery.Selection) {
			name := in.AttrOr("name", "")
			if name == "" {
				return
			}
			typ := in.AttrOr("type", "")
			if typ == "" {
				switch goquery.NodeName(in) {
				case "select":
					typ = "select"
				case "textarea":
					typ = "textarea"
				default:
					typ = "text"
				}
			}
			if typ == "hidden" {
				return
			}
			_, required := in.Attr("required")
			form.Fields = append(form.Fields, Field{
				Name:        name,
				Type:        typ,
				Required:    required,
				Placeholder: in.AttrOr("placeholder", ""),
				Value:       in.AttrOr("value", ""),
			})
		})
		page.Forms = append(page.Forms, form)
	})

	doc.Find("button, input[type='submit'], input[type='button']").Each(func(_ int, s *goquery.Selection) {
		if len(page.Buttons) >= maxButtons {
			return
		}
		text := strings.TrimSpace(s.Text())
		if text == "" {
			text = strings.TrimSpace(s.AttrOr("value", ""))
		}
		if text != "" {
			page.Buttons = append(page.Buttons, text)
		}
	})

	seen := map[string]bool{}
	doc.Find("a[href]").Each(func(_ int, s *goquery.Selection) {
		if len(page.Links) >= maxLinks {
			return
		}
		href := s.AttrOr("href", "")
		if href == "" || strings.HasPrefix(href, "#") || strings.HasPrefix(href, "javascript:") {
			return
		}
		abs := resolveRef(base, href)
		if seen[abs] {
			return
		}
		seen[abs] = true
		page.Links = append(page.Links, Link{
			Text: strings.Join(strings.Fields(s.Text()), " "),
			Href: abs,
		})
	})

	return page, nil
}

// FillMeta computes measured token accounting given the raw HTML and
// the serialized JSON the caller is about to return.
func (p *PageData) FillMeta(rawHTML, serializedJSON string) {
	raw := EstimateTokens(rawHTML)
	opt := EstimateTokens(serializedJSON)
	saved := raw - opt
	if saved < 0 {
		saved = 0
	}
	p.Meta = Meta{
		RawTokens:       raw,
		OptimizedTokens: opt,
		TokensSaved:     saved,
		Note:            tokenNote,
	}
	if raw > 0 {
		p.Meta.SavingsPct = float64(saved) / float64(raw) * 100
	}
}

func resolveRef(base *url.URL, ref string) string {
	if base == nil || ref == "" {
		return ref
	}
	u, err := url.Parse(ref)
	if err != nil {
		return ref
	}
	return base.ResolveReference(u).String()
}
