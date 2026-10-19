"""Regression: real Jack resume may return interim text; TAS must not release it."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_deep_reasoning_kernel import FakeKernel, install_deep_reasoning, ns, tools


def test_tool_checkpoint_drops_provisional_content_and_native_reasoning():
    async def run():
        kernel = FakeKernel()
        original_register = kernel._register_stage_tool_resume

        async def legacy_kernel_register(**kwargs):
            response = await original_register(**kwargs)
            # Real pre-TAS Kernel's shared stage registry returns raw content
            # for non-ULTRA modes. Deliberately inject both possible leaks.
            response.content = "UNTRUSTED_ANTITHESIS_PROVISIONAL_TEXT"
            response.reasoning_content = "UNTRUSTED_ANTITHESIS_NATIVE_REASONING"
            return response

        kernel._register_stage_tool_resume = legacy_kernel_register
        install_deep_reasoning(kernel, ns())
        first = await kernel._prepare_commit({
            "messages": [{"role": "user", "content": "Verify independently"}],
            "tools": tools(),
        })
        assert first.finish_reason == "tool_calls"
        assert first.content is None, "Antithesis text cannot be released at tool boundary"
        assert first.reasoning_content is None, "Antithesis native reasoning cannot be released at tool boundary"
        assert first.tool_calls and first.tool_calls[0]["id"] == "call-7"
        result = await kernel._resume_tool_stage_nonstream(
            kernel._pending_tool_resumes["call-7"],
            [{"tool_call_id": "call-7", "content": "17"}],
        )
        assert result.content == "Synthesis: Part B=17"
        assert result.reasoning_content == "ONLY_R3"

    asyncio.run(run())
