from google import genai
from google.genai.errors import ClientError, ServerError
import streamlit as st
import time
import random
import logging

# -------------------------------------------------------
# Load settings from Streamlit secrets
# -------------------------------------------------------

PROVIDERS = {
    "Gemini1": st.secrets["GEMINI_API_KEY_1"],
    "Gemini2": st.secrets["GEMINI_API_KEY_2"],
    "Gemini3": st.secrets["GEMINI_API_KEY_3"],
    "Gemini4": st.secrets["GEMINI_API_KEY_4"],
    "Gemini5": st.secrets["GEMINI_API_KEY_5"],
    "Gemini6": st.secrets["GEMINI_API_KEY_6"],
}

TRIAGE_ORDER = st.secrets["TRIAGE_PROVIDER_ORDER"].split(",")
CHAT_ORDER = st.secrets["PROVIDER_ORDER"].split(",")

MAX_RETRIES = int(st.secrets.get("GEMINI_MAX_RETRIES", 4))
BACKOFF = int(st.secrets.get("GEMINI_RETRY_BACKOFF", 2))

TRIAGE_MODEL = st.secrets.get("GEMINI_TRIAGE_MODEL", "gemini-3.5-flash-lite")
CHAT_MODEL = st.secrets.get("GEMINI_CHAT_MODEL", "gemini-3.5-flash")


# -------------------------------------------------------
# Cache Gemini clients
# -------------------------------------------------------

@st.cache_resource
def get_client(api_key):
    return genai.Client(api_key=api_key)


# -------------------------------------------------------
# Generic Gemini Call
# -------------------------------------------------------

def call_gemini(prompt, provider_order, model):

    last_error = None

    # Randomise provider order slightly to spread quota usage
    providers = provider_order.copy()
    random.shuffle(providers)

    for provider in providers:

        client = get_client(PROVIDERS[provider])

        wait = BACKOFF

        for attempt in range(MAX_RETRIES):

            try:

                logging.info(f"Using {provider} ({model})")

                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                )

                return response.text

            # Quota exhausted -> immediately try next API key.
            except ClientError as e:

                if e.status_code == 429:
                    logging.warning(f"{provider} quota exhausted.")
                    last_error = e
                    break

                raise

            # Temporary Google server errors.
            except ServerError as e:

                if e.status_code in [503, 504]:

                    logging.warning(
                        f"{provider} temporary server error "
                        f"{e.status_code}. Retry {attempt+1}"
                    )

                    last_error = e
                    time.sleep(wait)
                    wait *= 2
                    continue

                raise

    raise RuntimeError(f"All Gemini providers failed. {last_error}")


# -------------------------------------------------------
# Public helper functions
# -------------------------------------------------------

def triage(prompt):
    return call_gemini(prompt, TRIAGE_ORDER, TRIAGE_MODEL)


def answer(prompt):
    return call_gemini(prompt, CHAT_ORDER, CHAT_MODEL)
