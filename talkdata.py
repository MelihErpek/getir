# app.py
from openai import OpenAI
import re
import pandas as pd
import altair as alt
import streamlit as st
from prompts import get_system_prompt  # prompts.py içinde tanımlı olmalı

# =========================
# Altair/Vega: Türkçe sayı & tarih yereli
# =========================
alt.renderers.set_embed_options(
    formatLocale={
        "decimal": ",",
        "thousands": ".",
        "grouping": [3],
        "currency": ["", " ₺"],   # D3'te format="$,.0f" yazınca bu kullanılır
    },
    timeFormatLocale={
        "dateTime": "%A, %e %B %Y %X",
        "date": "%d.%m.%Y",
        "time": "%H:%M:%S",
        "periods": ["ÖÖ", "ÖS"],
        "days": ["Pazar","Pazartesi","Salı","Çarşamba","Perşembe","Cuma","Cumartesi"],
        "shortDays": ["Paz","Pts","Sal","Çar","Per","Cum","Cts"],
        "months": ["Ocak","Şubat","Mart","Nisan","Mayıs","Haziran","Temmuz","Ağustos","Eylül","Ekim","Kasım","Aralık"],
        "shortMonths": ["Oca","Şub","Mar","Nis","May","Haz","Tem","Ağu","Eyl","Eki","Kas","Ara"],
    },
)

# =========================
# Basit Login (demo)
# =========================
# VALID_USERNAME = "admin"
# VALID_PASSWORD = "1234"

# def login_screen():
#     st.title("Giriş Ekranı")
#     username = st.text_input("Kullanıcı Adı")
#     password = st.text_input("Şifre", type="password")
#     if st.button("Giriş Yap"):
#         if username == VALID_USERNAME and password == VALID_PASSWORD:
#             st.session_state.authenticated = True
#             st.success("Giriş başarılı!")
#             st.experimental_rerun()
#         else:
#             st.error("Kullanıcı adı veya şifre hatalı.")

# if "authenticated" not in st.session_state:
#     st.session_state.authenticated = False
# if not st.session_state.authenticated:
#     login_screen()
#     st.stop()

# =========================
# Başlık
# =========================
st.title("Getir - Talk To Your Competition Data")

# =========================
# OpenAI Client
# =========================
client = OpenAI(api_key=st.secrets.get("OPENAI_API_KEY", None))

# =========================
# Yardımcılar
# =========================
MONTH_ORDER = ["OCAK","ŞUBAT","MART","NİSAN","MAYIS","HAZİRAN",
               "TEMMUZ","AĞUSTOS","EYLÜL","EKİM","KASIM","ARALIK"]
MONTH_ORDER_IDX = {m:i for i,m in enumerate(MONTH_ORDER, start=1)}

def smart_to_numeric(s: pd.Series) -> pd.Series:
    """TR sayılarını (1.234,56) -> 1234.56 çevirir; değilse dokunmaz."""
    if pd.api.types.is_numeric_dtype(s):
        return s
    s = s.astype(str).str.strip()
    mask_both = s.str.contains(",", na=False) & s.str.contains(r"\.", regex=True, na=False)
    s.loc[mask_both] = s.loc[mask_both].str.replace(".", "", regex=False)
    mask_only_comma = s.str.contains(",", na=False) & ~s.str.contains(r"\.", regex=True, na=False)
    s.loc[mask_only_comma] = s.loc[mask_only_comma].str.replace(",", ".", regex=False)
    return pd.to_numeric(s, errors="ignore")

def to_datetime_tr(s: pd.Series) -> pd.Series:
    """'01.11.2024', '1/11/2024', datetime gibi değerleri güvenle datetime'a çevirir."""
    if pd.api.types.is_datetime64_any_dtype(s):
        return s
    s = s.astype(str).str.strip()
    dt = pd.to_datetime(s, dayfirst=True, errors="coerce")
    return dt

# ---------- Ay normalizasyonu: aksan/nokta duyarsız ----------
def tr_key(x: str) -> str:
    """Türkçe ay metnini aksan/nokta duyarsız anahtara çevirir."""
    x = str(x or "").strip().upper()
    # Türkçe özel harfleri ASCII benzerine indir
    x = (x.replace("İ", "I")
           .replace("I", "I")
           .replace("ı", "I")
           .replace("i", "I")
           .replace("Ö", "O").replace("Ü", "U")
           .replace("Ş", "S").replace("Ğ", "G")
           .replace("Ç", "C"))
    x = re.sub(r"\s+", "", x)
    return x

CANON_BY_KEY = {tr_key(m): m for m in MONTH_ORDER}

