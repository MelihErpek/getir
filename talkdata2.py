from openai import OpenAI
import re
import streamlit as st
from prompts import get_system_prompt

st.title("❤️ UM - Talk To Your Customer Data")

# Initialize the chat messages history
client = OpenAI(api_key=st.secrets.OPENAI_API_KEY)

# Initialize messages if not already set in session state
if "messages" not in st.session_state:
    # Use user role instead of system since o1-preview does not support 'system'
    initial_message_content = get_system_prompt()  # Get your system prompt content
    st.session_state.messages = [{"role": "user", "content": initial_message_content}]

# Prompt for user input and save
if prompt := st.chat_input():
    st.session_state.messages.append({"role": "user", "content": prompt})

# Display the existing chat messages
for message in st.session_state.messages:
    if message["role"] == "assistant":
        with st.chat_message(message["role"], avatar='avatar.png'):
            st.write(message["content"])
            if "results" in message:
                st.dataframe(message["results"])
    else:
        with st.chat_message(message["role"]):
            st.write(message["content"])
            if "results" in message:
                st.dataframe(message["results"])

# If last message is not from assistant, generate a new response
if st.session_state.messages[-1]["role"] != "assistant":
    with st.chat_message("assistant", avatar='avatar.png'):
        response = ""
        resp_container = st.empty()

        # Stream response from OpenAI's API
        for delta in client.chat.completions.create(
            model="o1-preview",
            messages=[{"role": m["role"], "content": m["content"]} for m in st.session_state.messages],
            stream=True,
        ):
            response += (delta.choices[0].delta.content or "")
            resp_container.markdown(response)

        # Prepare the assistant message object
        message = {"role": "assistant", "content": response, "avatar": 'avatar.png'}

        # Parse the response for a SQL query and execute if available
        sql_match = re.search(r"```sql\n(.*)\n```", response, re.DOTALL)
        if sql_match:
            sql = sql_match.group(1)
            conn = st.connection("snowflake")
            message["results"] = conn.query(sql)
            st.dataframe(message["results"])

        # Append the new assistant message to the session state
        st.session_state.messages.append(message)
