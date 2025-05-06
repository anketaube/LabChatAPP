# app.py
import streamlit as st
import pandas as pd
import httpx
from parsel import Selector
import re
from urllib.parse import urljoin
from PyPDF2 import PdfReader
from docx import Document
import xml.etree.ElementTree as ET

BASE_URL = "https://www.dnb.de/DE/Professionell/Services/WissenschaftundForschung/DNBLab"
START_URL = BASE_URL + "/dnblab_node.html"
EXTRA_URLS = [
    "https://www.dnb.de/DE/Professionell/Services/WissenschaftundForschung/DNBLab/dnblabTutorials.html?nn=849628",
    "https://www.dnb.de/DE/Professionell/Services/WissenschaftundForschung/DNBLabPraxis/dnblabPraxis_node.html",
    "https://www.dnb.de/DE/Professionell/Services/WissenschaftundForschung/DNBLab/dnblabSchnittstellen.html?nn=849628",
    "https://www.dnb.de/DE/Professionell/Services/WissenschaftundForschung/DNBLab/dnblabFreieDigitaleObjektsammlung.html?nn=849628"
]

def process_file(file):
    if file.type == "application/pdf":
        reader = PdfReader(file)
        text = " ".join([page.extract_text() for page in reader.pages])
    elif file.type == "text/xml":
        text = " ".join(ET.parse(file).getroot().itertext())
    elif "wordprocessingml" in file.type:
        doc = Document(file)
        text = " ".join([p.text for p in doc.paragraphs])
    else:
        text = ""
    return text

@st.cache_data(show_spinner=True)
def crawl_dnblab():
    client = httpx.Client(timeout=10, follow_redirects=True)
    visited = set()
    to_visit = set([START_URL] + EXTRA_URLS)
    data = []
    
    while to_visit:
        url = to_visit.pop()
        if url in visited:
            continue
        visited.add(url)
        
        try:
            resp = client.get(url)
            if resp.status_code != 200:
                continue
                
            selector = Selector(resp.text)
            content = ' '.join(selector.xpath('//main//text() | //div[@role="main"]//text()').getall())
            content = re.sub(r'\s+', ' ', content).strip()
            
            if content and len(content) > 50:
                data.append({
                    'datensetname': f"Web-Inhalt: {url}",
                    'volltextindex': content,
                    'quelle': url
                })
                
            for link in selector.xpath('//a/@href').getall():
                full_url = urljoin(url, link).split('#')[0]
                if full_url.startswith(BASE_URL) and full_url not in visited:
                    to_visit.add(full_url)
                    
        except Exception as e:
            st.warning(f"Fehler beim Crawlen von {url}: {e}")
    
    return pd.DataFrame(data) if data else None

# Session State Initialisierung
if 'combined_df' not in st.session_state:
    st.session_state.combined_df = crawl_dnblab()
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []

# Sidebar
st.sidebar.title("Konfiguration")
uploaded_files = st.sidebar.file_uploader(
    "Dateien hochladen",
    type=["xlsx", "xml", "pdf", "docx", "doc"],
    accept_multiple_files=True
)

# Dateiverarbeitung
if uploaded_files:
    file_data = [process_file(file) for file in uploaded_files]
    files_df = pd.DataFrame({
        'volltextindex': file_data,
        'quelle': [file.name for file in uploaded_files]
    })
    st.session_state.combined_df = pd.concat([st.session_state.combined_df, files_df])

# Chat-Historie anzeigen
for entry in st.session_state.chat_history:
    st.markdown(f"**Frage:** {entry['question']}") 
    st.markdown(f"**Antwort:** {entry['answer']} [Quelle: {entry['source']}]")

# Hauptanwendung
st.title("DNBLab-Chatbot")
query = st.text_input("Suchbegriff oder Frage eingeben:")

if query:
    # Hier würde die Such- und Antwortlogik integriert werden
    # Beispielantwort zur Demonstration
    sources = st.session_state.combined_df['quelle'].unique().tolist()
    answer = f"Beispielantwort zur Frage: {query} [Quelle: {', '.join(sources[:3])}]"
    
    # Eintrag in Chat-Historie
    st.session_state.chat_history.append({
        'question': query,
        'answer': answer,
        'source': ', '.join(sources[:3])
    })
    
    st.write(answer)
