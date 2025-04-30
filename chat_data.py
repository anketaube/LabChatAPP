import streamlit as st
import pandas as pd
from openai import OpenAI
import httpx
from parsel import Selector
import re
from urllib.parse import urljoin, urlparse
from tqdm import tqdm

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

def crawl_website(base_url):
    """Crawlt alle Unterseiten einer Website und extrahiert Textinhalte"""
    with st.spinner(f"Crawle Website {base_url}..."):
        try:
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
                    if not response.status_code == 200:
                        continue
                    selector = Selector(response.text)
                    # Hauptinhalt extrahieren
                    content = ' '.join(selector.xpath('//main//text() | //div[@role="main"]//text()').getall())
                    content = re.sub(r'\s+', ' ', content).strip()
                    if content:
                        data.append({
                            'datensetname': f"Web-Inhalt: {url}",
                            'volltextindex': content,
                            'quelle': url
                        })
                    # Alle Links auf der Seite finden
                    for link in selector.xpath('//a/@href').getall():
                        full_url = urljoin(url, link).split('#')[0]
                        # Nur interne Links mitnehmen
                        if full_url.startswith(base_url) and full_url not in visited:
                            to_visit.add(full_url)
                except Exception as e:
                    st.warning(f"Fehler beim Crawlen von {url}: {e}")
            return pd.DataFrame(data)
        except Exception as e:
            st.error(f"Fehler beim Crawlen: {e}")
            return pd.DataFrame()

@st.cache_data()
def load_data(file, website_url=None):
    try:
        dfs = []
        # Excel-Daten laden
        if file:
            xls = pd.ExcelFile(file)
            df = pd.read_excel(xls, sheet_name=xls.sheet_names[0], header=0, na_filter=False)
            df['volltextindex'] = df.apply(lambda row: ' | '.join(str(cell) for cell in row if pd.notnull(cell)), axis=1)
            df['quelle'] = "Excel-Datei"
            df.columns = df.columns.str.strip().str.lower()
            dfs.append(df)
        # Web-Daten crawlen
        if website_url and website_url.startswith("http"):
            web_df = crawl_website(website_url.rstrip("*"))
            if not web_df.empty:
                dfs.append(web_df)
        if not dfs:
            return pd.DataFrame()
        combined_df = pd.concat(dfs, ignore_index=True)
        combined_df.columns = combined_df.columns.str.strip().str.lower()
        return combined_df
    except Exception as e:
        st.error(f"Fehler beim Laden der Daten: {e}")
        return pd.DataFrame()

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

st.title("DNB-Datenset-Suche")

uploaded_file = st.sidebar.file_uploader("Excel-Datei hochladen", type=["xlsx"])
website_url = st.sidebar.text_input("Website-URL inkl. * für alle Unterseiten (z.B. https://dnb.de/dnblab*)")

df = load_data(uploaded_file, website_url)

if df is not None and not df.empty:
    st.write(f"Gesamte Datensätze: {len(df)} (Excel: {sum(df['quelle'] == 'Excel-Datei')} | Web: {sum(df['quelle'] != 'Excel-Datei')})")
    search_query = st.text_input("Suchbegriff oder Frage eingeben:")
    if search_query:
        # Einfache Heuristik, um zu erkennen, ob es eine Frage ist
        question_words = ["wie", "was", "welche", "wann", "warum", "wo", "wieviel", "wieviele", "zähl", "nenn", "gibt", "zeige"]
        is_question = any(search_query.lower().startswith(word) for word in question_words)
        if is_question:
            # Ganze Tabelle als Kontext an das Sprachmodell geben (mit Quellen)
            context = df[['volltextindex', 'quelle']].to_string(index=False)
            with st.spinner("Frage wird analysiert..."):
                answer = ask_question(search_query, context, chatgpt_model)
            st.subheader("Antwort des Sprachmodells:")
            st.write(answer)
        else:
            # Stichwortsuche
            results = full_text_search(df, search_query)
            if not results.empty:
                st.subheader("Suchergebnisse")
                display_cols = ['quelle'] + [col for col in ['datensetname', 'datenformat', 'kategorie 1', 'kategorie 2'] if col in results.columns]
                st.dataframe(results[display_cols])
                # Optional: Sprachmodell mit Treffern befragen
                context = results[['volltextindex', 'quelle']].to_string(index=False)
                with st.spinner("Analysiere Treffer..."):
                    answer = ask_question(search_query, context, chatgpt_model)
                st.subheader("Ergänzende Antwort des Sprachmodells:")
                st.write(answer)
            else:
                st.warning("Keine Treffer gefunden.")
else:
    st.info("Bitte laden Sie eine Excel-Datei hoch oder geben Sie eine Website-URL ein.")
