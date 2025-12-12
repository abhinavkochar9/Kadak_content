import streamlit as st
import google.generativeai as genai
import pdfplumber
from dotenv import load_dotenv
import os
import json
import io
import traceback
import streamlit.components.v1 as components
import re
from collections import Counter

# --- CONFIGURATION & SETUP ---
load_dotenv()

st.set_page_config(
    page_title="BTN Originals 🎧",
    page_icon="🎹",
    layout="wide",
    initial_sidebar_state="expanded"
)

# API Key Handling
if "GOOGLE_API_KEY" in os.environ:
    api_key = os.environ["GOOGLE_API_KEY"]
else:
    api_key = st.sidebar.text_input("Enter Google API Key", type="password")

if api_key:
    try:
        genai.configure(api_key=api_key)
    except Exception as e:
        st.error(f"API Key Error: {e}")

# --- HELPERS ---

STOPWORDS = set("""
the and for with that this from are is was were be by to of in on as an at it its which a an
""".split())

def extract_text_from_pdf(pdf_file, max_pages=35):
    """
    Reads up to `max_pages` pages from uploaded PDF (safe for Streamlit UploadedFile).
    Returns a single string with page blocks separated by double newlines.
    """
    text = ""
    try:
        try:
            pdf_file.seek(0)
        except Exception:
            pass
        raw_bytes = pdf_file.read()
        file_obj = io.BytesIO(raw_bytes)
        with pdfplumber.open(file_obj) as pdf:
            total = len(pdf.pages)
            pages_to = min(total, max_pages)
            for i in range(pages_to):
                p = pdf.pages[i]
                page_text = p.extract_text()
                if page_text:
                    text += page_text.strip() + "\n\n"
    except Exception as e:
        tb = traceback.format_exc()
        st.error(f"Error reading PDF: {e}\n\n{tb}")
        return None
    return text

def try_parse_json(raw_text):
    """Robust attempt to parse JSON from model output, or extract first {...} block."""
    if not raw_text:
        return None
    try:
        return json.loads(raw_text)
    except Exception:
        pass
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = raw_text[start:end+1]
        try:
            return json.loads(candidate)
        except Exception:
            pass
    return None

def local_single_word_keywords(page_text, topn=10):
    """
    Local fallback: extract top single-word technical keywords from a page.
    Filters stopwords, short tokens and digits.
    """
    txt = re.sub(r"[^A-Za-z0-9\s]", " ", page_text)
    tokens = [t.lower() for t in txt.split() if len(t) > 3 and not t.isdigit()]
    if not tokens:
        return []
    counts = Counter(tokens)
    # remove stopwords
    for s in list(counts):
        if s in STOPWORDS:
            del counts[s]
    common = [w for w, _ in counts.most_common(topn)]
    return common[:topn]

def generate_keywords_per_page(text_content, max_pages=35):
    """
    For each page block in text_content (split by blank line),
    return a line containing up to 10 single-word keywords for that page.
    The returned string has one line per page (number of lines == pages read).
    Try the model per page, fallback to local single-word extraction.
    """
    if not text_content:
        return "No text to summarise."

    pages = [p.strip() for p in text_content.split("\n\n") if p.strip()]
    pages = pages[:max_pages]

    model_available = bool(api_key)
    model = None
    if model_available:
        try:
            model = genai.GenerativeModel("gemini-2.5-flash")
        except Exception:
            model_available = False
            model = None

    results = []
    for idx, page_text in enumerate(pages, start=1):
        snippet = page_text[:12000]
        kws = []
        if model_available and model is not None:
            prompt = f"""
Extract up to 10 single-word keywords that best capture this page's content. 
Return ONLY a comma-separated list of single words (no phrases, no explanations). 
Prefer technical concepts, names or terms a student would search for. Avoid stopwords and numbers.

PAGE TEXT:
{snippet}
"""
            try:
                resp = model.generate_content(prompt)
                raw = (resp.text or "").strip()
                cleaned = raw.replace("```", "").strip()
                # take first non-empty line
                first = ""
                for ln in cleaned.splitlines():
                    if ln.strip():
                        first = ln.strip()
                        break
                if first:
                    # split by commas or whitespace, filter to single words, remove punctuation
                    cand = re.split(r",|;|\s+", first)
                    cand = [re.sub(r"[^A-Za-z0-9]", "", c).lower() for c in cand if c.strip()]
                    cand = [c for c in cand if len(c) > 2 and not c.isdigit() and c not in STOPWORDS]
                    # unique preserve order
                    seen = set()
                    for c in cand:
                        if c and c not in seen:
                            seen.add(c)
                            kws.append(c)
                        if len(kws) >= 10:
                            break
            except Exception:
                kws = []

        if not kws:
            kws = local_single_word_keywords(page_text, topn=10)

        if kws:
            results.append(", ".join(kws[:10]))
        else:
            results.append("—")
    return "\n".join(results)

