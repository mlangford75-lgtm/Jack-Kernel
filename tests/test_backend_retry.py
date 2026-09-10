import asyncio
import importlib.util
import json
import os
import sys
import uuid
from pathlib import Path

os.environ["JACK_REASONING_LEVEL"] = "agentic"
os.environ["JACK_BACKEND_MODEL"] = "test-model"
os.environ["JACK_FORENSIC_ARCHIVE_MODE"] = "off"
SRC = Path(__file__).resolve().parents[1] / "jack_kernel.py"
name = "jack_retry_" + uuid.uuid4().hex
spec = importlib.util.spec_from_file_location(name, SRC)
m = importlib.util.module_from_spec(spec)
sys.modules[name] = m
spec.loader.exec_module(m)


class Response:
    def __init__(self, status, text="", lines=None, data=None):
        self.status_code = status
        self.text = text
        self.lines = lines or []
        self.data = data

    def json(self):
        return self.data

    async def aread(self):
        return self.text.encode()

    async def aclose(self):
        return None

    async def aiter_lines(self):
        for line in self.lines:
            yield line


class Client:
    def __init__(self):
        self.posts = 0
        self.sends = 0

    async def post(self, *args, **kwargs):
        self.posts += 1
        if self.posts == 1:
            return Response(500, "synthetic 500")
        return Response(200, data={"choices": [{"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}], "usage": {}})

    def build_request(self, *args, **kwargs):
        return object()

    async def send(self, request, stream=False):
        self.sends += 1
        if self.sends == 1:
            return Response(500, "synthetic 500")
        payload = {"choices": [{"delta": {"content": "ok"}, "finish_reason": "stop"}]}
        return Response(200, lines=["data: " + json.dumps(payload), "data: [DONE]"])

    async def aclose(self):
        return None


async def main():
    backend = m.OpenAICompatibleBackend(m.CFG)
    client = Client()
    backend._client = client
    backend._resolved_model = "test-model"
    backend._model_metadata_checked = True

    data = await backend.chat(messages=[{"role": "user", "content": "x"}], secondary_system="", profile=m.STAGES["extended_initial"])
    assert data["choices"][0]["message"]["content"] == "ok"
    assert client.posts == 2

    chunks = [chunk async for chunk in backend.chat_stream(messages=[{"role": "user", "content": "x"}], secondary_system="", profile=m.STAGES["extended_initial"])]
    assert chunks
    assert client.sends == 2
    print("Jack Kernel initial HTTP 5xx retry tests: PASS")


if __name__ == "__main__":
    asyncio.run(main())
