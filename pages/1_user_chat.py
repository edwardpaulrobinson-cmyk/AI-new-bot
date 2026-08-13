import mimetypes
import os
import re
import sys

import streamlit as st
from openai import OpenAI
from google import genai
from google.genai import types

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import config
import rag
import media
import interaction_log
from email_escalation import send_escalation
from utils import parse_file
from security import safe_error, check_rate_limit

# Diagnostics = the provider waterfall, retrieval chunk count, the "Show retrieved
# passages" demo panel, AND Streamlit's own Deploy button / hamburger menu / footer.
# All of that is for admins/devs only and is HIDDEN from end users by default.
# While testing, set SHOW_DIAGNOSTICS=1 in .env to reveal them; remove it before go-live.
SHOW_DIAGNOSTICS = (config.get_secret("SHOW_DIAGNOSTICS") or "").strip().lower() in ("1", "true", "yes", "on")

# --- Client theme: clean, professional, light with a blue accent. To rebrand later,
# change ACCENT below (one hex) or swap the "GNB" badge in the header for a logo. ---
ACCENT = config.get_secret("BRAND_ACCENT") or "#185FA5"
_THEME_CSS = ("""
<style>
:root, .stApp { color-scheme: light !important; }
.stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] { background:#E6EBF2 !important; }
.stApp, .stApp p, .stApp span, .stApp label, .stApp li, [data-testid="stMarkdownContainer"] { color:#1A2230; }
[data-testid="stMainBlockContainer"], .block-container { max-width:760px !important; margin:1.2rem auto 2rem !important; background:#FFFFFF !important; border:1px solid #E1E7F0; border-radius:16px; box-shadow:0 4px 24px rgba(16,24,40,.06); padding:1.3rem 1.6rem 2rem !important; }
[data-testid="InputInstructions"] { display:none !important; }
.gnb-hero { display:flex; align-items:center; gap:12px; background:transparent; border:none; border-bottom:1px solid #EDF1F6; border-radius:0; padding:0 0 14px; margin:0 0 4px; }
.gnb-badge { width:44px; height:44px; border-radius:50%; background:__ACCENT__; color:#fff; font-weight:600; font-size:14px; letter-spacing:.5px; display:flex; align-items:center; justify-content:center; }
.gnb-hero-title { font-size:17px; font-weight:600; color:#1A2230; }
.gnb-hero-sub { font-size:12.5px; color:#5A6675; display:flex; align-items:center; gap:6px; }
.gnb-dot { width:7px; height:7px; border-radius:50%; background:#1D9E75; display:inline-block; }
[data-testid="stChatMessage"] { background:transparent !important; box-shadow:none !important; padding:.25rem 0 !important; gap:10px; }
[data-testid="stChatMessageContent"] { font-size:14.5px; line-height:1.65; }
[data-testid="stChatMessageAvatarAssistant"] { background:#E8F0FB !important; color:__ACCENT__ !important; border:none !important; }
[data-testid="stChatMessageAvatarUser"] { background:#DCE3EC !important; color:#495467 !important; border:none !important; }
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) [data-testid="stChatMessageContent"]{ background:#F4F7FB; border:1px solid #E4EAF2; border-radius:4px 16px 16px 16px; padding:12px 16px; color:#1A2230 !important; max-width:84%; }
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]){ flex-direction:row-reverse; }
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageContent"]{ background:__ACCENT__; border-radius:16px 16px 4px 16px; padding:12px 16px; max-width:84%; margin-left:auto; }
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageContent"] * { color:#FFFFFF !important; }
.stButton > button { border-radius:20px !important; border:1px solid #D5DEEA !important; background:#fff !important; color:#1A2230 !important; font-weight:500 !important; padding:.35rem 1.1rem !important; }
.stButton > button:hover { border-color:__ACCENT__ !important; color:__ACCENT__ !important; }
[data-testid="stFileUploader"] label, [data-testid="stFileUploaderDropzoneInstructions"] span, [data-testid="stFileUploaderDropzoneInstructions"] small, [data-testid="stFileUploaderDropzoneInstructions"] div { color:#5A6675 !important; }
[data-testid="stFileUploaderDropzone"] { background:#F4F7FB !important; border:1px dashed #C9D4E2 !important; border-radius:12px; }
[data-testid="stFileUploader"] button, [data-testid="stBaseButton-secondary"] { background:#FFFFFF !important; color:#1A2230 !important; border:1px solid #D5DEEA !important; border-radius:20px !important; }
section[data-testid="stBottom"], [data-testid="stBottom"] > div, [data-testid="stBottomBlockContainer"] { background:#E6EBF2 !important; }
[data-testid="stChatInput"], [data-testid="stChatInput"] > div, [data-testid="stChatInput"] div { background:#FFFFFF !important; }
[data-testid="stChatInput"] { border:1px solid #D5DEEA !important; border-radius:24px !important; }
[data-testid="stChatInput"] textarea { background:#FFFFFF !important; color:#1A2230 !important; -webkit-text-fill-color:#1A2230 !important; }
[data-testid="stChatInput"] textarea::placeholder { color:#8A94A3 !important; -webkit-text-fill-color:#8A94A3 !important; }
[data-testid="stChatInputSubmitButton"], [data-testid="stChatInput"] button { color:__ACCENT__ !important; }
</style>
""").replace("__ACCENT__", ACCENT)

