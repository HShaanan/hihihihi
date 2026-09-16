#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
process_sefaria.py
==================
מעבד את הטקסטים העבריים של ספריא (Sefaria-Export) לקבצי TXT נקיים ומרוכזים,
במבנה שמתאים להעלאה ל-NotebookLM (מגבלת 50 מקורות למחברת) ולגיבוי בגוגל דרייב.

רקע:
  מאגר ה-GitHub של Sefaria-Export מכיל כיום רק אינדקס (books.json) וכלים.
  הטקסטים עצמם יושבים בדלי GCS ציבורי (https://storage.googleapis.com/sefaria-export/).
  הסקריפט קורא את books.json מהשיבוט המקומי של המאגר, מוריד את כל קבצי
  ה-JSON העבריים הממוזגים (merged.json) + קבצי הסכמה, מנקה אותם ומאגד אותם לכרכים.

שימוש:
  python3 process_sefaria.py --repo ./Sefaria-Export --out ./sefaria_notebooklm_export
  אפשרויות: --cache DIR (מטמון הורדות), --workers N, --max-mb N (גודל כרך מרבי),
            --limit N (לבדיקה: מעבד רק N ספרים), --only 01,03 (רק תיקיות מסוימות)
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import html
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict, defaultdict
from pathlib import Path

BASE_URL = "https://storage.googleapis.com/sefaria-export"
TOC_URL = f"{BASE_URL}/table_of_contents.json"
BOOKS_JSON_RAW = "https://raw.githubusercontent.com/Sefaria/Sefaria-Export/master/books.json"

# ---------------------------------------------------------------------------
# תרגומים: שמות קטגוריות ושמות סעיפים (fallback כשאין סכמה)
# ---------------------------------------------------------------------------
SECTION_HE = {
    "Chapter": "פרק", "Verse": "פסוק", "Mishnah": "משנה", "Halakhah": "הלכה",
    "Daf": "דף", "Line": "שורה", "Siman": "סימן", "Seif": "סעיף", "Paragraph": "פסקה",
    "Comment": "פירוש", "Section": "קטע", "Segment": "קטע", "Teshuva": "תשובה",
    "Responsum": "תשובה", "Part": "חלק", "Volume": "כרך", "Parasha": "פרשה",
    "Parsha": "פרשה", "Piska": "פסקה", "Sefer": "ספר", "Gate": "שער", "Letter": "אות",
    "Page": "עמוד", "Book": "ספר", "Midrash": "מדרש", "Story": "סיפור", "Torah": "תורה",
    "Perek": "פרק", "Pasuk": "פסוק", "Mitzvah": "מצוה", "Klal": "כלל", "Seif Katan": "סעיף קטן",
    "Sha'ar": "שער", "Shaar": "שער", "Sermon": "דרשה", "Drasha": "דרשה", "Derasha": "דרשה",
    "Homily": "דרשה", "Essay": "מאמר", "Article": "מאמר", "Entry": "ערך", "Question": "שאלה",
    "Answer": "תשובה", "Introduction": "הקדמה", "Note": "הערה", "Footnote": "הערה",
    "Statement": "מאמר", "Dibur Hamatchil": "דיבור המתחיל", "Remez": "רמז", "Sign": "סימן",
    "Aliyah": "עליה", "Day": "יום", "Week": "שבוע", "Year": "שנה", "Month": "חודש",
    "Psalm": "מזמור", "Song": "שיר", "Prayer": "תפילה", "Blessing": "ברכה", "Rule": "כלל",
    "Topic": "נושא", "Subject": "נושא", "Item": "פריט", "Row": "שורה", "Column": "טור",
    "Root": "שורש", "Positive Commandment": "מצות עשה", "Negative Commandment": "מצות לא תעשה",
    "Commandment": "מצוה", "Lesson": "שיעור", "Talk": "שיחה", "Sicha": "שיחה", "Passage": "קטע",
    "Ot": "אות", "Sentence": "משפט", "Poem": "שיר", "Stanza": "בית", "Verset": "פסוקית",
}

CATEGORY_HE = {
    "Tanakh": 'תנ"ך', "Torah": "תורה", "Prophets": "נביאים", "Writings": "כתובים",
    "Targum": "תרגום", "Rishonim on Tanakh": 'ראשונים על התנ"ך',
    "Acharonim on Tanakh": 'אחרונים על התנ"ך', "Modern Commentary on Tanakh": 'פרשנות מודרנית על התנ"ך',
    "Mishnah": "משנה", "Seder Zeraim": "סדר זרעים", "Seder Moed": "סדר מועד", "Seder Nashim": "סדר נשים",
    "Seder Nezikin": "סדר נזיקין", "Seder Kodashim": "סדר קדשים", "Seder Tahorot": "סדר טהרות",
    "Rishonim on Mishnah": "ראשונים על המשנה", "Acharonim on Mishnah": "אחרונים על המשנה",
    "Modern Commentary on Mishnah": "פרשנות מודרנית על המשנה",
    "Talmud": "תלמוד", "Bavli": "בבלי", "Yerushalmi": "ירושלמי", "Minor Tractates": "מסכתות קטנות",
    "Commentary on Minor Tractates": "מפרשים על מסכתות קטנות", "Rishonim on Talmud": "ראשונים על התלמוד",
    "Acharonim on Talmud": "אחרונים על התלמוד", "Modern Commentary on Talmud": "פרשנות מודרנית על התלמוד",
    "Guides": "מבואות", "Commentary": "מפרשים", "Midrash": "מדרש", "Aggadah": "אגדה",
    "Halakhah": "הלכה", "Modern Texts": "טקסטים מודרניים", "Midrash Rabbah": "מדרש רבה",
    "Mishneh Torah": "משנה תורה", "Tur": "טור", "Shulchan Arukh": "שולחן ערוך",
    "Shulchan Arukh HaRav": "שולחן ערוך הרב", "Sifrei Mitzvot": "ספרי מצוות", "Rishonim": "ראשונים",
    "Acharonim": "אחרונים", "Modern": "מודרני", "Responsa": 'שו"ת', "Geonim": "גאונים",
    "Kabbalah": "קבלה", "Zohar": "זוהר", "Chasidut": "חסידות", "Jewish Thought": "מחשבת ישראל",
    "Musar": "מוסר", "Liturgy": "סדר התפילה", "Tosefta": "תוספתא", "Second Temple": "בית שני",
    "Reference": "ספרי יעץ", "Lieberman Edition": "מהדורת ליברמן", "Vilna Edition": "מהדורת וילנא",
    "Introduction": "הקדמה", "Sefer Madda": "ספר מדע", "Sefer Ahavah": "ספר אהבה",
    "Sefer Zemanim": "ספר זמנים", "Sefer Nashim": "ספר נשים", "Sefer Kedushah": "ספר קדושה",
    "Sefer Haflaah": "ספר הפלאה", "Sefer Zeraim": "ספר זרעים", "Sefer Avodah": "ספר עבודה",
    "Sefer Korbanot": "ספר קרבנות", "Sefer Taharah": "ספר טהרה", "Sefer Nezikim": "ספר נזיקין",
    "Sefer Kinyan": "ספר קניין", "Sefer Mishpatim": "ספר משפטים", "Sefer Shoftim": "ספר שופטים",
}

HEB_LETTERS = [
    (400, "ת"), (300, "ש"), (200, "ר"), (100, "ק"), (90, "צ"), (80, "פ"), (70, "ע"), (60, "ס"),
    (50, "נ"), (40, "מ"), (30, "ל"), (20, "כ"), (10, "י"), (9, "ט"), (8, "ח"), (7, "ז"), (6, "ו"),
    (5, "ה"), (4, "ד"), (3, "ג"), (2, "ב"), (1, "א"),
]


def gematria(n: int) -> str:
    """מספר → אותיות עבריות (א, ב, ... טו, טז, ... תתקצט). מעבר ל-999 מוסיפים ספרה רגילה."""
    if n <= 0:
        return str(n)
    if n >= 1000:
        return f"{gematria(n // 1000)}'{gematria(n % 1000) if n % 1000 else ''}".rstrip("'")
    out = ""
    rem = n
    for val, let in HEB_LETTERS:
        while rem >= val:
            # החרגות: 15 = טו, 16 = טז
            if rem == 15:
                out += "טו"
                rem = 0
                break
            if rem == 16:
                out += "טז"
                rem = 0
                break
            out += let
            rem -= val
    return out


def address_label(addr_type: str, idx: int) -> str:
    """מייצר תווית עברית לאינדקס (מבוסס 0) לפי סוג הכתובת של ספריא."""
    n = idx + 1
    if addr_type == "Talmud":
        daf = idx // 2 + 1  # בספריא: אינדקס 0 = דף א. (דף ב. = אינדקס 2)
        amud = "." if idx % 2 == 0 else ":"
        return f"{gematria(daf)}{amud}"
    if addr_type == "Folio":
        folio = idx // 4 + 1
        side = "אבגד"[idx % 4]
        return f"{gematria(folio)} ({side})"
    if addr_type in ("Year",):
        return str(n)
    return gematria(n)


# ---------------------------------------------------------------------------
# ניקוי HTML
# ---------------------------------------------------------------------------
_RE_BR = re.compile(r"<br\s*/?>", re.I)
_RE_FOOTNOTE = re.compile(
    r"<sup[^<>]*class=[\"']?footnote-marker[\"']?[^<>]*>.*?</sup>\s*<i[^<>]*class=[\"']?footnote[\"']?[^<>]*>(.*?)</i>",
    re.I | re.S,
)
_RE_FOOTNOTE_ONLY = re.compile(r"<i[^<>]*class=[\"']?footnote[\"']?[^<>]*>(.*?)</i>", re.I | re.S)
_RE_TAG = re.compile(r"<[^<>]*>")
_RE_TAG_LOOSE = re.compile("</?[a-zA-Z][^>\\u0590-\\u05ff]*>")  # תגית פגומה (מכילה < פנימי) – רק אם אין בה אותיות עבריות
_RE_TAG_FRAGMENT = re.compile(r"(?<![A-Za-z])/?(?:b|i|u|small|big|br|span|sup|sub|strong|em|a)>|</?(?:b|i|u|small|big|br|span|sup|sub|strong|em|a)(?![A-Za-z>])")
_RE_WS = re.compile("[ \\t\\u00a0\\u2000-\\u200a\\u202f]+")
_RE_MULTI_NL = re.compile(r"\n{3,}")
_RE_SPACE_BEFORE_PUNCT = re.compile(r" +([,.:;!?׃])")


def clean_text(s: str) -> str:
    """מסיר תגיות HTML ומחזיר טקסט עברי נקי."""
    if not s:
        return ""
    s = _RE_BR.sub("\n", s)
    s = _RE_FOOTNOTE.sub(lambda m: f" (הערה: {m.group(1)})", s)
    s = _RE_FOOTNOTE_ONLY.sub(lambda m: f" (הערה: {m.group(1)})", s)
    s = _RE_TAG.sub("", s)
    s = _RE_TAG_LOOSE.sub("", s)      # תגיות פגומות במקור, כגון <br<b> או </b<>>
    s = _RE_TAG_FRAGMENT.sub("", s)   # שאריות כגון "b>" אחרי תגית פגומה
    s = html.unescape(s)
    # תגיות שהיו מקודדות כישויות (&lt;b&gt;) הופכות לטקסט רק אחרי הפענוח – מנקים שוב
    if "<" in s:
        s = _RE_TAG.sub("", s)
        s = _RE_TAG_LOOSE.sub("", s)
        s = _RE_TAG_FRAGMENT.sub("", s)
    s = s.replace("\r", "")
    lines = [_RE_WS.sub(" ", ln).strip() for ln in s.split("\n")]
    s = "\n".join(ln for ln in lines if ln)
    s = _RE_SPACE_BEFORE_PUNCT.sub(r"\1", s)
    return s.strip()


# ---------------------------------------------------------------------------
# הורדה עם מטמון
# ---------------------------------------------------------------------------
def fetch(url: str, dest: Path, retries: int = 5) -> bool:
    if dest.exists() and dest.stat().st_size > 0:
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "sefaria-notebooklm-export/1.0"})
            with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
                shutil.copyfileobj(r, f, 1 << 20)
            os.replace(tmp, dest)
            return True
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return False
            time.sleep(2 ** attempt)
        except Exception:
            time.sleep(2 ** attempt)
    return False


