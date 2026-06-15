"""
HTTP client for the IntelGit Hub registry.
All network calls are optional – registry errors never crash the CLI.
"""
from __future__ import annotations

import json
from typing import Optional
from urllib.error import URLError
from urllib.request import urlopen, Request
from urllib.parse import urlencode, quote


class RegistryClient:
    def __init__(self, base_url: str, timeout: int = 10):
        self.base = base_url.rstrip("/")
        self.timeout = timeout

    def push(self, ko: dict, output_bytes: Optional[bytes] = None) -> dict:
        """
        POST /v1/ko with multipart form data.
        Returns the server response dict.
        """
        import urllib.request, urllib.parse, io
        boundary = "IntelGitBoundary"
        body_parts: list[bytes] = []

        def _part(name: str, data: bytes, content_type: str = "text/plain"):
            return (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n'
                f"Content-Type: {content_type}\r\n\r\n"
            ).encode() + data + b"\r\n"

        body_parts.append(_part("ko_json", json.dumps(ko, default=str).encode()))
        if output_bytes:
            body_parts.append(
                f'--{boundary}\r\nContent-Disposition: form-data; name="output"; '
                f'filename="output.txt"\r\nContent-Type: application/octet-stream\r\n\r\n'
                .encode() + output_bytes + b"\r\n"
            )
        body_parts.append(f"--{boundary}--\r\n".encode())
        body = b"".join(body_parts)

        req = Request(
            f"{self.base}/v1/ko",
            data=body,
            method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        return self._request(req)

    def get_ko(self, ko_id: str) -> Optional[dict]:
        safe_id = quote(ko_id, safe="")
        return self._request(Request(f"{self.base}/v1/ko/{safe_id}"))

    def get_output(self, ko_id: str) -> Optional[bytes]:
        safe_id = quote(ko_id, safe="")
        try:
            with urlopen(f"{self.base}/v1/output/{safe_id}", timeout=self.timeout) as r:
                return r.read()
        except Exception:
            return None

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        qs = urlencode({"q": query, "top_k": top_k})
        result = self._request(Request(f"{self.base}/v1/search?{qs}"))
        return (result or {}).get("results", [])

    def record_reuse(self, ko_id: str):
        safe_id = quote(ko_id, safe="")
        try:
            req = Request(f"{self.base}/v1/reuse/{safe_id}", data=b"", method="POST")
            self._request(req)
        except Exception:
            pass

    def leaderboard(self) -> list[dict]:
        result = self._request(Request(f"{self.base}/v1/leaderboard"))
        return (result or {}).get("results", [])

    def _request(self, req: Request) -> Optional[dict]:
        try:
            with urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read())
        except Exception:
            return None
