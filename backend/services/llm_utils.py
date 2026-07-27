"""LLM 输出解析工具。"""
import json


def parse_json(raw: str) -> dict:
    """解析 LLM 返回的 JSON，容忍 markdown 代码块包裹。失败返回空 dict。"""
    clean = raw.strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        return {}