st.set_page_config(page_title="GNB Property assistant", layout="wide",
                   initial_sidebar_state=("expanded" if SHOW_DIAGNOSTICS else "collapsed"))

if not SHOW_DIAGNOSTICS:
    # Hide Streamlit's Deploy button, hamburger (⋮) menu, toolbar and footer from users.
    st.markdown(
        "<style>"
        "[data-testid='stToolbar'],[data-testid='stStatusWidget'],"
        "[data-testid='stAppDeployButton'],.stDeployButton,#MainMenu,"
        "header[data-testid='stHeader'],footer{display:none !important;visibility:hidden !important;}"
        "</style>",
        unsafe_allow_html=True,
    )

# Clean client theme + branded header (replaces the plain "QUERY INTERFACE" title).
st.markdown(_THEME_CSS, unsafe_allow_html=True)
st.markdown(
    '<div class="gnb-hero">'
    '<div class="gnb-badge">GNB</div>'
    '<div><div class="gnb-hero-title">GNB Property assistant</div>'
    '<div class="gnb-hero-sub"><span class="gnb-dot"></span>Here to help with your GNB software</div></div>'
    '</div>',
    unsafe_allow_html=True,
)

KB_DIR = config.KB_DIR
user_id = (getattr(getattr(st, "user", None), "email", "") or "local")

# --- Model names (all overridable via .env, no code edits needed) ---
CEREBRAS_MODEL = config.get_secret("CEREBRAS_MODEL") or "llama3.1-8b"
GROQ_MODEL = config.get_secret("GROQ_MODEL") or "llama-3.3-70b-versatile"
SAMBANOVA_MODEL = config.get_secret("SAMBANOVA_MODEL") or "Meta-Llama-3.1-8B-Instruct"
OPENROUTER_MODEL = config.get_secret("OPENROUTER_MODEL") or "moonshotai/kimi-k2.5"
GEMINI_MODEL = config.get_secret("GEMINI_MODEL") or "gemini-3.5-flash"
OPENROUTER_VISION_MODEL = config.get_secret("OPENROUTER_VISION_MODEL") or "google/gemma-4-31b-it:free"

# GLM via Z.ai direct (OpenAI-compatible endpoint — no OpenRouter markup).
ZAI_MODEL = config.get_secret("ZAI_MODEL") or "glm-5.2"
ZAI_BASE_URL = config.get_secret("ZAI_BASE_URL") or "https://api.z.ai/api/paas/v4"

# Relevance gate: minimum SEMANTIC similarity (0..1) between the question and the
# best-matching passage before we bother treating the knowledge base as relevant.
# The TRIAGE step (which actually reads the passages) is the PRIMARY accuracy guard
# that decides ANSWER / CLARIFY / NONE; this numeric gate is only a cheap BACKSTOP to
# stop truly off-topic retrieval reaching the model. Keep it LOW, so a genuinely
# answerable question that happens to use different words (e.g. "make a property live
# in all my marketing platforms" vs the doc's "publish to portals") is NOT wrongly
# suppressed into a vague "not certain" reply. Watch real scores in the "Show
# retrieved passages" demo panel and tune from .env if needed.
RELEVANCE_MIN = float(config.get_secret("RELEVANCE_MIN") or "0.32")

# Per-provider request timeout (seconds). Lower = the waterfall abandons a dead or
# overloaded provider faster and reaches a working one sooner. A healthy Gemini/Groq
# answer usually returns in well under this. Tunable via .env REQUEST_TIMEOUT.
REQUEST_TIMEOUT = int(config.get_secret("REQUEST_TIMEOUT") or "25")

# --- Provider priority: BEST first, worst last (overridable via .env PROVIDER_ORDER) ---
# Used for the ANSWER stage, where quality matters most (Gemini first).
DEFAULT_ORDER = ["Gemini", "Zai", "OpenRouter", "Groq", "SambaNova", "Cerebras"]
_order = config.get_secret("PROVIDER_ORDER")
PROVIDER_ORDER = [p.strip() for p in _order.split(",")] if _order else DEFAULT_ORDER

