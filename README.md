# Yemot Business Finder Agent

סוכן ADK (Google Agent Development Kit) הפרוס על Cloud Run, שמקבל פנייה
ממערכת **ימות המשיח**, מבין את כוונת המשתמש, ומאתר עבורו עסקים מתאימים
מתוך רשימה מותאמת אישית.

## איך זה עובד

1. המשתמש מתקשר לשלוחת API בימות המשיח, שמכוונת ל-`/yemot` של השירות.
2. בפנייה הראשונה השירות מחזיר `read` עם זיהוי דיבור ומבקש מהמשתמש לומר
   מה הוא מחפש.
3. ימות מחזירה את הטקסט המזוהה (משתנה `intent`). הסוכן מבין את הכוונה,
   קורא לכלי `search_businesses` על הרשימה המותאמת, ומנסח תשובה קולית.
4. השירות מקריא את התשובה (`id_list_message`) ומסיים את השיחה.

## מבנה הפרויקט

```
app/
  main.py          # FastAPI: webhook /yemot + /healthz
  yemot.py         # פרוטוקול ימות המשיח (read / id_list_message)
  agent_runner.py  # הרצת סוכן ה-ADK לכל תור שיחה
business_agent/
  agent.py         # הגדרת הסוכן (Gemini + הוראות בעברית)
  businesses.py    # הכלי search_businesses
  data/businesses.json   # רשימת העסקים המותאמת אישית
Dockerfile
deploy/deploy_cloud_run.sh
```

## הרצה מקומית

```bash
pip install -r requirements.txt
cp .env.example .env   # ערכו את פרטי האימות (Vertex AI או GOOGLE_API_KEY)
set -a; source .env; set +a
uvicorn app.main:app --reload --port 8080
```

בדיקה (סבב ראשון – מבקש כוונה, סבב שני – עונה):

```bash
curl "http://localhost:8080/yemot"
curl "http://localhost:8080/yemot?intent=אני+צריך+מוסך+לרכב&ApiCallId=123"
```

## פריסה ל-Cloud Run

```bash
PROJECT_ID=your-gcp-project REGION=us-central1 ./deploy/deploy_cloud_run.sh
```

לאחר הפריסה, הגדירו את כתובת ה-`/yemot` שתודפס כשלוחת API בימות המשיח.

## התאמה אישית

- **רשימת העסקים**: ערכו את `business_agent/data/businesses.json`.
- **התנהגות הסוכן**: ערכו את ההוראות ב-`business_agent/agent.py`.
- **פורמט `read` של ימות**: `SPEECH_READ_TEMPLATE` ב-`app/yemot.py` —
  סדר הפרמטרים עשוי להשתנות בין גרסאות/הגדרות שלוחה בימות, התאימו לפי
  התיעוד של השלוחה שלכם.
