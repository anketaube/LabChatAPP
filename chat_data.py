import streamlit as st
import pandas as pd
from openai import OpenAI
import httpx
from parsel import Selector
import re
from urllib.parse import urljoin

# API-Key aus Streamlit-Secrets laden
if "OPENAI_API_KEY" not in st.secrets:
    st.error("API-Key fehlt. Bitte in den Streamlit-Secrets hinterlegen.")
    st.stop()
api_key = st.secrets["OPENAI_API_KEY"]

# Konfiguration in der Sidebar
st.sidebar.title("Konfiguration")
chatgpt_model = st.sidebar.selectbox(
    "ChatGPT Modell wählen",
    options=["gpt-3.5-turbo", "gpt-4-turbo"],
    index=1,
    help="Wähle das zu verwendende ChatGPT Modell"
)
st.sidebar.markdown(f"Verwendetes Modell: **{chatgpt_model}**")

# Datenquellen-Optionen in der Sidebar
data_source = st.sidebar.radio(
    "Datenquelle wählen:",
    options=["Excel-Datei", "Website (DNB Lab)"],
    index=0  # Standardmäßig Excel
)

# Excel-Upload
if data_source == "Excel-Datei":
    uploaded_file = st.sidebar.file_uploader("Excel-Datei hochladen", type=["xlsx"])
    website_url = None  # Deaktiviere Website-Option
# Website-URL
else:
    uploaded_file = None  # Deaktiviere Excel-Option
    website_url = st.sidebar.text_input("Website-URL (DNB Lab, z.B. https://www.dnb.de/dnblab)")

# Web-Crawling-Funktion
def crawl_website(base_url):
    """Crawlt alle Unterseiten einer Website und extrahiert Textinhalte"""
    with st.spinner(f"Crawle Website {base_url}..."):
        client = httpx.Client(timeout=10)
        visited = set()
        to_visit = set([base_url])
        data = []
        while to_visit:
            url = to_visit.pop()
            if url in visited:
                continue
            visited.add(url)
            try:
                response = client.get(url)
                if response.status_code != 200:
                    continue
                selector = Selector(response.text)
                # Hauptinhalt extrahieren (main, role=main, body, article, section, p)
                content = ' '.join(selector.xpath('//main//text() | //div[@role="main"]//text() | //body//text() | //article//text() | //section//text() | //p//text()').getall())
                content = re.sub(r'\s+', ' ', content).strip()
                if content and len(content) > 30:
                    data.append({
                        'datensetname': f"Web-Inhalt: {url}",
                        'volltextindex': content,
                        'quelle': url
                    })
                # Alle internen Links auf der Seite finden
                for link in selector.xpath('//a/@href').getall():
                    full_url = urljoin(url, link).split('#')[0]
                    if full_url.startswith(base_url) and full_url not in visited:
                        to_visit.add(full_url)
            except Exception as e:
                st.warning(f"Fehler beim Crawlen von {url}: {e}")
        if data:
            df = pd.DataFrame(data)
            df.columns = df.columns.str.strip().str.lower()
            st.success(f"{len(df)} Webseiten erfolgreich indexiert.")
            return df
        else:
            st.warning("Keine Inhalte auf der Website gefunden.")
            return None

# Excel-Ladefunktion
@st.cache_data()
def load_excel(file):
    try:
        xls = pd.ExcelFile(file)
        df = pd.read_excel(xls, sheet_name=xls.sheet_names[0], header=0, na_filter=False)
        df['volltextindex'] = df.apply(lambda row: ' | '.join(str(cell) for cell in row if pd.notnull(cell)), axis=1)
        df['quelle'] = "Excel-Datei"
        df.columns = df.columns.str.strip().str.lower()
        st.success(f"{len(df)} Zeilen erfolgreich geladen und indexiert.")
        return df
    except Exception as e:
        st.error(f"Fehler beim Laden der Excel-Datei: {e}")
        return None

# Suchfunktion
def full_text_search(df, query):
    try:
        mask = df['volltextindex'].str.lower().str.contains(query.lower())
        return df[mask]
    except Exception:
        return pd.DataFrame()

# OpenAI-Funktion
def ask_question(question, context, model):
    try:
        client = OpenAI(api_key=api_key)
        prompt = f"""
Du bist ein Datenexperte für die DNB-Datensätze.
Hier sind die Daten mit Quellenangaben:
{context}

Beantworte die folgende Frage basierend auf den Daten oben in ganzen Sätzen.
Gib immer die Quelle der Information an (entweder Excel-Datei oder Web-URL).
Frage: {question}
"""
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        return response.choices[0].message.content
    except Exception as e:
        st.error(f"Fehler bei OpenAI API-Abfrage: {e}")
        return "Fehler bei der Anfrage."

# Hauptbereich der App
st.title("DNBLab-Chatbot")

# Daten laden (entweder Excel oder Website)
df = None
if uploaded_file:
    df = load_excel(uploaded_file)
elif website_url:
    df = crawl_website(website_url)

# Suchfeld und Ergebnisse
if df is not None and not df.empty:
    st.write(f"Geladene Datensätze: {len(df)} (Quelle: {df['quelle'].iloc[0] if df['quelle'].nunique()==1 else 'gemischt'})")
    search_query = st.text_input("Suchbegriff oder Frage eingeben:")

    if search_query:
        question_words = ["wie", "was", "welche", "wann", "warum", "wo", "wieviel", "wieviele", "zähl", "nenn", "gibt", "zeige"]
        is_question = any(search_query.lower().startswith(word) for word in question_words)

        if is_question:
            context = df[['volltextindex', 'quelle']].to_string(index=False)
            with st.spinner("Frage wird analysiert..."):
                answer = ask_question(search_query, context, chatgpt_model)
            st.subheader("Antwort des Sprachmodells:")
            st.write(answer)
        else:
            results = full_text_search(df, search_query)
            if not results.empty:
                st.subheader("Suchergebnisse")
                display_cols = ['quelle'] + [col for col in ['datensetname', 'datenformat', 'kategorie 1', 'kategorie 2'] if col in results.columns]
                st.dataframe(results[display_cols] if display_cols else results)
                context = results[['volltextindex', 'quelle']].to_string(index=False)
                with st.spinner("Analysiere Treffer..."):
                    answer = ask_question(search_query, context, chatgpt_model)
                st.subheader("Ergänzende Antwort des Sprachmodells:")
                st.write(answer)
            else:
                st.warning("Keine Treffer gefunden.")
else:
    st.info("Bitte wählen Sie eine Datenquelle in der Sidebar und laden Sie die entsprechenden Daten.")
