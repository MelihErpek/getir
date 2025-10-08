from openai import OpenAI
import re
import streamlit as st
from prompts import get_system_prompt  # prompts.py'de bu fonksiyonun TANIMLI olduğundan emin ol

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
# (st.secrets.OPENAI_API_KEY varsa OpenAI(api_key=...) çalışır; yoksa ortam değişkenini kullanır)
client = OpenAI(api_key=st.secrets.get("OPENAI_API_KEY", None))

# Cache the system prompt result to avoid repeated computation
if "system_prompt" not in st.session_state:
    st.session_state.system_prompt = get_system_prompt()

# Initialize messages if not already set in session state
if "messages" not in st.session_state:
    # ✅ İlk mesajı SYSTEM rolü olarak ekleyelim
    st.session_state.messages = [{"role": "system", "content": st.session_state.system_prompt}]

# Prompt for user input and save
if prompt := st.chat_input("Sorunu yaz..."):
    st.session_state.messages.append({"role": "user", "content": prompt})

# Display the existing chat messages (system mesajını göstermeyelim)
for message in st.session_state.messages:
    if message["role"] == "system":
        continue
    if message["role"] == "assistant":
        with st.chat_message("assistant", avatar='UM_Logo_Heritage_Red.png'):
            st.write(message["content"])
            if "results" in message:
                st.dataframe(message["results"])
    else:
        with st.chat_message("user"):
            st.write(message["content"])
            if "results" in message:
                st.dataframe(message["results"])

# If the last message is not from the assistant, generate a new response
if st.session_state.messages and st.session_state.messages[-1]["role"] != "assistant":
    with st.chat_message("assistant", avatar='UM_Logo_Heritage_Red.png'):
        with st.spinner("Model yanıt üretiyor..."):
            # OpenAI'den yanıt al
            result = client.chat.completions.create(
                model="gpt-4.1",
                messages=st.session_state.messages
            )
            response = result.choices[0].message.content or ""
            st.markdown(response)

            # Asistan mesaj nesnesini hazırla
            message = {"role": "assistant", "content": response, "avatar": 'UM_Logo_Heritage_Red.png'}

            # ✅ SQL kod bloğunu daha sağlam bir regex ile yakala
            # - ```sql ile başlasın
            # - İçerik üçlü backtick'e kadar NON-GREEDY alsın
            sql_match = re.search(r"```sql\s*(.+?)\s*```", response, re.DOTALL | re.IGNORECASE)

            if sql_match:
                sql = sql_match.group(1).strip()
                try:
                    conn = st.connection("snowflake")
                    df = conn.query(sql)
                    message["results"] = df
                    st.dataframe(df)
                except Exception as e:
                    st.error(f"SQL çalıştırma hatası: {e}")

            # Mesajı hafızaya ekle
            st.session_state.messages.append(message)
