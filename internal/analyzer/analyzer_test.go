package analyzer

import (
	"encoding/json"
	"strings"
	"testing"
)

const fixtureHTML = `<!DOCTYPE html>
<html>
<head><title>  Contact Us  </title><style>body{color:red}</style></head>
<body>
<nav><a href="/home">Home</a><a href="#top">Top</a><a href="javascript:void(0)">JS</a></nav>
<form action="/submit" method="post">
  <input type="text" name="name" placeholder="Your name" required>
  <input type="email" name="email">
  <input type="hidden" name="csrf" value="abc123">
  <select name="topic"><option>Sales</option></select>
  <textarea name="message"></textarea>
  <button type="submit">Send Message</button>
</form>
<a href="https://example.com/about">About</a>
<a href="https://example.com/about">About duplicate</a>
<input type="submit" value="Go">
</body>
</html>`

func TestAnalyzeExtractsStructure(t *testing.T) {
	page, err := Analyze(strings.NewReader(fixtureHTML), "https://example.com/contact")
	if err != nil {
		t.Fatalf("Analyze returned error: %v", err)
	}

	if page.Title != "Contact Us" {
		t.Errorf("title = %q, want %q", page.Title, "Contact Us")
	}

	if len(page.Forms) != 1 {
		t.Fatalf("forms = %d, want 1", len(page.Forms))
	}
	form := page.Forms[0]
	if form.Action != "https://example.com/submit" {
		t.Errorf("form action = %q, want absolute URL", form.Action)
	}
	if form.Method != "POST" {
		t.Errorf("form method = %q, want POST", form.Method)
	}

	// hidden csrf field must be excluded; name/email/topic/message remain
	if len(form.Fields) != 4 {
		t.Fatalf("fields = %d, want 4 (hidden excluded): %+v", len(form.Fields), form.Fields)
	}
	if form.Fields[0].Name != "name" || !form.Fields[0].Required {
		t.Errorf("first field = %+v, want required name field", form.Fields[0])
	}
	if form.Fields[2].Type != "select" {
		t.Errorf("topic type = %q, want select", form.Fields[2].Type)
	}

	if len(page.Buttons) != 2 {
		t.Errorf("buttons = %v, want [Send Message, Go]", page.Buttons)
	}

	// /home resolved absolute, #top and javascript: dropped, About deduped
	if len(page.Links) != 2 {
		t.Fatalf("links = %+v, want 2", page.Links)
	}
	if page.Links[0].Href != "https://example.com/home" {
		t.Errorf("relative link not resolved: %q", page.Links[0].Href)
	}
}

func TestFillMetaMeasuresRealSavings(t *testing.T) {
	page, err := Analyze(strings.NewReader(fixtureHTML), "https://example.com/contact")
	if err != nil {
		t.Fatal(err)
	}
	out, _ := json.Marshal(page)
	page.FillMeta(fixtureHTML, string(out))

	if page.Meta.RawTokens != EstimateTokens(fixtureHTML) {
		t.Errorf("raw tokens = %d, want %d", page.Meta.RawTokens, EstimateTokens(fixtureHTML))
	}
	if page.Meta.TokensSaved != page.Meta.RawTokens-page.Meta.OptimizedTokens {
		t.Errorf("saved = %d, inconsistent with raw-optimized", page.Meta.TokensSaved)
	}
	if page.Meta.SavingsPct < 0 || page.Meta.SavingsPct > 100 {
		t.Errorf("savings pct out of range: %f", page.Meta.SavingsPct)
	}
}

func TestEstimateTokens(t *testing.T) {
	if got := EstimateTokens(""); got != 0 {
		t.Errorf("empty string = %d tokens, want 0", got)
	}
	if got := EstimateTokens("abcdefgh"); got != 2 {
		t.Errorf("8 chars = %d tokens, want 2", got)
	}
}