# --- Triage priority: CHEAP / high-limit providers FIRST (overridable via .env
# TRIAGE_PROVIDER_ORDER) ---
# Triage is a tiny yes/no classification, so it should NOT burn the scarcest, best
# model. Putting the small/fast providers first here reserves Gemini's low daily free
# quota (e.g. 20 requests/day) for the actual answers. Triage fails open to ANSWER, so
# a weaker model getting it slightly wrong just reverts to normal answering.
_torder = config.get_secret("TRIAGE_PROVIDER_ORDER")
TRIAGE_ORDER = [p.strip() for p in _torder.split(",")] if _torder else \
    ["Cerebras", "SambaNova", "Groq", "OpenRouter", "Zai", "Gemini"]


def build_clients():
    keys = config.provider_keys()
    clients, health = {}, {p: "Missing" for p in config.PROVIDER_ENV}
    if "Cerebras" in keys:
        clients["Cerebras"] = {"client": OpenAI(base_url="https://api.cerebras.ai/v1", api_key=keys["Cerebras"]), "model": CEREBRAS_MODEL}; health["Cerebras"] = "Active"
    if "Groq" in keys:
        clients["Groq"] = {"client": OpenAI(base_url="https://api.groq.com/openai/v1", api_key=keys["Groq"]), "model": GROQ_MODEL}; health["Groq"] = "Active"
    if "SambaNova" in keys:
        clients["SambaNova"] = {"client": OpenAI(base_url="https://api.sambanova.ai/v1", api_key=keys["SambaNova"]), "model": SAMBANOVA_MODEL}; health["SambaNova"] = "Active"
    if "OpenRouter" in keys:
        clients["OpenRouter"] = {"client": OpenAI(base_url="https://openrouter.ai/api/v1", api_key=keys["OpenRouter"]), "model": OPENROUTER_MODEL}; health["OpenRouter"] = "Active"
    # Gemini supports MULTIPLE keys for extra daily quota: GEMINI_API_KEY, then
    # GEMINI_API_KEY_2, GEMINI_API_KEY_3, ... Each becomes its own waterfall entry
    # (Gemini, Gemini2, ...) using the same model; when one hits its daily cap the
    # waterfall rolls to the next.
    _gk = config.get_secret("GEMINI_API_KEY")
    _gemini_keys = [("Gemini", _gk)] if _gk else []
    _n = 2
    while True:
        _k = config.get_secret(f"GEMINI_API_KEY_{_n}")
        if not _k:
            break
        _gemini_keys.append((f"Gemini{_n}", _k))
        _n += 1
    for _gname, _gkey in _gemini_keys:
        clients[_gname] = {"client": genai.Client(api_key=_gkey, http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT * 1000)), "model": GEMINI_MODEL, "kind": "gemini"}
        health[_gname] = "Active"
    # GLM via Z.ai direct — detected independently of config.provider_keys() so no
    # change to config.py is needed. OpenAI-compatible, so it uses the standard path.
    zai_key = config.get_secret("ZAI_API_KEY")
    if zai_key:
        clients["Zai"] = {"client": OpenAI(base_url=ZAI_BASE_URL, api_key=zai_key), "model": ZAI_MODEL}; health["Zai"] = "Active"
    if SHOW_DIAGNOSTICS:
        with st.sidebar:
            st.divider(); st.subheader("API Waterfall Status")
            st.caption("Tried top to bottom (best first)")
            ordered_health = [p for p in PROVIDER_ORDER if p in health] + [p for p in health if p not in PROVIDER_ORDER]
            for api in ordered_health:
                status = health[api]
                st.write(f"**{api}:** {'OK' if status == 'Active' else '--'} {status}")
    return clients


available_clients = build_clients()
if not available_clients:
    st.error("Service unavailable: no AI providers are configured.")
    st.stop()

gemini_key = config.get_secret("GEMINI_API_KEY")


def _ordered_clients(order=None):
    """Available providers in the given priority order, then any left over.
    Defaults to the ANSWER order (PROVIDER_ORDER); pass TRIAGE_ORDER for triage."""
    order = order or PROVIDER_ORDER
    ordered = [(n, available_clients[n]) for n in order if n in available_clients]
    ordered += [(n, c) for n, c in available_clients.items() if n not in order]
    return ordered


_SAFETY_LEAK = re.compile(r"(?i)\b(user|response|prompt|content)\s*safety\s*:\s*(safe|unsafe)\b[.\-\s]*")


