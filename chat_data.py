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
    """Lädt Excel-Dateien mit vollständiger Indexierung"""
    try:
        xls = pd.ExcelFile(file)
        df = pd.read_excel(xls, 
                          sheet_name=xls.sheet_names[0],
                          header=0,
                          skiprows=0,
                          na_filter=False)
        
        # Erstelle Volltextindex für alle Spalten
        df['Volltextindex'] = df.apply(
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
    # Behalte alle originalen Spalten bei
    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    df.columns = df.columns.str.strip().str.lower()
    return df.dropna(how='all')

def full_text_search(df, query):
    """Durchsucht alle Spalten mit Fuzzy-Matching"""
    try:
        query = query.lower()
        mask = df['volltextindex'].str.lower().str.contains(query)
        return df[mask]
    except:
        return pd.DataFrame()

def ask_question(prompt, context, api_key):
    """Analysiert die Frage mit Datenkontext"""
    try:
        client = OpenAI(api_key=api_key)
        
        prompt_text = f"""
        Analysiere diese Frage im Kontext der Datenbank:
        
        Datenbankstruktur:
        {context}
        
        Frage: {prompt}
        
        Antworte NUR mit einer kommaseparierten Liste der passenden Datensetnamen OHNE zusätzlichen Text.
        Falls keine passenden Ergebnisse, antworte 'Keine Treffer gefunden'.
        """
        
        response = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[{"role": "user", "content": prompt_text}],
            temperature=0
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
        
        # Volltextsuche-Interface
        search_query = st.text_input("Suchbegriff eingeben (z.B. 'METS/MODS' oder 'Hochschulschriften'):")
        
        if search_query:
            results = full_text_search(df, search_query)
            
            if not results.empty:
                st.subheader("Suchergebnisse")
                st.dataframe(results[['datensetname', 'datenformat', 'kategorie 1', 'kategorie 2']])
                
                # GPT-Zusatzanalyse
                if api_key:
                    with st.spinner("Analysiere Treffer..."):
                        context = f"""
                        Gefundene Datensets ({len(results)}):
                        {results[['datensetname', 'datenformat']].to_string(index=False)}
                        """
                        prompt = f"Fasse diese {len(results)} Treffer zum Suchbegriff '{search_query}' zusammen:"
                        analysis = ask_question(prompt, context, api_key)
                        st.write(analysis)
                else:
                    st.warning("API-Key benötigt für Zusatzanalysen")
            else:
                st.warning("Keine Treffer gefunden")

else:
    st.info("Bitte laden Sie eine Excel-Datei hoch")
