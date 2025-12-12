"""
Streamlit app: BTN Originals — robust, fallback-first, deploy-friendly.
- Works even without Google GenAI by falling back to local heuristics.
- If you add GEMINI_API_KEY (Streamlit Secrets or env), it will try the GenAI SDK.
- Save as `streamlit_app.py`. Add a `requirements.txt` with:
    streamlit>=1.20
    pdfplumber
    python-dotenv
    google-generativeai
(google-generativeai is optional; app still runs without it.)
"""

import os
import io
import json
import re
import traceback
from collections import Counter
from dotenv import load_dotenv

import streamlit as st

# Try optional imports with graceful fallback
GENAI_AVAILABLE = False
try:
    import google.generativeai as genai  # optional
    GENAI_AVAILABLE = True
except Exception:
    GENAI_AVAILABLE = False

import pdfplumber

load_dotenv()

st.set_page_config(page_title="BTN Originals 🎧", page_icon="🎹", layout="wide")

# ---------------------------
# Utility helpers
# ---------------------------
STOPWORDS = set(
    "the and for with that this from are is was were be by to of in on as an at it its which a an"
    .split()
)

def clean_lyrics(lyrics: str):
    if not lyrics:
        return lyrics
    s = lyrics
    s = re.sub(r"\$\$.*?\$\$", " [formula] ", s, flags=re.S)
    s = re.sub(r"\$.*?\$", " [formula] ", s, flags=re.S)
    s = re.sub(r"[^\n]{0,40}[=↔→<>+\-/*^]{2,}[^\n]{0,40}",
               lambda m: " [formula] " if len(m.group(0)) > 12 else m.group(0), s)
    s = re.sub(r"\b\d{4,}\b", " [num] ", s)
    nums = re.findall(r"\b\d+\b", s)
    if len(nums) > 6:
        def _rep(m):
            if _rep.c < 6:
                _rep.c += 1
                return m.group(0)
            return " [num] "
        _rep.c = 0
        s = re.sub(r"\b\d+\b", _rep, s)
    s = re.sub(r"(\[formula\]\s*){2,}", "[formula] ", s)
    s = re.sub(r"(\[num\]\s*){2,}", "[num] ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    s = re.sub(r"[ \t]{2,}", " ", s)
    return s.strip()

def local_single_word_keywords(page_text, topn=10):
    txt = re.sub(r"[^A-Za-z0-9\s]", " ", page_text or "")
    tokens = [t.lower() for t in txt.split() if len(t) > 3 and not t.isdigit()]
    if not tokens:
        return []
    counts = Counter(tokens)
    for s in list(counts):
        if s in STOPWORDS:
            del counts[s]
    return [w for w, _ in counts.most_common(topn)][:topn]

def extract_text_from_pdf(pdf_file, max_pages=35):
    try:
        try:
            pdf_file.seek(0)
        except Exception:
            pass
        raw = pdf_file.read()
        fileobj = io.BytesIO(raw)
        text = ""
        with pdfplumber.open(fileobj) as pdf:
            total = len(pdf.pages)
            pages = min(total, max_pages)
            for i in range(pages):
                p = pdf.pages[i]
                tx = p.extract_text()
                if tx:
                    text += tx.strip() + "\n\n"
        return text if text.strip() else None
    except Exception as e:
        st.error("PDF reading error. See console for traceback.")
        st.exception(e)
        return None

def try_parse_json(raw_text: str):
    if not raw_text:
        return None
    try:
        return json.loads(raw_text)
    except Exception:
        pass
    s = raw_text.find("{")
    e = raw_text.rfind("}")
    if s != -1 and e != -1 and e > s:
        candidate = raw_text[s:e+1]
        try:
            return json.loads(candidate)
        except Exception:
            pass
    return None

# ---------------------------
# Flexible model wrapper (tries multiple SDK call styles)
# ---------------------------
def configure_genai(key: str):
    if not GENAI_AVAILABLE:
        return False, "google-generativeai package not installed."
    try:
        genai.configure(api_key=key)
        return True, None
    except Exception as e:
        return False, f"configure() failed: {e}"

def call_genai_with_fallback(prompt: str, model_name="gemini-2.5-flash", max_tokens=512):
    """
    Try several SDK usage patterns and return text or raise.
    If SDK unavailable or all calls fail, raise Exception.
    """
    if not GENAI_AVAILABLE:
        raise RuntimeError("GenAI SDK not available")

    # try high-level genai.generate (newer SDKs)
    try:
        if hasattr(genai, "generate"):
            resp = genai.generate(model=model_name, prompt=prompt, max_output_tokens=max_tokens)
            # resp might be a dict-like or object with .text
            if isinstance(resp, dict):
                # try common keys
                for key in ("output", "text", "content"):
                    if key in resp:
                        return resp[key]
                # try deeper
                return json.dumps(resp)
            else:
                return str(getattr(resp, "text", resp))
    except Exception:
        pass

    # try older style: GenerativeModel().generate_content()
    try:
        if hasattr(genai, "GenerativeModel"):
            mm = genai.GenerativeModel(model_name)
            if hasattr(mm, "generate_content"):
                resp = mm.generate_content(prompt)
                return str(getattr(resp, "text", resp))
    except Exception:
        pass

    # try genai.text.generate (another pattern)
    try:
        if hasattr(genai, "text") and hasattr(genai.text, "generate"):
            resp = genai.text.generate(model=model_name, input=prompt, max_output_tokens=max_tokens)
            # resp may contain 'candidates'
            if isinstance(resp, dict):
                if "candidates" in resp and resp["candidates"]:
                    return resp["candidates"][0].get("content", "")
                return json.dumps(resp)
            return str(resp)
    except Exception:
        pass

    # nothing worked
    raise RuntimeError("All GenAI call patterns failed. Check SDK version and logs.")

# ---------------------------
# Song generation (uses model if available; otherwise local fallback)
# ---------------------------
def generate_songs(text_content: str, styles, language_mix, artist_ref, focus_topic, additional_instructions, duration_minutes, api_key):
    # Basic safety
    if not text_content:
        return {"songs": [{"type": "Fallback", "title": "Empty source", "vibe_description": "", "lyrics": ""}]}

    # Build a compact source snippet
    snippet = text_content[:12000]

    # Prompt for model (concise to avoid huge tokens)
    prompt = f"""You are a concise Gen-Z song writer. Produce one short song JSON with titles, vibe notes, and lyrics.
Return ONLY valid JSON with keys: songs -> list of objects with type, title, vibe_description, lyrics.
Lyrics must include the line 'beyond the notz' near the start and chorus repeated at least 3 times.
Keep verses <=6 lines. Avoid formulas. Keep language Hinglish mix:{language_mix}. Styles:{', '.join(styles)}.
Source excerpt:
{snippet}
USER_INSTR: {additional_instructions}
"""
    # If genai configured, try calling it
    if api_key and GENAI_AVAILABLE:
        try:
            out = call_genai_with_fallback(prompt, model_name="gemini-2.5-flash", max_tokens=700)
            cleaned = out.replace("```json", "").replace("```", "").strip()
            parsed = try_parse_json(cleaned)
            if parsed and isinstance(parsed, dict) and "songs" in parsed:
                for s in parsed.get("songs", []):
                    s["lyrics"] = clean_lyrics(s.get("lyrics", ""))
                return parsed
            else:
                # Model returned text — try to salvage with a best-effort wrapper
                return {
                    "songs": [
                        {
                            "type": styles[0] if styles else "Custom",
                            "title": "AI — fallback parsed",
                            "vibe_description": cleaned[:800],
                            "lyrics": clean_lyrics(cleaned)
                        }
                    ]
                }
        except Exception as e:
            # log for developer; fall back to local generator
            st.warning("GenAI call failed; using local fallback. See details in console.")
            st.exception(e)

    # LOCAL FALLBACK: simple templated song generation using chapter keywords
    # extract top keywords globally
    words = re.sub(r"[^A-Za-z0-9\s]", " ", text_content).lower().split()
    words = [w for w in words if len(w) > 3 and not w.isdigit() and w not in STOPWORDS]
    freq = Counter(words)
    top = [w for w, _ in freq.most_common(12)]
    chorus_kw = top[:3] if top else ["study", "notes", "exam"]
    verse_kw = top[3:9] if len(top) > 3 else ["remember", "revise", "practice", "focus", "concepts", "rules"]

    # build lyrics
    adlibs = "yeahh, aye vibe\nbeyond the notz\n"
    chorus = "\n".join([
        f"[CHORUS]",
        f"beyond the notz, remember {chorus_kw[0]}",
        f"we sing the {chorus_kw[1]} vibes, simple lines",
    ])
    # repeat chorus multiple times in structure
    verses = []
    for vnum in range(1, 4):
        lines = verse_kw[(vnum-1)*2:(vnum-1)*2+6]
        if not lines:
            lines = ["revise", "practice", "test yourself"]
        verse_text = "\n".join([f"[VERSE {vnum}]"] + [f"{ln} — keep it short" for ln in lines[:6]])
        verses.append(verse_text)

    lyrics = adlibs + chorus + "\n\n" + verses[0] + "\n\n" + chorus + "\n\n" + verses[1] + "\n\n" + chorus + "\n\n" + verses[2] + "\n\n" + chorus
    lyrics = clean_lyrics(lyrics)

    return {
        "songs": [
            {
                "type": styles[0] if styles else "Custom",
                "title": f"BTN Originals — {(' '.join(top[:2])) or 'Study Song'}",
                "vibe_description": f"Local fallback — Hinglish study song. Keywords: {', '.join(top[:6])}",
                "lyrics": lyrics
            }
        ]
    }

def generate_keywords_per_page(text_content, max_pages=35):
    if not text_content:
        return "No text to summarise."
    pages = [p.strip() for p in text_content.split("\n\n") if p.strip()][:max_pages]
    lines = []
    for p in pages:
        kws = local_single_word_keywords(p, topn=10)
        lines.append(", ".join(kws) if kws else "—")
    return "\n".join(lines)

# ---------------------------
# UI: Sidebar controls
# ---------------------------
st.sidebar.header("🎛️ Studio Controls")
style_options = [
    "Desi Hip-Hop / Trap",
    "Punjabi Drill",
    "Bollywood Pop Anthem",
    "Lofi Study Beats",
    "Sufi Rock",
    "EDM / Party",
    "Old School 90s Rap"
]
selected_styles = st.sidebar.multiselect("Select Music Styles", options=style_options, default=["Desi Hip-Hop / Trap"])
custom_style_input = st.sidebar.text_input("➕ Add Custom Style (Optional)", placeholder="e.g. K-Pop, Ghazal")
st.sidebar.subheader("🗣️ Language Mixer")
lang_mix = st.sidebar.slider("Hindi vs English", 0, 100, 50)
st.sidebar.subheader("⏱️ Track Duration")
duration_minutes = st.sidebar.slider("Length (Minutes)", 1.0, 5.0, 2.5, 0.5)
st.sidebar.subheader("✨ Fine Tuning")
artist_ref = st.sidebar.text_input("Artist Inspiration (Optional)", placeholder="e.g. Divine, Arijit Singh")
focus_topic = st.sidebar.text_input("Focus Topic (Optional)", placeholder="e.g. Soaps, Covalent Bonding")
additional_instructions = st.sidebar.text_area("📝 Additional Instructions", placeholder="e.g. keep it funny, short formulas only", height=100)

# API key: prefer Streamlit secrets, then env, then manual input
api_key = None
if hasattr(st, "secrets") and st.secrets:
    api_key = st.secrets.get("GEMINI_API_KEY") or st.secrets.get("GOOGLE_API_KEY")
if not api_key:
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
if not api_key:
    # allow manual entry (useful locally)
    api_key = st.sidebar.text_input("Enter Google API Key (optional)", type="password")

if api_key and GENAI_AVAILABLE:
    ok, err = configure_genai(api_key)
    if not ok:
        st.sidebar.error(f"GenAI config error: {err}")

# ---------------------------
# MAIN UI
# ---------------------------
st.title("🎹 BTN Originals")
st.markdown("Transform NCERT Chapters into Custom Songs — signature: *beyond the notz*")

uploaded_file = st.file_uploader("📂 Upload Chapter PDF (up to 35 pages read)", type=["pdf"])

if "song_data" not in st.session_state:
    st.session_state.song_data = None
if "keywords_per_page" not in st.session_state:
    st.session_state.keywords_per_page = None

def copy_button_html(text_to_copy):
    js_text = json.dumps(text_to_copy)
    html = f"""
    <button onclick='navigator.clipboard.writeText({js_text})' 
            style="padding:6px 10px;border-radius:6px;border:1px solid #ddd;background:#fff;cursor:pointer;font-weight:600;">
      📋 Copy
    </button>
    """
    return html

if uploaded_file is not None:
    if st.button("🚀 Generate Tracks"):
        final_styles = selected_styles.copy()
        if custom_style_input and custom_style_input.strip():
            if custom_style_input not in final_styles:
                final_styles.append(custom_style_input.strip())

        if not final_styles:
            st.warning("Select at least one style.")
        else:
            with st.spinner("📄 Extracting up to 35 pages..."):
                chapter_text = extract_text_from_pdf(uploaded_file, max_pages=35)
            if not chapter_text:
                st.error("Failed to extract text from PDF or PDF was empty.")
            else:
                with st.spinner("🎧 Composing tracks (fast fallback if no API)..."):
                    result = generate_songs(
                        chapter_text,
                        final_styles,
                        lang_mix,
                        artist_ref,
                        focus_topic,
                        additional_instructions,
                        duration_minutes,
                        api_key if api_key else None
                    )
                if result:
                    st.session_state.song_data = result
                    with st.spinner("🔎 Extracting single-word keywords per page..."):
                        st.session_state.keywords_per_page = generate_keywords_per_page(chapter_text, max_pages=35)
                    st.experimental_rerun()
                else:
                    st.error("No data returned. Try simplifying inputs or check logs.")

# Display results
if st.session_state.song_data:
    st.divider()
    st.subheader("🎵 Generated Tracks")
    songs = st.session_state.song_data.get("songs", [])
    if not songs:
        st.error("No songs found in the output.")
    else:
        tabs = st.tabs([s.get("type", f"Track {i+1}") for i, s in enumerate(songs)])
        for i, tab in enumerate(tabs):
            song = songs[i]
            with tab:
                col1, col2 = st.columns([1.6, 1])
                with col1:
                    st.subheader(song.get("title", f"Track {i+1}"))
                    st.markdown("**Lyrics**")
                    st.code(song.get("lyrics", ""), language=None)
                    st.components.v1.html(copy_button_html(song.get("lyrics", "")), height=44)
                with col2:
                    st.info("🎹 AI Production Prompt / Notes")
                    st.markdown(f"_{song.get('vibe_description', '')}_")
                    st.components.v1.html(copy_button_html(song.get("vibe_description", "")), height=44)
                    st.markdown("---")
                    if st.button("🗑️ Clear Results", key=f"clear_{i}"):
                        st.session_state.song_data = None
                        st.session_state.keywords_per_page = None
                        st.experimental_rerun()

    st.divider()
    st.subheader("🔎 Single-word keywords per page (one line = one page)")
    if st.session_state.keywords_per_page:
        st.code(st.session_state.keywords_per_page, language=None)
        st.components.v1.html(copy_button_html(st.session_state.keywords_per_page), height=44)
    else:
        st.info("Keywords not generated. Generate tracks to produce them.")

# Extra: health / debug panel (collapsed)
with st.expander("⚙️ Debug & Health checks (expand if troubleshooting)"):
    st.write("GenAI SDK available:", GENAI_AVAILABLE)
    st.write("API key present:", bool(api_key))
    if GENAI_AVAILABLE:
        try:
            st.write("genai module attrs:", ", ".join(sorted(attr for attr in dir(genai) if not attr.startswith("_"))[:40]))
        except Exception:
            st.write("Could not inspect genai module.")
    st.write("Tip: on Streamlit Cloud, set GEMINI_API_KEY in Secrets (not .env).")