def _clean_answer(text):
    """Strip leaked internal moderation/meta tags (e.g. 'User Safety: safe Response
    Safety: safe') and a leading provider tag (e.g. '[Gemini]') that weaker models
    sometimes emit, so they never reach the client. If nothing meaningful remains, the
    caller treats it as empty and falls through to the next provider."""
    if not text:
        return text
    t = _SAFETY_LEAK.sub("", text)
    t = re.sub(r"^\s*\[[A-Za-z0-9 _\-]{2,20}\]\s*", "", t)
    return t.strip()


def triage_question(question, context_text, recent=""):
    """STAGE 1 of a two-stage answer. A fast routing step that decides HOW to handle
    the question BEFORE any answer is written, so 'ask a clarifying question' can no
    longer lose to 'just answer' (they're now separate calls, not one prompt doing
    both). Runs through the same provider waterfall (non-streaming, 60s timeout).

    Returns one of:
        "ANSWER"                 -> single clear task; go generate the steps.
        "CLARIFY: <question>"    -> genuinely 2+ distinct documented tasks; ask first.
        "NONE"                   -> passages don't actually answer it; go to no-match.

    FAILS OPEN to "ANSWER": if every provider errors/times out, we never block a good
    answer on a routing hiccup — we just fall through to the normal answer path.
    """
    sys_rules = """You are the routing step for the GNB Property assistant, a help chatbot for staff using the GNB Property CRM. Do NOT answer or write any steps. Read the QUESTION (using RECENT CONVERSATION for context) against the REFERENCE PASSAGES and reply with EXACTLY ONE line:

ANSWER  - the passages genuinely contain the steps or facts for what they're asking (even if worded differently) and it points to ONE thing. Also use ANSWER for greetings, thanks, small talk, and for complaints or 'why did this happen' messages (the assistant handles those warmly).
CLARIFY: <one short question>  - the request GENUINELY could mean TWO OR MORE different things that are EACH actually documented in the passages, and you can't tell which. Offer only those real, documented options.
NONE  - the passages do NOT contain the actual steps or facts for what they're asking.

Rules:
- Prefer ANSWER. Only return CLARIFY when the request genuinely matches two or more COMPLETE documented workflows and the user's answer will determine which workflow to follow. Do not clarify based on shared words, page names or CRM objects alone. If every interpretation would result in NONE, return NONE instead of CLARIFY.
- Before returning CLARIFY, verify that each option has a complete documented workflow for the user's actual task. If the passages only mention the object or page but not the requested task, return NONE.
- Ask AT MOST ONE clarifying question. If a clarifying question has ALREADY been asked and the user has answered it (check RECENT CONVERSATION), choose ANSWER - never ask again and never re-ask a similar question. Don't clarify a greeting.
- If a vague message just mentions a person by name (e.g. 'I can't get in touch with Robin'), don't map it to a procedure - CLARIFY whether that person is their account manager or a contact in the CRM.
- Never ask a clarifying question unless it changes the final answer. If every possible answer would still be NONE, return NONE immediately.
- Output nothing but that single line."""

    user = ""
    if recent:
        user += "RECENT CONVERSATION:\n" + recent + "\n\n"
    user += "QUESTION:\n" + question + "\n\nREFERENCE PASSAGES:\n" + (context_text or "(none)")

    for name, pdata in _ordered_clients(TRIAGE_ORDER):
        try:
            if pdata.get("kind") == "gemini":
                resp = pdata["client"].models.generate_content(
                    model=pdata["model"],
                    contents=[types.Content(role="user", parts=[types.Part.from_text(text=user)])],
                    config=types.GenerateContentConfig(system_instruction=sys_rules, temperature=0.0))
                out = (getattr(resp, "text", "") or "").strip()
            else:
                resp = pdata["client"].chat.completions.create(
                    model=pdata["model"],
                    messages=[{"role": "system", "content": sys_rules},
                              {"role": "user", "content": user}],
                    temperature=0.0, timeout=REQUEST_TIMEOUT)
                out = ((resp.choices[0].message.content or "") if resp.choices else "").strip()
            if out:
                return out
        except Exception as e:
            safe_error(e, context=f"triage={name}")
            continue
    return "ANSWER"  # fail open — never block a good answer on a routing hiccup


_base_path = os.path.join(KB_DIR, config.BASE_CONTEXT_FILE)
base_text = parse_file(_base_path).strip() if os.path.exists(_base_path) else ""

mode = "Smart retrieval (RAG)"
if SHOW_DIAGNOSTICS:
    with st.sidebar:
        st.divider(); st.subheader("Answer mode")
        st.caption("Smart retrieval (RAG) — answers from the most relevant document passages.")
        show_sources = st.checkbox("Show retrieved passages (demo)", value=False)
