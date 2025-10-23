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
    if df is None or df.empty:
        return
    df = df.copy()

    # --- emniyet: başlangıç tanımları
    value_col, year_col = None, None

    # --- değer kolonunu otomatik bul (örnek: TOPLAM_GRP öncelik) ---
    preferred = [c for c in df.columns if c.upper() in ("TOPLAM_GRP","TOPLAM_HARCAMA")]
    if preferred:
        value_col = preferred[0]
    else:
        cand = [c for c in df.columns
                if pd.api.types.is_numeric_dtype(df[c])
                and any(k in c.upper() for k in ["TOPLAM","HARCAMA","TUTAR","GRP"])]
        if cand: value_col = cand[0]

    # --- AY normalizasyonu ---
    month_order = ["OCAK","ŞUBAT","MART","NİSAN","MAYIS","HAZİRAN",
                   "TEMMUZ","AĞUSTOS","EYLÜL","EKİM","KASIM","ARALIK"]
    if "AYISMI" in df.columns:
        df = df[df["AYISMI"].notna()].copy()
        df["AYISMI"] = df["AYISMI"].astype(str).str.strip().str.upper()
        df = df[df["AYISMI"].isin(month_order)].copy()

    # --- YIL kolonu var mı? (çoklu yıl senaryosu için) ---
    if "YIL" in df.columns: year_col = "YIL"
    elif "YEAR" in df.columns: year_col = "YEAR"

    # =========================
    # 1) Çoklu yıl varsa
    # =========================
    if value_col and year_col and "AYISMI" in df.columns:
        order_map = {m:i for i,m in enumerate(month_order, start=1)}
        df[year_col] = df[year_col].astype(str)
        # aynı yıl+ay birden fazla ise topla
        grp = (df.groupby([year_col,"AYISMI"], as_index=False)[value_col].sum())
        grp["_AY_ORDER"] = grp["AYISMI"].map(order_map)

        chart = (
            alt.Chart(grp)
            .mark_line(point=True, interpolate="monotone")
            .encode(
                x=alt.X("AYISMI:N", title="Ay", scale=alt.Scale(domain=month_order)),
                y=alt.Y(f"{value_col}:Q", title=value_col.replace("_"," ")),
                color=alt.Color(f"{year_col}:N", title="Yıl"),
                order=alt.Order("_AY_ORDER:Q"),
                tooltip=[year_col, "AYISMI", value_col]
            )
            .properties(height=360)
        )
        st.altair_chart(chart, use_container_width=True)
        return

    # =========================
    # 2) Tek seri (yıl yok) – sizin durumunuz
    # =========================
    if value_col and "AYISMI" in df.columns:
        order_map = {m:i for i,m in enumerate(month_order, start=1)}
        # Aynı ay birden çok satırsa topla (isterseniz mean de yapabilirsiniz)
        agg = df.groupby("AYISMI", as_index=False)[value_col].sum()
        agg["_AY_ORDER"] = agg["AYISMI"].map(order_map)
        agg = agg.sort_values("_AY_ORDER")

        chart = (
            alt.Chart(agg)
            .mark_line(point=True, interpolate="monotone")
            .encode(
                x=alt.X("AYISMI:N", title="Ay", scale=alt.Scale(domain=month_order)),
                y=alt.Y(f"{value_col}:Q", title=value_col.replace("_"," ")),
                order=alt.Order("_AY_ORDER:Q"),
                tooltip=["AYISMI", value_col]
            )
            .properties(height=360)
        )
        st.altair_chart(chart, use_container_width=True)
        return

    # Diğer fallback'ler (TARIH vb.) burada kalabilir…


    # --- Fallback çizimi ---
    if "AYISMI" in df.columns:
        x_enc = alt.X(
            "AYISMI:N",
            title="AYISMI",
            scale=alt.Scale(domain=month_order_tr)  # yine domain ile sabit sıra
        )
    elif "TARIH" in df.columns:
        df["TARIH_DT"] = pd.to_datetime(df["TARIH"], format="%d.%m.%Y", errors="coerce")
        x_enc = alt.X("TARIH_DT:T", title="TARIH")
    else:
        obj_cols = [c for c in df.columns if df[c].dtype == "object"]
        if not obj_cols:
            return
        x_enc = alt.X(f"{obj_cols[0]}:N", title=obj_cols[0])

    # yıl benzeri kolonları hariç tutup eritme vs. aynen:
    y_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and c not in ("YIL","YEAR")]
    if not y_cols:
        return

    melted = df[["AYISMI"] + y_cols].melt(id_vars=["AYISMI"], var_name="Seri", value_name="Değer")
    chart = (
        alt.Chart(melted)
        .mark_line(point=True)
        .encode(x=x_enc, y=alt.Y("Değer:Q"), color=alt.Color("Seri:N", title="Seri"),
                tooltip=["AYISMI", "Seri", "Değer"])
        .properties(height=360)
    )
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
                
                    # --- AYISMI'na göre takvim sırası (tablo için) ---
                    month_order = ["OCAK","ŞUBAT","MART","NİSAN","MAYIS","HAZİRAN",
                                   "TEMMUZ","AĞUSTOS","EYLÜL","EKİM","KASIM","ARALIK"]
                
                    if "AYISMI" in df.columns:
                        df["AYISMI"] = df["AYISMI"].astype(str).str.strip().str.upper()
                        df["AYISMI"] = pd.Categorical(df["AYISMI"], categories=month_order, ordered=True)
                        sort_cols = ["YIL","AYISMI"] if "YIL" in df.columns else ["AYISMI"]
                        df = df.sort_values(sort_cols)
                
                    message["results"] = df
                    st.dataframe(df)
                
                    # grafik tarafı zaten ay sırasını doğru çiziyor
                    render_line_chart(df)
                
                except Exception as e:
                    st.error(f"SQL çalıştırma hatası: {e}")


            # Mesajı hafızaya ekle
            st.session_state.messages.append(message)
