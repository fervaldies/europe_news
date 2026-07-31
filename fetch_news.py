"""
fetch_news.py — europe_news
---------------------------
Fetches top Europe news headlines using GNews API (free),
uses GitHub Models to pick the 5 most diverse/important stories,
then translates them to Spanish using GitHub Models (free).

Required environment variables:
  GNEWS_API_KEY   — free API key from gnews.io
  GITHUB_TOKEN    — automatically available in GitHub Actions
"""

import sys
import json
import re
import os
import urllib.request
import urllib.parse
from datetime import datetime

GNEWS_API_KEY      = os.environ.get("GNEWS_API_KEY", "")
GEMINI_API_KEY  = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL    = "gemini-3.5-flash-lite"
GEMINI_URL      = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"


def extract_json(text):
    text = text.strip()
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = text.replace("```", "").strip()
    start = text.find("{")
    end   = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object found in response: {repr(text)}")
    return text[start:end + 1]


def clean_title(title):
    if " - " in title:
        parts  = title.rsplit(" - ", 1)
        suffix = parts[1].strip()
        sentence_words = {"the","a","an","and","or","but","in","on","at","to",
                          "of","for","is","are","was","were","not","new","old","it"}
        words = suffix.lower().split()
        if len(suffix) < 30 and not any(w in sentence_words for w in words):
            return parts[0].strip()
    return title.strip()


