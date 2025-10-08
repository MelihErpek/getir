from openai import OpenAI
import re
import pandas as pd
import altair as alt
import streamlit as st
from prompts import get_system_prompt  # prompts.py içinde bu fonksiyon TANIMLI olmalı

# =========================
# Basit Login (demo amaçlı)
# =========================
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
    st.stop()  # Giriş yapılmadıysa uygulamayı durdur

# =========================
# Başlık
# =========================
st.title("Getir - Talk To Your Competition Data")

# =========================
# OpenAI Client
# =========================
# Önce st.secrets, yoksa OpenAI default env değişkenini kullanır
client = OpenAI(api_key=st.secrets.get("OPENAI_API_KEY", None))

# =========================
# Yardımcı: Sayı & Tarih dönüştürme + Grafik UI
# =========================
def _coerce_numeric_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Türkçe sayı formatlarını (binlik nokta, ondalık virgül) numeric'e çevirir."""
    for c in df.columns:
        s = df[c]
        if pd.api.types.is_numeric_dtype(s):
            continue
        try:
            # string'e çevirip . (binlik) sil, , (ondalık) -> .
            s2 = s.astype(str).str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
            df[c] = pd.to_numeric(s2, errors="ignore")
        except Exception:
            pass
    return df

def _add_parsed_date(df: pd.DataFrame) -> pd.DataFrame:
    """TARIH kolonunu DD.MM.YYYY formatından datetime'a çevirip yardımcı kolon ekler."""
    if "TARIH" in df.columns:
        dt = pd.to_datetime(df["TARIH"], format="%d.%m.%Y", errors="coerce")
        df["_TARIH_DT"] = dt
    return df

def render_chart_ui(df: pd.DataFrame):
    """Sonuç DataFrame'i için otomatik bir line chart çizer (aylar doğru sırada)."""
    if df is None or df.empty:
        return

    df = df.copy()

    # Türkçe sayı formatlarını düzelt
    for c in df.columns:
        if pd.api.types.is_numeric_dtype(df[c]):
            continue
        try:
            s = df[c].astype(str).str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
            df[c] = pd.to_numeric(s, errors="ignore")
        except Exception:
            pass

    # Tarih kolonu varsa dönüştür
    if "TARIH" in df.columns:
        df["TARIH_DT"] = pd.to_datetime(df["TARIH"], format="%d.%m.%Y", errors="coerce")

    # 🔹 AY sıralamasını düzelt
    month_order = [
        "OCAK", "ŞUBAT", "MART", "NİSAN", "MAYIS", "HAZİRAN",
        "TEMMUZ", "AĞUSTOS", "EYLÜL", "EKİM", "KASIM", "ARALIK"
    ]
    if "AYISMI" in df.columns:
        df["AYISMI"] = df["AYISMI"].str.upper().str.strip()
        df["AYISMI"] = pd.Categorical(df["AYISMI"], categories=month_order, ordered=True)
        df = df.sort_values("AYISMI")

    # X ve Y eksenlerini belirle
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    time_or_category_cols = [c for c in df.columns if c in ["TARIH_DT", "TARIH", "AYISMI"] or df[c].dtype == "object"]

    if not numeric_cols or not time_or_category_cols:
        st.info("Grafik çizebilmek için uygun kolonlar bulunamadı.")
        return

    x_col = time_or_category_cols[0]
    y_cols = numeric_cols

    plot_df = df[[x_col] + y_cols].dropna()
    melted = plot_df.melt(id_vars=[x_col], value_vars=y_cols, var_name="Seri", value_name="Değer")

    x_type = "temporal" if "TARIH" in x_col or pd.api.types.is_datetime64_any_dtype(df[x_col]) else "nominal"

    chart = (
        alt.Chart(melted)
        .mark_line(point=True)
        .encode(
            x=alt.X(f"{x_col}:{'T' if x_type=='temporal' else 'N'}", title=x_col),
            y=alt.Y("Değer:Q", title=", ".join(y_cols)),
            color="Seri:N",
            tooltip=[x_col, "Seri", "Değer"],
        )
        .properties(height=360)
    )

    st.subheader("📈 Line Grafik")
    st.altair_chart(chart, use_container_width=True)



# =========================
# System Prompt (cache)
# =========================
if "system_prompt" not in st.session_state:
    st.session_state.system_prompt = get_system_prompt()

# =========================
# Mesaj State
# =========================
if "messages" not in st.session_state:
    # İlk mesaj SYSTEM rolünde (prompt)
    st.session_state.messages = [{"role": "system", "content": st.session_state.system_prompt}]

# =========================
# Kullanıcı Girişi
# =========================
if prompt := st.chat_input("Sorunu yaz..."):
    st.session_state.messages.append({"role": "user", "content": prompt})

# =========================
# Mevcut Sohbeti Göster (system hariç)
# =========================
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

# =========================
# Yanıt Üretme (asistan sırasıysa)
# =========================
if st.session_state.messages and st.session_state.messages[-1]["role"] != "assistant":
    with st.chat_message("assistant", avatar='UM_Logo_Heritage_Red.png'):
        with st.spinner("Model yanıt üretiyor..."):

            # API'ye gidecek temiz mesaj listesi (yalnız role + content)
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

            # SQL kod bloğunu yakala ve Snowflake'te çalıştır
            sql_match = re.search(r"```sql\s*(.+?)\s*```", response, re.DOTALL | re.IGNORECASE)
            if sql_match:
                sql = sql_match.group(1).strip()
                try:
                    conn = st.connection("snowflake")
                    df = conn.query(sql)
                    message["results"] = df
                    st.dataframe(df)

                    # Sonuçtan grafik çizdir
                    render_chart_ui(df)

                except Exception as e:
                    st.error(f"SQL çalıştırma hatası: {e}")

            # Mesajı hafızaya ekle
            st.session_state.messages.append(message)
