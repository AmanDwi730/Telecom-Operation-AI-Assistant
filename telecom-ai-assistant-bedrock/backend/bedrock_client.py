from __future__ import annotations

import json
from typing import Tuple

import boto3

from config import MODEL_ID, REGION

_bedrock_runtime = boto3.client("bedrock-runtime", region_name=REGION)


def _invoke_converse(system_prompt: str, user_prompt: str) -> str:
    response = _bedrock_runtime.converse(
        modelId=MODEL_ID,
        system=[{"text": system_prompt}],
        messages=[{"role": "user", "content": [{"text": user_prompt}]}],
        inferenceConfig={
            "maxTokens": 900,
            "temperature": 0.3,
            "topP": 0.9,
        },
    )
    content = response["output"]["message"]["content"]
    if content and isinstance(content, list):
        return "".join(part.get("text", "") for part in content)
    return str(content)


def _invoke_model(system_prompt: str, user_prompt: str) -> str:
    payload = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 900,
        "temperature": 0.3,
        "top_p": 0.9,
        "system": system_prompt,
        "messages": [{"role": "user", "content": [{"type": "text", "text": user_prompt}]}],
    }
    response = _bedrock_runtime.invoke_model(
        modelId=MODEL_ID,
        body=json.dumps(payload),
        accept="application/json",
        contentType="application/json",
    )
    body = json.loads(response["body"].read())
    if "content" in body and body["content"]:
        return "".join(part.get("text", "") for part in body["content"])
    return str(body)


def invoke_bedrock(system_prompt: str, user_prompt: str) -> str:
    try:
        return _invoke_converse(system_prompt, user_prompt)
    except Exception:
        return _invoke_model(system_prompt, user_prompt)
