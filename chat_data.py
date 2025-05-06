import streamlit as st
import pandas as pd
import httpx
from parsel import Selector
import re
from urllib.parse import urljoin
from PyPDF2 import PdfReader
from docx import Document
import xml.etree.ElementTree as ET

BASE_URL = "https://www.dnb.de/DE/Professionell/Services/WissenschaftundForschung/DNBLab"
START_URL = BASE_URL + "/dnblab_node.html"
EXTRA_URLS = [
    "https://www.dnb.de/DE/Professionell/Services/WissenschaftundForschung/DNBLab/dnblabTutorials.html?nn=849628",
    "https://www.dnb.de/DE/Professionell/Services/WissenschaftundForschung/DNBLabPraxis/dnblabPraxis_node.html",
    "https://www.dnb.de/DE/Professionell/Services/WissenschaftundForschung/DNBLab/dnblabSchnittstellen.html?nn=849628",
    "https://www.dnb.de/DE/Professionell/Services/WissenschaftundForschung/DNBLab/dnblabFreieDigitaleObjektsammlung.html?nn=849628"
]

st.sidebar.title("Konfiguration")
chatgpt_model = st.sidebar.selectbox(
    "ChatGPT Modell wählen",
    options=["gpt-3.5-turbo", "gpt-4-turbo"],
    index=1
)
st.sidebar.markdown(f"Verwendetes Modell: **{chatgpt_model}**")

uploaded_files = st.sidebar.file_uploader(
    "Dateien (Excel, PDF, Word, XML) hochladen",
    type=["xlsx", "xml", "pdf", "docx", "doc"],
    accept_multiple_files=True
)
index_button = st.sidebar.button("Indexieren")

if "OPENAI_API_KEY" not in st.secrets:
    st.error("API-Key fehlt. Bitte in den Streamlit-Secrets hinterlegen.")
    st.stop()
api_key = st.secrets["OPENAI_API_KEY"]

# ------------------ Datei-Verarbeitung ------------------
def process_file(file):
    if file.type == "application/pdf":
        reader = PdfReader(file)
        text = " ".join([page.extract_text() or "" for page in reader.pages])
    elif file.type == "text/xml":
        text = " ".join(ET.parse(file).getroot().itertext())
    elif "wordprocessingml" in file.type or file.type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        doc = Document(file)
        text = " ".join([p.text for p in doc.paragraphs])
    elif file.type in ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/vnd.ms-excel"):
        try:
            xls = pd.ExcelFile(file)
            df = pd.read_excel(xls, sheet_name=xls.sheet_names[0], header=0, na_filter=False)
            text = df.apply(lambda row: ' | '.join(str(cell) for cell in row if pd.notnull(cell)), axis=1).str.cat(sep=" || ")
        except Exception:
            text = ""
    else:
        text = ""
    return text

# ------------------ Webseiten-Crawler ------------------
@st.cache_data(show_spinner=True)
def crawl_dnblab():
    client = httpx.Client(timeout=10, follow_redirects=True)
    visited = set()
    to_visit = set([START_URL] + EXTRA_URLS)
    data = []
    while to_visit:
        url = to_visit.pop()
        if url in visited:
            continue
        visited.add(url)
        try:
            resp = client.get(url)
            if resp.status_code != 200:
                continue
            selector = Selector(resp.text)
            content = ' '.join(selector.xpath(
                '//main//text() | //div[@role="main"]//text() | //body//text() | //article//text() | //section//text() | //p//text() | //li//text()'
            ).getall())
            content = re.sub(r'\s+', ' ', content).strip()
            if content and len(content) > 50:
                data.append({
                    'datensetname': f"Web-Inhalt: {url}",
                    'volltextindex': content,
                    'quelle': url
                })
            for link in selector.xpath('//a/@href').getall():
                full_url = urljoin(url, link).split('#')[0]
                if (
                    full_url.startswith(BASE_URL)
                    and full_url not in visited
                    and full_url not in to_visit
                ):
                    to_visit.add(full_url)
        except Exception as e:
            st.warning(f"Fehler beim Crawlen von {url}: {e}")
    if data:
        df = pd.DataFrame(data)
        df.columns = df.columns.str.strip().str.lower()
        return df
    else:
        return pd.DataFrame(columns=["datensetname", "volltextindex", "quelle"])

