import mimetypes
import os
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

st.set_page_config(page_title="Query Interface", layout="wide")
st.title("QUERY INTERFACE")
st.caption("Ask a question. You can also attach a screenshot, an Excel file, or a voice recording.")

KB_DIR = config.KB_DIR
user_id = (getattr(getattr(st, "user", None), "email", "") or "local")

# --- Model names (all overridable via .env, no code edits needed) ---
CEREBRAS_MODEL = config.get_secret("CEREBRAS_MODEL") or "llama3.1-8b"
GROQ_MODEL = config.get_secret("GROQ_MODEL") or "llama-3.3-70b-versatile"
SAMBANOVA_MODEL = config.get_secret("SAMBANOVA_MODEL") or "Meta-Llama-3.1-8B-Instruct"
OPENROUTER_MODEL = config.get_secret("OPENROUTER_MODEL") or "meta-llama/llama-3.3-70b-instruct:free"
GEMINI_MODEL = config.get_secret("GEMINI_MODEL") or "gemini-3.5-flash"
OPENROUTER_VISION_MODEL = config.get_secret("OPENROUTER_VISION_MODEL") or "google/gemma-4-31b-it:free"

# --- Provider priority: BEST first, worst last (overridable via .env PROVIDER_ORDER) ---
DEFAULT_ORDER = ["Gemini", "Groq", "OpenRouter", "SambaNova", "Cerebras"]
_order = config.get_secret("PROVIDER_ORDER")
PROVIDER_ORDER = [p.strip() for p in _order.split(",")] if _order else DEFAULT_ORDER


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
    if "Gemini" in keys:
        clients["Gemini"] = {"client": genai.Client(api_key=keys["Gemini"], http_options=types.HttpOptions(timeout=60000)), "model": GEMINI_MODEL}; health["Gemini"] = "Active"
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

_base_path = os.path.join(KB_DIR, config.BASE_CONTEXT_FILE)
base_text = parse_file(_base_path).strip() if os.path.exists(_base_path) else ""

mode = "Smart retrieval (RAG)"
with st.sidebar:
    st.divider(); st.subheader("Answer mode")
    st.caption("Smart retrieval (RAG) — answers from the most relevant document passages.")
    show_sources = st.checkbox("Show retrieved passages (demo)", value=False)


@st.cache_resource(show_spinner="Indexing knowledge base...")
def _load(sig, has_key):
    return rag.get_retriever(KB_DIR, gemini_key=(gemini_key if has_key else None))


retriever, info = _load(rag.kb_signature(KB_DIR), bool(gemini_key))
with st.sidebar:
    st.caption(f"Retrieval: {info['engine']} ({info['chunks']} chunks)")

