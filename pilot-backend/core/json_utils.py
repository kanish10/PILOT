import json
import re
import logging

logger = logging.getLogger(__name__)


def extract_json(text: str) -> dict:
    """
    Robustly extract a JSON object from an LLM response.
    Handles raw JSON, markdown code blocks, and JSON embedded in prose.
    """
    if not text:
        raise ValueError("Empty response from LLM")

    text = text.strip()

    # 1. Try direct parse first (fastest path)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. Strip markdown code fences (```json ... ``` or ``` ... ```)
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 3. Find the outermost { ... } in the text
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    logger.error("Failed to extract JSON from LLM response:\n%s", text[:600])
    raise ValueError("No valid JSON object found in LLM response")
