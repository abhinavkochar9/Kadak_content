# streamlit_app.py
"""
BTN Originals — single-file, deploy-friendly Streamlit app.
- Robust: won't crash if optional SDKs (google-generativeai) are missing.
- Falls back to a local generator if no API key / SDK available.
- Save as streamlit_app.py and deploy. Minimal required packages:
    streamlit, pdfplumber, python-dotenv (optional)
- If you want GenAI integration, add google-generativeai to requirements and
  set GEMINI_API_KEY (or GOOGLE_API_KEY) in Streamlit Secrets / env.
"""

import os
import io
import json
import re
from collections import Counter
from dotenv import load_dotenv

import streamlit as st

# optional imports guarded so app never fails at import-time
GENAI_AVAILABLE = False
try:
    import google.generativeai as genai  # optional, may not be installed
    GENAI_AVAILABLE = True
except Exception:
    GENAI_AVAILABLE = False

try:
    import pdfplumber
except Exception:
    pdfplumber = None

load_dotenv()

st.set_page_config(page_title="BTN Originals 🎧", page_icon="🎹", layout="wide")
st.title("🎹 BTN Originals — study songs, fast")

# ----------------- Utility helpers -----------------
STOPWORDS = set(
    "the and for with that this from are is was were be by to of in on as an at it its which a an"
    .split()
)

def clean_lyrics(lyrics: str):
    if not lyrics:
        return lyrics
    s = lyrics
    # redact LaTeX/inline math and long formulas
    s = re.sub(r"\$\$.*?\$\$", " [formula] ", s, flags=re.S)
    s = re.sub(r"\$.*?\$", " [formula] ", s, flags=re.S)
    s = re.sub(r"[^\n]{0,40}[=↔→<>+\-/*^]{2,}[^\n]{0,40}", lambda m: " [formula] " if len(m.group(0))>12 else m.group(0), s)
    s = re.sub(r"\b\d{4,}\b", " [num] ", s)
    nums = re.findall(r"\b\d+\b", s)
    if len(nums) > 6:
        def _r(m):
            if _r.c < 6:
                _r.c += 1
                return m.group(0)
            return " [num] "
        _r.c = 0
        s = re.sub(r"\b\d+\b", _r, s)
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

def extract_text_from_pdf(uploaded_file, max_pages=35):
    if pdfplumber is None:
        st.error("pdfplumber not installed. Add pdfplumber to requirements to read PDFs.")
        return None
    try:
        try:
            uploaded_file.seek(0)
        except Exception:
            pass
        raw = uploaded_file.read()
        fileobj = io.BytesIO(raw)
        text_blocks = []
        with pdfplumber.open(fileobj) as pdf:
            pages = min(len(pdf.pages), max_pages)
            for i in range(pages):
                page = pdf.pages[i]
                txt = page.extract_text()
                if txt:
                    text_blocks.append(txt.strip())
        return "\n\n".join(text_blocks) if text_blocks else None
    except Exception as e:
        st.exception(e)
        st.error("Failed to read PDF. Check file and try again.")
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

# ----------------- GenAI wrappers (safe) -----------------
def configure_genai_if_possible(api_key: str):
    if not GENAI_AVAILABLE:
        return False, "google-generativeai not installed"
    try:
        genai.configure(api_key=api_key)
        return True, None
    except Exception as e:
        return False, str(e)

def call_genai_safe(prompt: str, model_name="gemini-2.5-flash", max_tokens=700):
    """
    Tries several common patterns of the google-generativeai SDK.
    Returns string text or raises.
    """
    if not GENAI_AVAILABLE:
        raise RuntimeError("GenAI SDK not available")
    # pattern 1: genai.generate (newer)
    try:
        if hasattr(genai, "generate"):
            resp = genai.generate(model=model_name, prompt=prompt, max_output_tokens=max_tokens)
            # resp may be dict-like or object
            if isinstance(resp, dict):
                # try to extract obvious keys
                for k in ("output", "text", "content"):
                    if k in resp:
                        return resp[k]
                return json.dumps(resp)
            return str(getattr(resp, "text", resp))
    except Exception:
        pass
    # pattern 2: GenerativeModel
    try:
        if hasattr(genai, "GenerativeModel"):
            mm = genai.GenerativeModel(model_name)
            if hasattr(mm, "generate_content"):
                resp = mm.generate_content(prompt)
                return str(getattr(resp, "text", resp))
    except Exception:
        pass
    # pattern 3: text.generate
    try:
        if hasattr(genai, "text") and hasattr(genai.text, "generate"):
            resp = genai.text.generate(model=model_name, input=prompt, max_output_tokens=max_tokens)
            if isinstance(resp, dict):
                if "candidates" in resp and resp["candidates"]:
                    return resp["candidates"][0].get("content", "")
                return json.dumps(resp)
            return str(resp)
    except Exception:
        pass
    raise RuntimeError("All GenAI call patterns failed")

