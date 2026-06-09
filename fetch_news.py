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
GITHUB_TOKEN       = os.environ.get("GITHUB_TOKEN", "")
GITHUB_MODELS_URL  = "https://models.inference.ai.azure.com/chat/completions"
GITHUB_MODEL       = "gpt-4o-mini"


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
    if not GITHUB_TOKEN:
        raise ValueError("GITHUB_TOKEN is not set")
    payload = json.dumps({
        "model": GITHUB_MODEL,
        "messages": messages,
        "max_tokens": max_tokens
    }).encode("utf-8")
    req = urllib.request.Request(
        GITHUB_MODELS_URL,
        data=payload,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {GITHUB_TOKEN}"}
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        result = json.loads(r.read().decode("utf-8"))
    return result["choices"][0]["message"]["content"]


def fetch_europe_news():
    """Fetch headlines specifically about Europe using GNews search endpoint."""
    if not GNEWS_API_KEY:
        raise ValueError("GNEWS_API_KEY is not set")

    params = urllib.parse.urlencode({
        "q":      "Europe",
        "lang":   "en",
        "max":    "10",
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
            "You are a European news editor. From the list below, pick the 5 most "
            "important stories specifically about Europe or European countries. "
            "Prioritise variety of topics and countries. "
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


def get_news(day_name):
    all_headlines = fetch_europe_news()
    en_news  = pick_best_5(all_headlines)
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
