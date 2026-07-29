"""
media.py - Handle uploaded screenshots, spreadsheets and voice recordings.

- Data files (xlsx/csv/pdf/docx/txt) are parsed to text so any provider can use them.
- Audio is transcribed (Groq Whisper preferred, Gemini fallback) then treated as text.
- Images go to a vision model: Gemini first, then a free OpenRouter vision model
  as a fallback (so screenshots still work when Gemini is busy).

Model names are read from the environment so they can be swapped without code edits:
  GEMINI_MODEL             (default gemini-3.5-flash)
  OPENROUTER_VISION_MODEL  (default google/gemma-4-31b-it:free)
"""

import base64
import os
import tempfile

import config
from utils import parse_file
from security import safe_error

_GEMINI_MODEL = config.get_secret("GEMINI_MODEL") or "gemini-3.5-flash"
_OR_VISION_MODEL = config.get_secret("OPENROUTER_VISION_MODEL") or "google/gemma-4-31b-it:free"


def classify(filename: str) -> str:
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext in config.IMAGE_EXTENSIONS:
        return "image"
    if ext in config.AUDIO_EXTENSIONS:
        return "audio"
    if ext in config.DATA_EXTENSIONS:
        return "data"
    return "unknown"


def extract_data_text(uploaded) -> str:
    """Parse a spreadsheet/pdf/doc upload to text via a temp file."""
    suffix = "." + uploaded.name.lower().rsplit(".", 1)[-1]
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(uploaded.getbuffer())
            path = tmp.name
        text = parse_file(path)
        os.unlink(path)
        return text or ""
    except Exception as e:
        safe_error(e, context="extract_data_text")
        return ""


def transcribe_audio(uploaded, clients: dict, gemini_key: str | None) -> str | None:
    """Transcribe a voice recording. Returns transcript text or None."""
    data = uploaded.getvalue()
    mime = "audio/" + uploaded.name.lower().rsplit(".", 1)[-1].replace("m4a", "mp4")

    if "Groq" in clients:
        try:
            r = clients["Groq"]["client"].audio.transcriptions.create(
                model="whisper-large-v3", file=(uploaded.name, data))
            return getattr(r, "text", None)
        except Exception as e:
            safe_error(e, context="whisper")

    if gemini_key:
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=gemini_key)
            resp = client.models.generate_content(
                model=_GEMINI_MODEL,
                contents=[types.Content(role="user", parts=[
                    types.Part.from_text(text="Transcribe this audio verbatim."),
                    types.Part.from_bytes(data=data, mime_type=mime),
                ])])
            return getattr(resp, "text", None)
        except Exception as e:
            safe_error(e, context="gemini_transcribe")

    return None


def _gemini_vision(system_instruction, prompt, images, gemini_key):
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=gemini_key)
    parts = [types.Part.from_text(text=prompt)]
    for data, mime in images:
        parts.append(types.Part.from_bytes(data=data, mime_type=mime))
    resp = client.models.generate_content(
        model=_GEMINI_MODEL,
        contents=[types.Content(role="user", parts=parts)],
        config=types.GenerateContentConfig(system_instruction=system_instruction, temperature=0.4))
    return getattr(resp, "text", None)


def _openrouter_vision(system_instruction, prompt, images, clients, vision_model):
    """Free OpenRouter vision model via the OpenAI-compatible API."""
    content = [{"type": "text", "text": prompt}]
    for data, mime in images:
        b64 = base64.b64encode(data).decode()
        content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
    messages = [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": content},
    ]
    resp = clients["OpenRouter"]["client"].chat.completions.create(
        model=vision_model, messages=messages, temperature=0.4)
    return resp.choices[0].message.content


def answer_with_images(system_instruction, prompt, images, gemini_key,
                       clients=None, vision_model=None):
    """Answer a question about screenshot(s).
    Tries Gemini first, then a free OpenRouter vision model as fallback.
    Returns (text, engine) or (None, None)."""
    vision_model = vision_model or _OR_VISION_MODEL

    # 1) Gemini vision
    if gemini_key:
        try:
            text = _gemini_vision(system_instruction, prompt, images, gemini_key)
            if text and text.strip():
                return text, "Gemini (vision)"
        except Exception as e:
            safe_error(e, context="gemini_vision")

    # 2) OpenRouter free vision fallback
    if clients and "OpenRouter" in clients:
        try:
            text = _openrouter_vision(system_instruction, prompt, images, clients, vision_model)
            if text and text.strip():
                return text, f"OpenRouter vision ({vision_model})"
        except Exception as e:
            safe_error(e, context="openrouter_vision")

    return None, None
