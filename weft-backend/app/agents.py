import os
import httpx
from dotenv import load_dotenv

load_dotenv()

HIDEVS_API_KEY = os.getenv("HIDEVS_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://llm.hidevs.xyz/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-3.6-flash")

async def call_hidevs_llm(system_prompt: str, user_prompt: str) -> str:
    """Call Gemini 3.6 Flash via the HiDevs API gateway."""
    headers = {
        "Authorization": f"Bearer {HIDEVS_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.4
    }
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(f"{LLM_BASE_URL}/chat/completions", headers=headers, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            else:
                return f"[Mock/Fallback] Agent completed thought. (LLM returned status {resp.status_code})"
    except Exception as e:
        return f"[Fallback Thought] Analyzing competitive landscape under sub-10ms constraints."