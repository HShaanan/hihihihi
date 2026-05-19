"""שירות FastAPI: webhook של ימות המשיח -> סוכן ה-ADK לאיתור עסקים.

השירות נפרס ל-Cloud Run. יש לכוון שלוחת API בימות המשיח לכתובת `/yemot`.
ימות שולחת את פרמטרי השיחה כ-query string ומצפה לקבל בחזרה שורת תגובה
בפורמט (DSL) של ימות.
"""

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

from .agent_runner import ask_agent
from .yemot import ask_for_intent, call_id, extract_intent, say_and_hangup

app = FastAPI(title="Yemot Business Finder Agent")


@app.get("/healthz")
def healthz() -> dict:
    # בדיקת בריאות עבור Cloud Run / ניטור.
    return {"status": "ok"}


@app.api_route("/yemot", methods=["GET", "POST"])
async def yemot(request: Request) -> PlainTextResponse:
    # ימות עובדת ב-GET (query string); מקבלים גם POST form לגמישות.
    params = dict(request.query_params)
    if request.method == "POST":
        try:
            form = await request.form()
            params.update({k: str(v) for k, v in form.items()})
        except Exception:
            pass

    intent = extract_intent(params)

    # הפנייה הראשונה בשיחה: אין עדיין כוונה מדוברת -> מבקשים אותה בקול.
    if not intent:
        return PlainTextResponse(ask_for_intent())

    # יש לנו את בקשת המתקשר: הסוכן מבין את הכוונה ומאתר עסקים מתאימים.
    answer = await ask_agent(call_id(params), intent)
    return PlainTextResponse(say_and_hangup(answer))
