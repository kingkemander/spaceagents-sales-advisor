#!/usr/bin/env python3
"""Analyze local images through the SpaceAgents OpenAI-compatible vision API."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


DEFAULT_API_BASE = "https://token.spaceagents.cn/v1"
DEFAULT_MODEL = "qwen3.7-plus"
DEFAULT_FALLBACK_MODEL = "glm-5.2"
DEFAULT_KEY_ENV = "SPACEAGENTS_AUTO_API_KEY"


class VisionClientError(RuntimeError):
    pass


def api_base(explicit: str | None = None) -> str:
    return (explicit or os.environ.get("SPACEAGENTS_INFERENCE_URL") or DEFAULT_API_BASE).rstrip("/")


def api_key(env_name: str = DEFAULT_KEY_ENV) -> str:
    value = os.environ.get(env_name, "").strip()
    if not value:
        raise VisionClientError(f"missing API credential in environment variable {env_name}")
    return value


def request_json(url: str, key: str, payload: dict | None = None, timeout: int = 180) -> dict:
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Accept": "application/json", "Authorization": f"Bearer {key}", **({"Content-Type": "application/json"} if body else {})},
        method="POST" if body else "GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise VisionClientError(f"vision API HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise VisionClientError(f"vision API connection failed: {exc.reason}") from exc


def list_models(base: str | None = None, key_env: str = DEFAULT_KEY_ENV, timeout: int = 60) -> list[str]:
    data = request_json(f"{api_base(base)}/models", api_key(key_env), timeout=timeout)
    return sorted(str(item.get("id")) for item in data.get("data", []) if item.get("id"))


def image_mime(path: Path) -> str:
    guessed = mimetypes.guess_type(path.name)[0]
    if guessed and guessed.startswith("image/"):
        return guessed
    return "image/png"


def analyze_image(
    image_path: str | Path,
    question: str,
    model: str = DEFAULT_MODEL,
    base: str | None = None,
    key_env: str = DEFAULT_KEY_ENV,
    timeout: int = 180,
    max_tokens: int = 4096,
) -> str:
    path = Path(image_path).expanduser().resolve()
    if not path.is_file():
        raise VisionClientError(f"image not found: {path}")
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": 0.1,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": question},
                    {"type": "image_url", "image_url": {"url": f"data:{image_mime(path)};base64,{encoded}"}},
                ],
            }
        ],
    }
    data = request_json(f"{api_base(base)}/chat/completions", api_key(key_env), payload=payload, timeout=timeout)
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise VisionClientError("vision API response did not contain choices[0].message.content") from exc
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "\n".join(str(item.get("text", "")) for item in content if isinstance(item, dict)).strip()
    return str(content).strip()


def analyze_image_with_fallback(
    image_path: str | Path,
    question: str,
    models: list[str] | tuple[str, ...] = (DEFAULT_MODEL, DEFAULT_FALLBACK_MODEL),
    base: str | None = None,
    key_env: str = DEFAULT_KEY_ENV,
    timeout: int = 240,
    max_tokens: int = 4096,
) -> tuple[str, str, list[dict[str, str]]]:
    """Try vision models in order and return text, selected model, and prior errors."""
    errors: list[dict[str, str]] = []
    for model in models:
        try:
            text = analyze_image(
                image_path,
                question,
                model=model,
                base=base,
                key_env=key_env,
                timeout=timeout,
                max_tokens=max_tokens,
            )
            if not text:
                raise VisionClientError("vision model returned empty content")
            return text, model, errors
        except VisionClientError as exc:
            errors.append({"model": model, "error": str(exc)})
    summary = "; ".join(f"{item['model']}: {item['error']}" for item in errors)
    raise VisionClientError(f"all vision models failed ({summary})")


def default_question(customer_hint: str = "") -> str:
    customer_line = f"本批次客户提示：{customer_hint}。" if customer_hint else ""
    return f"""你是销售客户材料的视觉分析器。{customer_line}
只依据图片中直接可见的内容分析，不虚构被遮挡或模糊的信息，不做人脸身份识别，不推断敏感个人属性。
请用简体中文 Markdown 输出：
1. 图片类型、标题与用途；
2. 可见文字转录：聊天记录按时间顺序区分说话人，会议纪要/海报/表格按版块完整提取所有可辨认文字与数字；模糊处写“[无法辨认]”，不得猜字；
3. 非文字视觉信息：图表关系、空间布局、现场状态、物品、标识、文件或图片缩略图及其上下文；
4. 销售事实：客户需求、人物与组织、项目阶段、预算、面积、金额、日期、承诺、异议、风险、决策链和下一步，并标注其在图片中的依据；
5. 待核验内容；
6. AI 推断。所有推断必须明确标注“推断”，不得混入图片事实。
如果图片是超长聊天截图，也必须从顶部到底部处理，不得只总结局部。"""


def main() -> int:
    parser = argparse.ArgumentParser(description="SpaceAgents local-image vision client")
    sub = parser.add_subparsers(dest="command", required=True)
    models_parser = sub.add_parser("models")
    models_parser.add_argument("--base-url")
    models_parser.add_argument("--key-env", default=DEFAULT_KEY_ENV)
    analyze_parser = sub.add_parser("analyze")
    analyze_parser.add_argument("--image", required=True)
    analyze_parser.add_argument("--model", default=DEFAULT_MODEL)
    analyze_parser.add_argument("--fallback-model", default=DEFAULT_FALLBACK_MODEL)
    analyze_parser.add_argument("--no-fallback", action="store_true")
    analyze_parser.add_argument("--question")
    analyze_parser.add_argument("--customer-hint", default="")
    analyze_parser.add_argument("--base-url")
    analyze_parser.add_argument("--key-env", default=DEFAULT_KEY_ENV)
    analyze_parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    try:
        if args.command == "models":
            print(json.dumps({"models": list_models(args.base_url, args.key_env)}, ensure_ascii=False, indent=2))
        else:
            question = args.question or default_question(args.customer_hint)
            if args.no_fallback:
                print(analyze_image(args.image, question, model=args.model, base=args.base_url, key_env=args.key_env, timeout=args.timeout))
            else:
                text, selected_model, errors = analyze_image_with_fallback(
                    args.image,
                    question,
                    models=(args.model, args.fallback_model),
                    base=args.base_url,
                    key_env=args.key_env,
                    timeout=args.timeout,
                )
                print(json.dumps({"status": "completed", "model": selected_model, "prior_errors": errors, "analysis": text}, ensure_ascii=False, indent=2))
        return 0
    except VisionClientError as exc:
        print(json.dumps({"status": "vision_error", "message": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 7


if __name__ == "__main__":
    raise SystemExit(main())
