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

def crawl_dnblab():
    url = "https://www.dnb.de/DE/Professionell/Services/WissenschaftundForschung/DNBLab/dnblab_node.html"
    try:
        client = httpx.Client(timeout=10, follow_redirects=True)
        response = client.get(url)
        if response.status_code != 200:
            st.error(f"Fehler beim Abrufen der Webseite: {response.status_code}")
            return None
        selector = Selector(response.text)
        # Extrahiere Hauptinhalt (auch h1, h2, h3, p, li, section, main, article)
        content = ' '.join(selector.xpath('//main//text() | //section//text() | //article//text() | //h1//text() | //h2//text() | //h3//text() | //p//text() | //li//text()').getall())
        content = re.sub(r'\s+', ' ', content).strip()
        if not content or len(content) < 30:
            st.warning("Keine ausreichenden Inhalte auf der Webseite gefunden.")
            return None
        df = pd.DataFrame([{
            'datensetname': "DNBLab-Webseite",
            'volltextindex': content,
            'quelle': url
        }])
        df.columns = df.columns.str.strip().str.lower()
        st.success("DNBLab-Webseite erfolgreich indexiert.")
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
Du bist ein Experte für die DNB-Datensätze.
Hier sind die Daten (mit Quelle):
{context}

Beantworte die folgende Frage basierend auf den Daten oben in ganzen Sätzen. Gib immer die Quelle der Information an.
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

st.title("DNBLab-Chatbot")

df = crawl_dnblab()

if df is not None and not df.empty:
    st.write(f"Geladene Datensätze: {len(df)} (Quelle: {df['quelle'].iloc[0]})")
    query = st.text_input("Suchbegriff oder Frage eingeben:")
    if query:
        context = df[['volltextindex', 'quelle']].to_string(index=False)
        with st.spinner("Frage wird analysiert..."):
            answer = ask_question(query, context, chatgpt_model)
        st.subheader("Antwort des Sprachmodells:")
        st.write(answer)
else:
    st.info("Die DNBLab-Webseite konnte nicht indexiert werden.")
