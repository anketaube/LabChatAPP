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

# ... [Rest des Codes bleibt gleich bis auf den Uploader] ...

st.title("Chat with your data")
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
            
        # ... [Rest der Chat-Logik bleibt unverändert] ...
        
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
