from openai import OpenAI
import re
import streamlit as st
from prompts import get_system_prompt

# Demo login bilgileri
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

# Oturum doğrulama
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    login_screen()
    st.stop()

st.title("Getir - Talk To Your Competition Data")

# OpenAI client (önce secrets, yoksa env)
client = OpenAI(api_key=st.secrets.get("OPENAI_API_KEY", None))

# System prompt'u cache et
if "system_prompt" not in st.session_state:
    st.session_state.system_prompt = get_system_prompt()

# Mesajları başlat
if "messages" not in st.session_state:
    # İlk mesaj SYSTEM rolünde olsun
    st.session_state.messages = [{"role": "system", "content": st.session_state.system_prompt}]

# Kullanıcı girişi
if prompt := st.chat_input("Sorunu yaz..."):
    st.session_state.messages.append({"role": "user", "content": prompt})

# Sohbeti göster (system mesajını gizle)
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

# Asistan sırası ise yanıt üret
if st.session_state.messages and st.session_state.messages[-1]["role"] != "assistant":
    with st.chat_message("assistant", avatar='UM_Logo_Heritage_Red.png'):
        with st.spinner("Model yanıt üretiyor..."):

            # ✅ API'ye gidecek temiz mesaj listesi (yalnız role+content)
            api_messages = []
            for m in st.session_state.messages:
                role = m.get("role")
                content = m.get("content")
                if role in ("system", "user", "assistant"):
                    if isinstance(content, str):
                        api_messages.append({"role": role, "content": content})
                    elif content is not None:
                        api_messages.append({"role": role, "content": str(content)})

            # OpenAI çağrısı
            result = client.chat.completions.create(
                model="gpt-4.1",
                messages=api_messages
            )

            response = result.choices[0].message.content or ""
            st.markdown(response)

            # Asistan mesajını state'e eklemek için hazırla
            message = {"role": "assistant", "content": response, "avatar": 'UM_Logo_Heritage_Red.png'}

            # ✅ SQL kod bloğunu yakala ve Snowflake'te çalıştır
            # - ```sql ile başlasın, kapanana kadar NON-GREEDY alsın
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
