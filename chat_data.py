import streamlit as st
import pandas as pd
import httpx
from parsel import Selector
import re
from urllib.parse import urljoin

# Basis-URL und Wunsch-URLs
BASE_URL = "https://www.dnb.de/DE/Professionell/Services/WissenschaftundForschung/DNBLab"
START_URL = BASE_URL + "/dnblab_node.html"
EXTRA_URLS = [
    "https://www.dnb.de/DE/Professionell/Services/WissenschaftundForschung/DNBLab/dnblabTutorials.html?nn=849628",
    "https://www.dnb.de/DE/Professionell/Services/WissenschaftundForschung/DNBLabPraxis/dnblabPraxis_node.html",
    "https://www.dnb.de/DE/Professionell/Services/WissenschaftundForschung/DNBLab/dnblabSchnittstellen.html?nn=849628",
    "https://www.dnb.de/DE/Professionell/Services/WissenschaftundForschung/DNBLab/dnblabFreieDigitaleObjektsammlung.html?nn=849628"
]

st.sidebar.title("Konfiguration")
data_source = st.sidebar.radio("Datenquelle wählen:", ["Excel-Datei", "DNBLab-Webseite"])
chatgpt_model = st.sidebar.selectbox(
    "ChatGPT Modell wählen",
    options=["gpt-3.5-turbo", "gpt-4-turbo"],
    index=1
)
st.sidebar.markdown(f"Verwendetes Modell: **{chatgpt_model}**")

if "OPENAI_API_KEY" not in st.secrets:
    st.error("API-Key fehlt. Bitte in den Streamlit-Secrets hinterlegen.")
    st.stop()
api_key = st.secrets["OPENAI_API_KEY"]

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
        return None

@st.cache_data
def load_excel(file):
    try:
        xls = pd.ExcelFile(file)
        df = pd.read_excel(xls, sheet_name=xls.sheet_names[0], header=0, na_filter=False)
        df['volltextindex'] = df.apply(lambda row: ' | '.join(str(cell) for cell in row if pd.notnull(cell)), axis=1)
        df['quelle'] = "Excel-Datei"
        df.columns = df.columns.str.strip().str.lower()
        return df
    except Exception as e:
        st.error(f"Fehler beim Laden der Excel-Datei: {e}")
        return None

def full_text_search(df, query):
    try:
        mask = df['volltextindex'].str.lower().str.contains(query.lower())
        return df[mask]
    except Exception:
        return pd.DataFrame()

def ask_question(question, context, model):
    try:
        from openai import OpenAI
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

# Session State für Verlauf
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

st.title("DNBLab-Chatbot")

df = None
if data_source == "Excel-Datei":
    uploaded_file = st.sidebar.file_uploader("Excel-Datei hochladen", type=["xlsx"])
    if uploaded_file:
        with st.spinner("Excel-Datei wird geladen..."):
            df = load_excel(uploaded_file)
elif data_source == "DNBLab-Webseite":
    st.sidebar.info("Es wird die DNBLab-Webseite inkl. aller Unterseiten indexiert. Das kann einige Sekunden dauern.")
    with st.spinner("DNBLab-Webseite wird indexiert..."):
        df = crawl_dnblab()

if df is None or df.empty:
    st.info("Bitte laden Sie eine Excel-Datei hoch oder wählen Sie die DNBLab-Webseite aus der Sidebar.")
else:
    st.write(f"Geladene Datensätze: {len(df)}")
    st.markdown("**Folgende Seiten wurden indexiert:**")
    for url in sorted(df['quelle'].unique()):
        st.markdown(f"- [{url}]({url})" if url.startswith("http") else f"- {url}")

    # Chatverlauf anzeigen
    for i, entry in enumerate(st.session_state.chat_history):
        st.markdown(f"**Frage {i+1}:** {entry['question']}")
        st.markdown(f"**Antwort {i+1}:** {entry['answer']}")
        st.markdown("---")

    # Promptfeld unterhalb der letzten Antwort
    prompt = st.text_input("Frage oder Nachfrage eingeben:", key=f"prompt_{len(st.session_state.chat_history)}")
    absenden = st.button("Absenden")

    if absenden and prompt:
        # Frage oder Suchbegriff?
        question_words = ["wie", "was", "welche", "wann", "warum", "wo", "wieviel", "wieviele", "zähl", "nenn", "gibt", "zeige"]
        is_question = any(prompt.lower().startswith(word) for word in question_words)

        if is_question:
            context = df[['volltextindex', 'quelle']].to_string(index=False)
        else:
            results = full_text_search(df, prompt)
            if not results.empty:
                context = results[['volltextindex', 'quelle']].to_string(index=False)
            else:
                context = ""

        with st.spinner("Antwort wird generiert..."):
            answer = ask_question(prompt, context, chatgpt_model)
        st.session_state.chat_history.append({"question": prompt, "answer": answer})
        st.rerun()