def clean_lyrics(lyrics: str):
    """
    Post-process lyrics to remove long formulas or excessive numeric noise.
    Keeps short hints like 'F = ma' but strips long equation strings.
    """
    if not lyrics:
        return lyrics
    s = lyrics

    # Remove LaTeX-like blocks between $...$ or $$...$$
    s = re.sub(r"\$\$.*?\$\$", " [formula] ", s, flags=re.S)
    s = re.sub(r"\$.*?\$", " [formula] ", s, flags=re.S)

    # Replace long operator-rich fragments with placeholder
    s = re.sub(r"[^\n]{0,40}[=↔→<>+\-/*^]{2,}[^\n]{0,40}", lambda m: " [formula] " if len(m.group(0))>12 else m.group(0), s)

    # Replace long numeric tokens (4+ digits) with placeholder
    s = re.sub(r"\b\d{4,}\b", " [num] ", s)

    # Limit numeric tokens: if more than 6 numbers present, redact later ones
    nums = re.findall(r"\b\d+\b", s)
    if len(nums) > 6:
        def _replace_late_nums(match):
            if _replace_late_nums.count < 6:
                _replace_late_nums.count += 1
                return match.group(0)
            return " [num] "
        _replace_late_nums.count = 0
        s = re.sub(r"\b\d+\b", _replace_late_nums, s)

    # compress repeated placeholders
    s = re.sub(r"(\[formula\]\s*){2,}", "[formula] ", s)
    s = re.sub(r"(\[num\]\s*){2,}", "[num] ", s)

    # Trim extra spaces/newlines
    s = re.sub(r"\n{3,}", "\n\n", s)
    s = re.sub(r"[ \t]{2,}", " ", s)
    s = s.strip()
    return s

def generate_songs(text_content, styles, language_mix, artist_ref, focus_topic, additional_instructions, duration_minutes):
    """
    Generate songs using the model. Prompt strictly enforces:
    - aesthetic ad-libs then exact 'beyond the notz' line
    - strict section order with chorus repeated >=5 times
    - verses <=6 lines each
    Post-process lyrics to reduce numeric/formula noise.
    """
    if not api_key:
        st.error("Missing Google API key. Please enter it in the sidebar.")
        return None

    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
    except Exception as e:
        st.error(f"Model init error: {e}")
        return None

    style_list_str = ", ".join(styles)
    language_instruction = "Balanced Hinglish"
    if language_mix < 30:
        language_instruction = "Mostly Hindi (with English scientific terms)"
    elif language_mix > 70:
        language_instruction = "Mostly English (with Hindi connectors)"

    focus_instruction = f"Focus specifically on this topic: {focus_topic}" if focus_topic else "Cover the most important exam topics from the chapter."
    artist_instruction = f"Take inspiration from the style of: {artist_ref}" if artist_ref else ""
    custom_instructions = f"USER SPECIAL INSTRUCTIONS: {additional_instructions}" if additional_instructions else ""

    if duration_minutes <= 1.5:
        structure = "Quick: CHORUS -> VERSE -> CHORUS -> OUTRO (approx 150 words)"
    elif duration_minutes <= 2.5:
        structure = "Radio: CHORUS -> VERSE -> CHORUS -> VERSE -> CHORUS (200-250 words)"
    elif duration_minutes <= 3.5:
        structure = "Full: Intro/adlibs -> CHORUS -> VERSE -> CHORUS -> VERSE -> CHORUS -> Outro"
    else:
        structure = "Extended: multiple chorus/verse repeats to fit duration"

    source_snippet = text_content[:200000]

    # Strict prompt — enforces single-word chorus label blocks and structure
    prompt = f"""
You are an expert Gen-Z musical edu-tainer who writes short, funny, punchy, study-friendly songs.
IMPORTANT STRUCTURE & RULES (must follow exactly):
1) The song MUST START with 1-3 short aesthetic ad-libs (examples: "yeahh", "aye vibe", "mmm-hmm").
2) Immediately after ad-libs, on the NEXT LINE, you MUST have the exact text:
   beyond the notz
   (this line appears only once at the very start; the chorus will also include the phrase).
3) The output lyrics must include section labels and follow this exact sequence:
   [CHORUS]
   [VERSE 1]
   [CHORUS]
   [VERSE 2]
   [CHORUS]
   [VERSE 3]
   [CHORUS]
   [VERSE 4]
   [CHORUS]
   (Total: chorus appears at least 5 times. If you need extra choruses, append them at the end but keep this sequence.)
4) Each VERSE must be no more than 6 short lines (keep lines punchy).
5) CHORUS should be 2-6 lines and must include the phrase "beyond the notz" at least once.
6) Avoid long formulas and numeric dumps. You may include at most 1-2 very short hints (e.g., "F = ma", "valency 4") — no derivations, no multi-line equations.
7) Keep language Hinglish (Hindi+English) unless the user asked otherwise. Add light, classroom-safe humour.
8) Return ONLY valid JSON (no commentary) with this structure:
{{
  "songs": [
    {{
      "type": "Style Name",
      "title": "Creative Song Title",
      "vibe_description": "Suno-style production notes (instruments, BPM, mood)",
      "lyrics": "Full lyrics text with the exact labels and sequence above"
    }}
  ]
}}

SOURCE_EXCERPT:
{source_snippet}

USER SETTINGS:
Styles: {style_list_str}
Language mix: {language_instruction}
Focus: {focus_instruction}
Artist inspo: {artist_instruction}
Duration: {duration_minutes} minutes
Extra instructions: {custom_instructions}
"""
    try:
        resp = model.generate_content(prompt)
    except Exception as e:
        tb = traceback.format_exc()
        st.error(f"AI call error: {e}\n\n{tb}")
        return None

    raw_text = ""
    try:
        raw_text = resp.text if hasattr(resp, "text") else str(resp)
    except Exception:
        raw_text = str(resp)

    cleaned = raw_text.replace("```json", "").replace("```", "").strip()
    parsed = try_parse_json(cleaned)
    if parsed and isinstance(parsed, dict) and "songs" in parsed:
        # Post-process lyrics: reduce formulas and numbers
        for s in parsed.get("songs", []):
            s["lyrics"] = clean_lyrics(s.get("lyrics", ""))
        return parsed
    else:
        st.warning("Model didn't return clean JSON. Showing raw output as fallback (post-processed).")
        fallback_lyrics = clean_lyrics(cleaned)
        fallback = {
            "songs": [
                {
                    "type": styles[0] if styles else "Custom",
                    "title": "BTN Originals — fallback output",
                    "vibe_description": cleaned[:800],
                    "lyrics": fallback_lyrics
                }
            ]
        }
        return fallback

