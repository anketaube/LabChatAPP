import streamlit as st
import pandas as pd
from openai import OpenAI
import os
import random
import time

LOG = "questions.log"

# Add OpenAI API key input in sidebar
st.sidebar.title("Konfiguration")
api_key = st.sidebar.text_input(
    "OpenAI API Key eingeben",
    type="password",
    help="Hol dir deinen Key von https://platform.openai.com/account/api-keys"
)

# Zeige das verwendete Sprachmodell im Sidebar an
model_name = "gpt-3.5-turbo"  # Definiere den Modellnamen
st.sidebar.markdown(f"Verwendetes Sprachmodell: **{model_name}**")

@st.cache_data()
def load_data(file):
    """Lädt CSV oder Excel-Dateien mit automatischer Fehlerbehandlung"""
    try:
        # Check file type
        if file.name.endswith(('.xlsx', '.xls')):
            try:
                import openpyxl  # Stelle sicher, dass openpyxl installiert ist
            except ImportError:
                st.error("Fehler: 'openpyxl' ist nicht installiert. Bitte installiere es mit 'pip install openpyxl'")
                return None
            
            xls = pd.ExcelFile(file)
            try:
                df = pd.read_excel(xls, sheet_name=xls.sheet_names[0])
                st.success("Excel-Datei erfolgreich geladen")
                return pre_process(df)
            except Exception as e:
                st.error(f"Fehler beim Lesen der Excel-Datei: {str(e)}")
                return None
            
        elif file.name.endswith('.csv'):
            encodings = ['utf-8', 'latin1', 'cp1252', 'iso-8859-1']
            for encoding in encodings:
                try:
                    file.seek(0)  # Reset file pointer
                    df = pd.read_csv(file, encoding=encoding, delimiter=None, engine='python')
                    st.success(f"CSV mit {encoding} Kodierung geladen")
                    return pre_process(df)
                except UnicodeDecodeError:
                    continue
                except pd.errors.EmptyDataError:
                    st.error("CSV ist leer oder hat kein gültiges Format")
                    return None
            st.error("Kodierungsproblem - Speichere die Datei als UTF-8 oder Excel")
            return None
            
    except Exception as e:
        st.error(f"Kritischer Fehler: {str(e)}")
        return None

def pre_process(df):
    """Bereinigt das DataFrame"""
    if df.empty:
        st.error("Keine Daten nach der Bereinigung")
        return None
    
    # Lösche leere/unbenannte Spalten
    df = df.dropna(axis=1, how='all')
    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    
    if df.empty:
        st.error("Alle Spalten wurden entfernt")
        return None
        
    return df

def add_to_log(question):
    """Log the question"""
    with open(LOG, "a") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S") + " ")
        f.write(question + "\n")
        f.flush()

def ask_question(question, system="You are a data scientist.", api_key=None):
    """Ask a question and return the answer."""
    if not api_key:
        st.error("Bitte gib zuerst deinen OpenAI API Key ein.")
        return None  # Wichtig: Gib None zurück, um die Ausführung zu stoppen
    
    client = OpenAI(api_key=api_key)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": question}
    ]
    
    response = client.chat.completions.create(
        model=model_name,  # Verwende den definierten Modellnamen
        messages=messages,
        temperature=0,
        stop=["plt.show()", "st.pyplot(fig)"]
    )
    
    answer = response.choices[0].message.content
    return answer

def ask_question_with_retry(question, api_key, system="You are a data scientist.", retries=1):
    """Wrapper around ask_question that retries if it fails."""
    delay = 2 * (1 + random.random())
    time.sleep(delay)
    
    for i in range(retries):
        try:
            return ask_question(question, system=system, api_key=api_key)
        except Exception as e:
            delay = 2 * delay
            time.sleep(delay)
    return None

def prepare_question(description, question, initial_code):
    """Prepare a question for the chatbot."""
    return f"""
Context:
{description}
Question: {question}
Antwort:

"""