def full_text_search(df, query):
    try:
        mask = df['volltextindex'].str.lower().str.contains(query.lower())
        return df[mask]
    except Exception:
        return pd.DataFrame()

def ask_question(question, context, model, api_key):
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        prompt = f"""
Hier sind Daten aus verschiedenen Quellen (Web-URLs und Dateinamen).
Nutze diese Daten, um die folgende Frage zu beantworten. Wenn du Informationen verwendest, gib bitte die Quelle (URL oder Dateiname) mit an.
Frage: {question}
{context}
"""
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Du bist ein Datenexperte für die DNB-Datensätze."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )
        return response.choices[0].message.content
    except Exception as e:
        st.error(f"Fehler bei OpenAI API-Abfrage: {e}")
        return "Fehler bei der Anfrage."

st.title("DNBLab-Chatbot")

# Session State für Index und Chat
if "web_df" not in st.session_state:
    with st.spinner("Indexiere DNBLab-Webseiten ..."):
        st.session_state.web_df = crawl_dnblab()
if "file_df" not in st.session_state:
    st.session_state.file_df = pd.DataFrame(columns=["volltextindex", "quelle"])
if "combined_df" not in st.session_state:
    st.session_state.combined_df = st.session_state.web_df.copy()
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# Nach Datei-Upload: Index erweitern
if index_button and uploaded_files:
    file_data = []
    for file in uploaded_files:
        text = process_file(file)
        if text.strip():
            file_data.append({
                "volltextindex": text,
                "quelle": file.name
            })
    if file_data:
        new_file_df = pd.DataFrame(file_data)
        st.session_state.file_df = pd.concat([st.session_state.file_df, new_file_df], ignore_index=True)
        st.session_state.combined_df = pd.concat([st.session_state.web_df, st.session_state.file_df], ignore_index=True)
        st.success(f"{len(file_data)} Datei(en) zum Index hinzugefügt.")
    else:
        st.warning("Keine verwertbaren Inhalte in den hochgeladenen Dateien gefunden.")

# Index-Info
st.write(f"**Aktueller Index umfasst {len(st.session_state.combined_df)} Einträge.**")
st.markdown("**Quellen im Index:**")
for url in sorted(st.session_state.combined_df['quelle'].unique()):
    st.markdown(f"- {url}")

# Chat-UI: Verlauf & Prompt-Chaining
for i, entry in enumerate(st.session_state.chat_history):
    st.markdown(f"**Frage {i+1}:** {entry['question']}")
    st.markdown(f"**Antwort {i+1}:** {entry['answer']}")
    st.markdown("**Verwendete Quellen:**")
    for q in entry['sources']:
        if q.startswith("http"):
            st.markdown(f"- [{q}]({q})")
        else:
            st.markdown(f"- {q}")
    st.markdown("---")

# Eingabefeld für neue Frage oder Nachfrage
if len(st.session_state.chat_history) == 0:
    prompt = st.text_input("Frage eingeben:", key="input_0")
else:
    prompt = st.text_input("Nachfrage eingeben:", key=f"input_{len(st.session_state.chat_history)}")

absenden = st.button("Absenden")

if absenden and prompt:
    # Kontext: Relevante Einträge suchen (max. 5 Treffer à 1000 Zeichen)
    df = st.session_state.combined_df
    results = full_text_search(df, prompt)
    if not results.empty:
        context = "\n\n".join(
            f"Quelle: {row['quelle']}\nInhalt: {row['volltextindex'][:1000]}..."
            for _, row in results.head(5).iterrows()
        )
        quellen = results['quelle'].unique().tolist()
    else:
        context = ""
        quellen = []
    with st.spinner("Antwort wird generiert ..."):
        answer = ask_question(prompt, context, chatgpt_model, api_key)
    st.session_state.chat_history.append({"question": prompt, "answer": answer, "sources": quellen})
    st.rerun()
