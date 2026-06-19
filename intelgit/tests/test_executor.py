import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.core.crypto import generate_did_key
from src.core.executor import execute_and_commit
from src.core.store import KOLocalStore

_IDENTITY = generate_did_key()


def _make_store() -> KOLocalStore:
    return KOLocalStore(path=Path(tempfile.mkdtemp()))


def _fake_openai_response(text: str, prompt_tokens=10, completion_tokens=5):
    message = SimpleNamespace(content=text)
    choice = SimpleNamespace(message=message)
    usage = SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    return SimpleNamespace(choices=[choice], usage=usage)


def _fake_anthropic_response(text: str, input_tokens=10, output_tokens=5):
    block = SimpleNamespace(type="text", text=text)
    usage = SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)
    return SimpleNamespace(content=[block], usage=usage)


@patch("src.core.executor.get_or_create_identity", return_value=_IDENTITY)
def test_execute_and_commit_routes_openai_models(mock_identity):
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **kwargs: _fake_openai_response("hello from gpt")
            )
        )
    )
    with patch("openai.OpenAI", return_value=fake_client):
        ko, output = execute_and_commit(
            "test goal", {}, model="gpt-4-turbo", store=_make_store()
        )
    assert output == "hello from gpt"
    assert ko.proof.model == "gpt-4-turbo"
    assert ko.cost_usd > 0


@patch("src.core.executor.get_or_create_identity", return_value=_IDENTITY)
def test_execute_and_commit_routes_anthropic_models(mock_identity):
    fake_client = SimpleNamespace(
        messages=SimpleNamespace(
            create=lambda **kwargs: _fake_anthropic_response("hello from claude")
        )
    )
    with patch("anthropic.Anthropic", return_value=fake_client):
        ko, output = execute_and_commit(
            "test goal", {}, model="claude-3-5-sonnet-20241022", store=_make_store()
        )
    assert output == "hello from claude"
    assert ko.proof.model == "claude-3-5-sonnet-20241022"
    assert ko.cost_usd > 0
