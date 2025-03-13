import streamlit as st
import pandas as pd
from llama_index.core import VectorStoreIndex, Document
from llama_index.core import Settings
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.openai import OpenAI
import os

# Setze das Embedding-Modell
Settings.embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-small-en-v1.5")

# Setze das LLM
Settings.llm = OpenAI(model="gpt-3.5-turbo")

@st.cache_resource
def create_index(df):
    """
    Erstelle einen VectorStoreIndex aus dem DataFrame.
    """
    documents = [Document(text=row.to_string()) for _, row in df.iterrows()]
    index = VectorStoreIndex.from_documents(documents)
    return index

@st.cache_data
def load_data(file):
    """
    Lade die Daten und erstelle den Index.
    """
    df = pd.read_csv(file, encoding="utf-8", delimiter=",")
    df = pre_process(df)
    index = create_index(df)
    return df, index

def pre_process(df):
    """
    Vorverarbeitung der Daten.
    """
    for col in df.columns:
        if col.startswith("Unnamed"):
            df = df.drop(col, axis=1)
    return df

st.title("Chat mit deinen Daten")

uploaded_file = st.sidebar.file_uploader("Lade einen Datensatz hoch", type="csv")

if uploaded_file:
    df, index = load_data(uploaded_file)

    with st.chat_message("assistant"):
        st.markdown("Hier ist eine Tabelle mit den Daten:")
        st.dataframe(df, height=200)

    question = st.chat_input(placeholder="Stelle eine Frage zu den Daten")

    if question:
        with st.chat_message("user"):
            st.markdown(question)

        with st.spinner("Denke nach..."):
            query_engine = index.as_query_engine()
            response = query_engine.query(question)

        with st.chat_message("assistant"):
            st.markdown(response.response)

else:
    with st.chat_message("assistant"):
        st.markdown("Lade einen Datensatz hoch, um zu beginnen.")