def schema_url(title: str) -> str:
    return f"{BASE_URL}/schemas/{urllib.parse.quote(title.replace(' ', '_'))}.json"


# ---------------------------------------------------------------------------
# רינדור ספר → Markdown
# ---------------------------------------------------------------------------
class Renderer:
    def __init__(self, book: dict, data: dict, schema: dict | None):
        self.book = book
        self.data = data
        self.schema = (schema or {}).get("schema") if schema else None
        self.he_title = data.get("heTitle") or (schema or {}).get("heTitle") or book["title"]
        self.out: list[str] = []
        self.segments = 0

    # ---- עזרים
    def _he_sections(self, node: dict | None, en_names: list[str] | None) -> list[str]:
        """שמות הרמות בעברית: מהסכמה (heSectionNames), ורמות ריקות מושלמות מהשם האנגלי או ברירת מחדל."""
        en_names = list(en_names or (node or {}).get("sectionNames") or [])
        he_names = list((node or {}).get("heSectionNames") or [])
        n = max(len(en_names), len(he_names))
        out = []
        for i in range(n):
            he = he_names[i] if i < len(he_names) else ""
            en = en_names[i] if i < len(en_names) else ""
            out.append(he or SECTION_HE.get(en, en) or "קטע")
        return out

    def _addr_types(self, node: dict | None, en_names: list[str] | None) -> list[str]:
        if node and node.get("addressTypes"):
            return list(node["addressTypes"])
        en_names = en_names or (node or {}).get("sectionNames") or []
        return ["Talmud" if n == "Daf" else "Integer" for n in en_names]

    def _heading(self, level: int, text: str):
        level = max(1, min(level, 6))
        self.out.append("\n" + "#" * level + " " + text + "\n")

    # ---- JaggedArray
    def render_ja(self, arr, he_names: list[str], addr: list[str], level: int, depth_idx: int = 0):
        """מרנדר מערך מדורג. he_names/addr – שמות הרמות מהרמה הנוכחית ומטה."""
        if isinstance(arr, str):
            txt = clean_text(arr)
            if txt:
                self.out.append(txt + "\n")
                self.segments += 1
            return
        if not isinstance(arr, list):
            return
        name = he_names[0] if he_names else "קטע"
        atype = addr[0] if addr else "Integer"
        is_leaf_level = len(he_names) <= 1
        for i, item in enumerate(arr):
            if item is None or item == "" or item == []:
                continue
            label = f"{name} {address_label(atype, i)}"
            if isinstance(item, str) or is_leaf_level:
                if isinstance(item, list):
                    # עומק לא צפוי – שטח את הרשימה
                    flat = self._flatten(item)
                    txt = "\n".join(t for t in (clean_text(x) for x in flat) if t)
                else:
                    txt = clean_text(item)
                if not txt:
                    continue
                self.segments += 1
                if "\n" in txt:
                    self.out.append(f"{label}:\n{txt}\n")
                else:
                    self.out.append(f"{label}: {txt}\n")
            else:
                if not self._has_content(item):
                    continue
                self._heading(level, label)
                self.render_ja(item, he_names[1:], addr[1:], level + 1, depth_idx + 1)

    def _flatten(self, x):
        if isinstance(x, str):
            return [x]
        if isinstance(x, list):
            r = []
            for i in x:
                r.extend(self._flatten(i))
            return r
        return []

    def _has_content(self, x) -> bool:
        if isinstance(x, str):
            return bool(x.strip())
        if isinstance(x, list):
            return any(self._has_content(i) for i in x)
        if isinstance(x, dict):
            return any(self._has_content(v) for v in x.values())
        return False

    # ---- צמתי סכמה (טקסטים מורכבים)
    def _find_node(self, parent: dict | None, key: str) -> dict | None:
        if not parent:
            return None
        for n in parent.get("nodes", []) or []:
            if key in (n.get("key"), n.get("title"), n.get("sharedTitle")):
                return n
            if key == "" and (n.get("default") or n.get("key") == "default"):
                return n
        return None

    def _embedded_node(self, parent: dict | None, key: str) -> dict | None:
        """הסכמה המוטמעת ב-merged.json (רק heTitle/enTitle)"""
        if not parent:
            return None
        for n in parent.get("nodes", []) or []:
            if key in (n.get("enTitle"), n.get("key")):
                return n
        return None

    def render_node(self, content, schema_node: dict | None, embedded: dict | None, level: int, key: str = ""):
        if isinstance(content, dict):
            for k, v in content.items():
                if not self._has_content(v):
                    continue
                sn = self._find_node(schema_node, k)
                en = self._embedded_node(embedded, k)
                he = (sn or {}).get("heTitle") or (en or {}).get("heTitle") or ""
                is_default = (k == "" or k == "default" or (sn or {}).get("default"))
                if he and not is_default:
                    self._heading(level, he)
                    self.render_node(v, sn, en, level + 1, k)
                else:
                    self.render_node(v, sn, en, level, k)
        elif isinstance(content, list):
            he_names = self._he_sections(schema_node, None)
            addr = self._addr_types(schema_node, None)
            if not he_names:
                depth = self._depth(content)
                he_names = ["קטע"] * depth if depth > 0 else []
                if depth >= 2:
                    he_names = ["פרק"] + ["פסקה"] * (depth - 1)
                addr = ["Integer"] * len(he_names)
            self.render_ja(content, he_names, addr, level)
        elif isinstance(content, str):
            txt = clean_text(content)
            if txt:
                self.out.append(txt + "\n")
                self.segments += 1

    def _depth(self, x) -> int:
        d = 0
        while isinstance(x, list):
            d += 1
            nxt = next((i for i in x if isinstance(i, (list, str)) and i), None)
            if nxt is None:
                break
            x = nxt
        return d

    # ---- כניסה
    def render(self) -> str:
        cats = self.book.get("categories", [])
        he_cats = " / ".join(CATEGORY_HE.get(c, c) for c in cats)
        self.out.append(f"\n\n# {self.he_title}\n")
        self.out.append(f"(ספריא: {self.book['title']} | קטגוריה: {he_cats})\n")
        text = self.data.get("text")
        if isinstance(text, dict):
            self.render_node(text, self.schema, self.data.get("schema"), level=2)
        else:
            en_names = self.data.get("sectionNames") or []
            node = self.schema if self.schema and self.schema.get("nodeType") == "JaggedArrayNode" else None
            he_names = self._he_sections(node, en_names)
            addr = self._addr_types(node, en_names)
            if not he_names:
                depth = self._depth(text)
                he_names = (["פרק"] + ["פסקה"] * (depth - 1)) if depth >= 2 else ["פסקה"] * depth
                addr = ["Integer"] * len(he_names)
            self.render_ja(text, he_names, addr, level=2)
        body = "".join(self.out)
        body = _RE_MULTI_NL.sub("\n\n", body)
        return body