# --- UI: Sidebar controls ---
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

# --- MAIN UI ---
st.title("🎹 BTN Originals")
st.markdown("Transform NCERT Chapters into Custom Songs — signature: *beyond the notz*")

if "song_data" not in st.session_state:
    st.session_state.song_data = None
if "keywords_per_page" not in st.session_state:
    st.session_state.keywords_per_page = None

uploaded_file = st.file_uploader("📂 Upload Chapter PDF (up to 35 pages read)", type=["pdf"])

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
                final_styles.append(custom_style_input)

        if not api_key:
            st.warning("Please provide a Google API Key in the sidebar.")
        elif not final_styles:
            st.warning("Please select at least one style.")
        else:
            with st.spinner("📄 Extracting up to 35 pages..."):
                chapter_text = extract_text_from_pdf(uploaded_file, max_pages=35)
            if not chapter_text:
                st.error("Failed to extract text from PDF or PDF was empty.")
            else:
                with st.spinner("🎧 Composing tracks (may take up to 2-3 minutes for longer input)..."):
                    result = generate_songs(
                        chapter_text,
                        final_styles,
                        lang_mix,
                        artist_ref,
                        focus_topic,
                        additional_instructions,
                        duration_minutes
                    )
                if result:
                    st.session_state.song_data = result
                    # --- NEW: generate keywords per page (one line per page, up to 10 single-word keywords each)
                    with st.spinner("🔎 Extracting 10 single-word keywords per page..."):
                        st.session_state.keywords_per_page = generate_keywords_per_page(chapter_text, max_pages=35)
                    st.rerun()
                else:
                    st.error("No data returned from model. Try again or simplify inputs.")

# --- DISPLAY RESULTS ---
if st.session_state.song_data:
    st.divider()
    st.subheader("🎵 Generated Tracks")
    songs = st.session_state.song_data.get("songs", [])
    if not songs:
        st.error("No songs found in the model output.")
    else:
        tabs = st.tabs([s.get("type", f"Track {i+1}") for i, s in enumerate(songs)])
        for i, tab in enumerate(tabs):
            song = songs[i]
            with tab:
                col1, col2 = st.columns([1.5, 1])
                with col1:
                    st.subheader(song.get("title", f"Track {i+1}"))
                    st.markdown("**Lyrics**")
                    st.code(song.get("lyrics", ""), language=None)
                    components.html(copy_button_html(song.get("lyrics", "")), height=44)
                with col2:
                    st.info("🎹 AI Production Prompt")
                    st.markdown(f"_{song.get('vibe_description', '')}_")
                    components.html(copy_button_html(song.get("vibe_description", "")), height=44)
                    st.markdown("---")
                    st.success("✨ Tip: Paste this prompt into Suno.ai or your DAW.")
                    if st.button("🗑️ Clear Results", key=f"clear_{i}"):
                        st.session_state.song_data = None
                        st.session_state.keywords_per_page = None
                        st.rerun()

    # --- KEYWORDS PER PAGE (one line per page) ---
    st.divider()
    st.subheader("🔎 10 single-word keywords per page (one line = one page)")
    if st.session_state.keywords_per_page:
        st.code(st.session_state.keywords_per_page, language=None)
        components.html(copy_button_html(st.session_state.keywords_per_page), height=44)
    else:
        st.info("Keywords per page not generated. Generate tracks to produce them.")
