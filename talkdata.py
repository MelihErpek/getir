from openai import OpenAI
import re
import streamlit as st
from prompts import get_system_prompt

# Kullanıcı giriş bilgileri (demo amaçlı)
VALID_USERNAME = "admin"
VALID_PASSWORD = "1234"

def login_screen():
    st.title("Giriş Ekranı")
    username = st.text_input("Kullanıcı Adı")
    password = st.text_input("Şifre", type="password")
    login_button = st.button("Giriş Yap")

    if login_button:
        if username == VALID_USERNAME and password == VALID_PASSWORD:
            st.session_state.authenticated = True
            st.success("Giriş başarılı!")
            st.experimental_rerun()
        else:
            st.error("Kullanıcı adı veya şifre hatalı.")

# Oturum doğrulama kontrolü
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    login_screen()
    st.stop()  # Giriş yapılmadıysa uygulamanın devamını durdur


st.title("Getir - Talk To Your Competition Data")

# Initialize the OpenAI client
client = OpenAI(api_key=st.secrets.OPENAI_API_KEY)

# Cache the system prompt result to avoid repeated computation
if "system_prompt" not in st.session_state:
    st.session_state.system_prompt = get_system_prompt()

# Initialize messages if not already set in session state
if "messages" not in st.session_state:
    # Initialize with a single user message containing the system prompt
    st.session_state.messages = [{"role": "user", "content": st.session_state.system_prompt}]

# Prompt for user input and save
if prompt := st.chat_input():
    st.session_state.messages.append({"role": "user", "content": prompt})

# Display the existing chat messages, skipping the initial system prompt
for i, message in enumerate(st.session_state.messages):
    if i == 0 and message["content"] == st.session_state.system_prompt:
        continue  # Skip the initial message with the system prompt content
    
    if message["role"] == "assistant":
        with st.chat_message(message["role"], avatar='UM_Logo_Heritage_Red.png'):
            st.write(message["content"])
            if "results" in message:
                st.dataframe(message["results"])
    else:
        with st.chat_message(message["role"]):
            st.write(message["content"])
            if "results" in message:
                st.dataframe(message["results"])

# If the last message is not from the assistant, generate a new response
if st.session_state.messages[-1]["role"] != "assistant":
    with st.chat_message("assistant", avatar='UM_Logo_Heritage_Red.png'):
        # Display a loading spinner while waiting for the response
        with st.spinner("Getir gpt-4.1 model is typing..."):
            response = ""

            # Fetch the response from OpenAI's API (without streaming)
            result = client.chat.completions.create(
                model="gpt-4.1",
                messages=[{"role": m["role"], "content": m["content"]} for m in st.session_state.messages]
            )

            # Extract the content from the response
            response = result.choices[0].message.content
            st.markdown(response)

            # Prepare the assistant message object
            message = {"role": "assistant", "content": response, "avatar": 'UM_Logo_Heritage_Red.png'}

            # Parse the response for a SQL query and execute if available
            sql_match = re.search(r"```sql\n(.*)\n```", response, re.DOTALL)
            if sql_match:
                sql = sql_match.group(1)
                conn = st.connection("snowflake")
                message["results"] = conn.query(sql)
                st.dataframe(message["results"])

            # Append the new assistant message to the session state
            st.session_state.messages.append(message)
