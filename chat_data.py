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
    df = pd.read_csv(file, encoding="utf-8", delimiter=",")
    return pre_process(df)

def ask_question(question, system="You are a data scientist.", api_key=None):
    """Ask a question and return the answer."""
    if not api_key:
        raise ValueError("API Key fehlt")
    
    client = OpenAI(api_key=api_key)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": question}
    ]
    
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=messages,
        temperature=0,
        stop=["plt.show()", "st.pyplot(fig)"]
    )
    
    answer = response.choices[0].message.content
    return answer

def ask_question_with_retry(question, api_key, system="You are a data scientist.", retries=1):
    """Wrapper mit API Key Parameter"""
    delay = 2 * (1 + random.random())
    time.sleep(delay)
    
    for i in range(retries):
        try:
            return ask_question(question, system=system, api_key=api_key)
        except Exception as e:
            delay = 2 * delay
            time.sleep(delay)
    return None

# Rest des Codes bleibt gleich bis zur Main-Logik...

st.title("Chat with your data")
uploaded_file = st.sidebar.file_uploader("Dataset hochladen", type="csv")

if uploaded_file:
    df = load_data(uploaded_file)
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
    with st.chat_message("assistant"):
        st.markdown("Bitte laden Sie zuerst ein Dataset hoch")