# ---------------------------------------------------------------------------
# ארגון לתיקיות וכרכים
# ---------------------------------------------------------------------------
FOLDERS = OrderedDict([
    ("01", "01_תנך"),
    ("02", "02_משנה"),
    ("03", "03_תלמוד_בבלי"),
    ("04", "04_תלמוד_ירושלמי"),
    ("05", "05_מדרש"),
    ("06", "06_רמבם"),
    ("07", "07_הלכה_ושולחן_ערוך"),
    ("08", "08_מחשבה_ומוסר"),
    ("09", "09_קבלה_וחסידות"),
    ("10", "10_שות"),
    ("11", "11_תפילה_ושונות"),
])


def _cat(book: dict, i: int) -> str:
    c = book.get("categories", [])
    return c[i] if len(c) > i else ""


def assign(book: dict) -> tuple[str, str] | None:
    """מחזיר (קוד תיקייה, שם כרך) לספר, או None אם לא נכלל."""
    c0, c1, c2, c3 = (_cat(book, i) for i in range(4))
    t = book["title"]
    tl = t.lower()

    # ---- 06 רמב"ם (כל כתבי הרמב"ם ומפרשיהם)
    if c0 == "Halakhah" and c1 == "Mishneh Torah":
        if c2 == "Commentary":
            return "06", "מפרשי_משנה_תורה"
        return "06", "משנה_תורה"
    if c0 == "Halakhah" and c1 == "Sifrei Mitzvot" and (c2 == "Sefer HaMitzvot" or t.startswith("Sefer HaMitzvot")):
        return "06", "ספר_המצוות_ומפרשיו"
    if c0 == "Jewish Thought" and c1 == "Guide for the Perplexed" or t.startswith("Guide for the Perplexed"):
        return "06", "מורה_נבוכים_ומפרשיו"
    if c0 == "Responsa" and c2 == "Rambam" or tl.startswith("teshuvot harambam") or tl.startswith("responsa of rambam"):
        return "06", "שות_ואגרות_הרמבם"
    if "letters of" in tl and "rambam" in tl or tl.startswith("iggerot harambam") or t in ("Letter of Rambam to Yemen", "Treatise on Logic", "Commentary on Sefer HaMitzvot of Rambam"):
        return "06", "שות_ואגרות_הרמבם"

    # ---- 01 תנ"ך
    if c0 == "Tanakh":
        if c1 == "Torah":
            return "01", "תורה"
        if c1 == "Prophets":
            return "01", "נביאים"
        if c1 == "Writings":
            return "01", "כתובים"
        if c1 == "Targum":
            return "01", "תרגומים"
        if c1 == "Rishonim on Tanakh":
            if c2 == "Rashi":
                return "01", "רשי"
            if c2 in ("Ibn Ezra", "Radak", "Ralbag", "Ralbag Beur HaMilot"):
                return "01", "אבן_עזרא_רדק_ורלבג"
            if c2 in ("Abarbanel",):
                return "01", "אברבנאל"
            return "01", "ראשונים_על_התנך"
        if c1 == "Acharonim on Tanakh":
            if c2 in ("Malbim", "Metzudat David", "Metzudat Zion"):
                return "01", "מלבים_ומצודות"
            if c2 in ("Chida", "Alshich"):
                return "01", "חידא_ואלשיך"
            return "01", "אחרונים_על_התנך"
        if c1 == "Modern Commentary on Tanakh":
            return "01", "פרשנות_מודרנית"
        return "01", "שונות"

    # ---- 02 משנה + תוספתא
    if c0 == "Mishnah":
        if c1.startswith("Seder "):
            return "02", CATEGORY_HE[c1].replace(" ", "_")
        if c1 == "Rishonim on Mishnah":
            return "02", "ראשונים_על_המשנה"
        if c1 == "Acharonim on Mishnah":
            return "02", "אחרונים_על_המשנה"
        if c1 == "Modern Commentary on Mishnah":
            return "02", "פרשנות_מודרנית_על_המשנה"
        return "02", "שונות"
    if c0 == "Tosefta":
        if c2 == "Commentary":
            return "02", "מפרשי_התוספתא"
        return "02", "תוספתא"

    # ---- 03 תלמוד בבלי
    if c0 == "Talmud" and c1 == "Bavli":
        if c2.startswith("Seder "):
            return "03", CATEGORY_HE[c2].replace(" ", "_")
        if c2 in ("Minor Tractates", "Commentary on Minor Tractates", "Guides"):
            return "03", "מסכתות_קטנות_ומבואות"
        if c2 == "Rishonim on Talmud":
            if c3 in ("Rashi", "Tosafot"):
                return "03", "רשי_ותוספות"
            return "03", "ראשונים_על_התלמוד"
        if c2 == "Acharonim on Talmud":
            return "03", "אחרונים_על_התלמוד"
        if c2 == "Modern Commentary on Talmud":
            return "03", "פרשנות_מודרנית_על_התלמוד"
        return "03", "שונות"

    # ---- 04 תלמוד ירושלמי
    if c0 == "Talmud" and c1 == "Yerushalmi":
        if c2.startswith("Seder "):
            return "04", CATEGORY_HE[c2].replace(" ", "_")
        if c2 == "Commentary":
            if c3 in ("Penei Moshe", "Mareh HaPanim"):
                return "04", "פני_משה_ומראה_הפנים"
            if c3 in ("Korban HaEdah", "Sheyarei Korban"):
                return "04", "קרבן_העדה_ושיירי_קרבן"
            return "04", "מפרשי_הירושלמי"
        if c2 == "Modern Commentary on Talmud":
            return "04", "פרשנות_מודרנית_על_הירושלמי"
        return "04", "שונות"

    # ---- 05 מדרש
    if c0 == "Midrash":
        if c1 == "Halakhah":
            return "05", "מדרשי_הלכה"
        if c2 == "Midrash Rabbah":
            return "05", "מדרש_רבה"
        if tl.startswith("yalkut shimoni"):
            return "05", "ילקוט_שמעוני"
        if c2 == "Commentary":
            return "05", "מפרשי_המדרש"
        return "05", "מדרשי_אגדה"

    # ---- 10 שו"ת
    if c0 == "Responsa":
        if c1 in ("Geonim", "Rishonim"):
            return "10", "גאונים_וראשונים"
        if c1 == "Acharonim":
            return "10", "אחרונים"
        return "10", "מודרני"

    # ---- 07 הלכה ושולחן ערוך
    if c0 == "Halakhah":
        if c1 == "Tur":
            if t in ("Tur", "Beit Yosef"):
                return "07", "טור_ובית_יוסף"
            return "07", "מפרשי_הטור"
        if c1 in ("Shulchan Arukh", "Shulchan Arukh HaRav"):
            if c2 != "Commentary":
                return "07", "שולחן_ערוך_ושולחן_ערוך_הרב"
            key = f"{c3} {t}"
            if "Orach Chayim" in key or c3 in ("Mishnah Berurah", "Magen Avraham", "Machatzit HaShekel"):
                return "07", "נושאי_כלים_אורח_חיים"
            if "Yoreh De'ah" in key or "Yoreh Deah" in key:
                return "07", "נושאי_כלים_יורה_דעה"
            if "Even HaEzer" in key or c3 in ("Beit Shmuel", "Chelkat Mechokek"):
                return "07", "נושאי_כלים_אבן_העזר"
            if "Choshen Mishpat" in key or c3 in ("Urim VeTumim",):
                return "07", "נושאי_כלים_חושן_משפט"
            return "07", "נושאי_כלים_אורח_חיים"  # ספרים רב-חלקיים (למשל קול יעקב: או"ח + יו"ד)
        if t in ("Arukh HaShulchan", "Arukh HaShulchan HeAtid") or c1 in ("Arukh HaShulchan", "Arukh HaShulchan HeAtid"):
            return "07", "ערוך_השולחן"
        if t in ("Kitzur Shulchan Arukh", "Chayyei Adam", "Chokhmat Adam", "Ben Ish Hai") or c1 in ("Kitzur Shulchan Arukh", "Chayyei Adam", "Chokhmat Adam", "Ben Ish Hai"):
            return "07", "קיצור_שולחן_ערוך_חיי_אדם_ובן_איש_חי"
        if c1 == "Rishonim" or t in ("Halakhot Gedolot", "Piskei Recanati") or c1 in ("Halakhot Gedolot", "Piskei Recanati"):
            return "07", "הלכה_ראשונים"
        if c1 == "Sifrei Mitzvot" or "Sefer HaMitzvot" in t or "Sefer Hamitzvot" in t or "Sefer Mitzvot" in t:
            return "07", "ספרי_מצוות"
        if c1 in ("Acharonim", "Commentary"):
            return "07", "הלכה_אחרונים"
        if c1 == "Modern":
            return "07", "הלכה_מודרנית"
        return "07", "הלכה_אחרונים"

    # ---- 08 מחשבה ומוסר
    if c0 == "Jewish Thought":
        if c1 == "Rishonim":
            return "08", "מחשבה_ראשונים"
        if c1 == "Acharonim":
            if c2 == "Maharal":
                return "08", "מהרל"
            return "08", "מחשבה_אחרונים"
        if c1 == "Modern":
            if c2 == "Rav Kook":
                return "08", "הרב_קוק"
            return "08", "מחשבה_מודרנית"
        return "08", "מחשבה_שונות"
    if c0 == "Musar":
        if c1 == "Rishonim":
            return "08", "מוסר_ראשונים"
        if c1 == "Acharonim":
            return "08", "מוסר_אחרונים"
        return "08", "מוסר_מודרני"

    # ---- 09 קבלה וחסידות
    if c0 == "Kabbalah":
        if c1 == "Zohar":
            if t == "Zohar":
                return "09", "זוהר"
            return "09", "מפרשי_הזוהר_וזוהר_חדש"
        if c1 == "Arizal and Chaim Vital":
            return "09", "כתבי_האריזל"
        if c1 in ("Ramak", "Ramchal", "Baal HaSulam"):
            return "09", "רמק_רמחל_ובעל_הסולם"
        return "09", "קבלה_ספרים_שונים"
    if c0 == "Chasidut":
        if c1 == "Early Works":
            return "09", "ראשית_החסידות"
        if c1 == "Breslov":
            return "09", "ברסלב"
        if c1 == "Chabad":
            return "09", "חבד"
        if c1 in ("Izhbitz", "R' Tzadok HaKohen", "Piaseczno Rebbe"):
            return "09", "איזביצא_רצדוק_ופיאסצנה"
        return "09", "חסידות_ספרים_שונים"

    # ---- 11 תפילה ושונות
    if c0 == "Liturgy":
        if c1 == "Haggadah":
            return "11", "הגדה_של_פסח_ומפרשיה"
        if c1 == "High Holidays":
            return "11", "ימים_נוראים"
        return "11", "סידור_ופיוטים"
    if c0 == "Second Temple":
        return "11", "ספרות_בית_שני"
    if c0 == "Reference":
        return "11", "מילונים_וספרי_יעץ"
    return "11", "שונות"