def describe_dataframe(df):
    """Describe the dataframe."""
    description = []
    description.append(f"Das Dataframe hat die folgenden Spalten: {', '.join(df.columns)}.")
    
    # Explizite Beschreibung jeder Spalte
    for column in df.columns:
        dtype = df[column].dtype
        description.append(f"Die Spalte '{column}' hat den Datentyp {dtype}.")
        if dtype == 'object':  # String-Spalten
            unique_vals = df[column].unique()
            description.append(f"Die Spalte '{column}' hat die folgenden eindeutigen Werte: {', '.join(map(str, unique_vals[:10]))}{'...' if len(unique_vals) > 10 else ''}.")  # Zeige max. 10 Werte
        elif dtype in ['int64', 'float64']:  # Numerische Spalten
            description.append(f"Die Spalte '{column}' hat den minimalen Wert {df[column].min()} und den maximalen Wert {df[column].max()}.")
    
    description.append("Bitte beantworte die Frage direkt basierend auf diesen Informationen.")
    return "\n".join(description)

def check_categorical_variables(df):
    """Check that all values of categorical variables are strings."""
    return [column for column in df.columns if df[column].dtype == "object"
            and not all(isinstance(x, str) for x in df[column].dropna().unique())]

def list_non_categorical_values(df, column):
    """List the non-categorical values in a column."""
    return [x for x in df[column].unique() if not isinstance(x, str)]

def code_prefix():
    """Code to prefix to the visualization code."""
    return """
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(6.4, 2.4))
"""

def generate_placeholder_question(df):
    return "Nenne mir alle Datensetnamen mit dem Datenformat METS/MOds"

st.title("Chat mit deinen Daten")
uploaded_file = st.sidebar.file_uploader(
    "Dataset hochladen", 
    type=["csv", "xlsx", "xls"],  # Unterstützte Formate
    help="Unterstützte Formate: CSV, Excel (.xlsx, .xls)"
)

if uploaded_file:
    df = load_data(uploaded_file)
    
    if df is not None and not df.empty:
        with st.chat_message("assistant"):
            st.markdown("Erfolgreich geladene Daten:")
            st.dataframe(df.head(3), height=150)  # Zeige nur die ersten Zeilen
        
        # Hier befindet sich das Chatfeld jetzt
        question = st.chat_input(placeholder=generate_placeholder_question(df))
        
        if question:
            with st.chat_message("user"):
                st.markdown(question)
            add_to_log(f"Question: {question}")
            
            description = describe_dataframe(df)
            
            if "ERROR" in description:
                with st.chat_message("assistant"):
                    st.markdown(description)
            else:
                initial_code = ""  # Leerer initial_code, da wir keine Visualisierungen erwarten
                with st.spinner("Thinking..."):
                    # API Key Check vor der Abfrage
                    if not api_key:
                        st.error("Bitte zuerst OpenAI API Key eingeben!")
                    else:
                        # Überprüfe, ob ask_question eine Antwort liefert
                        answer = ask_question_with_retry(
                            prepare_question(description, question, initial_code),
                            api_key=api_key,
                            system="Du bist ein hilfreicher Assistent, der Fragen basierend auf dem gegebenen Kontext beantwortet."  # Angepasster System-Prompt
                        )
                        
                if answer:
                    with st.chat_message("assistant"):
                        st.markdown(answer)  # Gib die direkte Antwort aus
                else:
                    st.error("Die Anfrage konnte nicht beantwortet werden.")
    else:
        st.error("""
        Behebung von Upload-Problemen:
        1. Bei CSV: Als UTF-8 speichern (in Excel: 'Datei > Speichern unter > CSV UTF-8')
        2. Bei Excel: Sicherstellen, dass Daten ab Zelle A1 beginnen
        3. Leere Zeilen/Spalten entfernen
        """)
else:
    with st.chat_message("assistant"):
        st.markdown("Lade eine Datei hoch um zu beginnen (CSV oder Excel)")
