from openai import OpenAI
import re
import streamlit as st
from prompts import get_system_prompt

st.title("❤️ UM - Talk To Your Customer Data")

# Initialize the chat messages history
client = OpenAI(api_key=st.secrets.OPENAI_API_KEY)
if "messages" not in st.session_state:
    # system prompt includes table information, rules, and prompts the LLM to produce
    # a welcome message to the user.
    st.session_state.messages = [{"role": "system", "content": get_system_prompt()}]

# Prompt for user input and save
if prompt := st.chat_input():
    st.session_state.messages.append({"role": "user", "content": prompt})

# display the existing chat messages
for message in st.session_state.messages:
    if message["role"] == "system":
        continue
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
    

# If last message is not from assistant, we need to generate a new response
if st.session_state.messages[-1]["role"] != "assistant":
    with st.chat_message("assistant", avatar='avatar.png'):
        response = ""
        resp_container = st.empty()
        for delta in client.chat.completions.create(
            model="o1-preview",
            messages=[{"role": m["role"], "content": m["content"]} for m in st.session_state.messages],
            stream=True,
        ):
            response += (delta.choices[0].delta.content or "")
            resp_container.markdown(response)

        message = {"role": "assistant", "content": response, "avatar": 'avatar.png'}
        # Parse the response for a SQL query and execute if available
        sql_match = re.search(r"```sql\n(.*)\n```", response, re.DOTALL)
        if sql_match:
            sql = sql_match.group(1)
            conn = st.connection("snowflake")
            message["results"] = conn.query(sql)
            st.dataframe(message["results"])
        st.session_state.messages.append(message)

 

# Check if the last message is not from the assistant
if st.session_state.messages[-1]["role"] != "assistant":
    # Create an assistant message container with an avatar
    with st.chat_message("assistant", avatar='avatar.png'):
        response = ""  # Initialize response container
        resp_container = st.empty()  # Placeholder for response content

        # Stream response from OpenAI's API
        for delta in client.chat.completions.create(
            model="o1-preview",
            messages=[{"role": m["role"], "content": m["content"]} for m in st.session_state.messages],
            stream=True,
        ):
            response += (delta.choices[0].delta.content or "")  # Concatenate streamed content
            resp_container.markdown(response)  # Update the placeholder with new content

        # Prepare the assistant message object
        message = {"role": "assistant", "content": response, "avatar": 'avatar.png'}

        # Extract SQL query from the response if available
        sql_match = re.search(r"```sql\n(.*)\n```", response, re.DOTALL)
        if sql_match:
            sql = sql_match.group(1)  # Extract SQL query from the response
            conn = st.connection("snowflake")  # Connect to Snowflake
            message["results"] = conn.query(sql)  # Execute the SQL query
            st.dataframe(message["results"])  # Display query results in a dataframe
        
        # Append the new assistant message to the session state
        st.session_state.messages.append(message)
