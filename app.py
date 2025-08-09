import streamlit as st
import feedparser
from bs4 import BeautifulSoup
from dateutil import tz
from datetime import datetime, timedelta, date
import re
import csv
from io import StringIO
import requests

# --------- Paramètres ---------
APP_TITLE = "News Éco Maroc"
TIMEZONE = tz.gettz("Africa/Casablanca")

RSS_FEEDS = [
    "https://www.challenge.ma/feed",
    "https://www.ecoactu.ma/feed",
    "https://medias24.com/feed",
    "https://www.lavieeco.com/feed",
    "https://www.aujourdhui.ma/feed",
    "https://ledesk.ma/feed",
    "https://fr.le360.ma/economie/feed",
    "https://ar.le360.ma/economie/feed",
    "https://www.hespress.com/economie/feed",
    "https://lematin.ma/rss"
]

ECON_KEYWORDS = [
    "économie", "economy", "business", "finance", "bourse", "marché",
    "banque", "bank", "investissement", "investment", "entreprise", "PME",
    "inflation", "croissance", "PIB", "export", "import", "commerce",
    "industrie", "énergie", "oil", "gaz", "mines", "telecom", "tourisme",
]

HEADERS = {"User-Agent": "Mozilla/5.0"}

# --------- Fonctions utilitaires ---------
def clean_html(text: str) -> str:
    if not text:
        return ""
    soup = BeautifulSoup(text, "html.parser")
    return soup.get_text(" ", strip=True)

def simple_summarize(text: str, max_sentences: int = 2, max_words: int = 50) -> str:
    txt = clean_html(text)
    txt = re.sub(r"\s+", " ", txt).strip()
    if not txt:
        return ""
    sentences = re.split(r"(?<=[\.\!\?])\s+", txt)
    picked = []
    word_count = 0
    for s in sentences:
        w = len(s.split())
        if w == 0:
            continue
        if word_count + w > max_words and picked:
            break
        picked.append(s)
        word_count += w
        if len(picked) >= max_sentences:
            break
    summary = " ".join(picked)
    words = summary.split()
    if len(words) > max_words:
        summary = " ".join(words[:max_words]) + " …"
    return summary

def parse_entry_datetime(entry) -> datetime | None:
    t = None
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        if hasattr(entry, key):
            t = getattr(entry, key)
            if t:
                break
        if key in entry:
            t = entry[key]
            if t:
                break
    if t is None:
        return None
    dt = datetime(*t[:6])
    return dt.replace(tzinfo=TIMEZONE)

def same_day(dt: datetime, target_day: date) -> bool:
    local = dt.astimezone(TIMEZONE)
    return local.date() == target_day

# --------- Scrapers HTML ---------
def fetch_boursenews_html(target_day: date):
    items = []
    try:
        url = "https://www.boursenews.ma/"
        r = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        articles = soup.select(".article-item")
        for art in articles:
            title_tag = art.find("h3")
            if not title_tag:
                continue
            title = clean_html(title_tag.text)
            link = title_tag.find("a").get("href", "")
            desc_tag = art.find("p")
            summary = clean_html(desc_tag.text) if desc_tag else ""
            items.append({
                "source": "Boursenews",
                "title": title,
                "summary": summary,
                "time": "--:--",
                "link": link
            })
    except Exception:
        pass
    return items

def fetch_leboursier_html(target_day: date):
    items = []
    try:
        url = "https://leboursier.ma/"
        r = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        articles = soup.select("article")
        for art in articles:
            title_tag = art.find("h2") or art.find("h3")
            if not title_tag:
                continue
            title = clean_html(title_tag.text)
            link_tag = title_tag.find("a")
            link = link_tag.get("href", "") if link_tag else ""
            summary_tag = art.find("p")
            summary = clean_html(summary_tag.text) if summary_tag else ""
            items.append({
                "source": "LeBoursier",
                "title": title,
                "summary": summary,
                "time": "--:--",
                "link": link
            })
    except Exception:
        pass
    return items

# --------- Récupération combinée ---------
def fetch_news_for_day(target_day: date):
    items = []
    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
        except Exception:
            continue
        source_title = feed.feed.get("title", url)
        for entry in feed.entries:
            dt = parse_entry_datetime(entry) or datetime.now(TIMEZONE)
            if not same_day(dt, target_day):
                continue
            title = clean_html(entry.get("title", "(sans titre)"))
            link = entry.get("link", "")
            desc = entry.get("summary") or entry.get("description") or ""
            summary = simple_summarize(desc)
            haystack = f"{title} {desc}".lower()
            if any(domain in url for domain in ["telquel", "lematin", "le360", "hespress"]) and not any(k in haystack for k in ECON_KEYWORDS):
                continue
            items.append({
                "source": source_title,
                "title": title,
                "summary": summary or "(Résumé non disponible)",
                "time": dt.strftime("%H:%M"),
                "link": link
            })
    items.extend(fetch_boursenews_html(target_day))
    items.extend(fetch_leboursier_html(target_day))
    seen = set()
    unique = []
    for it in items:
        key = (it["title"], it["source"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(it)
    return unique

def export_csv(rows):
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=["source", "title", "summary", "time", "link"])
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return output.getvalue()

# --------- UI Streamlit ---------
st.set_page_config(page_title="News Éco Maroc", page_icon="📰", layout="centered")

st.title(APP_TITLE)

mode = st.selectbox("Choisir le jour", ["Aujourd'hui", "Hier", "Autre"], index=0)
if mode == "Aujourd'hui":
    selected_day = datetime.now(TIMEZONE).date()
elif mode == "Hier":
    selected_day = (datetime.now(TIMEZONE) - timedelta(days=1)).date()
else:
    selected_day = st.date_input("Choisir la date", value=datetime.now(TIMEZONE).date())

if st.button("🔄 Rafraîchir"):
    st.rerun()

news = fetch_news_for_day(selected_day)

st.subheader(f"Résultats — {len(news)} article(s) • {selected_day.isoformat()}")

if not news:
    st.info("Aucun article trouvé pour cette date.")
else:
    for item in news:
        with st.container():
            st.markdown(f"### {item['title']}")
            st.write(item["summary"])
            meta = f"**Source :** {item['source']}  •  **Heure :** {item['time']}"
            st.markdown(meta)
            st.link_button("Lire l'article", item["link"], use_container_width=True)
    csv_data = export_csv(news)
    st.download_button(
        label="⬇️ Exporter CSV",
        data=csv_data,
        file_name=f"news_eco_maroc_{selected_day.isoformat()}.csv",
        mime="text/csv",
        use_container_width=True,
    )
