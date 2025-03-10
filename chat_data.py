import streamlit as st
import pandas as pd
from openai import OpenAI
import os
import random
import time

LOG = "questions.log"

# Konfiguration im Sidebar
st.sidebar.title("Konfiguration")
api_key = st.sidebar.text_input(
    "OpenAI API Key eingeben",
    type="password",
    help="Hol dir deinen Key von https://platform.openai.com/account/api-keys"
)

@st.cache_data()
def load_data(file):
    """Lädt Excel-Dateien und erstellt einen Suchindex"""
    try:
        xls = pd.ExcelFile(file)
        df = pd.read_excel(xls, sheet_name=xls.sheet_names[0])
        
        # Erstelle einen Suchindex für alle Spalten
        df['SearchIndex'] = df.apply(
            lambda row: ' '.join(str(val) for val in row), 
            axis=1
        )
        
        return pre_process(df)
    except Exception as e:
        st.error(f"Fehler beim Laden: {str(e)}")
        return None

def pre_process(df):
    """Bereinigt das DataFrame"""
    # Entferne leere Spalten
    df = df.dropna(axis=1, how='all')
    # Normalisiere Spaltennamen
    df.columns = df.columns.str.strip().str.lower()
    return df

def search_datasets(df, query):
    """Durchsucht den Suchindex nach dem Query"""
    try:
        # Suche über alle Spalten
        mask = df.apply(
            lambda row: any(
                str(query).lower() in str(cell_value).lower()
                for cell_value in row
            ),
            axis=1
        )
        
        results = df[mask]
        return results if not results.empty else None
        
    except Exception as e:
        st.error(f"Suchfehler: {str(e)}")
        return None

def ask_question(question, context, api_key):
    """Analysiert die Frage mit Datenkontext"""
    client = OpenAI(api_key=api_key)
    
    prompt = f"""
Analysiere diese Frage im Kontext der Datenbank:

Datenbankstruktur:
{context}

Frage: {question}

Antworte NUR mit einer kommaseparierten Liste der passenden Datensetnamen OHNE zusätzlichen Text.
Falls keine passenden Ergebnisse, antworte 'Keine Treffer gefunden'.
"""
    
    response = client.chat.completions.create(
        model="gpt-4-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )
    
    return response.choices[0].message.content

def generate_context(df):
    """Erstellt einen detaillierten Kontext für das Modell"""
    context = []
    
    # Grundlegende Statistiken
    context.append(f"Die Tabelle enthält {len(df)} Einträge mit diesen Spalten:")
    context.append(", ".join(df.columns))
    
    # Wertelisten für wichtige Spalten
    for col in ['datenformat', 'kategorie 1', 'kategorie 2']:
        if col in df.columns:
            unique_vals = df[col].dropna().unique()
            context.append(f"\n\nSpalte '{col}':")
            context.append(", ".join(str(v) for v in unique_vals[:10]) + ("..." if len(unique_vals) > 10 else ""))
    
    # Beispiel-Datensätze
    context.append("\n\nBeispiel-Datensätze:")
    for _, row in df.head(3).iterrows():
        context.append(f"\n- {row['datensetname']}: {row['datenformat']}")
    
    return "\n".join(context)

# UI
st.title("DNB-Datenbankabfrage")

uploaded_file = st.sidebar.file_uploader(
    "Excel-Datei hochladen", 
    type=["xlsx"],
    help="Nur Excel-Dateien (.xlsx) mit korrekter Spaltenstruktur"
)

if uploaded_file:
    df = load_data(uploaded_file)
    
    if df is not None:
        st.success("Datenbank erfolgreich geladen")
        with st.expander("Datenvorschau"):
            st.dataframe(df.head(3))
        
        question = st.text_input("Stelle deine Frage (z.B. 'Zeige alle Datensets mit METS/MODS'):")
        
        if question and api_key:
            with st.spinner("Analysiere Datenbank..."):
                context = generate_context(df)
                answer = ask_question(question, context, api_key)
                
                # Direkte Suche als Fallback
                direct_results = search_datasets(df, question)
                
            if "keine treffer" not in answer.lower():
                st.subheader("GPT-basierte Ergebnisse:")
                st.write(answer)
                
            if direct_results is not None:
                st.subheader("Direkte Treffer:")
                st.dataframe(direct_results[['datensetname', 'datenformat']])
                
            elif "keine treffer" in answer.lower():
                st.warning("Keine passenden Datensätze gefunden")

else:
    st.info("Bitte laden Sie zuerst eine Excel-Datei hoch")

