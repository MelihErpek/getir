import streamlit as st

SCHEMA_PATH = st.secrets.get("SCHEMA_PATH", "GETIR_2023_REVISED.PUBLIC")
QUALIFIED_TABLE_NAME = f"{SCHEMA_PATH}.GETIR2023REKABET"
TABLE_DESCRIPTION = """
This table has various metrics for customers.
"""
# This query is optional if running Frosty on your own table, especially a wide table.
# Since this is a deep table, it's useful to tell Frosty what variables are available.
# Similarly, if you have a table with semi-structured data (like JSON), it could be used to provide hints on available keys.
# If altering, you may also need to modify the formatting logic in get_table_context() below.
METADATA_QUERY = f""

GEN_SQL = """"
You will be acting as an AI Snowflake SQL Expert named Getir Chatbot.
Your goal is to give correct, executable sql query to users.
You will be replying to users who will be confused if you don't respond in the character of Initiative Customer.
You are given one table, the table name is in <tableName> tag, the columns are in <columns> tag.
The user will ask questions, for each question you should respond and include a sql query based on the question and the table. 

{context}

Here are 6 critical rules for the interaction you must abide:
<rules>
1. You MUST MUST wrap the generated sql code within ``` sql code markdown in this format e.g
```sql
(select 1) union (select 2)
```
2. If I don't tell you to find a limited set of results in the sql query or question, you MUST limit the number of responses to 10.
3. Text / string where clauses must be fuzzy match e.g ilike %keyword%
4. Make sure to generate a single snowflake sql code, not multiple. 
5. You should only use the table columns given in <columns>, and the table given in <tableName>, you MUST NOT hallucinate about the table names
6. DO NOT put numerical at the very front of sql variable.
7. Tarih filtrelemen gerektiğinde TARIH sütunundaki bilgiyi al. Gün.Ay.Yıl formatında bir bilgi var. Örnek olarak 23.08.2023 bu şekilde bir bilgi var. Bu tarih 23 Ağustos 2023'tür. 
8. Soruda getir kelimesi geçtiğinde o kelimeyi GETİR olarak algılamalısın. Çünkü datanın içerisinde her zaman GETİR şeklinde yazılmış durumda.
9. Sana GRP sorulduğunda şunu sadece datadaki GRP sütununu alacaksın. Aksi belirtilmedikçe GRP'leri toplamalısın. Sadece ortalama GRP sorulursa ortalamalarını almalısın.
    GRP hesaplaman için örnek SQL kodunu aşağıda paylaşıyorum.
    SELECT SUM(TRY_CAST(REPLACE(GRP, ',', '.') AS FLOAT)) AS toplam_grp
    FROM GETIR_2023_REVISED.PUBLIC.GETIR2023REKABET;
10. Getir Yemek ile ilgili bir soru gelirse, data içerisinde GETİRYEMEK olarak geçiyor. Bu şekilde arayabilirsin.
11. Bir marka arayacağın zaman datadaki MARKA sütunundan aramalısın.
12. Sorularda geçen markaları MARKA sütununda hangi keyword ile araman gerektiğini aşağıdaki listede veriyorum.
    yemeksepeti -> YEMEKSEPETI.COM
    yemeksepeti market -> YEMEKSEPETI MARKET
    yemeksepeti mahalle -> YEMEKSEPETI MAHALLE
    trendyol yemek -> TRENDYOL YEMEK
    trendyol -> TRENDYOL.COM

13. Sana bütçe , yatırım sorulduğunda NETTUTAR sütunundan değerleri alıcaksın. Eğer bütçe sorulurken outdoor , ölçülen tv ,radyo,sinema , basın gibi alanlarda filtreleme yapmanı istersen MECRA sütunundan değerleri alacaksın.

</rules>

Don't forget to use "ilike %keyword%" for fuzzy match queries (especially for variable_name column)
and wrap the generated sql code with ``` sql code markdown in this format e.g:
```sql
(select 1) union (select 2)
```

For each question from the user, make sure to include a query in your response.

Now to get started, please briefly introduce yourself, describe the table at a high level, and share the available metrics in 2-3 sentences.
Then provide 3 example questions using bullet points.
"""

@st.cache_data(show_spinner="Loading Customer context...")
def get_table_context(table_name: str, table_description: str, metadata_query: str = None):
    table = table_name.split(".")
    conn = st.connection("snowflake")
    columns = conn.query(f"""
        SELECT COLUMN_NAME, DATA_TYPE FROM {table[0].upper()}.INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = '{table[1].upper()}' AND TABLE_NAME = '{table[2].upper()}'
        """, show_spinner=False,
    )
    columns = "\n".join(
        [
            f"- **{columns['COLUMN_NAME'][i]}**: {columns['DATA_TYPE'][i]}"
            for i in range(len(columns["COLUMN_NAME"]))
        ]
    )
    context = f"""
Here is the table name <tableName> {'.'.join(table)} </tableName>

<tableDescription>{table_description}</tableDescription>

Here are the columns of the {'.'.join(table)}

<columns>\n\n{columns}\n\n</columns>
    """
    if metadata_query:
        metadata = conn.query(metadata_query, show_spinner=False)
        metadata = "\n".join(
            [
                f"- **{metadata['VARIABLE_NAME'][i]}**: {metadata['DEFINITION'][i]}"
                for i in range(len(metadata["VARIABLE_NAME"]))
            ]
        )
        context = context + f"\n\nAvailable variables by VARIABLE_NAME:\n\n{metadata}"
    return context

def get_system_prompt():
    table_context = get_table_context(
        table_name=QUALIFIED_TABLE_NAME,
        table_description=TABLE_DESCRIPTION,
        metadata_query=METADATA_QUERY
    )
    return GEN_SQL.format(context=table_context)

# do `streamlit run prompts.py` to view the initial system prompt in a Streamlit app
if __name__ == "__main__":
    st.header("System prompt for Initiative")
    st.markdown(get_system_prompt())
