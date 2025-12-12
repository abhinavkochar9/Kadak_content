import streamlit as st
import google.generativeai as genai
import pdfplumber
from dotenv import load_dotenv
import os
import json
import io
import re

# --- CONFIGURATION & SETUP ---
load_dotenv()

st.set_page_config(
    page_title="BTN Originals AI Pro 🎧",
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
else:
    st.sidebar.warning("No Google API key found. Please enter it to generate songs and summaries.")

# --- PDF EXTRACTION ---
def extract_text_from_pdf(pdf_file):
    """
    Safely extracts raw text from an UploadedFile using pdfplumber.
    """
    text = ""
    try:
        # Ensure we pass a file-like object (BytesIO) to pdfplumber
        pdf_file.seek(0)
        raw_bytes = pdf_file.read()
        file_obj = io.BytesIO(raw_bytes)
        with pdfplumber.open(file_obj) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        st.error(f"Error reading PDF: {e}")
        return None
    return text

# --- 20 LINE SUMMARY ---
def generate_summary20(text_content):
    """
    Generate a concise 20-line summary (one line = one short sentence/phrase).
    """
    if not api_key:
        st.error("Cannot generate summary: missing API key.")
        return None

    model = genai.GenerativeModel("gemini-2.5-flash")
    snippet = text_content[:16000]

    prompt = f"""
Read the SOURCE MATERIAL below and produce a concise, informative summary of the chapter in EXACTLY 20 lines.
Each line should include 1–2 important keywords, must be short, and must cover the entire chapter.

Return ONLY the 20 lines. No extra text.

SOURCE MATERIAL:
{snippet}
"""

    try:
        resp = model.generate_content(prompt)
        raw = (resp.text or "").strip()
        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]

        # If too many lines → cut to 20
        lines = lines[:20]

        # If too few → pad with placeholders
        while len(lines) < 20:
            lines.append("—")

        return "\n".join(lines)

    except Exception as e:
        st.error(f"Summary Generation Error: {e}")
        return None

# --- SONG GENERATION ---
def try_parse_json_from_text(raw_text):
    """Try to extract/parse a JSON object from raw model text."""
    if not raw_text:
        return None
    try:
        return json.loads(raw_text)
    except Exception:
        pass

    # try to extract first {...} block
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = raw_text[start:end+1]
        try:
            return json.loads(candidate)
        except Exception:
            pass
    return None

def generate_songs(text_content, styles, language_mix, artist_ref, focus_topic, additional_instructions, duration_minutes):
    if not api_key:
        st.error("Cannot generate songs: missing API key.")
        return None

    model = genai.GenerativeModel("gemini-2.5-flash")
    style_list_str = ", ".join(styles)

    # LANGUAGE LOGIC
    language_instruction = "Balanced Hinglish"
    if language_mix < 30:
        language_instruction = "Mostly Hindi with English scientific terms"
    elif language_mix > 70:
        language_instruction = "Mostly English with Hindi connectors"

    # DESCRIPTION INPUTS
    focus_instruction = (
        f"Focus specifically on this topic: {focus_topic}"
        if focus_topic else
        "Cover the most important exam topics from the chapter."
    )
    artist_instruction = f"Take inspiration from the style of: {artist_ref}" if artist_ref else ""
    custom_instructions = f"USER SPECIAL INSTRUCTIONS: {additional_instructions}" if additional_instructions else ""

    # STRUCTURE MAPPING
    if duration_minutes <= 1.5:
        structure = "Quick Snippet: Chorus -> Verse 1 -> Chorus -> Outro (~150 words)"
    elif duration_minutes <= 2.5:
        structure = "Radio Edit: Chorus -> Verse 1 -> Chorus -> Verse 2 -> Chorus (~200–250 words)"
    elif duration_minutes <= 3.5:
        structure = "Full Song: Intro -> Chorus -> Verse 1 -> Chorus -> Verse 2 -> Chorus -> Bridge -> Chorus (~400 words)"
    else:
        structure = "Extended Anthem (~450+ words)"

    STYLE_REQUIREMENTS = """
All songs MUST embody the following characteristics in both lyrics and vibe_description:
- melodic rap soulmate style
- confident, classroom-friendly but powerful
- addictive and legendary
- viral, catchy, enthusiastic
- Hindi + English hybrid
- melody-driven writing
- cinematic rise sections
- groove-heavy rhythms
- correct pronunciation of pure English words
- extremely smooth, emotional, aesthetic Gen-Z friendly storytelling
"""

    prompt = f"""
You are an expert musical edu-tainer for Gen Z Indian students.

SOURCE MATERIAL:
{text_content[:50000]}

USER PARAMETERS:
- Target Styles: {style_list_str}
- Language Mix: {language_instruction}
- Content Focus: {focus_instruction}
- Artist Inspiration: {artist_instruction}
- Target Duration: {duration_minutes} minutes
- Required Structure: {structure}
- {custom_instructions}

MANDATORY SONG RULES:
1. The VERY FIRST lines must be aesthetic ad-libs (e.g., "yeahh", "aye vibe", "mmm-hmm", etc.).
2. Immediately after ad-libs, the next line MUST contain exactly:
   beyond the notz
3. The structure MUST follow this sequence (strict):
   [CHORUS]
   [VERSE 1]
   [CHORUS]
   [VERSE 2]
   [CHORUS]
   [VERSE 3]
   [CHORUS]
   [VERSE 4]
   [CHORUS]
4. The chorus must appear AT LEAST 5 times (more is allowed).
5. Every VERSE must have no more than 6 lines.
6. The CHORUS must include beyond the notz once inside it.
7. Include key formulas, definitions & keywords inside VERSES only.
8. Maintain the STYLE REQUIREMENTS below in every song:

{STYLE_REQUIREMENTS}

OUTPUT FORMAT:
Return ONLY valid JSON:
{{
  "songs": [
    {{
      "type": "Style Name",
      "title": "Creative Song Title",
      "vibe_description": "Describe production style (include all style requirements).",
      "lyrics": "Full lyrics with section labels."
    }}
  ]
}}
"""

    try:
        resp = model.generate_content(prompt)
        raw = (resp.text or "").strip()
        # first try parse
        parsed = try_parse_json_from_text(raw)
        if parsed and "songs" in parsed:
            return parsed

        # fallback: create a single-song fallback using the raw response
        fallback = {
            "songs": [
                {
                    "type": styles[0] if styles else "Custom Style",
                    "title": "BTN Originals - fallback (raw output)",
                    "vibe_description": "Fallback: raw model output; please inspect.",
                    "lyrics": raw
                }
            ]
        }
        st.warning("Model output wasn't valid JSON. Showing raw output in a fallback song. If this persists, try re-running or simplifying the prompt.")
        return fallback

    except Exception as e:
        st.error(f"AI Generation Error: {e}")
        return None

