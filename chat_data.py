import streamlit as st
import pandas as pd
from openai import OpenAI

# API-Key aus Streamlit-Secrets laden (kein UI-Feld mehr)
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
    try:
        xls = pd.ExcelFile(file)
        df = pd.read_excel(xls, sheet_name=xls.sheet_names[0], header=0, na_filter=False)
        # Volltextindex für einfache Stichwortsuche
        df['volltextindex'] = df.apply(lambda row: ' | '.join(str(cell) for cell in row if pd.notnull(cell)), axis=1)
        df.columns = df.columns.str.strip().str.lower()
        st.success(f"{len(df)} Zeilen erfolgreich geladen und indexiert.")
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
        client = OpenAI(api_key=api_key)
        prompt = f"""
Du bist ein Datenexperte für die DNB-Datensätze.
Hier sind die Daten:
{context}

Beantworte die folgende Frage basierend auf den Daten oben in ganzen Sätzen:
{question}
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

if uploaded_file:
    df = load_data(uploaded_file)
    if df is not None:
        st.write(f"Geladene Datensätze: {len(df)}")
        search_query = st.text_input("Suchbegriff oder Frage eingeben:")

        if search_query:
            # Einfache Heuristik, um zu erkennen, ob es eine Frage ist
            question_words = ["wie", "was", "welche", "wann", "warum", "wo", "wieviel", "wieviele", "zähl", "nenn", "gibt", "zeige"]
            is_question = any(search_query.lower().startswith(word) for word in question_words)

            if is_question:
                # Ganze Tabelle als Kontext an das Sprachmodell geben
                context = df.to_string(index=False)
                with st.spinner("Frage wird analysiert..."):
                    answer = ask_question(search_query, context, chatgpt_model)
                    st.subheader("Antwort des Sprachmodells:")
                    st.write(answer)
            else:
                # Stichwortsuche
                results = full_text_search(df, search_query)
                if not results.empty:
                    st.subheader("Suchergebnisse")
                    display_cols = [col for col in ['datensetname', 'datenformat', 'kategorie 1', 'kategorie 2'] if col in results.columns]
                    st.dataframe(results[display_cols] if display_cols else results)
                    # Optional: Sprachmodell mit Treffern befragen
                    context = results.to_string(index=False, columns=display_cols) if display_cols else results.to_string(index=False)
                    with st.spinner("Analysiere Treffer..."):
                        answer = ask_question(search_query, context, chatgpt_model)
                        st.subheader("Ergänzende Antwort des Sprachmodells:")
                        st.write(answer)
                else:
                    st.warning("Keine Treffer gefunden.")
    else:
        st.info("Bitte laden Sie eine Excel-Datei hoch.")
else:
    st.info("Bitte laden Sie eine Excel-Datei hoch.")
