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

@st.cache_data()
def load_data(file):
    """Load the data."""
    try:
        df = pd.read_csv(file, encoding="utf-8", delimiter=",")
        if df.empty:
            st.error("Die Datei ist leer oder enthält keine Daten.")
            return None
        return pre_process(df)
    except pd.errors.EmptyDataError:
        st.error("Fehler: Die CSV-Datei ist leer oder enthält keine gültigen Daten.")
        return None
    except Exception as e:
        st.error(f"Fehler beim Laden der Datei: {str(e)}")
        return None

def pre_process(df):
    """Pre-process the data."""
    # Überprüfe auf leeres DataFrame nach dem Löschen der Spalten
    if df.empty:
        st.error("Keine gültigen Daten nach der Vorverarbeitung.")
        return None
    
    # Drop columns that start with "Unnamed"
    cols_to_drop = [col for col in df.columns if col.startswith("Unnamed")]
    df = df.drop(columns=cols_to_drop)
    
    # Zusätzliche Überprüfung auf NaN-Spalten
    df = df.dropna(axis=1, how='all')
    
    if df.empty:
        st.error("Alle Spalten wurden entfernt. Überprüfe das Datenformat.")
        return None
        
    return df

# ... [Rest des Codes bleibt unverändert bis zur Main-Logik] ...

st.title("Chat with your data")
uploaded_file = st.sidebar.file_uploader("Dataset hochladen", type="csv")

if uploaded_file:
    df = load_data(uploaded_file)
    
    if df is not None and not df.empty:  # Doppelte Überprüfung
        with st.chat_message("assistant"):
            st.markdown("Hier sind Ihre Daten:")
            st.dataframe(df, height=200)
            
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
                initial_code = code_prefix()
                with st.spinner("Analysiere..."):
                    # API Key Check vor der Abfrage
                    if not api_key:
                        st.error("Bitte zuerst OpenAI API Key eingeben!")
                    else:
                        answer = ask_question_with_retry(
                            prepare_question(description, question, initial_code),
                            api_key=api_key
                        )
                        
                if answer:
                    with st.chat_message("assistant"):
                        try:
                            script = initial_code + answer + "st.pyplot(fig)"
                            exec(script)
                            st.markdown("Generierter Code:")
                            st.code(script, language="python")
                        except Exception as e:
                            add_to_log(f"Error: {str(e)}")
                            st.error("Fehler bei der Code-Ausführung")
                else:
                    st.error("Anfrage fehlgeschlagen. Bitte Key überprüfen.")
    else:
        st.warning("Daten konnten nicht geladen werden. Bitte Dateiformat überprüfen.")
else:
    with st.chat_message("assistant"):
        st.markdown("Bitte laden Sie zuerst ein Dataset hoch")
