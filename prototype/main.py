import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from ollama import AsyncClient, ResponseError
from pydantic import BaseModel

from monitor import TOOLS, run_tool

MODEL = os.getenv("AGENTICA_MODEL", "qwen3.8:27b")
# Negative = never unload. Reloading a 27B model takes ~30s, so an idle timeout means a slow
# first reply after every quiet spell. Set e.g. "30m" to free VRAM when idle instead.
KEEP_ALIVE = os.getenv("AGENTICA_KEEP_ALIVE", "-1m")
MAX_TOOL_ROUNDS = 5
SYSTEM = {"role": "system", "content": (
    "You are Agentica, an IT operations AI agent running on this Windows host. You help with IT "
    "work such as troubleshooting, Windows administration, networking and scripting, and you have "
    "read-only tools that inspect this host live: CPU, memory, disks, GPU, processes, network, "
    "services and the Windows Event Log.\n"
    "Use the tools only when the user asks about a performance or health issue on this host: "
    "slowness, high CPU/RAM/GPU/disk usage, low disk space, what is using resources, errors, "
    "crashes, failing services or network problems. Answer everything else from your own "
    "knowledge without tools, including general IT questions (how to do something, what an error "
    "code or event ID means, explaining a concept), writing scripts, greetings and small talk.\n"
    "When you use tools, report the actual numbers concisely, point out anything that looks "
    "wrong (e.g. a nearly full disk or repeated errors) and suggest next steps.\n"
    "Replies are rendered as Markdown. Put file paths, commands and process names in inline code."
)}
HERE = Path(__file__).parent
log = logging.getLogger("uvicorn.error")
llm = AsyncClient()


async def preload():
    # An empty chat makes Ollama load the model without generating anything
    try:
        await llm.chat(MODEL, [], keep_alive=KEEP_ALIVE)
        log.info("model %s loaded", MODEL)
    except Exception as e:
        log.warning("could not preload %s: %s", MODEL, e)


@asynccontextmanager
async def lifespan(app):
    # Load in the background so the server is up immediately; a chat sent meanwhile just
    # waits for the load to finish rather than starting a second one.
    task = asyncio.create_task(preload())
    yield
    task.cancel()


app = FastAPI(title="Agentica", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")


class Chat(BaseModel):
    messages: list[dict[str, str]]


@app.get("/")
async def index():
    return FileResponse(HERE / "index.html")


async def agent(messages):
    for round_ in range(MAX_TOOL_ROUNDS + 1):
        content, calls = "", []
        # The final round offers no tools, forcing an answer instead of an endless tool loop.
        # think=False skips Qwen's reasoning pass
        tools = TOOLS if round_ < MAX_TOOL_ROUNDS else None
        async for part in await llm.chat(MODEL, messages, tools=tools, stream=True, think=False, keep_alive=KEEP_ALIVE):
            if part.message.content:
                content += part.message.content
                yield part.message.content
            calls.extend(part.message.tool_calls or [])
        if not calls:
            return
        if content:
            yield "\n\n"
        messages.append({"role": "assistant", "content": content, "tool_calls": calls})
        for call in calls:
            log.info("tool call: %s %s", call.function.name, dict(call.function.arguments or {}))
            # Tools block (sampling sleeps, subprocesses), so keep them off the event loop
            result = await asyncio.to_thread(run_tool, call.function.name, call.function.arguments)
            messages.append({"role": "tool", "content": result, "tool_name": call.function.name})


@app.post("/chat")
async def chat(req: Chat):
    async def stream():
        # Headers are sent before the first chunk, so an uncaught error just drops the connection
        # and the page shows a bare "network error". Put the real cause in the reply instead.
        try:
            async for text in agent([SYSTEM, *req.messages]):
                yield text
        except ResponseError as e:
            hint = f" Run `ollama pull {MODEL}` or set AGENTICA_MODEL to a model from `ollama list`." if e.status_code == 404 else ""
            yield f"\n\n[Ollama error: {e.error}.{hint}]"
        except Exception as e:
            log.exception("chat failed")
            yield f"\n\n[Error: {type(e).__name__}: {e}]"

    return StreamingResponse(stream(), media_type="text/plain")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
