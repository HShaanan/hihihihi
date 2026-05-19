"""עטיפה דקה שמריצה את סוכן ה-ADK עבור תור שיחה בודד בימות."""

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from business_agent import root_agent

APP_NAME = "yemot_business_finder"

_session_service = InMemorySessionService()
_runner = Runner(
    agent=root_agent,
    app_name=APP_NAME,
    session_service=_session_service,
)


async def ask_agent(call_id: str, user_text: str) -> str:
    """שולח את טקסט המתקשר לסוכן ומחזיר את התשובה הסופית להקראה.

    מזהה השיחה של ימות משמש גם כ-user id וגם כ-session id, כך
    שפניות חוזרות באותה שיחת טלפון ממשיכות את אותה שיחה עם הסוכן.
    """
    session = await _session_service.get_session(
        app_name=APP_NAME, user_id=call_id, session_id=call_id
    )
    if session is None:
        await _session_service.create_session(
            app_name=APP_NAME, user_id=call_id, session_id=call_id
        )

    message = types.Content(role="user", parts=[types.Part(text=user_text)])

    final_text = ""
    async for event in _runner.run_async(
        user_id=call_id, session_id=call_id, new_message=message
    ):
        if event.is_final_response() and event.content and event.content.parts:
            final_text = event.content.parts[0].text or final_text

    return final_text.strip() or "מצטערים, לא הצלחנו לעבד את הבקשה. נסו שוב מאוחר יותר."
