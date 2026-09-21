from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: List[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") in {"input_text", "output_text", "text"}:
                parts.append(str(item.get("text") or ""))
        return "\n".join(p for p in parts if p)
    if isinstance(value, dict):
        if "body" in value:
            return _text(value["body"])
        if "content" in value:
            return _text(value["content"])
        if "text" in value:
            return str(value.get("text") or "")
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _message_content(value: Any) -> Any:
    if not isinstance(value, list):
        return _text(value)
    blocks: List[Dict[str, Any]] = []
    text_buf: List[str] = []
    for item in value:
        if not isinstance(item, dict):
            text_buf.append(_text(item))
            continue
        typ = str(item.get("type") or "")
        if typ in {"input_text", "output_text", "text"}:
            text_buf.append(str(item.get("text") or ""))
        elif typ in {"input_image", "image_url"}:
            url = item.get("image_url") or item.get("url")
            if url:
                if text_buf:
                    blocks.append({"type": "text", "text": "".join(text_buf)})
                    text_buf = []
                blocks.append({"type": "image_url", "image_url": {"url": str(url)}})
    if text_buf:
        blocks.append({"type": "text", "text": "".join(text_buf)})
    if blocks and all(x.get("type") == "text" for x in blocks):
        return "".join(str(x.get("text") or "") for x in blocks)
    return blocks or ""


def _tools(value: Any) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    if not isinstance(value, list):
        return [], {}
    out: List[Dict[str, Any]] = []
    kinds: Dict[str, str] = {}
    for tool in value:
        if not isinstance(tool, dict):
            continue
        typ, name = str(tool.get("type") or ""), str(tool.get("name") or "")
        if typ == "function" and name:
            out.append({"type": "function", "function": {
                "name": name,
                "description": str(tool.get("description") or ""),
                "parameters": tool.get("parameters") if isinstance(tool.get("parameters"), dict) else {"type": "object", "properties": {}},
            }})
            kinds[name] = "function"
        elif typ == "custom" and name:
            # Chat Completions has no freeform tool. Use a one-string surrogate and
            # convert the resulting call back to Responses custom_tool_call.
            out.append({"type": "function", "function": {
                "name": name,
                "description": str(tool.get("description") or ""),
                "parameters": {"type": "object", "properties": {"input": {"type": "string"}}, "required": ["input"], "additionalProperties": False},
            }})
            kinds[name] = "custom"
        # Provider-hosted tools (web_search/file_search/etc.) are intentionally not
        # invented at this compatibility boundary. Codex client tools are function/custom.
    return out, kinds


def _messages(body: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if body.get("instructions"):
        # Preserve Jack's existing authority rule. This stays developer context;
        # Jack's normal history policy decides whether it reaches a model stage.
        out.append({"role": "developer", "content": str(body["instructions"])})
    inp = body.get("input")
    if isinstance(inp, str):
        return out + [{"role": "user", "content": inp}]
    if inp is None:
        return out
    if not isinstance(inp, list):
        raise HTTPException(status_code=400, detail="Responses input must be a string or array")
    pending: List[Dict[str, Any]] = []

    def flush() -> None:
        if pending:
            out.append({"role": "assistant", "content": "", "tool_calls": list(pending)})
            pending.clear()

    for item in inp:
        if isinstance(item, str):
            flush(); out.append({"role": "user", "content": item}); continue
        if not isinstance(item, dict):
            continue
        typ = str(item.get("type") or "message")
        if typ == "message":
            flush()
            role = str(item.get("role") or "user")
            if role not in {"user", "assistant", "system", "developer", "tool"}:
                role = "user"
            out.append({"role": role, "content": _message_content(item.get("content"))})
        elif typ in {"function_call", "custom_tool_call"}:
            call_id = str(item.get("call_id") or item.get("id") or f"call_{uuid.uuid4().hex}")
            name = str(item.get("name") or "")
            args = item.get("arguments", "{}") if typ == "function_call" else json.dumps({"input": str(item.get("input") or "")}, separators=(",", ":"))
            if not isinstance(args, str):
                args = json.dumps(args, separators=(",", ":"))
            pending.append({"id": call_id, "type": "function", "function": {"name": name, "arguments": args}})
        elif typ in {"function_call_output", "custom_tool_call_output"}:
            flush()
            # Current Codex can occasionally replay malformed output without call_id.
            # Drop it rather than fabricate linkage to the wrong tool call.
            call_id = str(item.get("call_id") or "")
            if call_id:
                out.append({"role": "tool", "tool_call_id": call_id, "content": _text(item.get("output"))})
        elif typ == "reasoning":
            # External/opaque reasoning is not re-injected; Jack owns reasoning state.
            continue
        else:
            # Non-chat Responses history records (compaction, item_reference, hosted
            # tool records) are not model-authoritative in this bridge and are ignored.
            continue
    flush()
    return out


def _choice(value: Any) -> Any:
    if value in (None, "auto", "none"):
        return value or "auto"
    if value == "required":
        return "required"
    raise HTTPException(status_code=400, detail="unsupported Responses tool_choice")


def _chat_body(body: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, str]]:
    tools, kinds = _tools(body.get("tools"))
    chat: Dict[str, Any] = {"messages": _messages(body), "stream": bool(body.get("stream", False))}
    if body.get("model") is not None:
        chat["model"] = body["model"]  # virtual only; sanitize_agent_request removes authority.
    if tools:
        requested_choice = body.get("tool_choice", "auto")
        if (
            isinstance(requested_choice, dict)
            and requested_choice.get("type") in {"function", "custom"}
            and requested_choice.get("name")
        ):
            requested_type = str(requested_choice["type"])
            requested_name = str(requested_choice["name"])
            if kinds.get(requested_name) != requested_type:
                raise HTTPException(status_code=400, detail="Responses named tool_choice does not match an available tool")
            selected = [
                tool for tool in tools
                if str((tool.get("function") or {}).get("name") or "") == requested_name
            ]
            if len(selected) != 1:
                raise HTTPException(status_code=400, detail="Responses named tool_choice is ambiguous or unavailable")
            # Some OpenAI-compatible local backends accept only the string
            # tool_choice forms. Restricting the visible tool surface to the named
            # tool and requiring a tool call preserves exact named-tool semantics.
            chat["tools"] = selected
            chat["tool_choice"] = "required"
        else:
            chat["tools"] = tools
            chat["tool_choice"] = _choice(requested_choice)
    return chat, kinds


def _usage(value: Any) -> Dict[str, Any]:
    value = value if isinstance(value, dict) else {}
    i, o = int(value.get("prompt_tokens") or 0), int(value.get("completion_tokens") or 0)
    return {"input_tokens": i, "input_tokens_details": {"cached_tokens": 0}, "output_tokens": o,
            "output_tokens_details": {"reasoning_tokens": 0}, "total_tokens": int(value.get("total_tokens") or i + o)}


def _tool_item(call: Dict[str, Any], kinds: Dict[str, str]) -> Dict[str, Any]:
    fn = call.get("function") if isinstance(call.get("function"), dict) else {}
    name, args = str(fn.get("name") or ""), fn.get("arguments", "{}")
    if not isinstance(args, str):
        args = json.dumps(args, separators=(",", ":"))
    call_id = str(call.get("id") or f"call_{uuid.uuid4().hex}")
    if kinds.get(name) == "custom":
        raw = args
        try:
            parsed = json.loads(args)
            if isinstance(parsed, dict) and "input" in parsed:
                raw = str(parsed.get("input") or "")
        except Exception:
            pass
        return {"id": f"ctc_{uuid.uuid4().hex}", "type": "custom_tool_call", "call_id": call_id, "name": name, "input": raw, "status": "completed"}
    return {"id": f"fc_{uuid.uuid4().hex}", "type": "function_call", "call_id": call_id, "name": name, "arguments": args, "status": "completed"}


def _sse(kind: str, data: Dict[str, Any]) -> bytes:
    if "type" not in data:
        data = {"type": kind, **data}
    return f"event: {kind}\ndata: {json.dumps(data, ensure_ascii=False, separators=(',', ':'))}\n\n".encode()


def _chat_events(chunk: Any) -> List[Any]:
    text = chunk.decode("utf-8", "replace") if isinstance(chunk, bytes) else str(chunk)
    out: List[Any] = []
    for line in text.replace("\r\n", "\n").splitlines():
        if not line.startswith("data:"):
            continue
        raw = line[5:].strip()
        if raw == "[DONE]": out.append(raw)
        elif raw:
            try: out.append(json.loads(raw))
            except Exception: pass
    return out


async def _stream(jk: Any, chat: Dict[str, Any], kinds: Dict[str, str]) -> AsyncIterator[bytes]:
    rid, created = f"resp_jack_{uuid.uuid4().hex}", int(time.time())
    stub = {"id": rid, "object": "response", "created_at": created, "status": "in_progress", "model": jk.CFG.virtual_model, "output": []}
    yield _sse("response.created", {"response": stub})
    yield _sse("response.in_progress", {"response": stub})
    msg_id, rs_id = f"msg_{uuid.uuid4().hex}", f"rs_{uuid.uuid4().hex}"
    visible: List[str] = []; reasoning: List[str] = []; tool_acc: Dict[int, Dict[str, Any]] = {}; usage = None
    msg_open = rs_open = False
    try:
        async for chunk in jk.KERNEL.stream(chat):
            for obj in _chat_events(chunk):
                if not isinstance(obj, dict): continue
                if isinstance(obj.get("usage"), dict): usage = obj["usage"]
                choices = obj.get("choices")
                if not isinstance(choices, list) or not choices: continue
                delta = choices[0].get("delta") if isinstance(choices[0], dict) else None
                if not isinstance(delta, dict): continue
                r = delta.get("reasoning_content") if delta.get("reasoning_content") is not None else delta.get("reasoning")
                if r:
                    if not rs_open:
                        rs_open = True
                        yield _sse("response.output_item.added", {"output_index": 0, "item": {"id": rs_id, "type": "reasoning", "summary": [], "content": [], "status": "in_progress"}})
                    r = str(r); reasoning.append(r)
                    # Codex consumes reasoning_summary_text.delta as live reasoning telemetry.
                    yield _sse("response.reasoning_summary_text.delta", {"item_id": rs_id, "output_index": 0, "summary_index": 0, "delta": r})
                    yield _sse("response.reasoning_text.delta", {"item_id": rs_id, "output_index": 0, "content_index": 0, "delta": r})
                c = delta.get("content")
                if c:
                    oi = 1 if rs_open else 0
                    if not msg_open:
                        msg_open = True
                        yield _sse("response.output_item.added", {"output_index": oi, "item": {"id": msg_id, "type": "message", "role": "assistant", "status": "in_progress", "content": []}})
                    c = str(c); visible.append(c)
                    yield _sse("response.output_text.delta", {"item_id": msg_id, "output_index": oi, "content_index": 0, "delta": c, "logprobs": []})
                for tc in delta.get("tool_calls") or []:
                    if not isinstance(tc, dict): continue
                    idx = int(tc.get("index") or 0)
                    acc = tool_acc.setdefault(idx, {"id": "", "function": {"name": "", "arguments": ""}})
                    if tc.get("id"): acc["id"] = str(tc["id"])
                    fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
                    if fn.get("name"): acc["function"]["name"] += str(fn["name"])
                    if fn.get("arguments"): acc["function"]["arguments"] += str(fn["arguments"])
    except Exception as exc:
        failed = {"id": rid, "object": "response", "created_at": created, "completed_at": int(time.time()), "status": "failed",
                  "error": {"code": "jack_responses_stream_error", "message": str(exc)}, "model": jk.CFG.virtual_model, "output": []}
        yield _sse("response.failed", {"response": failed, "error": failed["error"]}); return
    finally:
        await jk.KERNEL._rearm_pending_tool_resume_for_messages(chat.get("messages"))
        await jk.KERNEL._rearm_pending_debugging_resumes_for_messages(chat.get("messages"))

    output: List[Dict[str, Any]] = []; oi = 0
    if rs_open:
        text = "".join(reasoning)
        item = {"id": rs_id, "type": "reasoning", "summary": [{"type": "summary_text", "text": text}], "content": [{"type": "reasoning_text", "text": text}], "status": "completed"}
        output.append(item)
        yield _sse("response.reasoning_summary_text.done", {"item_id": rs_id, "output_index": oi, "summary_index": 0, "text": text})
        yield _sse("response.output_item.done", {"output_index": oi, "item": item}); oi += 1
    if msg_open:
        text = "".join(visible)
        item = {"id": msg_id, "type": "message", "role": "assistant", "status": "completed", "content": [{"type": "output_text", "text": text, "annotations": []}]}
        output.append(item)
        yield _sse("response.output_item.done", {"output_index": oi, "item": item}); oi += 1
    for idx in sorted(tool_acc):
        item = _tool_item(tool_acc[idx], kinds); output.append(item)
        yield _sse("response.output_item.done", {"output_index": oi, "item": item}); oi += 1
    completed = {"id": rid, "object": "response", "created_at": created, "completed_at": int(time.time()), "status": "completed",
                 "error": None, "incomplete_details": None, "model": jk.CFG.virtual_model, "output": output,
                 "output_text": "".join(visible), "usage": _usage(usage), "metadata": {}}
    yield _sse("response.completed", {"response": completed})


def _nonstream(jk: Any, result: Any, kinds: Dict[str, str]) -> Dict[str, Any]:
    output: List[Dict[str, Any]] = []; now = int(time.time())
    reasoning = str(getattr(result, "reasoning_content", "") or "")
    content = str(getattr(result, "content", "") or "")
    if reasoning:
        output.append({"id": f"rs_{uuid.uuid4().hex}", "type": "reasoning", "summary": [{"type": "summary_text", "text": reasoning}], "content": [{"type": "reasoning_text", "text": reasoning}], "status": "completed"})
    if content:
        output.append({"id": f"msg_{uuid.uuid4().hex}", "type": "message", "role": "assistant", "status": "completed", "content": [{"type": "output_text", "text": content, "annotations": []}]})
    for call in getattr(result, "tool_calls", None) or []:
        if isinstance(call, dict): output.append(_tool_item(call, kinds))
    return {"id": f"resp_jack_{uuid.uuid4().hex}", "object": "response", "created_at": now, "completed_at": now, "status": "completed",
            "error": None, "incomplete_details": None, "model": jk.CFG.virtual_model, "output": output, "output_text": content,
            "usage": _usage(getattr(result, "usage", None)), "metadata": {}}


def register(jk: Any) -> None:
    if any(getattr(route, "path", None) == "/v1/responses" for route in jk.APP.routes):
        return

    @jk.APP.post("/v1/responses")
    async def responses(request: Request):
        await jk.enforce_kernel_auth(request)
        try: body = await request.json()
        except Exception as exc: raise HTTPException(status_code=400, detail="invalid JSON request body") from exc
        if not isinstance(body, dict): raise HTTPException(status_code=400, detail="Responses request body must be an object")
        chat, kinds = _chat_body(body)
        # Reuse the existing public authority filter; Responses parameters cannot
        # override Jack's model, reasoning, sampling, limits, or stage topology.
        chat = jk.sanitize_agent_request(chat)
        if body.get("stream"):
            return StreamingResponse(_stream(jk, chat, kinds), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})
        try: result = await jk.KERNEL.run(chat)
        except HTTPException: raise
        except Exception as exc:
            jk.LOG.exception("Responses compatibility request failed")
            raise HTTPException(status_code=500, detail=f"Jack Responses compatibility failure: {exc}") from exc
        return JSONResponse(_nonstream(jk, result, kinds))


def main() -> None:
    import jack_kernel as jk
    register(jk)
    # The interactive Jack CLI re-spawns a --serve child. Keep the compatibility
    # route registered in that child too.
    jk._server_command = lambda: [sys.executable, str(Path(__file__).resolve()), "--serve"]
    jk.main()


if __name__ == "__main__":
    main()
