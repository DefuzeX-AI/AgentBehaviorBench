#!/usr/bin/env python3
"""\u6d4b\u8bd5 OpenAI-compatible \u591a\u6a21\u6001 VLM \u63a8\u7406\u670d\u52a1\u3002\u7eaf\u6807\u51c6\u5e93\uff0c\u65e0\u9700 pip\u3002

\u5e73\u53f0\u7279\u6027:
  - OpenAI \u517c\u5bb9\u5355\u7aef\u70b9, \u8bf7\u6c42\u4f53\u91cc\u7684 model \u51b3\u5b9a\u7528\u54ea\u4e2a\u6a21\u578b, \u9996\u6b21\u8bf7\u6c42\u81ea\u52a8\u52a0\u8f7d (\u51b7\u542f\u52a8
    2B\u22481\u5206\u949f / 8B\u22482\u5206\u949f / InternVL\u22484\u5206\u949f), \u52a0\u8f7d\u540e\u5e38\u9a7b\u79d2\u56de; \u53cc\u5361\u6700\u591a\u540c\u65f6\u5e38\u9a7b 2 \u4e2a (LRU \u6dd8\u6c70)\u3002
  - \u591a\u6a21\u6001: \u6587\u672c / \u56fe\u7247 / \u89c6\u9891 \u5747\u5df2\u9a8c\u8bc1\u53ef\u7528 (Qwen3-VL / InternVL / MiniCPM \u652f\u6301\u89c6\u9891)\u3002
  - \u53ef\u7528\u6a21\u578b (model \u5b57\u6bb5\u53d6\u503c):
      qwen3vl-2b  qwen3vl-4b  qwen3vl-8b  internvl3_5-8b  minicpm-v-4_5  gemma3-4b  pixtral-12b

\u7aef\u70b9\u8bf4\u660e:
  GET  /v1/models           \u5217\u51fa\u53ef\u7528\u6a21\u578b (\u542b\u662f\u5426\u5df2\u52a0\u8f7d)
  GET  /health              \u5f53\u524d\u5e38\u9a7b\u6a21\u578b / GPU \u5360\u7528
  POST /v1/chat/completions \u5bf9\u8bdd (OpenAI \u683c\u5f0f; \u81ea\u52a8\u6309\u9700\u52a0\u8f7d\u6240\u9009\u6a21\u578b)

\u63a5\u5165\u5730\u5740\u7531 --base \u6307\u5b9a\uff0c\u9ed8\u8ba4\u4e3a\u672c\u673a http://127.0.0.1:9000\u3002
\u8fdc\u7a0b\u670d\u52a1\u53ef\u76f4\u63a5\u586b\u5199\u53ef\u8bbf\u95ee\u7684 HTTP(S) \u5730\u5740\uff0c\u6216\u5148\u901a\u8fc7 SSH \u5efa\u7acb\u672c\u5730\u7aef\u53e3\u8f6c\u53d1\u3002

\u591a\u6a21\u6001\u8bf7\u6c42\u683c\u5f0f (OpenAI content \u6570\u7ec4):
  \u56fe\u7247: {"type":"image_url","image_url":{"url":"data:image/jpeg;base64,..."}}
  \u89c6\u9891: {"type":"video_url","video_url":{"url":"data:video/mp4;base64,..."}}  # \u6216\u516c\u7f51 http \u89c6\u9891 URL
  \u9ed8\u8ba4\u6bcf\u6761 prompt \u9650 1 \u56fe / 1 \u89c6\u9891; \u9700\u8981\u591a\u56fe/\u591a\u89c6\u9891\u65f6\u5728\u670d\u52a1\u7aef models.json \u7ed9\u8be5\u6a21\u578b\u52a0
  "--limit-mm-per-prompt","{\"image\":4,\"video\":1}" (\u6539\u5b8c\u4e0b\u6b21\u8bf7\u6c42\u81ea\u52a8\u751f\u6548)\u3002

\u7528\u6cd5 (\u672c\u4ed3\u5e93\u8bf7\u7528 .venv/bin/python \u6267\u884c):
  .venv/bin/python scripts/vlm_api_test.py --list
  .venv/bin/python scripts/vlm_api_test.py --health
  .venv/bin/python scripts/vlm_api_test.py --model qwen3vl-8b --prompt "\u4f60\u597d, \u4ecb\u7ecd\u4e00\u4e0b\u4f60\u81ea\u5df1"
  .venv/bin/python scripts/vlm_api_test.py --model qwen3vl-8b --image /path/to.jpg --prompt "\u63cf\u8ff0\u8fd9\u5f20\u56fe"
  .venv/bin/python scripts/vlm_api_test.py --model qwen3vl-8b --video /path/to.mp4 --prompt "\u89c6\u9891\u91cc\u53d1\u751f\u4e86\u4ec0\u4e48"
"""
import argparse
import base64
import json
import mimetypes
import sys
import urllib.error
import urllib.request