# ----------------- Song generation -----------------
def generate_songs(text_content, styles, lang_mix, artist_ref, focus_topic, extra_instructions, duration_minutes, api_key):
    if not text_content:
        return {"songs": [{"type":"Fallback","title":"No content","vibe_description":"","lyrics":""}]}

    snippet = text_content[:12000]
    prompt = f"""You are a Gen-Z study songwriter. Produce valid JSON only.
Return: {{ "songs": [ {{ "type": "...", "title": "...", "vibe_description": "...", "lyrics": "..." }} ] }}
Lyrics MUST include the line 'beyond the notz' and chorus repeated at least 3 times. Keep verses <=6 lines.
Source snippet:\n{snippet}
USER: {extra_instructions}
"""
    # try model if key + SDK available
    if api_key and GENAI_AVAILABLE:
        try:
            raw = call_genai_safe(prompt, model_name="gemini-2.5-flash", max_tokens=700)
            txt = (raw or "").replace("```json", "").replace("```", "").strip()
            parsed = try_parse_json(txt)
            if parsed and isinstance(parsed, dict) and "songs" in parsed:
                for s in parsed.get("songs", []):
                    s["lyrics"] = clean_lyrics(s.get("lyrics",""))
                return parsed
            # fallback: wrap returned text
            return {
                "songs":[
                    {
                        "type": styles[0] if styles else "Custom",
                        "title": "AI fallback song",
                        "vibe_description": txt[:800],
                        "lyrics": clean_lyrics(txt)
                    }
                ]
            }
        except Exception as e:
            # non-fatal; fall back to local generator
            st.warning("GenAI call failed; using local fallback.")
            st.write("GenAI error:", str(e))

    # Local fallback generator: simple templated song using keywords
    words = re.sub(r"[^A-Za-z0-9\s]", " ", text_content).lower().split()
    words = [w for w in words if len(w)>3 and not w.isdigit() and w not in STOPWORDS]
    freq = Counter(words)
    top = [w for w,_ in freq.most_common(12)]
    chorus_kw = top[:2] if top else ["study","notes"]
    verse_kw = top[2:8] if len(top)>2 else ["revise","practice","remember","examples","concepts","rules"]

    adlibs = "yeahh, aye vibe\nbeyond the notz\n"
    chorus_lines = [
        "[CHORUS]",
        f"beyond the notz, we chant {chorus_kw[0]}",
        f"keep it simple: {chorus_kw[1]} on repeat"
    ]
    verses = []
    for vi in range(1,4):
        slice_start = (vi-1)*2
        lines = verse_kw[slice_start:slice_start+6]
        if not lines:
            lines = ["revise", "practice", "test your mind"]
        verse = "[VERSE {}]\n".format(vi) + "\n".join([f"{l} — short" for l in lines[:6]])
        verses.append(verse)

    lyrics = adlibs + "\n".join(chorus_lines) + "\n\n" + verses[0] + "\n\n" + "\n".join(chorus_lines) + "\n\n" + verses[1] + "\n\n" + "\n".join(chorus_lines) + "\n\n" + verses[2] + "\n\n" + "\n".join(chorus_lines)
    lyrics = clean_lyrics(lyrics)

    return {
        "songs":[
            {
                "type": styles[0] if styles else "Custom",
                "title": f"BTN — {(' '.join(top[:2]) or 'Study Song')}",
                "vibe_description": f"Local fallback — keywords: {', '.join(top[:6])}",
                "lyrics": lyrics
            }
        ]
    }

def generate_keywords_per_page(text_content, max_pages=35):
    if not text_content:
        return "No text"
    pages = [p.strip() for p in text_content.split("\n\n") if p.strip()][:max_pages]
    lines = []
    for p in pages:
        kws = local_single_word_keywords(p, topn=10)
        lines.append(", ".join(kws) if kws else "—")
    return "\n".join(lines)

