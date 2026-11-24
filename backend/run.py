"""Agentica backend launcher.

Uses asyncio.run() with WindowsSelectorEventLoopPolicy so psycopg3 async
works on Windows (ProactorEventLoop is the default and is incompatible).
"""
import asyncio
import os
import sys

# Redirect HuggingFace/sentence-transformers cache to D:\Temp (C drive is full)
os.environ.setdefault("HF_HOME", r"D:\Temp\hf-cache")
os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", r"D:\Temp\hf-cache\sentence-transformers")
os.environ.setdefault("TRANSFORMERS_CACHE", r"D:\Temp\hf-cache\transformers")
os.environ.setdefault("HF_DATASETS_CACHE", r"D:\Temp\hf-cache\datasets")

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn


async def _serve(host: str, port: int, reload: bool) -> None:
    config = uvicorn.Config("agentica.main:app", host=host, port=port, reload=reload)
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--reload", action="store_true")
    args = p.parse_args()

    asyncio.run(_serve(args.host, args.port, args.reload))
