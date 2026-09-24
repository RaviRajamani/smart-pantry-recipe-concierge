"""FastAPI proxy for deployed A2A agent on Vertex AI Agent Runtime."""

import os
import uuid
import google.auth
import google.auth.transport.requests
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from google.protobuf.json_format import MessageToDict
from a2a.client import create_client, ClientConfig
from a2a.types import SendMessageRequest, Message, Part

RESOURCE = os.environ["AGENT_ENGINE_RESOURCE_NAME"]
AGENT_DIRECTORY = os.environ.get("AGENT_DIRECTORY", "app")
LOCATION = RESOURCE.split("/locations/")[1].split("/")[0]

A2A_BASE = (
    f"https://{LOCATION}-aiplatform.googleapis.com/reasoningEngines/v1/"
    f"{RESOURCE}/api/a2a/{AGENT_DIRECTORY}"
)

_A2UI_MIME = "application/json+a2ui"

_creds, _ = google.auth.default(
    scopes=["https://www.googleapis.com/auth/cloud-platform"]
)


def _auth_headers() -> dict[str, str]:
    _creds.refresh(google.auth.transport.requests.Request())
    return {
        "Authorization": f"Bearer {_creds.token}",
        "Content-Type": "application/json",
    }


app = FastAPI()


@app.exception_handler(Exception)
async def _json_errors(request: Request, exc: Exception):
    return JSONResponse(
        status_code=200,
        content={
            "parts": [{"kind": "text", "text": f"Error: {type(exc).__name__}: {exc}"}]
        },
    )


_contexts: dict[str, str] = {}


def _extract_parts(artifact) -> list[dict]:
    out = []
    for p in getattr(artifact, "parts", []):
        if getattr(p, "text", None):
            out.append({"kind": "text", "text": p.text})
        elif p.HasField("data"):
            dict_data = MessageToDict(p.data)
            dict_meta = MessageToDict(p.metadata) if p.HasField("metadata") else {}
            mime = dict_meta.get("mimeType") or dict_meta.get("mime_type")
            if mime == _A2UI_MIME or "a2ui" in str(mime) or "surfaceUpdate" in str(dict_data) or "beginRendering" in str(dict_data):
                out.append({"kind": "a2ui", "data": dict_data})
            else:
                out.append({"kind": "a2ui", "data": dict_data})
        elif getattr(p, "file", None) and getattr(p.file, "uri", None):
            out.append({"kind": "text", "text": p.file.uri})
    return out


@app.post("/chat")
async def chat(req: Request):
    body = await req.json()
    message_text = body.get("message", "")
    user_id = body.get("user_id") or "web-user"
    parts: list[dict] = []

    async with httpx.AsyncClient(headers=_auth_headers(), timeout=120) as client:
        a2a_client = await create_client(agent=A2A_BASE, client_config=ClientConfig(httpx_client=client))
        
        msg = Message(
            message_id=str(uuid.uuid4()),
            role="ROLE_USER",
            parts=[Part(text=message_text)],
            context_id=_contexts.get(user_id),
        )
        req_obj = SendMessageRequest(message=msg)

        async for resp in a2a_client.send_message(req_obj):
            if resp.HasField("artifact_update"):
                parts.extend(_extract_parts(resp.artifact_update.artifact))
            elif resp.HasField("status_update"):
                if resp.status_update.context_id:
                    _contexts[user_id] = resp.status_update.context_id
            elif resp.HasField("task"):
                if resp.task.context_id:
                    _contexts[user_id] = resp.task.context_id
                for artifact in resp.task.artifacts:
                    parts.extend(_extract_parts(artifact))
            elif resp.HasField("message"):
                if resp.message.context_id:
                    _contexts[user_id] = resp.message.context_id
                for p in resp.message.parts:
                    if p.text:
                        parts.append({"kind": "text", "text": p.text})

    if not parts:
        parts = [{"kind": "text", "text": "(The agent didn't return a reply.)"}]
    return JSONResponse({"parts": parts})


app.mount("/", StaticFiles(directory="static", html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
