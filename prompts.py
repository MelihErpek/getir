import streamlit as st

SCHEMA_PATH = st.secrets.get("SCHEMA_PATH", "GETIR_2023_REVISED.PUBLIC")

# 🔹 Aynı anda tanıtmak istediğin tabloları buraya ekle
TARGET_TABLES = [
    f"{SCHEMA_PATH}.GETIR2023REKABET",
    f"{SCHEMA_PATH}.GETIR2024REKABET",
]

TABLE_DESCRIPTION = """
This table has various metrics for customers.
"""

METADATA_QUERY = f""  # İstersen tabloya özel metadata mantığını ayrıca ekleyebilirsin

GEN_SQL = """" 
You will be acting as an AI Snowflake SQL Expert named Getir Chatbot.
Your goal is to give correct, executable sql query to users.
You are given multiple tables. Each table is described in separate <table> blocks with <tableName> and <columns>.
For each user question, FIRST decide which single table is appropriate and then generate ONE Snowflake SQL query using ONLY that chosen table.

{context}

Here are the critical rules:
<rules>
1. You MUST wrap the generated sql code within ```sql ... ``` fences (single code block).
2. If the user doesn't state a limit, you MUST add LIMIT 10.
3. Text/string filters MUST use ILIKE '%keyword%'.
4. Generate a single Snowflake SQL query (not multiple).
5. You MUST ONLY use the table names and columns provided in the <table> blocks. Do NOT invent tables/columns.
6. DO NOT start identifiers with numerics.
7. Tarih filtrelemen gerektiğinde TARIH sütunundaki bilgi Gün.Ay.Yıl (DD.MM.YYYY). Örn: 23.08.2023 → 23 Ağustos 2023.
8. Soruda "getir" geçerse data içinde "GETİR" olarak yazılmış olabilir; accordingly search upper/diacritics-insensitive with ILIKE.
9. GRP istendiğinde datadaki GRP sütununu kullan. Aksi belirtilmezse SUM al; ortalama denirse AVG al.
   Ör: SELECT SUM(TRY_CAST(REPLACE(GRP, ',', '.') AS FLOAT)) AS toplam_grp
       FROM GETIR_2023_REVISED.PUBLIC.GETIR2023REKABET;
10. Getir Yemek → veride "GETİRYEMEK".
11. Marka ararken MARKA sütunu.
12. Marka eşlemeleri:
    yemeksepeti -> YEMEKSEPETI.COM
    yemeksepeti market -> YEMEKSEPETI MARKET
    yemeksepeti mahalle -> YEMEKSEPETI MAHALLE
    trendyol yemek -> TRENDYOL YEMEK
    trendyol -> TRENDYOL.COM
13. Bütçe / yatırım istenirse NETTUTAR kullan; outdoor/ölçülen tv/radyo/sinema/basın gibi filtreler MECRA üzerinden yapılır.
</rules>

Always include exactly one SQL query block in your response.
"""

@st.cache_data(show_spinner="Loading table context...")
def get_table_context(table_name: str, table_description: str, metadata_query: str = None):
    table = table_name.split(".")
    conn = st.connection("snowflake")
    cols = conn.query(f"""
        SELECT COLUMN_NAME, DATA_TYPE
        FROM {table[0].upper()}.INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = '{table[1].upper()}'
          AND TABLE_NAME   = '{table[2].upper()}'
        ORDER BY ORDINAL_POSITION
        """, show_spinner=False,
    )
    columns_fmt = "\n".join(
        [f"- **{cols['COLUMN_NAME'][i]}**: {cols['DATA_TYPE'][i]}" for i in range(len(cols))]
    )
    ctx = f"""
<table>
Here is the table name <tableName> {'.'.join(table)} </tableName>

<tableDescription>{table_description}</tableDescription>

Here are the columns of {'.'.join(table)}:
<columns>
{columns_fmt}
</columns>
</table>
"""
    if metadata_query:
        md = conn.query(metadata_query, show_spinner=False)
        if len(md) > 0:
            md_fmt = "\n".join(
                [f"- **{md['VARIABLE_NAME'][i]}**: {md['DEFINITION'][i]}" for i in range(len(md))]
            )
            ctx += f"\nAvailable variables by VARIABLE_NAME:\n{md_fmt}\n"
    return ctx

def get_multi_table_prompt():
    # Birden fazla tabloyu tek context içinde birleştir
    contexts = []
    for t in TARGET_TABLES:
        contexts.append(get_table_context(t, TABLE_DESCRIPTION, METADATA_QUERY))
    combined_context = "\n\n".join(contexts)
    return GEN_SQL.format(context=combined_context)

# Streamlit önizleme
if __name__ == "__main__":
    st.header("System prompt (multi-table)")
    st.markdown(get_multi_table_prompt())