else:
    show_sources = False


@st.cache_resource(show_spinner="Indexing knowledge base...")
def _load(sig, has_key):
    return rag.get_retriever(KB_DIR, gemini_key=(gemini_key if has_key else None))


retriever, info = _load(rag.kb_signature(KB_DIR), bool(gemini_key))
if SHOW_DIAGNOSTICS:
    with st.sidebar:
        st.caption(f"Retrieval: {info['engine']} ({info['chunks']} chunks)")

# Instruction used when the knowledge base does NOT actually cover the question
# (relevance below the gate, or triage returned NONE). It replaces the retrieved
# passages so the model has nothing to answer from and cannot fabricate steps.
NO_MATCH_NOTE = (
    "(Nothing in the knowledge base is a relevant match for this question. You do NOT "
    "have the steps or facts to answer it. Do not invent or guess ANY steps, buttons, "
    "menus, tabs, page names, portals, settings or figures. Warmly tell them you're not "
    "completely certain on this one, and OFFER TO ARRANGE A CALLBACK from one of our account "
    "managers. You CANNOT look things up, check, consult anyone, or 'come back to them' "
    "yourself — arranging a callback is your ONLY way to take it further. Never say you'll "
    "find out, check, or get back to them. Do NOT list or summarise what you can or can't help with, and do NOT mention guides, documents, sources or 'the information you have' - just say plainly and warmly that you're not sure of the exact steps, and offer the callback.)"
)

SYSTEM_RULES = """You are the GNB Property assistant - a warm, human colleague who helps GNB Property staff use the GNB Property CRM. You sound natural, never robotic.

WHO YOU ARE:
    - You help with GNB Property and its CRM: properties, tenancies, landlords, tenants, finance, marketing and the related tools.
    - The user is a staff agent already signed in to the CRM. NEVER tell them to log in, and do NOT list login, credential or permission prerequisites — go straight to the actual task steps.
    - If someone greets you or makes small talk, reply warmly and briefly, then offer to help.
    - If a question is clearly outside GNB Property / the CRM, gently say it's not really your area and steer back to how you can help.

HOW YOU ANSWER
- Answer ONLY from the VERIFIED INFORMATION below. If it genuinely contains the steps or facts for what they asked (even under different words), give the real steps - the actual page/section names, buttons and correct order - for the SPECIFIC thing asked. Don't pad with unrelated pages or fields.
- If the exact thing they asked is NOT in the VERIFIED INFORMATION, you do NOT know it. Never invent or guess steps, buttons, tabs, pages, fields or figures; never assemble reference facts (like balances or reconciliation logic) into a made-up procedure; never present a plausible-sounding flow. Instead say warmly you're not aware of the exact steps for that one, and offer to arrange a callback with an account manager.
- Arranging a callback is the ONLY way you can take something further - you cannot look things up, check, consult anyone or 'get back to them'. Never promise to.
- If a self-serve step in the VERIFIED INFORMATION might fix their issue (e.g. Fetch Enquiries when enquiries aren't showing), offer that first; escalate only if it doesn't work - unless the information says to escalate immediately (data loss, deleted records, client money).
- Guide branching tasks one short step at a time. Only ask a situational question when the steps genuinely differ by situation and it isn't already clear - never reflexively ask 'new or existing'.
- Keep the conversation's thread: a follow-up inherits the earlier topic.
- You MAY combine steps that span different sections WHEN they are clearly part of the SAME task or goal that the VERIFIED INFORMATION itself describes. But do NOT stitch separate, unrelated features together to construct an answer for a goal the information never actually describes, and never invent a claim that doing them achieves that goal - e.g. the information nowhere says 'set the letting service type + add landlord bank details = how to receive rent', so do not assemble that. If the thing they asked for isn't itself a task the information describes, say you're not sure of a specific process for it and offer a callback. No generic disclaimers ('may vary by configuration'). Don't perform financial calculations or reconciliations - explain the process and point to the proper tool.
- UK English; dates DD/MM/YYYY; money in pounds like £1,250.00.
- Never reveal or refer to HOW you know things: don't mention 'guides', 'documents', 'sources', 'the verified information', 'the information I have', 'what I can reference' or 'the knowledge base', and do NOT list or summarise what you can or can't help with. Never say 'that's not documented' or 'I couldn't find it'. When you're unsure, keep it short and human - e.g. 'I'm not completely sure of the exact steps for that one, and I'd rather not guess. I can get one of our account managers to walk you through it.'

TONE & FORMATTING
- Warm and human, like talking to a workmate. Open with a short friendly line, then help. Don't put a big title on every answer.
- Use a numbered list only for a real step-by-step sequence; otherwise plain sentences. Put button, menu and page names in bold (e.g. **Edit**). Explain in your own words - don't copy a document's layout.

USING ATTACHMENTS
- The user may attach a screenshot, spreadsheet, or transcribed voice note - use them together with the VERIFIED INFORMATION. If something is unclear, ask one short question.
"""