SYSTEM_RULES = (
    "You are the GNB Property assistant — a warm, knowledgeable colleague who helps GNB Property staff use the GNB Property CRM. You sound human and natural, never robotic.\n\n"
    "WHO YOU ARE:\n"
    "- You help with GNB Property and its CRM: properties, tenancies, landlords, tenants, finance, marketing and the related tools.\n"
    "- The user is a staff agent already signed in to the CRM. NEVER tell them to log in, and do NOT list login, credential or permission prerequisites — go straight to the actual task steps.\n"
    "- If someone greets you or makes small talk, reply warmly and briefly, then offer to help.\n"
    "- If a question is clearly outside GNB Property / the CRM, gently say it's not really your area and steer back to how you can help.\n\n"
    "HOW YOU ANSWER:\n"
    "- FIRST decide before answering: does this question clearly map to ONE task, or could it genuinely mean TWO OR MORE different documented tasks? If two or more genuinely-different and relevant tasks fit, ASK one short clarifying question first (offering only the relevant ones) and STOP — wait for their answer before giving steps. Only skip the question when it clearly maps to a single task.\n"
    "- When it maps to a single clear documented procedure, GIVE the actual numbered steps straight away. Do NOT say 'would you like me to walk you through it?' — just walk them through. Withholding steps you already have behind an offer is not helpful.\n"
    "- Be concise and don't pad, but give the real steps — don't stop at prerequisites and offer to continue.\n"
    "- Write in UK English. Dates as DD/MM/YYYY; money in pounds with commas (£1,250.00).\n"
    "- Only describe multiple methods when there are genuinely two or more SEPARATE, distinct procedures for the same goal. Then summarize them briefly and ASK which one they want.\n"
    "- NEVER stitch together steps from different procedures or different articles into one answer.\n"
    "- CLARIFY, THEN GUIDE: when a request is broad or could genuinely mean more than one distinct task, ASK which one they mean FIRST and WAIT for their reply — do not dump all the steps up front. Offer only the genuinely-distinct options you actually have information for.\n"
    "- After they choose, ask any short follow-up whose answer would CHANGE the steps (e.g. whether they've already completed a prerequisite, or which of two situations applies) before giving the steps. Then give the steps for their exact situation, using only the information you have.\n"
    "- For tasks with branches, guide one step at a time — a short question, then the next step — instead of one long dump. For a simple, single-path question, just give the steps directly.\n"
    "- If only ONE genuinely-relevant procedure applies, do not ask — just give its steps.\n"
    "- Do NOT invent or imply extra methods. A single procedure with sub-steps, a dropdown, a filter, or options WITHIN it is ONE way, not several. Sub-options like 'search existing OR add new' inside a step are part of that one procedure, NOT two different ways to do the task.\n"
    "- Give the complete steps for the task in one go — specific and in order. Don't be vague, don't paraphrase away the detail, and don't truncate.\n"
    "- Do NOT add generic disclaimers such as 'these steps may vary depending on your configuration' or 'based on the CRM system'. State only what the information actually says.\n\n"
    "USING ATTACHMENTS:\n"
    "- The user may attach a screenshot, an Excel/CSV file, or a voice recording (already transcribed). Read them together with your knowledge to answer.\n"
    "- If an attachment or the question is unclear, ask ONE short clarifying question before answering.\n\n"
    "FORMATTING RULES:\n"
    "- Use Bold Headers (### Header) for structure.\n"
    "- Use bullet points for steps.\n"
    "- Use bold text for buttons or menus (**Settings → Billing**).\n\n"
    "STAYING ACCURATE (most important):\n"
    "1. Answer ONLY with facts that literally appear in the VERIFIED INFORMATION. Some passages there may be unrelated to the question — ignore those. GENERAL BACKGROUND is for terminology/orientation only, never for building instructions.\n"
    "2. CONNECT THE DOTS from what you have: if the question uses different words from the VERIFIED INFORMATION but the real steps or facts are present, recognise the link and give those real steps (e.g. a general goal that is achieved by a specific feature). Synthesising from information that IS present is encouraged.\n"
    "3. BUT if the actual steps or facts are NOT present in the VERIFIED INFORMATION, you do NOT know the answer here — even if you know how similar software usually works. Never guess or fill in from general knowledge: do not invent steps, buttons, menus, page or portal names, settings or figures (for example, do not assume a 'Settings -> Billing' page exists). Instead say warmly that you're not certain and offer to check with their account manager.\n"
    "4. The test is simple: is the specific fact/step actually in the VERIFIED INFORMATION? If yes, use it (even if the wording differs). If no, don't produce it.\n"
    "5. NEVER talk about 'documents', 'sources' or 'the knowledge base', and never say things like 'that's not documented' or 'I couldn't find that'. Speak naturally, as a colleague would.\n"
    "6. If you're not sure or don't have enough to answer confidently, DON'T guess. Respond warmly and humanly — e.g. 'I'm not completely certain on that one — let me get it checked and come back to you' — and offer to pass it to their account manager.\n"
    "7. Ask a short clarifying question ONLY when the request is genuinely ambiguous. Otherwise just answer, then offer to clarify.\n"
    "8. When a task has ordered steps, number them so they are easy to follow.\n"
    "9. FINANCE & NUMBERS: Do not perform exact calculations or reconciliations (adding up columns, matching statements, computing balances or totals). You may explain the process and point the user to the proper reconciliation tool, but never present a computed financial figure as fact.\n\n"
)

