"""The fake client agents use in tests."""

from pathlib import Path

import pytest

from pipeline.models.client import CallRequest, ModelCallError
from pipeline.models.fake import FakeModelClient
from pipeline.models.prompts import PromptError
from tests.prompt_files import write_prompt

INPUTS = {"title": "T", "abstract": "A"}


def test_returns_scripted_reply(tmp_path: Path) -> None:
    prompt = write_prompt(tmp_path)
    client = FakeModelClient(lambda request: {"in_scope": False, "reason": request.inputs["title"]})
    result = client.call(CallRequest(run_id=1, prompt=prompt, inputs=INPUTS))
    assert result.reply == {"in_scope": False, "reason": "T"}
    assert result.prompt_version == prompt.version
    assert len(client.requests) == 1


def test_rejects_replies_the_real_client_would(tmp_path: Path) -> None:
    prompt = write_prompt(tmp_path)
    client = FakeModelClient(lambda _: {"in_scope": "no"})
    with pytest.raises(ModelCallError):
        client.call(CallRequest(run_id=1, prompt=prompt, inputs=INPUTS))


def test_raises_scripted_errors_and_checks_inputs(tmp_path: Path) -> None:
    prompt = write_prompt(tmp_path)
    client = FakeModelClient(lambda _: ModelCallError("down"))
    with pytest.raises(ModelCallError, match="down"):
        client.call(CallRequest(run_id=1, prompt=prompt, inputs=INPUTS))
    with pytest.raises(PromptError):
        client.call(CallRequest(run_id=1, prompt=prompt, inputs={}))
