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

# ============================================================
# Yardımcılar: sayı/tarih dönüştürme + tablo/grafik biçimleme
# ============================================================
def _coerce_numeric_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Türkçe sayı formatlarını (binlik nokta, ondalık virgül) numeric'e çevirir."""
    for c in df.columns:
        s = df[c]
        if pd.api.types.is_numeric_dtype(s):
            continue
        try:
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

# --------- YENİ: TR binlik biçimleyici + tablo için görünüm ----------
def format_thousands_tr(x, decimals=0):
    """10000 -> '10.000' ; 12345.67 -> '12.346' (decimals=0)"""
    if pd.isna(x):
        return ""
    fmt = f"{{:,.{decimals}f}}"
    s = fmt.format(float(x))
    # en-US → TR dönüşümü
    s = s.replace(",", "§").replace(".", ",").replace("§", ".")
    if decimals == 0:
        s = s.split(",")[0]
    return s

def dataframe_to_tr_strings(df: pd.DataFrame, decimals=0) -> pd.DataFrame:
    """Sayısal kolonları '10.000.000' metnine çevirir (sadece görüntü için)."""
    out = df.copy()
    for c in out.columns:
        if pd.api.types.is_numeric_dtype(out[c]):
            out[c] = out[c].apply(lambda v: format_thousands_tr(v, decimals))
    return out
# ---------------------------------------------------------------------

