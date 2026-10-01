import streamlit as st
from openai import OpenAI
from google import genai
from google.genai import types
import os
import sys

# Add parent directory to path so we can import utils
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils import get_all_kb_text

st.set_page_config(page_title="Query Interface", layout="wide")

st.title("QUERY INTERFACE")
st.markdown(
    "Engine: `Waterfall Router (Cerebras -> Groq -> SambaNova -> OpenRouter -> Gemini)` "
    "| State: **Ready**"
)

KB_DIR = "knowledge_base"


# Initialize ALL available clients
def get_clients():
    def get_key(name):
        val = os.getenv(name)
        if not val:
            try:
                val = st.secrets[name]
            except Exception:
                pass
        return val

    clients = {}
    health_status = {}

    # 1. Cerebras
    ck = get_key("CEREBRAS_API_KEY")
    if ck:
        clients["Cerebras"] = {"client": OpenAI(base_url="https://api.cerebras.ai/v1", api_key=ck), "model": "llama3.1-8b"}
        health_status["Cerebras"] = "Active"
    else:
        health_status["Cerebras"] = "Missing"

    # 2. Groq
    gk = get_key("GROQ_API_KEY")
    if gk:
        clients["Groq"] = {"client": OpenAI(base_url="https://api.groq.com/openai/v1", api_key=gk), "model": "llama-3.3-70b-versatile"}
        health_status["Groq"] = "Active"
    else:
        health_status["Groq"] = "Missing"

    # 3. SambaNova
    sk = get_key("SAMBANOVA_API_KEY")
    if sk:
        clients["SambaNova"] = {"client": OpenAI(base_url="https://api.sambanova.ai/v1", api_key=sk), "model": "Meta-Llama-3.1-8B-Instruct"}
        health_status["SambaNova"] = "Active"
    else:
        health_status["SambaNova"] = "Missing"

    # 4. OpenRouter
    ok = get_key("OPENROUTER_API_KEY")
    if ok:
        clients["OpenRouter"] = {"client": OpenAI(base_url="https://openrouter.ai/api/v1", api_key=ok), "model": "meta-llama/llama-3.3-70b-instruct:free"}
        health_status["OpenRouter"] = "Active"
    else:
        health_status["OpenRouter"] = "Missing"

    # 5. Gemini
    gmk = get_key("GEMINI_API_KEY")
    if gmk:
        clients["Gemini"] = {"client": genai.Client(api_key=gmk), "model": "gemini-2.5-flash"}
        health_status["Gemini"] = "Active"
    else:
        health_status["Gemini"] = "Missing"

    # Display health in sidebar
    with st.sidebar:
        st.divider()
        st.subheader("API Waterfall Status")
        for api, status in health_status.items():
            icon = "OK" if status == "Active" else "--"
            st.write(f"**{api}:** {icon} {status}")
        st.info("The bot will automatically skip failed or missing providers.")

    return clients


available_clients = get_clients()
if not available_clients:
    st.error("Admin error: No API Keys found in Streamlit Secrets.")
    st.info("Check the sidebar for status. Please add keys to Streamlit Cloud Secrets.")
    st.stop()


# Helper function to get KB text
def prep_knowledge_base():
    return get_all_kb_text(KB_DIR)


# Load KB into memory
kb_text = prep_knowledge_base()
if not kb_text.strip():
    st.info("The staff has not uploaded any documents yet. Please check back later!")
    st.stop()

# Rough guard: the whole KB is stuffed into the prompt. Warn if it is very large.
# ~4 chars per token; most free models cap around 8k-32k tokens of context.
approx_tokens = len(kb_text) // 4
if approx_tokens > 25000:
    st.warning(
        f"Knowledge base is large (~{approx_tokens:,} tokens). Some free models may "
        "truncate or reject it. Consider enabling retrieval (RAG) if answers degrade."
    )

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []
    st.session_state.messages.append({
        "role": "model",  # 'model' internally to support Gemini's strict schema
        "content": "Hello! I've read the available knowledge base. What would you like to know?",
    })

# Display chat messages
for message in st.session_state.messages:
    if message["role"] != "system":
        role_label = "assistant" if message["role"] == "model" else message["role"]
        with st.chat_message(role_label):
            st.markdown(message["content"])

