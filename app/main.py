"""FastAPI service: Yemot HaMashiach webhook -> ADK business-finder agent.

Deployed to Cloud Run. Point a Yemot API extension at the `/yemot` URL.
Yemot sends call params as the query string and expects a Yemot-DSL line back.
"""

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

from .agent_runner import ask_agent
from .yemot import ask_for_intent, call_id, extract_intent, say_and_hangup

app = FastAPI(title="Yemot Business Finder Agent")


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.api_route("/yemot", methods=["GET", "POST"])
async def yemot(request: Request) -> PlainTextResponse:
    # Yemot uses GET (query string); accept POST form too for flexibility.
    params = dict(request.query_params)
    if request.method == "POST":
        try:
            form = await request.form()
            params.update({k: str(v) for k, v in form.items()})
        except Exception:
            pass

    intent = extract_intent(params)

    # First hit of the call: no spoken intent yet -> ask for it by voice.
    if not intent:
        return PlainTextResponse(ask_for_intent())

    # We have the caller's request: let the agent understand & match businesses.
    answer = await ask_agent(call_id(params), intent)
    return PlainTextResponse(say_and_hangup(answer))