def render_line_chart(df: pd.DataFrame):
    """Varsa AYISMI+YIL+harcama kolonu ile 'her yıl bir line' grafiği; yoksa genel fallback."""
    if df is None or df.empty:
        return
    df = df.copy()

    # --- sayı parse (virgül/nokta)
    def smart_to_numeric(s: pd.Series) -> pd.Series:
        if pd.api.types.is_numeric_dtype(s):
            return s
        s = s.astype(str).str.strip()
        mask_both = s.str.contains(",", na=False) & s.str.contains(r"\.", regex=True, na=False)
        s.loc[mask_both] = s.loc[mask_both].str.replace(",", "", regex=False)
        mask_only_comma = s.str.contains(",", na=False) & ~s.str.contains(r"\.", regex=True, na=False)
        s.loc[mask_only_comma] = (
            s.loc[mask_only_comma]
            .str.replace(".", "", regex=False)
            .str.replace(",", ".", regex=False)
        )
        return pd.to_numeric(s, errors="ignore")

    for c in df.columns:
        try:
            df[c] = smart_to_numeric(df[c])
        except Exception:
            pass

    # --- hedef kolonları otomatik tespit
    if "AYISMI" not in df.columns:
        pass
    else:
        # değer (harcama) kolonu
        value_col = None
        pref = [c for c in df.columns if c.upper() == "TOPLAM_HARCAMA"]
        if pref:
            value_col = pref[0]
        else:
            cand = [
                c for c in df.columns
                if (("HARCAMA" in c.upper()) or ("TUTAR" in c.upper()) or ("TOPLAM" in c.upper()))
                and pd.api.types.is_numeric_dtype(df[c])
            ]
            if cand:
                value_col = cand[0]

        # yıl kolonu
        year_col = None
        if "YIL" in df.columns:
            year_col = "YIL"
        elif "YEAR" in df.columns:
            year_col = "YEAR"
        else:
            for c in df.columns:
                if pd.api.types.is_integer_dtype(df[c]) or pd.api.types.is_string_dtype(df[c]):
                    s = df[c].astype(str).str.fullmatch(r"\d{4}")
                    if s.notna().any() and s.sum() >= max(1, len(df) * 0.3):
                        year_col = c
                        break

        # Eğer üçü de varsa: otomatik çoklu yıl çizimi
        if value_col and year_col and "AYISMI" in df.columns:
            # ay sırası
            month_order_tr = ["OCAK","ŞUBAT","MART","NİSAN","MAYIS","HAZİRAN",
                              "TEMMUZ","AĞUSTOS","EYLÜL","EKİM","KASIM","ARALIK"]
            month_order_no_diac = ["OCAK","SUBAT","MART","NISAN","MAYIS","HAZIRAN",
                                   "TEMMUZ","AGUSTOS","EYLUL","EKIM","KASIM","ARALIK"]

            df["AYISMI"] = df["AYISMI"].astype(str).str.strip().str.upper()
            x_sort = month_order_tr if set(df["AYISMI"].unique()).issubset(set(month_order_tr)) else month_order_no_diac

            # yıl legend düzgün görünsün diye stringe çevir
            df[year_col] = df[year_col].astype(str)

            # --- YENİ: tooltip için biçimlenmiş metin
            df["_tooltip_val"] = df[value_col].apply(lambda v: format_thousands_tr(v, 0))

            chart = (
                alt.Chart(df)
                .mark_line(point=True)
                .encode(
                    x=alt.X("AYISMI:N", sort=x_sort, title="Ay"),
                    y=alt.Y(f"{value_col}:Q",
                            title=value_col.replace("_", " "),
                            axis=alt.Axis(labelExpr="replace(datum.label, ',', '.')")),
                    color=alt.Color(f"{year_col}:N", title="Yıl"),
                    tooltip=[year_col, "AYISMI", alt.Tooltip("_tooltip_val:N", title="Değer")]
                )
                .properties(height=360)
            )
            st.altair_chart(chart, use_container_width=True)
            return

    # --- burada değilse: genel fallback
    x_col, x_is_time, x_sort = None, False, None
    if "AYISMI" in df.columns:
        df["AYISMI"] = df["AYISMI"].astype(str).str.strip().str.upper()
        month_order_tr = ["OCAK","ŞUBAT","MART","NİSAN","MAYIS","HAZIRAN",
                          "TEMMUZ","AĞUSTOS","EYLÜL","EKİM","KASIM","ARALIK"]
        month_order_no_diac = ["OCAK","SUBAT","MART","NISAN","MAYIS","HAZIRAN",
                               "TEMMUZ","AGUSTOS","EYLUL","EKIM","KASIM","ARALIK"]
        x_sort = month_order_tr if set(df["AYISMI"].unique()).issubset(set(month_order_tr)) else month_order_no_diac
        x_col = "AYISMI"
    elif "TARIH" in df.columns:
        df["TARIH_DT"] = pd.to_datetime(df["TARIH"], format="%d.%m.%Y", errors="coerce")
        x_col, x_is_time = "TARIH_DT", True
    else:
        obj_cols = [c for c in df.columns if df[c].dtype == "object"]
        if not obj_cols:
            return
        x_col = obj_cols[0]

    # yıl benzeri kolonları Y eksenine dahil etme
    def is_year_like(col):
        if col.upper() in ("YIL","YEAR"):
            return True
        if pd.api.types.is_integer_dtype(df[col]) or pd.api.types.is_string_dtype(df[col]):
            s = df[col].astype(str).str.fullmatch(r"\d{4}")
            return s.notna().any() and s.sum() >= max(1, len(df) * 0.3)
        return False

    y_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and not is_year_like(c)]
    if not y_cols:
        return

    melted = df[[x_col] + y_cols].dropna().melt(
        id_vars=[x_col], value_vars=y_cols, var_name="Seri", value_name="Değer"
    )
    # --- YENİ: tooltip için biçimlenmiş değer sütunu
    melted["Değer_fmt"] = melted["Değer"].apply(lambda v: format_thousands_tr(v, 0))

    x_enc = alt.X(f"{x_col}:{'T' if x_is_time else 'N'}",
                  title=x_col, sort=x_sort if x_sort else None)

    chart = (
        alt.Chart(melted).mark_line(point=True)
        .encode(
            x=x_enc,
            y=alt.Y("Değer:Q",
                    axis=alt.Axis(labelExpr="replace(datum.label, ',', '.')")),
            color=alt.Color("Seri:N", title="Seri"),
            tooltip=[x_col, "Seri", alt.Tooltip("Değer_fmt:N", title="Değer")]
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

                    # --- AYISMI'na göre takvim sırası (tablo/grafik için)
                    month_order = ["OCAK","ŞUBAT","MART","NİSAN","MAYIS","HAZIRAN",
                                   "TEMMUZ","AĞUSTOS","EYLÜL","EKİM","KASIM","ARALIK"]
                    if "AYISMI" in df.columns:
                        df["AYISMI"] = df["AYISMI"].astype(str).str.strip().str.upper()
                        df["AYISMI"] = pd.Categorical(df["AYISMI"], categories=month_order, ordered=True)
                        sort_cols = ["YIL","AYISMI"] if "YIL" in df.columns else ["AYISMI"]
                        df = df.sort_values(sort_cols)

                    # ---- TABLO: noktalı gösterim için ayrı display DF
                    df_display = dataframe_to_tr_strings(df, decimals=0)
                    message["results"] = df_display
                    st.dataframe(df_display)

                    # ---- GRAFİK: orijinal sayısal DF ile çiz
                    render_line_chart(df)

                except Exception as e:
                    st.error(f"SQL çalıştırma hatası: {e}")

            # Mesajı hafızaya ekle
            st.session_state.messages.append(message)
