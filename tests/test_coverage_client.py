"""The benchmark HTTP client keeps completed work and handles server failures."""

import io
import json

import pytest

from opulse.bench import client


def test_chat_retries_invalid_json_and_preserves_request(monkeypatch):
    replies = iter([b"not json", (b'{"choices": [{"message": {"content": "Answer: 7"}, '
                                  b'"finish_reason": "stop"}], "usage": {"total_tokens": 4}}')])
    requests = []
    delays = []

    def urlopen(request, timeout):
        requests.append((request, timeout))
        return io.BytesIO(next(replies))

    monkeypatch.setattr(client.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(client.time, "sleep", delays.append)
    result = client.chat("http://localhost:8000/v1/", "model", "prompt", 32, 0.25,
                         api_key="key", timeout=5, retries=2, extra={"top_p": 0.8})

    assert result == {"response": "Answer: 7", "finish_reason": "stop", "usage": {"total_tokens": 4}}
    assert delays == [1]
    assert len(requests) == 2
    request, timeout = requests[0]
    assert request.full_url == "http://localhost:8000/v1/chat/completions"
    assert request.get_header("Authorization") == "Bearer key"
    assert timeout == 5
    assert json.loads(request.data) == {
        "model": "model", "messages": [{"role": "user", "content": "prompt"}],
        "temperature": 0.25, "max_tokens": 32, "top_p": 0.8,
    }


@pytest.mark.parametrize(("payload", "error"), [
    (b"invalid", "JSONDecodeError"),
    (b'{"choices": []}', "IndexError"),
    (b'{"choices": null}', "TypeError"),
])
def test_chat_reports_invalid_json_after_retries(monkeypatch, payload, error):
    monkeypatch.setattr(client.urllib.request, "urlopen", lambda *args, **kwargs: io.BytesIO(payload))
    monkeypatch.setattr(client.time, "sleep", lambda seconds: None)
    result = client.chat("http://localhost/v1", "model", "prompt", None, 0, retries=2)
    assert result["response"] == ""
    assert error in result["error"]


def test_run_tasks_resumes_good_rows_and_retries_failed_rows(tmp_path, monkeypatch):
    out = tmp_path / "responses.jsonl"
    out.write_text(json.dumps({"id": "done", "response": "old"}) + "\n" +
                   json.dumps({"id": "failed", "response": "", "error": "timeout"}) + "\n")
    calls = []

    def chat(base_url, model, prompt, max_tokens, temperature, api_key, extra):
        calls.append(prompt)
        return {"response": prompt.upper(), "usage": {"total_tokens": 1}}

    monkeypatch.setattr(client, "chat", chat)
    tasks = [{"id": key, "prompt": key} for key in ("done", "failed", "new")]
    assert client.run_tasks(tasks, out, "http://localhost/v1", "model", 12, 0.2, concurrency=2,
                            api_key="key", extra={"seed": 3}) == 2
    rows = {row["id"]: row for row in map(json.loads, out.read_text().splitlines())}
    assert set(calls) == {"failed", "new"}
    assert set(rows) == {"done", "failed", "new"}
    assert rows["done"]["response"] == "old"
    assert rows["failed"]["response"] == "FAILED"
    assert rows["new"]["sampling"] == {"temperature": 0.2, "max_tokens": 12, "seed": 3}
