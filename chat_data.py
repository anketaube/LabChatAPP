import streamlit as st
import pandas as pd
import requests
import zipfile
import io
import os
import json

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
def load_vector_json_from_github():
    ZIP_URL = "https://github.com/anketaube/LabChatAPP/raw/main/dnblab_index.zip"
    extract_to = "vektor_index"
    response = requests.get(ZIP_URL)
    if response.status_code != 200:
        st.error("Fehler beim Laden des Vektorindex von GitHub.")
        return None
    z = zipfile.ZipFile(io.BytesIO(response.content))
    z.extractall(extract_to)
    # Alle JSON-Dateien einlesen
    data = []
    for root, dirs, files in os.walk(extract_to):
        for file in files:
            if file.endswith(".json"):
                with open(os.path.join(root, file), "r", encoding="utf-8") as f:
                    try:
                        json_data = json.load(f)
                        # Robust: Liste oder einzelnes Dict
                        if isinstance(json_data, dict):
                            json_data = [json_data]
                        if isinstance(json_data, list):
                            for entry in json_data:
                                if isinstance(entry, dict):
                                    data.append({
                                        'datensetname': entry.get('metadata', {}).get('title', 'Web-Inhalt'),
                                        'volltextindex': entry.get('text', ''),
                                        'quelle': entry.get('metadata', {}).get('source', ''),
                                    })
                    except Exception as e:
                        st.warning(f"Fehler beim Parsen von {file}: {e}")
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

st.title("DNBLab-Chatbot")

df = None

if data_source == "Excel-Datei":
    uploaded_file = st.sidebar.file_uploader("Excel-Datei hochladen", type=["xlsx"])
    if uploaded_file:
        with st.spinner("Excel-Datei wird geladen..."):
            df = load_excel(uploaded_file)

elif data_source == "DNBLab-Webseite":
    st.sidebar.info("Es wird der vorberechnete Vektorindex aus GitHub geladen (kein Live-Crawling).")
    with st.spinner("Vektorindex wird geladen..."):
        df = load_vector_json_from_github()

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