# ----------------- UI controls -----------------
st.sidebar.header("Studio Controls")
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
custom_style = st.sidebar.text_input("Add custom style (optional)")
lang_mix = st.sidebar.slider("Hindi vs English", 0, 100, 50)
duration_minutes = st.sidebar.slider("Length (minutes)", 1.0, 5.0, 2.5, 0.5)
artist_ref = st.sidebar.text_input("Artist inspiration (optional)")
focus_topic = st.sidebar.text_input("Focus topic (optional)")
extra_instructions = st.sidebar.text_area("Additional instructions (optional)", height=120)

# API key: prefer Streamlit secrets, then env, then manual
api_key = None
if hasattr(st, "secrets") and st.secrets:
    api_key = st.secrets.get("GEMINI_API_KEY") or st.secrets.get("GOOGLE_API_KEY")
if not api_key:
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
if not api_key:
    api_key = st.sidebar.text_input("Enter GEMINI_API_KEY (optional)", type="password")

# If SDK present and key present, try configure but do not crash on failure
if api_key and GENAI_AVAILABLE:
    ok, err = configure_genai_if_possible(api_key)
    if not ok:
        st.sidebar.error("GenAI configure error: " + (err or "unknown"))

uploaded_file = st.file_uploader("Upload Chapter PDF (up to 35 pages)", type=["pdf"])

if "song_data" not in st.session_state:
    st.session_state.song_data = None
if "keywords_per_page" not in st.session_state:
    st.session_state.keywords_per_page = None

def copy_button_html(text_to_copy: str):
    txt = json.dumps(text_to_copy)
    return f"""
    <button onclick='navigator.clipboard.writeText({txt})' 
      style="padding:6px 10px;border-radius:6px;border:1px solid #ddd;background:#fff;cursor:pointer;font-weight:600;">
      📋 Copy
    </button>
    """

if uploaded_file and st.button("Generate Tracks"):
    styles = selected_styles.copy()
    if custom_style and custom_style.strip():
        if custom_style.strip() not in styles:
            styles.append(custom_style.strip())

    if not styles:
        st.warning("Please select at least one style.")
    else:
        with st.spinner("Extracting text from PDF..."):
            chapter_text = extract_text_from_pdf(uploaded_file, max_pages=35)
        if not chapter_text:
            st.error("Could not extract text from PDF. Try a different file or install pdfplumber.")
        else:
            with st.spinner("Composing tracks..."):
                result = generate_songs(
                    chapter_text, styles, lang_mix, artist_ref, focus_topic, extra_instructions, duration_minutes, api_key
                )
            st.session_state.song_data = result
            with st.spinner("Generating keywords per page..."):
                st.session_state.keywords_per_page = generate_keywords_per_page(chapter_text, max_pages=35)
            st.experimental_rerun()

# Display results
if st.session_state.song_data:
    st.subheader("Generated Tracks")
    songs = st.session_state.song_data.get("songs", [])
    if not songs:
        st.error("No songs produced.")
    else:
        tabs = st.tabs([s.get("type", f"Track {i+1}") for i,s in enumerate(songs)])
        for i, tab in enumerate(tabs):
            song = songs[i]
            with tab:
                c1, c2 = st.columns([1.6, 1])
                with c1:
                    st.subheader(song.get("title", f"Track {i+1}"))
                    st.markdown("**Lyrics**")
                    st.code(song.get("lyrics", ""), language=None)
                    st.components.v1.html(copy_button_html(song.get("lyrics","")), height=44)
                with c2:
                    st.info("AI Production Notes")
                    st.markdown(f"_{song.get('vibe_description','')}_")
                    st.components.v1.html(copy_button_html(song.get("vibe_description","")), height=44)
                    st.markdown("---")
                    if st.button("Clear results", key=f"clear_{i}"):
                        st.session_state.song_data = None
                        st.session_state.keywords_per_page = None
                        st.experimental_rerun()

    st.subheader("Single-word keywords per page (one line = one page)")
    if st.session_state.keywords_per_page:
        st.code(st.session_state.keywords_per_page, language=None)
        st.components.v1.html(copy_button_html(st.session_state.keywords_per_page), height=44)
    else:
        st.info("Keywords not generated yet.")

# Debug expander
with st.expander("Debug & Health"):
    st.write("GenAI SDK installed:", GENAI_AVAILABLE)
    st.write("API key present:", bool(api_key))
    st.write("pdfplumber available:", pdfplumber is not None)
    st.write("Python exec:", os.environ.get("PYTHONPATH", "not set"))
    st.write("Tip: On Streamlit Cloud put GEMINI_API_KEY in Secrets (not .env).")
