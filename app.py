import streamlit as st
import google.generativeai as genai
import pdfplumber 
from dotenv import load_dotenv
import os
import json

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

# --- PDF EXTRACTION ---
def extract_text_from_pdf(pdf_file):
    text = ""
    try:
        with pdfplumber.open(pdf_file) as pdf:
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

        # If too few → pad
        while len(lines) < 20:
            lines.append("—")

        return "\n".join(lines)

    except Exception as e:
        st.error(f"Summary Generation Error: {e}")
        return None


# --- SONG GENERATION ---
def generate_songs(text_content, styles, language_mix, artist_ref, focus_topic, additional_instructions, duration_minutes):

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

    # ---------------- NEW STYLE REQUIREMENTS YOU REQUESTED ----------------
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
    # ----------------------------------------------------------------------

    # --- AI PROMPT (UPDATED MINIMALLY) ---
    prompt = f"""
You are an expert musical edu-tainer for Gen Z Indian students.

SOURCE MATERIAL:
{text_content[:25000]}

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
5. Every VERSE must have **no more than 8 lines**.
6. The CHORUS must include **beyond the notz** once inside it.
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
        response = model.generate_content(prompt)
        cleaned_text = (response.text or "").replace("```json", "").replace("```", "").strip()
        return json.loads(cleaned_text)

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

selected_styles = st.sidebar.multiselect("Select Music Styles", options=style_options, default=["Desi Hip-Hop / Trap"])
custom_style_input = st.sidebar.text_input("➕ Add Custom Style", placeholder="e.g. K-Pop, Ghazal")
lang_mix = st.sidebar.slider("Hindi vs English", 0, 100, 50)
duration_minutes = st.sidebar.slider("Length (Minutes)", 1.0, 5.0, 2.5, 0.5)
artist_ref = st.sidebar.text_input("Artist Inspiration", placeholder="e.g. Divine, Arijit")
focus_topic = st.sidebar.text_input("Focus Topic", placeholder="e.g. Soaps, Genetics")
additional_instructions = st.sidebar.text_area("Extra Instructions", height=80)

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
        if custom_style_input.strip():
            final_styles.append(custom_style_input)

        with st.spinner("Extracting & Composing..."):
            chapter_text = extract_text_from_pdf(uploaded_file)

        if chapter_text:
            songs = generate_songs(
                chapter_text,
                final_styles,
                lang_mix,
                artist_ref,
                focus_topic,
                additional_instructions,
                duration_minutes
            )

            if songs:
                st.session_state.song_data = songs
                st.session_state.summary20_text = generate_summary20(chapter_text)
                st.rerun()

# --- DISPLAY RESULTS ---
if st.session_state.song_data:
    st.divider()
    st.subheader("🎵 Generated Tracks")

    songs = st.session_state.song_data["songs"]

    tabs = st.tabs([s["type"] for s in songs])

    for i, tab in enumerate(tabs):
        song = songs[i]
        with tab:
            col1, col2 = st.columns([1.5, 1])

            with col1:
                st.subheader(song["title"])
                st.markdown("**Lyrics**")
                st.code(song["lyrics"], language=None)

            with col2:
                st.info("🎹 Suno AI Style Prompt")
                st.code(song["vibe_description"], language=None)

                if st.button(f"🗑️ Clear Results", key=f"clear_{i}"):
                    st.session_state.song_data = None
                    st.session_state.summary20_text = None
                    st.rerun()

    # --- SUMMARY ---
    st.divider()
    st.subheader("📝 20-Line Summary (Quick Chapter Check)")
    st.code(st.session_state.summary20_text, language=None)
