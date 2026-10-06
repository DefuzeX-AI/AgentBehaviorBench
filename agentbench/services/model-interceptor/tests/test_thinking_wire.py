"""Explicit legacy-thinking wire regressions; no model calls or proxy dependencies."""
from copy import deepcopy
import json
from types import SimpleNamespace
import unittest

from model.native import NativeJsonWire
from model.thinking import ThinkingChatWire
from defuzex_model_interceptor.observation.decoders import THINKING_CHAT_PROTOCOL
from defuzex_model_interceptor.transport.sse import SSEDecoder


def event(delta, finish=None):
    return {"id": "test", "object": "chat.completion.chunk", "model": "candidate",
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}


def frames(events, *, done=True):
    return b"".join(b"data: " + json.dumps(e, ensure_ascii=False).encode() + b"\n\n" for e in events) + (
        b"data: [DONE]\n\n" if done else b"")


def content(output):
    parser = SSEDecoder()
    events = parser.feed(output)
    parser.feed(b"")
    return "".join((c.get("delta") or {}).get("content") or "" for e in events for c in e.get("choices", []))


class ThinkingWireTests(unittest.TestCase):
    def test_reasoning_and_answer_preserved_across_byte_boundaries(self):
        events = [event({"role": "assistant", "content": None}),
                  event({"reasoning_content": "实际"}), event({"reasoning_content": "推理"}),
                  event({"content": '[{"query":"CFTR"}]'}), event({}, "stop"),
                  {"choices": [], "usage": {"total_tokens": 42}}]
        stream = ThinkingChatWire().stream()
        output = b"".join(stream.feed(bytes([b])) for b in frames(events)) + stream.feed(b"")
        self.assertEqual(content(output), '<think>实际推理</think>[{"query":"CFTR"}]')
        decoded = THINKING_CHAT_PROTOCOL.decode_response(output, "text/event-stream")["events"]
        self.assertEqual(sum("usage" in e for e in decoded), 1)
        self.assertEqual(decoded[-1]["usage"], {"total_tokens": 42})
        self.assertEqual(decoded[-2]["choices"][0]["finish_reason"], "stop")
        self.assertEqual(output.count(b"data: [DONE]"), 1)
        self.assertTrue(any(e["choices"] and e["choices"][0]["delta"].get("content") == "</think>"
                            for e in decoded))

    def test_simultaneous_reasoning_answer_has_one_usage_and_finish(self):
        e = event({"reasoning_content": "why", "content": "answer"}, "length")
        e["usage"] = {"total_tokens": 3}
        stream = ThinkingChatWire().stream()
        output = stream.feed(frames([e])) + stream.feed(b"")
        self.assertEqual(content(output), "<think>why</think>answer")
        parsed = THINKING_CHAT_PROTOCOL.decode_response(output, "text/event-stream")["events"]
        self.assertEqual(sum("usage" in p for p in parsed), 1)
        self.assertEqual(parsed[-1]["choices"][0]["finish_reason"], "length")

    def test_no_reasoning_does_not_create_markers_or_queries(self):
        stream = ThinkingChatWire().stream()
        output = stream.feed(frames([event({"content": "[]"}, "stop")])) + stream.feed(b"")
        self.assertEqual(content(output), "[]")

    def test_reasoning_only_does_not_create_answer_or_closing_marker(self):
        stream = ThinkingChatWire().stream()
        output = stream.feed(frames([event({"reasoning_content": "unfinished"}, "length")])) + stream.feed(b"")
        self.assertEqual(content(output), "<think>unfinished")

    def test_existing_inline_format_preserved_without_separate_reasoning(self):
        stream = ThinkingChatWire().stream()
        original = "<think>native</think>answer"
        self.assertEqual(content(stream.feed(frames([event({"content": original}, "stop")])) + stream.feed(b"")), original)

    def test_stream_state_is_per_call_and_explicit_only(self):
        self.assertIsNone(ThinkingChatWire().signature)
        wire = ThinkingChatWire()
        first, second = wire.stream(), wire.stream()
        first.feed(frames([event({"reasoning_content": "first"})], done=False))
        self.assertEqual(content(second.feed(frames([event({"content": "second"}, "stop")])) + second.feed(b"")), "second")

    def test_late_reasoning_and_tool_calls_rejected(self):
        stream = ThinkingChatWire().stream()
        stream.feed(frames([event({"content": "answer"})], done=False))
        with self.assertRaisesRegex(ValueError, "Reasoning after answer"):
            stream.feed(frames([event({"reasoning_content": "too late"})]))
        with self.assertRaisesRegex(ValueError, "tool calls"):
            ThinkingChatWire().stream().feed(frames([event({"tool_calls": [{"id": "tool"}]})]))

    def test_unfinished_error_and_non_text_stream_rejected(self):
        stream = ThinkingChatWire().stream()
        stream.feed(frames([event({"content": "answer"})], done=False))
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            stream.feed(b"")
        with self.assertRaises(ValueError):
            ThinkingChatWire().stream().feed(frames([{"error": {"message": "upstream failed"}}]))
        with self.assertRaisesRegex(ValueError, "string"):
            ThinkingChatWire().stream().feed(frames([event({"reasoning_content": ["invalid"]})]))

    def test_ambiguous_mixed_format_and_multiple_choices_rejected(self):
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            ThinkingChatWire().stream().feed(frames([event({"reasoning_content": "why", "content": "</think>answer"})]))
        multiple = event({"content": "one"})
        multiple["choices"].append({"index": 1, "delta": {"content": "two"}})
        with self.assertRaisesRegex(ValueError, "one choice"):
            ThinkingChatWire().stream().feed(frames([multiple]))

    def test_unary_preserves_source_usage_finish_and_errors(self):
        source = {"choices": [{"index": 0, "message": {"role": "assistant", "reasoning_content": "why", "content": "answer"},
                               "finish_reason": "stop"}], "usage": {"total_tokens": 20}}
        original = deepcopy(source)
        response = ThinkingChatWire().response(source, 200)
        self.assertEqual(source, original)
        self.assertEqual(response, original)
        self.assertEqual(response["choices"][0]["message"]["content"], "answer")
        self.assertEqual(response["choices"][0]["message"]["reasoning_content"], "why")
        self.assertEqual(response["usage"], original["usage"])
        self.assertEqual(response["choices"][0]["finish_reason"], "stop")
        error = {"error": {"message": "unavailable"}}
        self.assertEqual(ThinkingChatWire().response(error, 410), error)

    def test_issue229_unary_native_intention_and_relevancy_json(self):
        # Real failing run returned these valid JSON objects with reasoning in
        # a separate field. The native ainvoke callers do not strip </think>.
        for answer in ({"intention": "no"}, {"score": "no"}):
            with self.subTest(answer=answer):
                source = {"choices": [{"index": 0, "message": {
                    "role": "assistant", "content": json.dumps(answer),
                    "reasoning_content": "actual separate reasoning"},
                    "finish_reason": "stop"}], "usage": {"total_tokens": 20}}
                response = ThinkingChatWire().response(source, 200)
                self.assertEqual(json.loads(response["choices"][0]["message"]["content"]), answer)
                self.assertEqual(response, source)

    def test_unary_empty_or_malformed_answer_is_not_repaired(self):
        for answer in ("", "not JSON", None):
            source = {"choices": [{"message": {"content": answer,
                       "reasoning_content": "actual reasoning"}, "finish_reason": "length"}]}
            self.assertEqual(ThinkingChatWire().response(source, 200), source)

    def test_decode_preserves_model_and_request_and_rejects_n(self):
        payload = {"model": "native", "messages": [{"role": "system", "content": "detailed thinking on"}], "stream": True}
        request = SimpleNamespace(content=json.dumps(payload).encode())
        source, forwarded = ThinkingChatWire().decode(request)
        self.assertEqual(source, payload)
        self.assertEqual(forwarded, payload)
        request.content = json.dumps({**payload, "n": 2}).encode()
        with self.assertRaisesRegex(ValueError, "n=1"):
            ThinkingChatWire().decode(request)

    def test_standard_native_chat_stream_remains_byte_for_byte(self):
        raw = frames([event({"reasoning_content": "why"}), event({"content": "answer"}, "stop")])
        stream = NativeJsonWire("/chat/completions").stream()
        self.assertEqual(stream.feed(raw), raw)
        self.assertEqual(stream.feed(b""), b"")


if __name__ == "__main__":
    unittest.main()
