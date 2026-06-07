# Agent OS Gateway

**Author:** Emodv

## Skills

### web_analyze
Extract all forms and clickables from a URL.
Input: `{"url": "string"}`
Output: `{"forms": [...], "clickables": [...]}`

### web_submit
Submit a form on a webpage.
Input: `{"url": "string", "form_id": "string", "values": {...}}`
Output: `{"success": bool, "status_code": int}`