def _req(method, url, payload=None, timeout=600):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        raise SystemExit(f"HTTP {e.code}: {body[:500]}")
    except Exception as e:  # noqa: BLE001
        raise SystemExit(f"\u8bf7\u6c42\u5931\u8d25: {e}")
    if body.lstrip().startswith("<"):
        raise SystemExit(
            "\u8fd4\u56de\u7684\u662f HTML \u800c\u975e JSON\u3002\u8bf7\u786e\u8ba4 --base \u6307\u5411 OpenAI-compatible API \u6839\u5730\u5740\uff0c"
            "\u5e76\u68c0\u67e5\u53cd\u5411\u4ee3\u7406\u6216\u7aef\u53e3\u8f6c\u53d1\u914d\u7f6e\u3002"
        )
    return json.loads(body)


def _data_url(path, default_mime):
    mime = mimetypes.guess_type(path)[0] or default_mime
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:9000",
                    help="VLM \u670d\u52a1\u5730\u5740 (\u9ed8\u8ba4: http://127.0.0.1:9000)")
    ap.add_argument("--model", default="qwen3vl-8b")
    ap.add_argument("--prompt", default="\u7528\u4e00\u53e5\u8bdd\u4ecb\u7ecd\u4f60\u81ea\u5df1")
    ap.add_argument("--image", help="\u53ef\u9009: \u672c\u5730\u56fe\u7247\u8def\u5f84 (\u8d70\u89c6\u89c9)")
    ap.add_argument("--video", help="\u53ef\u9009: \u672c\u5730\u89c6\u9891\u8def\u5f84 (mp4 \u7b49; \u8d70\u89c6\u9891\u7406\u89e3)")
    ap.add_argument("--max-tokens", type=int, default=256)
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--list", action="store_true", help="\u53ea\u5217\u6a21\u578b")
    ap.add_argument("--health", action="store_true", help="\u53ea\u770b\u5e38\u9a7b\u72b6\u6001")
    args = ap.parse_args()
    base = args.base.rstrip("/")

    if args.list:
        print(json.dumps(_req("GET", f"{base}/v1/models"), ensure_ascii=False, indent=2))
        return
    if args.health:
        print(json.dumps(_req("GET", f"{base}/health"), ensure_ascii=False, indent=2))
        return

    if args.image or args.video:
        content = [{"type": "text", "text": args.prompt}]
        if args.image:
            content.append({"type": "image_url",
                            "image_url": {"url": _data_url(args.image, "image/jpeg")}})
        if args.video:
            content.append({"type": "video_url",
                            "video_url": {"url": _data_url(args.video, "video/mp4")}})
    else:
        content = args.prompt

    payload = {
        "model": args.model,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": args.max_tokens,
        "temperature": args.temperature,
    }
    mm = "+".join([t for t, v in (("\u56fe\u7247", args.image), ("\u89c6\u9891", args.video)) if v]) or "\u7eaf\u6587\u672c"
    print(f"\u2192 {base}/v1/chat/completions  model={args.model}  [{mm}]"
          f"  (\u9996\u6b21\u52a0\u8f7d\u8be5\u6a21\u578b\u53ef\u80fd 1-4 \u5206\u949f)", file=sys.stderr)
    resp = _req("POST", f"{base}/v1/chat/completions", payload)
    msg = resp["choices"][0]["message"]["content"]
    usage = resp.get("usage", {})
    print("\n=== \u56de\u590d ===\n" + msg)
    print(f"\n=== tokens === prompt={usage.get('prompt_tokens')} "
          f"completion={usage.get('completion_tokens')} total={usage.get('total_tokens')}")


if __name__ == "__main__":
    main()