# --- SIDEBAR ---
st.sidebar.header("🎛️ Studio Controls")

style_options = [
    "Desi Hip-Hop / Trap",
    "HOOKY & VIRAL MELODIC RAP",
    "Punjabi Drill",
    "Bollywood Pop Anthem",
    "Lofi Study Beats",
    "Sufi Rock",
    "EDM / Party",
    "Old School 90s Rap"
]

selected_styles = st.sidebar.multiselect(
    "Select Music Styles",
    options=style_options,
    default=["Desi Hip-Hop / Trap"]
)

custom_style_input = st.sidebar.text_input(
    "➕ Add Custom Style",
    placeholder="e.g. K-Pop, Ghazal"
)

lang_mix = st.sidebar.slider("Hindi vs English", 0, 100, 50)

duration_minutes = st.sidebar.slider(
    "Length (Minutes)",
    min_value=1.0,
    max_value=5.0,
    value=2.5,
    step=0.5,
)

st.sidebar.subheader("✨ Fine Tuning")
artist_ref = st.sidebar.text_input("Artist Inspiration (Optional)", placeholder="e.g. Divine, Arijit Singh")
focus_topic = st.sidebar.text_input("Focus Topic (Optional)", placeholder="e.g. Soaps, Covalent Bonding")

additional_instructions = st.sidebar.text_area(
    "📝 Additional Instructions",
    placeholder="e.g. Use lots of rhyming slang, make the bridge about a specific formula...",
    height=100,
)

# --- MAIN UI ---
st.title("🎹 BTN Originals AI Pro")
st.markdown("Transform NCERT Chapters into Custom Songs.")

if "song_data" not in st.session_state:
    st.session_state.song_data = None
if "summary20_text" not in st.session_state:
    st.session_state.summary20_text = None

uploaded_file = st.file_uploader("📂 Upload PDF", type=["pdf"])

if uploaded_file is not None:
    generate_btn = st.button("🚀 Generate Tracks")
    if generate_btn:
        final_styles = selected_styles.copy()
        if custom_style_input and custom_style_input.strip() != "":
            if custom_style_input not in final_styles:
                final_styles.append(custom_style_input)

        if not api_key:
            st.warning("Please provide a Google API Key in the sidebar.")
        elif not final_styles:
            st.warning("Please select at least one style.")
        else:
            # Extraction spinner
            with st.spinner("Extracting PDF text..."):
                chapter_text = extract_text_from_pdf(uploaded_file)

            if not chapter_text:
                st.error("Failed to extract text from PDF or PDF was empty.")
            else:
                # Composition spinner
                with st.spinner("Composing tracks (this can take ~20-40s)..."):
                    songs_data = generate_songs(
                        chapter_text,
                        final_styles,
                        lang_mix,
                        artist_ref,
                        focus_topic,
                        additional_instructions,
                        duration_minutes
                    )

                if songs_data:
                    st.session_state.song_data = songs_data
                    # Generate 20-line summary in background step (still synchronous)
                    with st.spinner("Generating 20-line chapter summary..."):
                        summary_text = generate_summary20(chapter_text)
                        st.session_state.summary20_text = summary_text
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
        tabs = st.tabs([s.get('type', f"Track {i+1}") for i, s in enumerate(songs)])

        for i, tab in enumerate(tabs):
            song = songs[i]
            with tab:
                col1, col2 = st.columns([1.5, 1])
                with col1:
                    st.subheader(song.get("title", f"Track {i+1}"))
                    st.markdown("**Lyrics**")
                    st.code(song.get("lyrics", "No lyrics returned."), language=None)
                with col2:
                    st.info("🎹 Suno AI Style Prompt")
                    st.code(song.get("vibe_description", "No vibe description returned."), language=None)

                    if st.button(f"🗑️ Clear Results", key=f"clear_{i}"):
                        st.session_state.song_data = None
                        st.session_state.summary20_text = None
                        st.rerun()

# --- SUMMARY ---
st.divider()
st.subheader("📝 20-Line Summary (Quick Chapter Check)")
if st.session_state.summary20_text:
    st.code(st.session_state.summary20_text, language=None)
else:
    st.info("Summary not generated. Re-run generation to create the 20-line summary.")
