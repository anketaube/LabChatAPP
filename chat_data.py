import streamlit as st
import pandas as pd
from openai import OpenAI

# API-Key aus Secrets laden
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

@st.cache_data(ttl=3600)
def load_data(file):
    try:
        xls = pd.ExcelFile(file)
        df = pd.read_excel(xls, sheet_name=xls.sheet_names[0], header=0, na_filter=False)
        df['volltextindex'] = df.apply(lambda row: ' | '.join(str(cell) for cell in row if pd.notnull(cell)), axis=1)
        st.success(f"{len(df)} Zeilen erfolgreich indexiert")
        return df.loc[:, ~df.columns.str.contains('^Unnamed')].dropna(how='all')
    except Exception as e:
        st.error(f"Fehler beim Laden: {e}")
        return None

def full_text_search(df, query):
    try:
        mask = df['volltextindex'].str.lower().str.contains(query.lower())
        return df[mask]
    except:
        return pd.DataFrame()

def ask_question(question, context, model):
    try:
        client = OpenAI(api_key=api_key)
        prompt = f"""
Du bist ein Datenexperte für die DNB-Datensätze.
Basierend auf dem gegebenen Kontext beantworte die Frage.
Kontext:
{context}
Frage: {question}
Gib eine ausführliche Antwort in ganzen Sätzen.
"""
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
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
            results = full_text_search(df, search_query)
            if not results.empty:
                st.subheader("Suchergebnisse")
                st.dataframe(results[['datensetname', 'datenformat', 'kategorie 1', 'kategorie 2']])
                with st.spinner("Analysiere Treffer..."):
                    context = results.to_string(index=False, columns=['datensetname', 'datenformat', 'kategorie 1', 'kategorie 2'])
                    answer = ask_question(search_query, context, chatgpt_model)
                    st.subheader("ChatGPT Antwort:")
                    st.write(answer)
            else:
                st.warning("Keine Treffer gefunden")
else:
    st.info("Bitte laden Sie eine Excel-Datei hoch")
