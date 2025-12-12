import streamlit as st
import google.generativeai as genai
import pdfplumber
from dotenv import load_dotenv
import os
import json
import io
import traceback
import streamlit.components.v1 as components

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

def extract_text_from_pdf(pdf_file, max_pages=35):
    """
    Reads up to `max_pages` pages from uploaded PDF (safe for Streamlit UploadedFile).
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
                    # add a page marker to help AI separate pages
                    text += page_text + "\n\n"
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
    # attempt to find first { ... } block
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = raw_text[start:end+1]
        try:
            return json.loads(candidate)
        except Exception:
            pass
    return None

def generate_summary20(text_content):
    """Ask model for a 20-line quick-check summary (fallback safe)."""
    if not api_key:
        return "Summary requires Google API key."
    model = genai.GenerativeModel("gemini-2.5-flash")
    snippet = text_content[:16000]  # chunk for speed - chapter check
    prompt = f"""
Read the SOURCE MATERIAL below and return a concise 20-line summary (one short line each).
Each line should include 1-3 important keywords or short phrase so I can quickly check coverage.
Return ONLY 20 lines and nothing else.

SOURCE MATERIAL:
{snippet}
"""
    try:
        resp = model.generate_content(prompt)
        raw = (resp.text or "").strip()
        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        lines = lines[:20]
        while len(lines) < 20:
            lines.append("—")
        return "\n".join(lines)
    except Exception as e:
        return f"Summary generation error: {e}"

def generate_songs(text_content, styles, language_mix, artist_ref, focus_topic, additional_instructions, duration_minutes):
    """
    Generate songs using the model.
    - Reads a large snippet (extract_text_from_pdf already limited to pages).
    - Enforces signature, adlibs, and short-formula guideline in prompt.
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

    # Structure mapping (kept succinct)
    if duration_minutes <= 1.5:
        structure = "Quick: CHORUS -> VERSE -> CHORUS -> OUTRO (approx 150 words)"
    elif duration_minutes <= 2.5:
        structure = "Radio: CHORUS -> VERSE -> CHORUS -> VERSE -> CHORUS (200-250 words)"
    elif duration_minutes <= 3.5:
        structure = "Full: Intro/adlibs -> CHORUS -> VERSE -> CHORUS -> VERSE -> CHORUS -> Outro"
    else:
        structure = "Extended: multiple chorus/verse repeats to fit duration"

    # Use a reasonably large slice so model sees content (text_content already limited to pages)
    source_snippet = text_content[:200000]

    # Updated prompt to produce funny, short, Gen-Z songs + signature rules
    prompt = f"""
You are an expert Gen-Z musical edu-tainer who writes short, funny, punchy, study-friendly songs.
Goals: make students remember chapters by turning content into viral, catchy music lines.

IMPORTANT:
- Always start with aesthetic ad-libs (examples: "yeahh", "aye vibe", "mmm-hmm", "uh-huh").
- Immediately after ad-libs, the NEXT LINE MUST contain exactly:
  beyond the notz
- The chorus must include "beyond the notz" at least once and be ultra-catchy.
- Keep songs FUNNY, INTERESTING, and WOW — add light, classroom-safe humour and relatable metaphors.
- Short symbolic formulas/hints are allowed (e.g., "F = ma", "valency 4") but DO NOT include long multi-line textbook formulas or full derivations — keep them short so the song stays musical.
- Verses should be short lines (<= 6 lines per verse recommended) and rhythmic.
- Avoid textbook paragraphs and long lists. Prefer punchlines and quick mnemonic lines.
- Maintain smooth Hindi+English (Hinglish) vibe unless user specified otherwise.

SOURCE MATERIAL (up to 35 pages excerpt):
{source_snippet}

USER SETTINGS:
- Styles: {style_list_str}
- Language mix: {language_instruction}
- Focus: {focus_instruction}
- Artist inspo: {artist_instruction}
- Duration: {duration_minutes} minutes
- Structure guidance: {structure}
- Extra instructions: {custom_instructions}

OUTPUT:
Return ONLY valid JSON with this exact structure (no extra commentary):
{{
  "songs": [
    {{
      "type": "Style Name",
      "title": "Creative Song Title",
      "vibe_description": "Suno-style production notes (instruments, BPM, mood)",
      "lyrics": "Full lyrics text (include section labels like [CHORUS], [VERSE])"
    }}
  ]
}}
"""
    try:
        resp = model.generate_content(prompt)
    except Exception as e:
        tb = traceback.format_exc()
        st.error(f"AI call error: {e}\n\n{tb}")
        return None

    # get raw text
    raw_text = ""
    try:
        raw_text = resp.text if hasattr(resp, "text") else str(resp)
    except Exception:
        raw_text = str(resp)

    cleaned = raw_text.replace("```json", "").replace("```", "").strip()
    parsed = try_parse_json(cleaned)
    if parsed and isinstance(parsed, dict) and "songs" in parsed:
        return parsed
    else:
        # fallback - return raw text inside one song so UI shows something
        st.warning("Model didn't return clean JSON. Showing raw output as fallback.")
        fallback = {
            "songs": [
                {
                    "type": styles[0] if styles else "Custom",
                    "title": "BTN Originals — fallback output",
                    "vibe_description": cleaned[:800],
                    "lyrics": cleaned
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
if "summary20_text" not in st.session_state:
    st.session_state.summary20_text = None

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
                    # also generate 20-line summary (quick chapter check)
                    with st.spinner("📝 Creating 20-line chapter check..."):
                        st.session_state.summary20_text = generate_summary20(chapter_text)
                    st.experimental_rerun()
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
                    # show lyrics in code box for copy-friendly view
                    st.code(song.get("lyrics", ""), language=None)
                    # copy button
                    components.html(copy_button_html(song.get("lyrics", "")), height=44)
                with col2:
                    st.info("🎹 AI Production Prompt")
                    st.markdown(f"_{song.get('vibe_description','')}_")
                    components.html(copy_button_html(song.get("vibe_description", "")), height=44)
                    st.markdown("---")
                    st.success("✨ Tip: Paste this prompt into Suno.ai or your DAW.")
                    if st.button("🗑️ Clear Results", key=f"clear_{i}"):
                        st.session_state.song_data = None
                        st.session_state.summary20_text = None
                        st.experimental_rerun()

    # 20-line check summary
    st.divider()
    st.subheader("📝 20-Line Quick Chapter Check")
    if st.session_state.summary20_text:
        st.code(st.session_state.summary20_text, language=None)
        components.html(copy_button_html(st.session_state.summary20_text), height=44)
    else:
        st.info("Summary not available. Generate tracks to produce the quick chapter check.")