def _build_system_instruction(verified_block, background):
    """Assemble the full system prompt for the ANSWER stage. `verified_block` is the
    retrieved passages (+ attachments) when the KB covers the topic, or the
    NO_MATCH_NOTE when it does not."""
    return (
        SYSTEM_RULES
        + "=== VERIFIED INFORMATION (trusted — answer from this) ===\n"
        + (verified_block if verified_block else NO_MATCH_NOTE)
        + "\n====================================================="
        + background)


uploads = st.file_uploader(
    "Attach a screenshot, Excel, or voice recording (optional)",
    type=sorted(config.IMAGE_EXTENSIONS | config.AUDIO_EXTENSIONS | config.DATA_EXTENSIONS),
    accept_multiple_files=True,
)

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "model", "content": "Hi there! 👋 I'm here to help you get the most out of your GNB property management software. Ask me anything, or share a screenshot, spreadsheet, or voice note if you'd like."}]

for m in st.session_state.messages:
    if m["role"] != "system":
        with st.chat_message("assistant" if m["role"] == "model" else m["role"]):
            st.markdown(m["content"])


def guess_mime(name):
    return mimetypes.guess_type(name)[0] or "application/octet-stream"


if prompt := st.chat_input("Ask a question (attach files above if needed)..."):
    if not check_rate_limit(st.session_state):
        st.warning("You're sending messages too quickly. Please wait a moment.")
        st.stop()

    data_texts, images, assets, transcripts = [], [], [], []
    for uf in (uploads or []):
        if uf.size > config.MAX_ATTACH_MB * 1024 * 1024:
            st.warning(f"{uf.name} is too large (max {config.MAX_ATTACH_MB} MB) and was skipped.")
            continue
        kind = media.classify(uf.name)
        assets.append((uf.name, uf.getvalue(), guess_mime(uf.name)))
        if kind == "data":
            txt = media.extract_data_text(uf)
            if txt.strip():
                data_texts.append(f"\n\n--- ATTACHED FILE: {uf.name} ---\n{txt}")
        elif kind == "image":
            images.append((uf.getvalue(), guess_mime(uf.name)))
        elif kind == "audio":
            t = media.transcribe_audio(uf, available_clients, gemini_key)
            if t:
                transcripts.append(f"\n\n[Voice message '{uf.name}' transcript]:\n{t}")

    user_display = prompt + ("\n\n_(attached: " + ", ".join(u.name for u in uploads) + ")_" if uploads else "")
    st.chat_message("user").markdown(user_display)
    st.session_state.messages.append({"role": "user", "content": user_display})

    full_prompt = prompt + "".join(transcripts)

    # Build the retrieval query from the recent USER turns, not just this message. A short
    # reply to a clarifying question (e.g. "existing", "what if it is new") matches nothing
    # on its own — and the clarify flow we added produces exactly those short follow-ups —
    # so carry the previous question(s) into the query to keep retrieval on-topic across turns.
    _prior_user = [m["content"] for m in st.session_state.messages[:-1] if m["role"] == "user"][-2:]
    retrieval_query = " ".join(_prior_user + [full_prompt]).strip()

    # --- Retrieve, then measure genuine relevance (raw similarity, not the RRF score) ---
    try:
        # One embedding of the query serves both ranking AND the relevance gate.
        kb_results, rel = retriever.query_and_relevance(retrieval_query, k=8)
        retrieved = rag.format_context(kb_results)
    except Exception as e:
        safe_error(e, context="retrieval")
        kb_results, retrieved, rel = [], "", 0.0

    kb_block = retrieved.strip()
    attach_block = "".join(data_texts).strip()
    kb_covered = bool(kb_block) and rel >= RELEVANCE_MIN

    # What the model is allowed to treat as verified. Attachments the user supplied
    # are always trusted; KB passages only when they actually match (relevance gate).
    if kb_covered and attach_block:
        verified_block = kb_block + "\n\n" + attach_block
    elif kb_covered:
        verified_block = kb_block
    elif attach_block:
        verified_block = attach_block
    else:
        verified_block = ""   # nothing grounded -> no-match path

    background = ("\n\n=== GENERAL BACKGROUND (orientation only — NOT step-by-step instructions) ===\n"
                  + base_text + "\n=====================================================") if base_text else ""

    # Cap history so long conversations don't bloat the request; ensure it starts
    # with a user turn (Gemini requires the first history item to be 'user').
    hist = st.session_state.messages[1:-1][-8:]
    while hist and hist[0]["role"] != "user":
        hist = hist[1:]
    recent = "\n".join(
        ("User: " if m["role"] == "user" else "Assistant: ") + m["content"]
        for m in hist[-4:]
    )

    route_dbg = "(skipped)"       # for the demo debug panel
    with st.chat_message("assistant"):
        placeholder = st.empty()
        answer, success, provider_used, is_clarify = "", False, "", False

        if images:
            # Vision path is unchanged: screenshots go straight to the vision model.
            placeholder.markdown("*(Looking at your screenshot...)*")
            system_instruction = _build_system_instruction(verified_block, background)
            text, engine = media.answer_with_images(
                system_instruction, full_prompt, images, gemini_key,
                clients=available_clients, vision_model=OPENROUTER_VISION_MODEL)
            if text:
                answer, success, provider_used = _clean_answer(text), True, engine
            else:
                answer = ("I couldn't read that screenshot — image understanding needs Gemini or an "
                          "OpenRouter vision model configured. You can also type the details.")
                success, provider_used = True, "none (no vision)"
            placeholder.markdown(answer)

        else:
            # --- STAGE 1: triage (only when there's grounded material to route over) ---
            # LOOP-BREAKER: never ask more than ONE clarifying question in a row. After that,
            # answer with whatever we have, so the bot can't get stuck re-asking the same thing
            # (which happens when a weaker triage model ignores 'don't repeat').
            if not verified_block:
                route = "NONE"   # no grounded material at all
            elif st.session_state.get("clarify_streak", 0) >= 1:
                route = "ANSWER"  # already clarified once — stop looping, just answer
            else:
                placeholder.markdown("*(Checking your question...)*")
                route = triage_question(full_prompt, verified_block, recent)
            route_dbg = route

            if route.upper().startswith("CLARIFY"):
                # Ask the clarifying question and STOP — no answer is generated this turn.
                q = route.split(":", 1)[1].strip() if ":" in route else ""
                answer = q or "Could you tell me a bit more about exactly what you'd like to do?"
                success, provider_used, is_clarify = True, "triage", True
                st.session_state.clarify_streak = st.session_state.get("clarify_streak", 0) + 1
                placeholder.markdown(answer)
            else:
                st.session_state.clarify_streak = 0   # answered -> reset the loop counter
                # NONE -> force the honest no-invent instruction; ANSWER -> normal grounded steps.
                if route.upper().startswith("NONE"):
                    system_instruction = _build_system_instruction("", background)
                else:
                    system_instruction = _build_system_instruction(verified_block, background)

                # --- STAGE 2: generate the answer through the provider waterfall ---
                for i, (name, pdata) in enumerate(_ordered_clients()):
                    placeholder.markdown("*(Thinking...)*" if i == 0 else "*(Still working on it...)*")
                    try:
                        answer = ""
                        if pdata.get("kind") == "gemini":
                            contents = []
                            for msg in hist:
                                contents.append(types.Content(role=msg["role"], parts=[types.Part.from_text(text=msg["content"])]))
                            contents.append(types.Content(role="user", parts=[types.Part.from_text(text=full_prompt)]))
                            resp = pdata["client"].models.generate_content(
                                model=pdata["model"], contents=contents,
                                config=types.GenerateContentConfig(system_instruction=system_instruction, temperature=0.1))
                            answer = getattr(resp, "text", "") or ""
                        else:
                            api_msgs = [{"role": "system", "content": system_instruction}]
                            for msg in hist:
                                api_msgs.append({"role": "assistant" if msg["role"] == "model" else msg["role"], "content": msg["content"]})
                            api_msgs.append({"role": "user", "content": full_prompt})
                            resp = pdata["client"].chat.completions.create(
                                model=pdata["model"], messages=api_msgs, temperature=0.1, timeout=REQUEST_TIMEOUT)
                            answer = (resp.choices[0].message.content or "") if resp.choices else ""
                        answer = _clean_answer(answer)
                        if answer.strip():
                            placeholder.markdown(answer)
                            success = True
                            provider_used = name
                            break
                    except Exception as e:
                        safe_error(e, context=f"provider={name}")
                        continue

        if not success:
            answer = "Sorry — the assistant is temporarily unavailable. Please try again shortly."
            placeholder.markdown(answer)

        # Demo: show the relevance score + routing so the gate can be calibrated.
        if show_sources:
            with st.expander(f"🔎 Retrieval debug — relevance {rel:.2f} "
                             f"(gate {RELEVANCE_MIN:.2f}, {'COVERED' if kb_covered else 'no match'}), "
                             f"route: {route_dbg}"):
                if kb_results:
                    for ch, sc in kb_results:
                        st.markdown(f"**{ch['source']}** · rrf {sc:.4f}")
                        st.caption(ch["text"][:400] + ("..." if len(ch["text"]) > 400 else ""))
                else:
                    st.caption("No passages retrieved.")

    st.session_state.messages.append({"role": "model", "content": answer})
    # --- audit log: record the question and the answer given ---
    interaction_log.log_event(
        status=("clarify" if is_clarify else ("answered" if success else "failed")),
        question=prompt, answer=answer, user=user_id, mode=mode, provider=provider_used,
        tokens_in=len(full_prompt) // 4,
        tokens_out=len(answer) // 4,
    )
    # A clarifying question is mid-conversation — don't show the "was this helpful? /
    # did this solve it?" feedback + escalation flow until we've actually answered.
    if is_clarify:
        st.rerun()
    st.session_state.pending = {"question": prompt, "answer": answer, "assets": assets, "provider": provider_used}
    st.session_state.resolved = False
    st.session_state.rated = False
    st.rerun()