# React to user input
if prompt := st.chat_input("Ask a question about the documents..."):
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("assistant"):
        message_placeholder = st.empty()

        system_instruction = (
            "You are an advanced, empathetic software guide. You are helping a colleague navigate internal documents.\n\n"
            "BE HUMAN & CONVERSATIONAL:\n"
            "- Do not just dump information. Be a helpful partner.\n"
            "- If the documents mention multiple ways to do something (e.g. 'Method A' vs 'Method B'), summarize them briefly and ASK the user which one they would like to see the details for.\n"
            "- Example: 'I see there are two ways to add rent: via the property page or the tenant page. Which would you prefer to see?'\n"
            "- Keep your initial answers bite-sized and helpful. Don't overwhelm.\n\n"
            "FORMATTING RULES:\n"
            "- Use Bold Headers (### Header) for structure.\n"
            "- Use bullet points for steps.\n"
            "- Use bold text for buttons or menus (**Settings \u2192 Billing**).\n\n"
            "CRITICAL RULES:\n"
            "1. ONLY use the provided documents. If not found, say you don't know.\n"
            "2. Never mention the 'documents' as your source in a robotic way; speak naturally.\n"
            "3. If a specific detail (a number, name, button label, or step) is not stated, say it is not specified rather than inventing it.\n"
            "4. If the question is unclear or could mean several things, ask ONE short clarifying question before answering.\n"
            "5. When a task has ordered steps, number them so they are easy to follow.\n\n"
            f"=== KNOWLEDGE BASE DOCUMENTS ===\n{kb_text}\n================================="
        )

        success = False
        last_error = None

        # WATERFALL ROUTER: Try each provider until one successfully streams
        for i, (provider_name, provider_data) in enumerate(available_clients.items()):
            if i > 0:
                message_placeholder.markdown(f"*(Provider failed. Swerving to {provider_name}...)*")
            else:
                message_placeholder.markdown("*(Thinking...)*")

            try:
                full_response = ""

                if provider_name == "Gemini":
                    contents = []
                    for msg in st.session_state.messages[1:-1]:  # Skip intro + current prompt
                        contents.append(types.Content(role=msg["role"], parts=[types.Part.from_text(text=msg["content"])]))
                    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=prompt)]))

                    response = provider_data["client"].models.generate_content_stream(
                        model=provider_data["model"],
                        contents=contents,
                        config=types.GenerateContentConfig(system_instruction=system_instruction, temperature=0.7),
                    )
                    for chunk in response:
                        if chunk.text:
                            full_response += chunk.text
                            message_placeholder.markdown(f"**[{provider_name}]**\n\n" + full_response + "|")

                else:
                    api_messages = [{"role": "system", "content": system_instruction}]
                    for msg in st.session_state.messages[1:-1]:
                        r = "assistant" if msg["role"] == "model" else msg["role"]
                        api_messages.append({"role": r, "content": msg["content"]})
                    api_messages.append({"role": "user", "content": prompt})

                    response = provider_data["client"].chat.completions.create(
                        model=provider_data["model"],
                        messages=api_messages,
                        stream=True,
                        temperature=0.7,
                    )
                    for chunk in response:
                        if chunk.choices and len(chunk.choices) > 0 and chunk.choices[0].delta.content:
                            full_response += chunk.choices[0].delta.content
                            message_placeholder.markdown(f"**[{provider_name}]**\n\n" + full_response + "|")

                # If loop finishes without raising an Error, we succeeded!
                message_placeholder.markdown(f"**[{provider_name}]**\n\n" + full_response)
                st.session_state.messages.append({"role": "model", "content": f"**[{provider_name}]**\n\n" + full_response})
                success = True
                break

            except Exception as e:
                last_error = f"{provider_name}: {str(e)}"
                continue

        if not success:
            st.error(
                "SYSTEM FAILURE: All configured AI providers failed.\n\n"
                "**Common Fixes:**\n"
                "1. Get a **fresh** Gemini Key.\n"
                "2. Add extra free keys (Cerebras, Groq, or SambaNova) to your Streamlit Secrets for 100% uptime.\n\n"
                f"*Technical Detail: {last_error}*"
            )
            st.session_state.messages.pop()  # Remove failed prompt
