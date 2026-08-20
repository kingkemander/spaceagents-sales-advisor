"""Keep customer-facing views free of internal processing language."""

from __future__ import annotations

import re


INTERNAL_PATTERNS = (
    r"AI\s*(?:识图|处理|生成|推断|总结|分析|提取)",
    r"\bOCR\b",
    r"\bcustomer\.json\b",
    r"\bcombined-(?:analysis|ocr)\.md\b",
    r"\b(?:sources|inbox|image-batches)/",
    r"识别路径",
    r"识别模型",
    r"模型降级",
    r"置信度",
    r"SHA-?256",
    r"新建客户档案",
    r"写入客户档案",
    r"确认入库",
    r"材料入库",
    r"插件处理",
    r"技能处理",
)
INTERNAL_RE = re.compile("|".join(f"(?:{pattern})" for pattern in INTERNAL_PATTERNS), re.IGNORECASE)
PREFIX_RE = re.compile(r"^(?:根据|据|从)?(?:上述|本次|现有|三份|多份)?(?:材料|文件|截图)(?:显示|可见|表明|中提取)[:：，, ]*")


def contains_internal_language(value) -> bool:
    if isinstance(value, dict):
        return any(contains_internal_language(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(contains_internal_language(item) for item in value)
    return bool(INTERNAL_RE.search(str(value or "")))


def clean_public_text(value, empty: str = "") -> str:
    text = str(value or "").strip()
    if not text:
        return empty
    pieces = re.split(r"(?<=[。！？!?；;])|\n+", text)
    kept = []
    for piece in pieces:
        candidate = PREFIX_RE.sub("", piece.strip())
        if candidate and not INTERNAL_RE.search(candidate):
            kept.append(candidate)
    return "".join(kept).strip() or empty


def clean_public_value(value):
    if isinstance(value, dict):
        return {key: clean_public_value(item) for key, item in value.items()}
    if isinstance(value, list):
        cleaned = [clean_public_value(item) for item in value]
        return [item for item in cleaned if item not in ("", None, [], {})]
    if isinstance(value, str):
        return clean_public_text(value)
    return value