@st.dialog("Arrange a callback")
def callback_dialog():
    """Callback form in a floating modal, so it never collides with the fixed input bar."""
    p = st.session_state.get("pending") or {}
    st.write("No problem — I'll arrange for one of our account managers to give you a call. "
             "Just let me know a good time and the best number, and someone will be in touch.")
    when = st.text_input("Convenient time for a call", placeholder="e.g. tomorrow afternoon after 2pm")
    phone = st.text_input("Best number to reach you on (optional)")
    if st.button("Send callback request", type="primary", use_container_width=True):
        if not when.strip():
            st.warning("Just let me know a convenient time and I'll get it arranged for you.")
            return
        note = (f"Callback requested for: {when.strip()}."
                + (f" Contact: {phone.strip()}." if phone.strip() else ""))
        if config.EMAIL_ENABLED:
            transcript = "\n\n".join(
                f"{'Customer' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
                for m in st.session_state.messages[1:] if m["role"] in ("user", "model"))
            body = (f"Callback request from the GNB Property assistant.\n\n"
                    f"REQUESTED CALL TIME: {when.strip()}\n"
                    f"CONTACT NUMBER: {phone.strip() or '(not provided)'}\n"
                    f"USER: {user_id}\n\n"
                    f"CUSTOMER'S LATEST QUESTION:\n{p.get('question', '')}\n\n"
                    f"===== FULL CONVERSATION =====\n{transcript}\n===== END OF CONVERSATION =====\n")
            send_escalation(subject=f"[Callback request] {p.get('question', '')[:60]}",
                            body=body, attachments=p.get("assets"))
        interaction_log.log_event(status="callback_requested", question=p.get("question", ""),
                                  answer=p.get("answer", ""), user=user_id, mode=mode,
                                  provider=p.get("provider", ""),
                                  escalated_to=(config.ACCOUNT_MANAGER_EMAIL or ""), message=note)
        st.session_state.messages.append({"role": "model", "content":
            f"Thank you — I'll ask one of our account managers to call you {when.strip()}. "
            "You're in good hands, and someone will be in touch."})
        st.session_state.resolved = True
        st.session_state.pop("pending", None)
        st.session_state.pop("show_escalation", None)
        st.rerun()


