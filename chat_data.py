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
    # Weitere Wunsch-URLs einfach ergänzen!
]

st.sidebar.title("Konfiguration")
data_source = st.sidebar.radio("Datenquelle wählen:", ["Excel-Datei", "DNBLab-Webseite"])
mistral_model = st.sidebar.selectbox(
    "Mistral Modell wählen",
    options=["mistral-small", "mistral-medium", "mistral-large"],
    index=1
)
st.sidebar.markdown(f"Verwendetes Modell: **{mistral_model}**")

if "MISTRAL_API_KEY" not in st.secrets:
    st.error("Mistral API-Key fehlt. Bitte in den Streamlit-Secrets hinterlegen (MISTRAL_API_KEY).")
    st.stop()
api_key = st.secrets["MISTRAL_API_KEY"]

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
            # Hauptinhalt extrahieren
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
            # Interne Links sammeln
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
        from mistralai.client import MistralClient
        client = MistralClient(api_key=api_key)
        prompt = f"""
Du bist ein Datenexperte für die DNB-Datensätze.
Hier sind die Daten mit Quellenangaben:

{context}

Beantworte die folgende Frage basierend auf den Daten oben in ganzen Sätzen.
Gib immer die Quelle der Information an (entweder Excel-Datei oder Web-URL).
Frage: {question}
"""
        response = client.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        return response.choices[0].message.content
    except Exception as e:
        st.error(f"Fehler bei Mistral API-Abfrage: {e}")
        return "Fehler bei der Anfrage."

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
        st.markdown(f"- [{url}]({url})")

    query = st.text_input("Suchbegriff oder Frage eingeben:")

    if query:
        question_words = ["wie", "was", "welche", "wann", "warum", "wo", "wieviel", "wieviele", "zähl", "nenn", "gibt", "zeige"]
        is_question = any(query.lower().startswith(word) for word in question_words)

        if is_question:
            context = df[['volltextindex', 'quelle']].to_string(index=False)
            with st.spinner("Frage wird analysiert..."):
                answer = ask_question(query, context, mistral_model)
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
                    answer = ask_question(query, context, mistral_model)
                st.subheader("Ergänzende Antwort des Sprachmodells:")
                st.write(answer)
            else:
                st.warning("Keine Treffer gefunden.")