def normalize_months(df: pd.DataFrame, month_col: str = "AYISMI") -> pd.DataFrame:
    """AYISMI'nı kanonik ay adına çevirir, geçersizleri atar, sıralama için _AY_ORDER ekler."""
    if month_col not in df.columns:
        return df
    df = df[df[month_col].notna()].copy()

    keys = df[month_col].apply(tr_key)
    canon = keys.map(CANON_BY_KEY)

    df = df[canon.notna()].copy()
    if df.empty:
        return df

    df[month_col] = canon.values
    df["_AY_ORDER"] = df[month_col].map(MONTH_ORDER_IDX)
    return df
# -------------------------------------------------------------

def pick_year_col(df: pd.DataFrame) -> str | None:
    """YIL/YEAR veya 4 haneli yıl benzeri bir kolonu seç."""
    if "YIL" in df.columns: return "YIL"
    if "YEAR" in df.columns: return "YEAR"
    for c in df.columns:
        if pd.api.types.is_numeric_dtype(df[c]) or pd.api.types.is_string_dtype(df[c]):
            s = df[c].astype(str)
            if (s.str.fullmatch(r"\d{4}", na=False)).sum() >= max(1, len(df) * 0.3):
                return c
    return None

def render_monthly_lines(df: pd.DataFrame, month_col: str = "AYISMI"):
    """Genel çizim: AYISMI + (opsiyonel) YIL + tüm sayısal metrikler (aynı yıl+ay toplanır)."""
    if df is None or df.empty:
        return

    df = df.copy()
    for c in df.columns:
        try: df[c] = smart_to_numeric(df[c])
        except Exception: pass

    if month_col not in df.columns:
        st.warning(f"Grafik için '{month_col}' kolonu yok.")
        return
    df = normalize_months(df, month_col)
    if df.empty:
        st.warning("Geçerli ay satırı kalmadı.")
        return

    year_col = pick_year_col(df)
    if year_col:
        df[year_col] = df[year_col].astype(str)

    def is_year_like(col: str) -> bool:
        if col.upper() in ("YIL","YEAR"): return True
        s = df[col].astype(str)
        return (s.str.fullmatch(r"\d{4}", na=False)).sum() >= max(1, len(df) * 0.3)

    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    metric_cols = [c for c in numeric_cols if c not in (year_col, "_AY_ORDER") and not is_year_like(c)]
    if not metric_cols:
        st.warning("Çizilecek sayısal metrik bulunamadı.")
        return

    group_keys = [month_col] + ([year_col] if year_col else [])
    agg = df[group_keys + metric_cols].groupby(group_keys, as_index=False).sum(numeric_only=True)

    long_df = agg.melt(id_vars=group_keys, value_vars=metric_cols,
                       var_name="Metric", value_name="Değer")

    if year_col:
        long_df["Seri"] = long_df["Metric"].astype(str) + " - " + long_df[year_col].astype(str)
    else:
        long_df["Seri"] = long_df["Metric"].astype(str)

    long_df["_AY_ORDER"] = long_df[month_col].map(MONTH_ORDER_IDX)
    long_df = long_df.sort_values(["Seri","_AY_ORDER"])

    is_integer_vals = (long_df["Değer"].dropna() % 1 == 0).all()
    money_keywords = ["HARCAMA", "CİRO", "CIRO", "HASILAT", "REVENUE", "SATIŞ", "SATIS", "TUTAR"]
    is_money = any(any(k in m.upper() for k in money_keywords) for m in metric_cols)
    if is_money:
        fmt = "$,.0f" if is_integer_vals else "$,.2f"
        y_title = "Tutar (₺)"
    else:
        fmt = ",.0f" if is_integer_vals else ",.2f"
        y_title = "Değer"

    x_enc = alt.X(f"{month_col}:N", title="Ay", scale=alt.Scale(domain=MONTH_ORDER))
    chart = (
        alt.Chart(long_df)
        .mark_line(point=True, interpolate="linear")
        .encode(
            x=x_enc,
            y=alt.Y("Değer:Q", title=y_title, axis=alt.Axis(format=fmt)),
            color=alt.Color("Seri:N", title="Seri"),
            detail="Seri:N",
            order=alt.Order("_AY_ORDER:Q"),
            tooltip=[month_col, "Seri", alt.Tooltip("Değer:Q", title=y_title, format=fmt)],
        )
        .properties(height=360)
    )
    st.altair_chart(chart, use_container_width=True)