# ---- "Is this sorted?" + escalate to account manager ----
pending = st.session_state.get("pending")
if pending and not st.session_state.get("resolved"):
    st.divider()
    if not st.session_state.get("rated"):
        st.caption("Was this answer helpful?")
        fb1, fb2, _ = st.columns([1, 1, 8])
        if fb1.button("👍"):
            interaction_log.log_event(status="feedback_up", question=pending["question"],
                                      answer=pending["answer"], user=user_id, mode=mode,
                                      provider=pending.get("provider", ""))
            st.session_state.rated = True
            st.rerun()
        if fb2.button("👎"):
            interaction_log.log_event(status="feedback_down", question=pending["question"],
                                      answer=pending["answer"], user=user_id, mode=mode,
                                      provider=pending.get("provider", ""))
            st.session_state.rated = True
            st.rerun()
    st.markdown("**Did this sort your query?**")
    c1, c2 = st.columns(2)
    if c1.button("✅ Yes, all sorted"):
        interaction_log.log_event(status="sorted", question=pending["question"],
                                  answer=pending["answer"], user=user_id, mode=mode,
                                  provider=pending.get("provider", ""))
        st.session_state.resolved = True
        st.session_state.pop("pending", None)
        st.rerun()
    if c2.button("🙋 No — arrange a callback"):
        callback_dialog()
