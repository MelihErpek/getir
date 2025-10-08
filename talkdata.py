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

def render_line_chart(df: pd.DataFrame):
    """Sonuç DataFrame'i için otomatik bir line chart çizer (aylar doğru sırada, sayılar doğru parse)."""
    if df is None or df.empty:
        return

    df = df.copy()

    # --- Sayı parse: '72,286,612.7266' -> en-US; '2.603,43' -> eu
    def smart_to_numeric(s: pd.Series) -> pd.Series:
        if pd.api.types.is_numeric_dtype(s):
            return s
        s = s.astype(str).str.strip()

        # iki işaret birden varsa (virgül + nokta)
        mask_both = s.str.contains(",", na=False) & s.str.contains(r"\.", regex=True, na=False)
        # en-US: 12,345,678.90 -> virgülleri sil, nokta kalsın
        s.loc[mask_both] = s.loc[mask_both].str.replace(",", "", regex=False)

        # sadece virgül varsa -> 12.345,67 veya 123,45 (ondalık virgül)
        mask_only_comma = s.str.contains(",", na=False) & ~s.str.contains(r"\.", regex=True, na=False)
        s.loc[mask_only_comma] = (
            s.loc[mask_only_comma]
            .str.replace(".", "", regex=False)  # varsa binlik nokta
            .str.replace(",", ".", regex=False)  # ondalık virgül -> nokta
        )

        # sadece nokta varsa: zaten en-US ondalık, dokunma
        # diğer durumlar numeric değilse NaN kalır
        return pd.to_numeric(s, errors="ignore")

    for c in df.columns:
        try:
            df[c] = smart_to_numeric(df[c])
        except Exception:
            pass

    # --- Tarih parse (varsa)
    if "TARIH" in df.columns:
        df["TARIH_DT"] = pd.to_datetime(df["TARIH"], format="%d.%m.%Y", errors="coerce")

    # --- Ay sıralaması
    month_order_tr = [
        "OCAK", "ŞUBAT", "MART", "NİSAN", "MAYIS", "HAZİRAN",
        "TEMMUZ", "AĞUSTOS", "EYLÜL", "EKİM", "KASIM", "ARALIK"
    ]
    # aksansız varyant da olabiliyor (OZEL -> OZEL)
    month_order_no_diac = [
        "OCAK", "SUBAT", "MART", "NISAN", "MAYIS", "HAZIRAN",
        "TEMMUZ", "AGUSTOS", "EYLUL", "EKIM", "KASIM", "ARALIK"
    ]

    # X ekseni seçimi: AYISMI varsa onu kullan; yoksa TARIH_DT; yoksa ilk object kolon
    if "AYISMI" in df.columns:
        df["AYISMI"] = df["AYISMI"].astype(str).str.strip().str.upper()
        # iki farklı kategori listesi dene
        if set(df["AYISMI"].unique()).issubset(set(month_order_tr)):
            cat = pd.Categorical(df["AYISMI"], categories=month_order_tr, ordered=True)
            df["AYISMI"] = cat
            df = df.sort_values("AYISMI")
            x_col = "AYISMI"
            x_is_time = False
            x_sort = month_order_tr  # Altair için açık sort
        else:
            cat = pd.Categorical(df["AYISMI"], categories=month_order_no_diac, ordered=True)
            df["AYISMI"] = cat
            df = df.sort_values("AYISMI")
            x_col = "AYISMI"
            x_is_time = False
            x_sort = month_order_no_diac
    elif "TARIH_DT" in df.columns:
        x_col = "TARIH_DT"
        x_is_time = True
        x_sort = None
        df = df.sort_values(x_col)
    else:
        # fallback: ilk object kolon
        obj_cols = [c for c in df.columns if df[c].dtype == "object"]
        if not obj_cols:
            st.info("Grafik çizebilmek için uygun X ekseni bulunamadı.")
            return
        x_col = obj_cols[0]
        x_is_time = False
        x_sort = None

    # Y ekseni: tüm sayısal sütunlar (mantıklı olanları bırakmak istersen burada filtreleyebilirsin)
    y_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    if not y_cols:
        st.info("Grafik çizebilmek için sayısal kolon bulunamadı.")
        return

    plot_df = df[[x_col] + y_cols].dropna()
    if plot_df.empty:
        st.info("Seçilen alanlarda grafik oluşturmak için yeterli veri yok.")
        return

    melted = plot_df.melt(id_vars=[x_col], value_vars=y_cols, var_name="Seri", value_name="Değer")

    x_enc = alt.X(
        f"{x_col}:{'T' if x_is_time else 'N'}",
        title=x_col,
        sort=x_sort if x_sort else None  # 🔑 Ay sırası burada dayatılıyor
    )

    chart = (
        alt.Chart(melted)
        .mark_line(point=True)
        .encode(
            x=x_enc,
            y=alt.Y("Değer:Q", title=", ".join(y_cols)),
            color=alt.Color("Seri:N", legend=alt.Legend(title="Seri")),
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
