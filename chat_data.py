import streamlit as st
import pandas as pd
from openai import OpenAI

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
def load_data(file):
    """Lädt Excel-Dateien mit vollständiger Indexierung"""
    try:
        xls = pd.ExcelFile(file)
        df = pd.read_excel(
            xls,
            sheet_name=xls.sheet_names[0],
            header=0,
            skiprows=0,
            na_filter=False
        )
        # Erstelle Volltextindex für alle Spalten
        df['volltextindex'] = df.apply(
            lambda row: ' | '.join(str(cell) for cell in row if pd.notnull(cell)),
            axis=1
        )
        st.success(f"{len(df)} Zeilen erfolgreich indexiert")
        return pre_process(df)
    except Exception as e:
        st.error(f"Fehler beim Laden: {str(e)}")
        return None

def pre_process(df):
    """Bereinigt das DataFrame"""
    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    df.columns = df.columns.str.strip().str.lower()
    return df.dropna(how='all')

def full_text_search(df, query):
    """Durchsucht alle Spalten mit Fuzzy-Matching"""
    try:
        mask = df['volltextindex'].str.lower().str.contains(query.lower())
        return df[mask]
    except Exception:
        return pd.DataFrame()

def ask_question(question, context, model):
    """Verwendet ChatGPT zur Beantwortung der Frage mit Datenkontext"""
    try:
        client = OpenAI(api_key=api_key)
        prompt_text = f"""
Du bist ein Datenexperte für die DNB-Datensätze.
Basierend auf dem gegebenen Kontext beantworte die Frage.
Kontext:
{context}
Frage: {question}
Gib eine ausführliche Antwort in ganzen Sätzen.
"""
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt_text}],
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        st.error(f"Fehler bei OpenAI API-Abfrage: {str(e)}")
        return "Fehler bei der Anfrage."

st.title("DNB-Datenset-Suche")

uploaded_file = st.sidebar.file_uploader(
    "Excel-Datei hochladen",
    type=["xlsx"],
    help="Nur Excel-Dateien (.xlsx) mit der korrekten Struktur"
)

if uploaded_file:
    df = load_data(uploaded_file)
    if df is not None:
        st.write(f"Geladene Datensätze: {len(df)}")
        search_query = st.text_input("Suchbegriff oder Frage eingeben (z.B. 'METS/MODS', 'Welche Datensets sind für Hochschulschriften geeignet?'):")
        if search_query:
            results = full_text_search(df, search_query)
            if not results.empty:
                st.subheader("Suchergebnisse")
                # Prüfe, ob die erwarteten Spalten existieren
                display_cols = [col for col in ['datensetname', 'datenformat', 'kategorie 1', 'kategorie 2'] if col in results.columns]
                if display_cols:
                    st.dataframe(results[display_cols])
                else:
                    st.dataframe(results)
                with st.spinner("Analysiere Treffer..."):
                    context = results.to_string(index=False, columns=display_cols) if display_cols else results.to_string(index=False)
                    answer = ask_question(search_query, context, chatgpt_model)
                    st.subheader("ChatGPT Antwort:")
                    st.write(answer)
            else:
                st.warning("Keine Treffer gefunden")
    else:
        st.info("Bitte laden Sie eine Excel-Datei hoch")
else:
    st.info("Bitte laden Sie eine Excel-Datei hoch")