uploads = st.file_uploader(
    "Attach a screenshot, Excel, or voice recording (optional)",
    type=sorted(config.IMAGE_EXTENSIONS | config.AUDIO_EXTENSIONS | config.DATA_EXTENSIONS),
    accept_multiple_files=True,
)

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "model", "content": "Hello! Ask me anything — you can also attach a screenshot, spreadsheet, or voice note."}]

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
    try:
        retrieved = rag.format_context(retriever.query(full_prompt, k=8))
    except Exception as e:
        safe_error(e, context="retrieval")
        retrieved = ""
    docs_block = (retrieved + "".join(data_texts)).strip()
    background = ("\n\n=== GENERAL BACKGROUND (orientation only — NOT step-by-step instructions) ===\n"
                  + base_text + "\n=====================================================") if base_text else ""
    system_instruction = (
        SYSTEM_RULES
        + "=== VERIFIED INFORMATION (trusted — answer from this) ===\n"
        + (docs_block if docs_block else "(no specific verified information matched this question)")
        + "\n====================================================="
        + background)

    # Cap history so long conversations don't bloat the request; ensure it starts
    # with a user turn (Gemini requires the first history item to be 'user').
    hist = st.session_state.messages[1:-1][-8:]
    while hist and hist[0]["role"] != "user":
        hist = hist[1:]

    with st.chat_message("assistant"):
        placeholder = st.empty()
        answer, success, provider_used = "", False, ""

        if images:
            placeholder.markdown("*(Looking at your screenshot...)*")
            text, engine = media.answer_with_images(
                system_instruction, full_prompt, images, gemini_key,
                clients=available_clients, vision_model=OPENROUTER_VISION_MODEL)
            if text:
                answer, success, provider_used = text, True, engine
            else:
                answer = ("I couldn't read that screenshot — image understanding needs Gemini or an "
                          "OpenRouter vision model configured. You can also type the details.")
                success, provider_used = True, "none (no vision)"
            placeholder.markdown(answer)

        if not images:
            ordered = [(n, available_clients[n]) for n in PROVIDER_ORDER if n in available_clients]
            ordered += [(n, c) for n, c in available_clients.items() if n not in PROVIDER_ORDER]
            for i, (name, pdata) in enumerate(ordered):
                placeholder.markdown("*(Thinking...)*" if i == 0 else f"*(Trying {name}...)*")
                try:
                    answer = ""
                    if name == "Gemini":
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
                            model=pdata["model"], messages=api_msgs, temperature=0.1, timeout=60)
                        answer = (resp.choices[0].message.content or "") if resp.choices else ""
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

    st.session_state.messages.append({"role": "model", "content": answer})
    # --- audit log: record the question and the answer given ---
    interaction_log.log_event(
        status="answered" if success else "failed",
        question=prompt, answer=answer, user=user_id, mode=mode, provider=provider_used,
        tokens_in=len(system_instruction + full_prompt) // 4,
        tokens_out=len(answer) // 4,
    )
    st.session_state.pending = {"question": prompt, "answer": answer, "assets": assets, "provider": provider_used}
    st.session_state.resolved = False
    st.session_state.rated = False
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
    st.markdown("**Did this solve your question?**")
    c1, c2 = st.columns(2)
    if c1.button("✅ Yes, sorted"):
        interaction_log.log_event(status="sorted", question=pending["question"],
                                  answer=pending["answer"], user=user_id, mode=mode,
                                  provider=pending.get("provider", ""))
        st.session_state.resolved = True
        st.session_state.pop("pending", None)
        st.rerun()
    if c2.button("🙋 No — send to my account manager"):
        st.session_state.show_escalation = True

    if st.session_state.get("show_escalation"):
        if not config.EMAIL_ENABLED:
            st.info("Forwarding to an account manager isn't switched on yet. An admin needs to set the "
                    "account-manager email and an email provider (SendGrid or SMTP).")
        else:
            with st.form("escalation"):
                st.write(f"This will email **{config.ACCOUNT_MANAGER_EMAIL}** with your question, the assistant's "
                         "answer, and any files you attached.")
                extra = st.text_area("Add a message for your account manager (optional):",
                                     value=f"Hi, I couldn't fully resolve this:\n\n\"{pending['question']}\"\n\nCould you help?")
                sent = st.form_submit_button("Send to account manager")
                if sent:
                    body = (f"Escalation from the GNB Property assistant.\n\n"
                            f"USER QUESTION:\n{pending['question']}\n\n"
                            f"ASSISTANT ANSWER:\n{pending['answer']}\n\n"
                            f"USER MESSAGE:\n{extra}\n")
                    ok, msg = send_escalation(
                        subject=f"[Assistant escalation] {pending['question'][:60]}",
                        body=body,
                        attachments=pending["assets"],
                    )
                    (st.success if ok else st.error)(msg)
                    if ok:
                        interaction_log.log_event(status="escalated", question=pending["question"],
                                                  answer=pending["answer"], user=user_id, mode=mode,
                                                  provider=pending.get("provider", ""),
                                                  escalated_to=config.ACCOUNT_MANAGER_EMAIL, message=extra)
                        st.session_state.resolved = True
                        st.session_state.pop("pending", None)
                        st.session_state.pop("show_escalation", None)
