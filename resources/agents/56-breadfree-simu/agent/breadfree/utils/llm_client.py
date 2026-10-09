from openai import OpenAI
import os
import re
import json
from datetime import datetime
from typing import Dict, Any, Optional

from breadfree.utils.logger import get_logger
logging = get_logger(__name__, mode="file")

# Ensure you set this environment variable or replace it with your actual key
HUNYUAN_API_KEY = os.environ.get("HUNYUAN_API_KEY")
if not HUNYUAN_API_KEY or HUNYUAN_API_KEY == "YOUR_API_KEY_HERE":
    raise RuntimeError("No valid HUNYUAN_API_KEY environment variable detected. Please set it and try again.")



async def async_hunyuan_chat(
        query=None,
        prompt=None,
        model="deepseek-v3.2", # deepseek-r1 deepseek-v3.1
        temperature=0.2, 
        top_p=0.3, 
        max_tokens=4096,
        stream=False,
    ):
    try:
        # Construct client
        client = OpenAI(
            api_key= HUNYUAN_API_KEY, # Hunyuan APIKey
            # base_url="https://api.hunyuan.cloud.tencent.com/v1",  # Hunyuan endpoint
            base_url="https://api.lkeap.cloud.tencent.com/v1"
        )
        messages=[]
        if prompt is not None:
            messages.append({"role": "system", "content": prompt})
        if query is not None:
            messages.append({"role": "user", "content": query})
        
        # Log the request with system prompt, user query and model
        # logging.info(f"--- LLM Request ---\nModel: {model}\nPrompt: {prompt}\nQuery: {query}\n-------------------")
        # Log the request with query and model
        logging.info(f"--- LLM Request ---\nModel: {model}\nQuery: {query}\n-------------------")
        completion = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            stream=stream,
        )
        
        response_content = completion.choices[0].message.content
        total_tokens = completion.usage.total_tokens
        
        # Log the response
        logging.info(f"--- LLM Response ---\nContent: {response_content}\nTokens: {total_tokens}\n--------------------")

        return response_content, total_tokens
    except Exception as e:
        error_msg = f"LLM Call Error: {e}"
        print(error_msg)
        logging.error(error_msg)
        return "", 0

def parse_llm_response(response: str, fallback: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse JSON from LLM response string with markdown block support and fallback.
    """
    try:
        patterns = [
            r'```json\s*(.*?)\s*```',
            r'```\s*(.*?)\s*```',
            r'({.*})'
        ]
        for pattern in patterns:
            match = re.search(pattern, response, re.DOTALL)
            if match:
                return json.loads(match.group(1))
        return json.loads(response)
    except Exception:
        return fallback