def github_models_call(messages, max_tokens=600):
    """Make a call to Gemini API and return the response text.
    Keeps the same function name/interface so callers don't need to change."""
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set")

    # Gemini has no separate "system" role — fold everything into one user turn
    prompt_text = "\n\n".join(m["content"] for m in messages)

    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt_text}]}],
        "generationConfig": {"maxOutputTokens": max_tokens}
    }).encode("utf-8")

    url = f"{GEMINI_URL}?key={GEMINI_API_KEY}"
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"}
    )

    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                result = json.loads(r.read().decode("utf-8"))
            return result["candidates"][0]["content"]["parts"][0]["text"]
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:
                wait = 5 * (attempt + 1)
                print(f"  ⏳ Gemini rate limited, retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise


def fetch_europe_news():
    """Fetch headlines specifically about Europe using GNews search endpoint."""
    if not GNEWS_API_KEY:
        raise ValueError("GNEWS_API_KEY is not set")

    params = urllib.parse.urlencode({
        "q":      "Europe",
        "lang":   "en",
        "max":    "25",
        "apikey": GNEWS_API_KEY
    })
    url = f"https://gnews.io/api/v4/search?{params}"

    print("📰 Fetching Europe news from GNews search API...")
    with urllib.request.urlopen(url, timeout=15) as r:
        data = json.loads(r.read().decode("utf-8"))

    articles = data.get("articles", [])
    print(f"  GNews returned {len(articles)} articles")

    if len(articles) < 5:
        raise ValueError(f"GNews returned only {len(articles)} articles — need at least 5")

    headlines = []
    seen = set()
    for article in articles:
        title = clean_title(article.get("title", ""))
        if title and len(title) > 10 and title not in seen:
            seen.add(title)
            headlines.append(title)

    if len(headlines) < 5:
        raise ValueError(f"Only {len(headlines)} valid headlines after cleaning")

    return headlines


def pick_best_5(headlines):
    """Use GitHub Models to pick the 5 most important Europe-specific stories."""
    numbered = "\n".join(f"{i}. {h}" for i, h in enumerate(headlines))
    print("🤖 Picking best 5 via GitHub Models...")
    text = github_models_call([{
        "role": "user",
        "content": (
            "You are a European news editor. Pick the 5 best stories from the list.\n\n"
            "STEP 1 — Remove duplicates FIRST. Group headlines that describe the same "
            "underlying event (same country + same topic = same story, even if the "
            "wording, angle, or numbers differ). Example: 'France limits alcohol during "
            "heatwave' and 'France restricts alcohol sales in heatwave' are the SAME "
            "story — keep only ONE. From each group pick the single clearest headline.\n\n"
            "STEP 2 — From the de-duplicated stories, pick the 5 most important. "
            "Each of the 5 MUST be about a different event. Never select two headlines "
            "that share the same country and topic.\n\n"
            "AVOID vague headlines with no specific person, country, company, or place, "
            "and minor sport or celebrity items.\n\n"
            "PREFER headlines naming a specific European country, leader, company, or "
            "concrete event, with variety of countries and topics.\n\n"
            "Return ONLY raw JSON, no markdown, no backticks:\n"
            '{"selected_indexes": [0, 1, 2, 3, 4]}\n\n'
            f"Indexes are 0-based. Stories:\n\n{numbered}"
        )
    }], max_tokens=100)
    text    = extract_json(text)
    indexes = json.loads(text)["selected_indexes"]
    selected = [headlines[i] for i in indexes if i < len(headlines)]
    if len(selected) < 5:
        for h in headlines:
            if h not in selected:
                selected.append(h)
            if len(selected) == 5:
                break
    return [{"title": t} for t in selected[:5]]


def translate_to_spanish(headlines):
    """Translate headlines to Spanish (Spain) using GitHub Models."""
    headlines_text = "\n".join(f"- {n['title']}" for n in headlines)
    print("🌐 Translating via GitHub Models...")
    text = github_models_call([{
        "role": "user",
        "content": (
            "Translate these headlines to Spanish from Spain. "
            "Return ONLY raw JSON, no markdown, no backticks, no explanation:\n"
            '{"news": [{"title": "translated"}, {"title": "translated"}, '
            '{"title": "translated"}, {"title": "translated"}, {"title": "translated"}]}\n\n'
            f"Headlines:\n{headlines_text}"
        )
    }])
    return extract_json(text)

def rewrite_headlines(headlines):
    """Rewrite raw API headlines to sound natural and punchy for social media."""
    numbered = "\n".join(f"{i+1}. {n['title']}" for i, n in enumerate(headlines))
    print("✍️ Rewriting headlines for natural language...")
    text = github_models_call([{
        "role": "user",
        "content": (
            "Rewrite these 5 news headlines to sound natural and punchy for social media. "
            "Rules: remove prefixes like 'LIVE UPDATES:', 'Study:', 'Report:', 'Breaking:'. "
            "Remove dates in parentheses. Replace semicolons with a comma or 'and'. "
            "Simplify scientific jargon into plain language. Remove marketing-speak. "
            "Keep each headline under 20 words and factually accurate. "
            "Return ONLY raw JSON, no markdown, no backticks:\n"
            '{"news": [{"title": "rewritten"}, {"title": "rewritten"}, '
            '{"title": "rewritten"}, {"title": "rewritten"}, {"title": "rewritten"}]}\n\n'
            f"Headlines:\n{numbered}"
        )
    }])
    text = extract_json(text)
    rewritten = json.loads(text)["news"]
    return rewritten


def get_news(day_name):
    all_headlines = fetch_europe_news()
    en_news  = pick_best_5(all_headlines)
    en_news  = rewrite_headlines(en_news)
    en_data  = {"news": en_news}
    print(f"✅ Selected {len(en_data['news'])} headlines:")
    for n in en_data["news"]:
        print(f"  - {n['title']}")

    es_text = translate_to_spanish(en_data["news"])
    es_data = json.loads(es_text)
    print("✅ Translation complete")

    date_str = datetime.now().strftime("%Y-%m-%d")

    def build_yml(data):
        lines = [f"date: {date_str}", f"day: {day_name}", "news:"]
        for item in data["news"]:
            title = item["title"].replace('"', "'")
            lines.append(f'  - title: "{title}"')
        return "\n".join(lines) + "\n"

    with open(f"{day_name}NewsEN.yml", "w", encoding="utf-8") as f:
        f.write(build_yml(en_data))
    with open(f"{day_name}NewsES.yml", "w", encoding="utf-8") as f:
        f.write(build_yml(es_data))

    print(f"✅ Created {day_name}NewsEN.yml and {day_name}NewsES.yml")


if __name__ == "__main__":
    day_name = sys.argv[1]
    get_news(day_name)