def render_date_lines(df: pd.DataFrame, date_col: str = "TARIH"):
    """Tarih bazlı (günlük/haftalık) tüm sayısal metrikleri çizer."""
    if df is None or df.empty:
        return

    df = df.copy()
    for c in df.columns:
        try: df[c] = smart_to_numeric(df[c])
        except Exception: pass

    if date_col not in df.columns:
        if "TARİH" in df.columns:
            date_col = "TARİH"
        else:
            st.warning(f"Grafik için '{date_col}' kolonu yok.")
            return

    df[date_col] = to_datetime_tr(df[date_col])
    df = df[df[date_col].notna()].copy()
    if df.empty:
        st.warning("Geçerli tarih satırı kalmadı.")
        return

    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    metric_cols = [c for c in numeric_cols if c not in (date_col,)]
    if not metric_cols:
        st.warning("Çizilecek sayısal metrik bulunamadı.")
        return

    agg = df[[date_col] + metric_cols].groupby(date_col, as_index=False).sum(numeric_only=True)

    long_df = agg.melt(id_vars=[date_col], value_vars=metric_cols, var_name="Metric", value_name="Değer")

    is_integer_vals = (long_df["Değer"].dropna() % 1 == 0).all()
    money_keywords = ["HARCAMA", "CİRO", "CIRO", "HASILAT", "REVENUE", "SATIŞ", "SATIS", "TUTAR", "BÜTÇE", "BUTCE"]
    is_money = any(any(k in m.upper() for k in money_keywords) for m in metric_cols)
    if is_money:
        fmt = "$,.0f" if is_integer_vals else "$,.2f"
        y_title = "Tutar (₺)"
    else:
        fmt = ",.0f" if is_integer_vals else ",.2f"
        y_title = "Değer"

    chart = (
        alt.Chart(long_df.sort_values(date_col))
        .mark_line(point=True)
        .encode(
            x=alt.X(f"{date_col}:T", title="Tarih"),
            y=alt.Y("Değer:Q", title=y_title, axis=alt.Axis(format=fmt)),
            color=alt.Color("Metric:N", title="Metrik"),
            tooltip=[alt.Tooltip(f"{date_col}:T", title="Tarih"), "Metric", alt.Tooltip("Değer:Q", title=y_title, format=fmt)],
        )
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
    st.session_state.messages = [{"role": "system", "content": st.session_state.system_prompt}]

# =========================
# Kullanıcı girişi
# =========================
if prompt := st.chat_input("Sorunu yaz..."):
    st.session_state.messages.append({"role": "user", "content": prompt})

# =========================
# Mevcut sohbeti göster
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
# Yanıt üretme + SQL varsa çalıştırma
# =========================
if st.session_state.messages and st.session_state.messages[-1]["role"] != "assistant":
    with st.chat_message("assistant", avatar='UM_Logo_Heritage_Red.png'):
        with st.spinner("Model yanıt üretiyor..."):
            api_messages = []
            for m in st.session_state.messages:
                role = m.get("role")
                content = m.get("content")
                if role in ("system", "user", "assistant"):
                    api_messages.append({"role": role, "content": str(content or "")})

            result = client.chat.completions.create(
                model="gpt-5",
                messages=api_messages
            )
            response = result.choices[0].message.content or ""
            st.markdown(response)

            message = {"role": "assistant", "content": response, "avatar": 'UM_Logo_Heritage_Red.png'}

            sql_match = re.search(r"```sql\s*(.+?)\s*```", response, re.DOTALL | re.IGNORECASE)
            if sql_match:
                sql = sql_match.group(1).strip()
                try:
                    conn = st.connection("snowflake")
                    df = conn.query(sql)

                    # Tabloyu ay veya tarih sütununa göre sırala
                    date_col = None
                    if "AYISMI" in df.columns:
                        df = normalize_months(df, "AYISMI")
                        sort_cols = (["YIL", "_AY_ORDER"] if "YIL" in df.columns else ["_AY_ORDER"])
                        df = df.sort_values(sort_cols).drop(columns=["_AY_ORDER"])
                    elif "TARIH" in df.columns or "TARİH" in df.columns:
                        date_col = "TARIH" if "TARIH" in df.columns else "TARİH"
                        df[date_col] = to_datetime_tr(df[date_col])
                        df = df.sort_values(date_col)
                        try:
                            df[date_col] = df[date_col].dt.strftime("%d.%m.%Y")
                        except Exception:
                            pass

                    message["results"] = df
                    st.dataframe(df)

                    # Grafik: varsa tarih bazlı, yoksa aylık
                    if date_col:
                        render_date_lines(df.copy(), date_col=date_col)
                    else:
                        render_monthly_lines(df.copy(), month_col="AYISMI")

                except Exception as e:
                    st.error(f"SQL çalıştırma hatası: {e}")

            st.session_state.messages.append(message)