# ---------------------------------------------------------------------------
# TOC: סדר הספרים
# ---------------------------------------------------------------------------
def toc_ranks(toc: list) -> dict[str, int]:
    """מחזיר דירוג (סדר) לכל ספר לפי תוכן העניינים של ספריא, וממלא את CATEGORY_HE משמות הקטגוריות בעברית."""
    ranks: dict[str, int] = {}
    counter = [0]

    def walk(node):
        if isinstance(node, dict):
            if "contents" in node:
                if node.get("category") and node.get("heCategory"):
                    CATEGORY_HE.setdefault(node["category"], node["heCategory"])
                for c in node["contents"]:
                    walk(c)
            elif node.get("title"):
                if node["title"] not in ranks:
                    ranks[node["title"]] = counter[0]
                    counter[0] += 1
        elif isinstance(node, list):
            for c in node:
                walk(c)

    walk(toc)
    return ranks


# ---------------------------------------------------------------------------
# כתיבת כרכים
# ---------------------------------------------------------------------------
class VolumeWriter:
    """כותב ספרים לכרך אחד, ומפצל לחלקים כשגודל הקובץ עובר את המגבלה."""

    def __init__(self, out_dir: Path, folder: str, volume: str, max_bytes: int):
        self.out_dir = out_dir
        self.folder = folder
        self.volume = volume
        self.max_bytes = max_bytes
        self.parts: list[dict] = []  # {path, bytes, books}
        self.cur = None

    def _new_part(self):
        idx = len(self.parts) + 1
        self.cur = {"idx": idx, "buf": [], "bytes": 0, "books": []}
        self.parts.append(self.cur)

    def add_book(self, he_title: str, body: bytes, sections_split: list[bytes] | None = None):
        if self.cur is None:
            self._new_part()
        if self.cur["bytes"] > 0 and self.cur["bytes"] + len(body) > self.max_bytes:
            self._new_part()
        if len(body) > self.max_bytes and sections_split:
            # ספר יחיד גדול מהמגבלה – פיצול לפי סעיפים ראשיים
            for chunk in sections_split:
                if self.cur["bytes"] > 0 and self.cur["bytes"] + len(chunk) > self.max_bytes:
                    self._new_part()
                self.cur["buf"].append(chunk)
                self.cur["bytes"] += len(chunk)
                if he_title not in self.cur["books"]:
                    self.cur["books"].append(he_title)
            return
        self.cur["buf"].append(body)
        self.cur["bytes"] += len(body)
        self.cur["books"].append(he_title)

    def flush(self, folder_he: str) -> list[Path]:
        written = []
        n = len(self.parts)
        for p in self.parts:
            if p["bytes"] == 0:
                continue
            suffix = f"_חלק_{gematria(p['idx'])}" if n > 1 else ""
            fname = f"{self.folder[:2]}_{self.folder[3:]}_{self.volume}{suffix}.txt"
            path = self.out_dir / self.folder / fname
            path.parent.mkdir(parents=True, exist_ok=True)
            vol_he = self.volume.replace("_", " ")
            header = (
                f"# ספריא – {folder_he.replace('_', ' ')} – {vol_he}"
                + (f" (חלק {gematria(p['idx'])} מתוך {n})" if n > 1 else "")
                + "\n"
                + f"מקור: Sefaria (https://www.sefaria.org) | קידוד: UTF-8\n"
                + "ספרים בקובץ זה: " + ", ".join(p["books"]) + "\n"
            )
            with open(path, "wb") as f:
                f.write(header.encode("utf-8"))
                for chunk in p["buf"]:
                    f.write(chunk)
            written.append(path)
        return written


