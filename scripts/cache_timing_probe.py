"""Minimal cache timing probe: same single-shot proposal request, twice, one process.

Call 1 = cold (LLM miss + embedding-model first load + PFS).
Call 2 = warm (LLM cache hit + embedding model already loaded + PFS).

Prints the wall-clock for each call so the LLM-cache benefit is visible.
"""
from __future__ import annotations

import os
import time

from dotenv import load_dotenv

load_dotenv(".env")

import httpx  # noqa: E402

CLIENT_ID = "PB-HK-000007-5"
PRODUCT_ID = "PROD054"
URL = "http://127.0.0.1:8000/api/v1/product-opportunity-proposal"

BODY = {
    "client_id": CLIENT_ID,
    "product_id": PRODUCT_ID,
    "rationale": "Income-focused client seeking stable Treasury exposure.",
    "run_matcher": False,
    "alternative_count": 2,
    "output_prompt_to_llm": False,
}


def call(label: str) -> float:
    t0 = time.perf_counter()
    r = httpx.post(URL, json=BODY, timeout=600.0)
    dt = time.perf_counter() - t0
    print(f"[{label}] HTTP {r.status_code}  elapsed={dt:.1f}s")
    if r.status_code != 200:
        print(r.text[:1000])
    return dt


if __name__ == "__main__":
    print(f"probe target: {URL}")
    print(f"client={CLIENT_ID} product={PRODUCT_ID}")
    print(f"provider key set: BACHERLIER_API_KEY={'yes' if os.getenv('BACHERLIER_API_KEY') else 'no'}, "
          f"DEEPSEEK_API_KEY={'yes' if os.getenv('DEEPSEEK_API_KEY') else 'no'}")
    t_cold = call("cold (1st)")
    t_warm = call("warm (2nd)")
    print(f"\nRESULT cold={t_cold:.1f}s warm={t_warm:.1f}s speedup={t_cold / t_warm:.1f}x")
