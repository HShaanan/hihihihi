"""פונקציות עזר לפרוטוקול ה-API של ימות המשיח.

ימות פונה לכתובת שלנו עם פרמטרי השיחה ב-query string. אנו מחזירים שורת
טקסט אחת בפורמט (DSL) של ימות. שני המרכיבים שבשימוש כאן:

* ``read``  - להשמיע הודעה ולאסוף קלט. אנו משתמשים בזיהוי דיבור כדי
  שהמתקשר פשוט יאמר איזה עסק הוא צריך. הטקסט המזוהה חוזר אלינו בפנייה
  הבאה תחת שם המשתנה שבחרנו.
* ``id_list_message`` - להשמיע הודעת טקסט סופית, ולאחריה מנתקים את השיחה.

הערה: סדר הפרמטרים של ``read`` בימות עשוי להשתנות מעט בין גרסאות מערכת /
הגדרות שלוחה. ``SPEECH_READ_TEMPLATE`` הוא בכוונה מקום יחיד לכוונון כדי
להתאים לתיעוד השלוחה שלכם.
"""

# {prompt} = טקסט להקראה (TTS), {var} = שם המשתנה שאליו יחזור הדיבור המזוהה.
SPEECH_READ_TEMPLATE = "read=t-{prompt}={var},,voice,,,,,,,,,he-IL"

# שם המשתנה שיישא בחזרה אלינו את הדיבור המזוהה.
INTENT_VAR = "intent"

_PROMPT = "שלום, איזה עסק או שירות אתם מחפשים? דברו אחרי הצליל."


def _sanitize(text: str) -> str:
    """מסיר תווים שעלולים לשבור את שורת התגובה של ימות."""
    if not text:
        return ""
    for ch in ("&", "=", ",", "\n", "\r", "\t"):
        text = text.replace(ch, " ")
    return text.strip()


def ask_for_intent() -> str:
    """תגובה ששואלת את המתקשר (בקול) מה הוא מחפש."""
    return SPEECH_READ_TEMPLATE.format(prompt=_sanitize(_PROMPT), var=INTENT_VAR)


def say_and_hangup(message: str) -> str:
    """תגובה שמקריאה את ``message`` למתקשר ומסיימת את השיחה."""
    return f"id_list_message=t-{_sanitize(message)}&hangup=yes"


def extract_intent(params: dict) -> str:
    """שולף מתוך פרמטרי ימות את הדיבור המזוהה / הכוונה שהוקלדה."""
    return (params.get(INTENT_VAR) or "").strip()


def call_id(params: dict) -> str:
    """מזהה יציב לכל שיחה, משמש כמפתח לשיחת הסוכן (session)."""
    return (params.get("ApiCallId") or params.get("ApiPhone") or "anon").strip()
