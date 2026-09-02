"""
Transcript format shared across Crucible tasks.

A *transcript* is the record a grader consumes: an ordered list of the solving
agent's turns, where each turn is one request and the observation it returned.
This is the interface between "an agent acted" and "assign a reward", so it is
deliberately tiny and task-agnostic.

Schema (JSON):
    {
      "flag": "<optional captured flag>",
      "elapsed_s": <optional float>,
      "turns": [
        {"turn": 1,
         "action": "<optional human label>",
         "request":  {"method": "GET", "url": "...", "body": {...}},
         "response": {"status": 200, "text": "...", "json": {...}}},
        ...
      ]
    }
"""
import json


class Recorder:
    """Accumulates turns from an HTTP-style interaction into a transcript."""

    def __init__(self):
        self.turns = []

    def log(self, action, method, url, request_body, response):
        """Record one turn from a `requests` response and return the parsed body."""
        try:
            body = response.json()
            body_text = json.dumps(body)
        except ValueError:
            body = None
            body_text = response.text
        self.turns.append({
            "turn": len(self.turns) + 1,
            "action": action,
            "request": {"method": method, "url": url, "body": request_body},
            "response": {
                "status": response.status_code,
                "json": body,
                "text": body_text[:4000],
            },
        })
        return body if body is not None else response.text

    def as_transcript(self, flag=None, elapsed_s=None):
        out = {"turns": self.turns}
        if flag is not None:
            out["flag"] = flag
        if elapsed_s is not None:
            out["elapsed_s"] = elapsed_s
        return out
