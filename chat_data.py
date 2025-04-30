import streamlit as st
import pandas as pd
from openai import OpenAI
import httpx
from parsel import Selector
import re

# API-Key aus Streamlit-Secrets laden
if "OPENAI_API_KEY" not in st.secrets:
    st.error("API-Key fehlt. Bitte in den Streamlit-Secrets hinterlegen.")
    st.stop()
api_key = st.secrets["OPENAI_API_KEY"]

st.sidebar.title("Konfiguration")
chatgpt_model = st.sidebar.selectbox(
    "ChatGPT Modell wählen",
    options=["gpt-3.5-turbo", "gpt-4-turbo"],
    index=1,
    help="Wähle das zu verwendende ChatGPT Modell"
)
st.sidebar.markdown(f"Verwendetes Modell: **{chatgpt_model}**")

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

def crawl_dnb_dnblab():
    """Nur die Startseite https://www.dnb.de/dnblab indexieren (ohne Unterseiten)"""
    url = "https://www.dnb.de/dnblab"
    try:
        client = httpx.Client(timeout=10)
        response = client.get(url)
        if response.status_code != 200:
            st.error(f"Fehler beim Abrufen der Webseite: {response.status_code}")
            return None
        selector = Selector(response.text)
        # Text aus Hauptbereichen extrahieren (main, role=main, body, article, section, p)
        content = ' '.join(selector.xpath(
            '//main//text() | //div[@role="main"]//text() | //body//text() | //article//text() | //section//text() | //p//text()'
        ).getall())
        content = re.sub(r'\s+', ' ', content).strip()
        if not content or len(content) < 30:
            st.warning("Keine ausreichenden Inhalte auf der Webseite gefunden.")
            return None
        df = pd.DataFrame([{
            'datensetname': f"Web-Inhalt: {url}",
            'volltextindex': content,
            'quelle': url
        }])
        df.columns = df.columns.str.strip().str.lower()
        st.success("Webseite https://www.dnb.de/dnblab erfolgreich indexiert.")
        return df
    except Exception as e:
        st.error(f"Fehler beim Crawlen der Webseite: {e}")
        return None

def full_text_search(df, query):
    try:
        mask = df['volltextindex'].str.lower().str.contains(query.lower())
        return df[mask]
    except Exception:
        return pd.DataFrame()

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

# --- UI ---

st.sidebar.title("Datenquelle wählen")
data_source = st.sidebar.radio("Quelle:", ["Excel-Datei", "DNB Lab Webseite (https://www.dnb.de/dnblab)"])

df = None

if data_source == "Excel-Datei":
    uploaded_file = st.sidebar.file_uploader("Excel-Datei hochladen", type=["xlsx"])
    if uploaded_file:
        df = load_excel(uploaded_file)
else:
    # Webseite laden (ohne Eingabefeld, immer feste URL)
    df = crawl_dnb_dnblab()

# Hauptbereich mit Titel und Eingabefeld
st.title("DNBLab-Chatbot")

if df is not None and not df.empty:
    st.write(f"Geladene Datensätze: {len(df)} (Quelle: {df['quelle'].iloc[0] if df['quelle'].nunique()==1 else 'gemischt'})")
    query = st.text_input("Suchbegriff oder Frage eingeben:")
    if query:
        question_words = ["wie", "was", "welche", "wann", "warum", "wo", "wieviel", "wieviele", "zähl", "nenn", "gibt", "zeige"]
        is_question = any(query.lower().startswith(word) for word in question_words)
        if is_question:
            context = df[['volltextindex', 'quelle']].to_string(index=False)
            with st.spinner("Frage wird analysiert..."):
                answer = ask_question(query, context, chatgpt_model)
            st.subheader("Antwort des Sprachmodells:")
            st.write(answer)
        else:
            results = full_text_search(df, query)
            if not results.empty:
                st.subheader("Suchergebnisse")
                display_cols = ['quelle'] + [col for col in ['datensetname', 'datenformat', 'kategorie 1', 'kategorie 2'] if col in results.columns]
                st.dataframe(results[display_cols] if display_cols else results)
                context = results[['volltextindex', 'quelle']].to_string(index=False)
                with st.spinner("Analysiere Treffer..."):
                    answer = ask_question(query, context, chatgpt_model)
                st.subheader("Ergänzende Antwort des Sprachmodells:")
                st.write(answer)
            else:
                st.warning("Keine Treffer gefunden.")
else:
    st.info("Bitte wählen Sie eine Datenquelle und laden Sie die Daten bzw. warten Sie auf die Indexierung der Webseite.")
