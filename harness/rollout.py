"""
Recorded rollouts — run a task's stochastic agent policy against the live
service while capturing the full request/response transcript, WITHOUT modifying
the task's agent.

The task agents call the `requests` module directly (`requests.get/post`). To
record them non-invasively, we temporarily swap the agent module's `requests`
reference for a thin recording proxy that logs each call and delegates
everything else (exceptions, sessions, ...) to the real library. The agent's
behaviour and its probabilities are unchanged; only observation is added.

Used by `harness.export` (dataset generation) and `harness.analyze` (reward
signal-quality analysis).
"""
import requests as _real_requests

from harness.transcript import Recorder


class _RecordingHTTP:
    """Drop-in for the `requests` module that records get/post into a Recorder."""

    def __init__(self, recorder):
        self._rec = recorder

    def get(self, url, **kw):
        resp = _real_requests.get(url, **kw)
        self._rec.log("get", "GET", url, kw.get("json") or kw.get("params"), resp)
        return resp

    def post(self, url, **kw):
        resp = _real_requests.post(url, **kw)
        self._rec.log("post", "POST", url, kw.get("json"), resp)
        return resp

    def __getattr__(self, name):
        # RequestException, exceptions, Session, etc. delegate to the real lib.
        return getattr(_real_requests, name)


def record_rollout(agent_module, base, profile, budget, seed):
    """Run one rollout of agent_module.run_rollout with recording.

    Returns (result_dict, transcript_dict) where result_dict is the agent's own
    {solved, turns} and transcript_dict is the captured turns.
    """
    recorder = Recorder()
    saved = getattr(agent_module, "requests", None)
    agent_module.requests = _RecordingHTTP(recorder)
    try:
        result = agent_module.run_rollout(base, profile, budget=budget, seed=seed)
    finally:
        if saved is not None:
            agent_module.requests = saved
    return result, recorder.as_transcript(
        flag=None, elapsed_s=None)