def split_book_by_sections(body: str) -> list[bytes]:
    """מפצל גוף ספר לפי כותרות רמה 2 (## ...), לשימוש כשספר בודד גדול מהמגבלה."""
    parts = re.split(r"(?m)^(?=## )", body)
    return [p.encode("utf-8") for p in parts if p.strip()]


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="עיבוד טקסטים עבריים מספריא לקבצי TXT עבור NotebookLM")
    ap.add_argument("--repo", default="./Sefaria-Export", help="נתיב לשיבוט של Sefaria-Export (עם books.json)")
    ap.add_argument("--out", default="./sefaria_notebooklm_export", help="תיקיית פלט")
    ap.add_argument("--cache", default="./sefaria_cache", help="תיקיית מטמון להורדות")
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--max-mb", type=float, default=45.0, help="גודל מרבי לקובץ TXT (MB)")
    ap.add_argument("--limit", type=int, default=0, help="לבדיקה: עיבוד N ספרים בלבד")
    ap.add_argument("--only", default="", help="רק תיקיות אלו, לדוגמה 01,03")
    args = ap.parse_args()

    out_dir = Path(args.out)
    cache = Path(args.cache)
    cache.mkdir(parents=True, exist_ok=True)
    max_bytes = int(args.max_mb * 1024 * 1024)

    # --- books.json
    books_path = Path(args.repo) / "books.json"
    if books_path.exists():
        books_index = json.load(open(books_path, encoding="utf-8"))
    else:
        print(f"[!] {books_path} לא נמצא – מוריד books.json מ-GitHub")
        dest = cache / "books.json"
        fetch(BOOKS_JSON_RAW, dest)
        books_index = json.load(open(dest, encoding="utf-8"))
    books = [b for b in books_index["books"] if b.get("language") == "Hebrew" and b.get("versionTitle") == "merged"]
    print(f"[i] books.json: {books_index.get('total_texts')} טקסטים, מתוכם {len(books)} קבצי עברית ממוזגים")

    # --- TOC
    toc_path = cache / "table_of_contents.json"
    fetch(TOC_URL, toc_path)
    ranks = toc_ranks(json.load(open(toc_path, encoding="utf-8")))

    # --- שיוך לתיקיות/כרכים
    plan: dict[tuple[str, str], list[dict]] = defaultdict(list)
    only = set(x.strip() for x in args.only.split(",") if x.strip())
    for b in books:
        a = assign(b)
        if a is None:
            continue
        if only and a[0] not in only:
            continue
        plan[a].append(b)
    for key in plan:
        plan[key].sort(key=lambda b: (ranks.get(b["title"], 10**9), b["title"]))
    selected = [b for lst in plan.values() for b in lst]
    if args.limit:
        selected = selected[: args.limit]
        keep = set(b["title"] for b in selected)
        for key in list(plan):
            plan[key] = [b for b in plan[key] if b["title"] in keep]
            if not plan[key]:
                del plan[key]
    print(f"[i] לעיבוד: {len(selected)} ספרים ב-{len(plan)} כרכים")

    # --- הורדה
    def local_json(b):
        rel = urllib.parse.unquote(b["json_url"].split("/sefaria-export/")[1])
        return cache / rel

    def local_schema(b):
        return cache / "schemas" / (b["title"].replace(" ", "_").replace("/", "_") + ".json")

    jobs = []
    for b in selected:
        jobs.append((b["json_url"], local_json(b)))
        jobs.append((schema_url(b["title"]), local_schema(b)))
    todo = [(u, p) for u, p in jobs if not p.exists()]
    print(f"[i] הורדה: {len(todo)} קבצים ({len(jobs) - len(todo)} כבר במטמון)")
    t0 = time.time()
    done = 0
    failed = []
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(fetch, u, p): (u, p) for u, p in todo}
        for fut in cf.as_completed(futs):
            done += 1
            if not fut.result():
                failed.append(futs[fut][0])
            if done % 500 == 0 or done == len(todo):
                print(f"    ... {done}/{len(todo)} ({time.time() - t0:.0f}s)")
    if failed:
        print(f"[!] {len(failed)} הורדות נכשלו (סכמות חסרות אינן קריטיות)")

    # --- עיבוד וכתיבה
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    summary: dict[str, dict] = OrderedDict()
    errors = []
    total_segments = 0
    t0 = time.time()
    processed = 0
    for (fcode, volume), lst in sorted(plan.items(), key=lambda kv: (kv[0][0], min(ranks.get(b["title"], 10**9) for b in kv[1]))):
        folder = FOLDERS[fcode]
        vw = VolumeWriter(out_dir, folder, volume, max_bytes)
        prev_group = None
        for b in lst:
            jp = local_json(b)
            if not jp.exists():
                errors.append((b["title"], "לא הורד"))
                continue
            try:
                data = json.load(open(jp, encoding="utf-8"))
                sp = local_schema(b)
                schema = json.load(open(sp, encoding="utf-8")) if sp.exists() else None
                r = Renderer(b, data, schema)
                body = r.render()
                if r.segments == 0:
                    continue
                # כותרת-קבוצה כשתת-הקטגוריה משתנה בתוך הכרך (למשל "ספר מדע" במשנה תורה, שם המפרש בכרכי מפרשים)
                cats = b.get("categories", [])
                group = " / ".join(CATEGORY_HE.get(c, c) for c in cats[2:]) if len(cats) >= 3 else None
                if group and group != prev_group:
                    body = f"\n\n# ═══ {group} ═══\n" + body
                prev_group = group
                total_segments += r.segments
                body_b = body.encode("utf-8")
                vw.add_book(r.he_title, body_b, split_book_by_sections(body) if len(body_b) > max_bytes else None)
            except Exception as e:  # noqa
                errors.append((b["title"], repr(e)[:200]))
            processed += 1
            if processed % 500 == 0:
                print(f"    ... עובדו {processed}/{len(selected)} ספרים ({time.time() - t0:.0f}s)")
        written = vw.flush(folder)
        s = summary.setdefault(folder, {"files": 0, "bytes": 0, "books": 0})
        s["files"] += len(written)
        s["bytes"] += sum(p.stat().st_size for p in written)
        s["books"] += len(lst)

    # --- סיכום
    print("\n" + "=" * 72)
    print("סיכום העיבוד – Sefaria → NotebookLM")
    print("=" * 72)
    grand_files = grand_bytes = grand_books = 0
    for folder, s in summary.items():
        print(f"  {folder:<28} קבצים: {s['files']:>3}   ספרים: {s['books']:>5}   גודל: {s['bytes'] / 1e6:8.1f} MB")
        grand_files += s["files"]
        grand_bytes += s["bytes"]
        grand_books += s["books"]
    print("-" * 72)
    total_label = 'סה"כ'
    print(f"  {total_label:<28} קבצים: {grand_files:>3}   ספרים: {grand_books:>5}   גודל: {grand_bytes / 1e6:8.1f} MB")
    print(f"  קטעי טקסט (פסוקים/משניות/שורות/הלכות): {total_segments:,}")
    if errors:
        print(f"  [!] שגיאות: {len(errors)}")
        for t, e in errors[:20]:
            print(f"      - {t}: {e}")
    print(f"\n  התיקייה המוכנה להעלאה לגוגל דרייב / NotebookLM:\n  {out_dir.resolve()}")
    print("=" * 72)


if __name__ == "__main__":
    main()
