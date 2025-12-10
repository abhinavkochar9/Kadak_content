import streamlit as st
import google.generativeai as genai
import pdfplumber
from dotenv import load_dotenv
import os
import textwrap

# --- CONFIGURATION & SETUP ---
load_dotenv()

# Page Config
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

# --- HELPER FUNCTIONS ---

def extract_text_from_pdf(pdf_file, max_pages=15):
    """
    Extracts raw text from an uploaded PDF file using pdfplumber.
    Limits to first `max_pages` pages for speed.
    """
    text = ""
    try:
        with pdfplumber.open(pdf_file) as pdf:
            for i, page in enumerate(pdf.pages):
                if i >= max_pages:
                    break
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        st.error(f"Error reading PDF: {e}")
        return None
    return text


def parse_songs_from_text(raw_text, styles):
    """
    Parse songs from the custom block format:

    === SONG START ===
    TYPE: ...
    TITLE: ...
    VIBE: ...
    LYRICS:
    line 1
    line 2
    ...
    === SONG END ===
    """
    songs = []
    blocks = raw_text.split("=== SONG START ===")
    for block in blocks:
        block = block.strip()
        if not block:
            continue

        # Trim at SONG END if present
        if "=== SONG END ===" in block:
            block = block.split("=== SONG END ===")[0].strip()

        lines = [l.rstrip("\r") for l in block.splitlines()]
        type_val = ""
        title_val = ""
        vibe_val = ""
        lyrics_lines = []
        in_lyrics = False

        for line in lines:
            stripped = line.strip()
            if not stripped and not in_lyrics:
                continue

            if stripped.startswith("TYPE:"):
                type_val = stripped[len("TYPE:"):].strip()
            elif stripped.startswith("TITLE:"):
                title_val = stripped[len("TITLE:"):].strip()
            elif stripped.startswith("VIBE:"):
                vibe_val = stripped[len("VIBE:"):].strip()
            elif stripped.startswith("LYRICS:"):
                in_lyrics = True
            else:
                if in_lyrics:
                    lyrics_lines.append(line)

        lyrics_text = "\n".join(lyrics_lines).strip()

        # Fallbacks if model misses some fields
        if not type_val:
            idx = len(songs)
            if idx < len(styles):
                type_val = styles[idx]
            elif styles:
                type_val = styles[0]
            else:
                type_val = "Custom Style"

        if not title_val:
            title_val = f"BTN Track {len(songs) + 1} – beyond the notz"

        if not vibe_val:
            vibe_val = "Moody, modern educational trap beat, beyond the notz."

        if not lyrics_text:
            lyrics_text = block

        songs.append(
            {
                "type": type_val,
                "title": title_val,
                "vibe_description": vibe_val,
                "lyrics": lyrics_text,
            }
        )

    # If nothing parsed, fallback: whole text as one song
    if not songs:
        main_style = styles[0] if styles else "Custom Style"
        songs.append(
            {
                "type": main_style,
                "title": "BTN Originals – beyond the notz",
                "vibe_description": "Raw model output. Use as creative reference.",
                "lyrics": raw_text,
            }
        )

    return {"songs": songs}


def generate_songs(
    text_content,
    styles,
    language_mix,
    artist_ref,
    focus_topic,
    additional_instructions,
    duration_minutes
):
    """
    Generates songs based on custom user parameters including exact duration in minutes.
    Uses a custom text format instead of JSON for robustness.
    """
    model = genai.GenerativeModel(
        "gemini-2.5-flash",
        generation_config={
            "max_output_tokens": 900  # keeps responses tighter & faster
        }
    )

    style_list_str = ", ".join(styles)

    language_instruction = "Balanced Hinglish"
    if language_mix < 30:
        language_instruction = "Mostly Hindi (with English scientific terms)"
    elif language_mix > 70:
        language_instruction = "Mostly English (with Hindi slang/connectors)"

    focus_instruction = (
        f"Focus specifically on this topic: {focus_topic}"
        if focus_topic
        else "Cover the most important exam topics from the chapter."
    )
    artist_instruction = (
        f"Take inspiration from the style of: {artist_ref}" if artist_ref else ""
    )
    custom_instructions = (
        f"USER SPECIAL INSTRUCTIONS: {additional_instructions}"
        if additional_instructions
        else ""
    )

    # --- DURATION TO STRUCTURE MAPPING ---
    if duration_minutes <= 1.5:
        structure = (
            "Quick Snippet: Intro ad-libs -> Verse 1 -> Chorus -> Outro "
            "(Approx 150 words)"
        )
    elif 1.5 < duration_minutes <= 2.5:
        structure = (
            "Standard Radio Edit: Intro ad-libs -> Verse 1 -> Chorus -> Verse 2 "
            "-> Chorus (Approx 200-250 words)"
        )
    elif 2.5 < duration_minutes <= 3.5:
        structure = (
            "Full Song: Intro ad-libs -> Verse 1 -> Chorus -> Verse 2 -> Chorus "
            "-> Bridge -> Chorus -> Outro (Approx 300-350 words)"
        )
    else:  # > 3.5 minutes
        structure = (
            "Extended Anthem: Intro ad-libs -> Verse 1 -> Chorus -> Verse 2 -> Chorus "
            "-> Solo/Bridge -> Verse 3 -> Chorus -> Outro (Approx 400+ words)"
        )

    prompt = f"""
You are an expert musical edu-tainer for Gen Z Indian students (Class 10 CBSE).

SOURCE MATERIAL (TEXTBOOK CHAPTER):
{text_content[:15000]}

USER REQUEST PARAMETERS:
- Target Styles: {style_list_str} (Generate one song for each selected style).
- Language Mix: {language_instruction}.
- Content Focus: {focus_instruction}.
- Artist Inspiration: {artist_instruction}.
- Target Duration: {duration_minutes} Minutes.
- Required Structure: {structure}
- Special Instructions: {custom_instructions}

TASK:
Create distinct musical lyrics for the selected styles to help students memorize the content. Do not mention book name.

REQUIREMENTS:
1. Educational Accuracy: You MUST include specific formulas, definitions, and lists from the text.
2. Structure: Strictly follow the "{structure}" outlined above to match the requested time length.
3. The Hook: The chorus must be extremely catchy and repetitive.
4. Signature Intro: Every song MUST start with a short line of random vocal ad-libs
   (for example: "yeah, ayy, okay, listen", etc.) followed IMMEDIATELY by a line
   that contains the exact phrase "beyond the notz". These ad-libs should vary
   between songs.
5. Signature Phrase in Hook: The phrase "beyond the notz" must also appear at
   least once in the hook/chorus of every song.
6. Overall Tone: Keep it a smooth Hindi–English hybrid with strong rhythm and
   study-focused storytelling.

OUTPUT FORMAT (VERY IMPORTANT):
Return the songs ONLY in the following exact text format.
Do NOT add any explanations or extra text outside this structure.

For EACH song, output:

=== SONG START ===
TYPE: <Style Name>
TITLE: <Creative Song Title>
VIBE: <Detailed prompt for AI Music Generator (Instruments, BPM, Mood, Vocals)>
LYRICS:
<Full lyrics here, line by line>
=== SONG END ===

Repeat this block for each generated song (one per selected style).
"""

    try:
        response = model.generate_content(prompt)
        raw_text = (response.text or "").strip()
        if not raw_text:
            st.error("AI Generation Error: Empty response from model.")
            return None
        return parse_songs_from_text(raw_text, styles)
    except Exception as e:
        st.error(f"AI Generation Error: {e}")
        return None


# --- SIDEBAR: CUSTOMIZATION ---
st.sidebar.header("🎛️ Studio Controls")

style_options = [
    "Desi Hip-Hop / Trap",
    "Punjabi Drill",
    "Bollywood Pop Anthem",
    "Lofi Study Beats",
    "Sufi Rock",
    "EDM / Party",
    "Old School 90s Rap",
]

selected_styles = st.sidebar.multiselect(
    "Select Music Styles",
    options=style_options,
    default=["Desi Hip-Hop / Trap"],
)

custom_style_input = st.sidebar.text_input(
    "➕ Add Custom Style (Optional)",
    placeholder="e.g. K-Pop, Heavy Metal, Ghazal",
)

st.sidebar.subheader("🗣️ Language Mixer")
lang_mix = st.sidebar.slider("Hindi vs English", 0, 100, 50)

st.sidebar.subheader("⏱️ Track Duration")
duration_minutes = st.sidebar.slider(
    "Length (Minutes)",
    min_value=1.0,
    max_value=5.0,
    value=2.5,
    step=0.5,
    format="%f min",
)

st.sidebar.subheader("✨ Fine Tuning")
artist_ref = st.sidebar.text_input(
    "Artist Inspiration (Optional)", placeholder="e.g. Divine, Arijit Singh"
)
focus_topic = st.sidebar.text_input(
    "Focus Topic (Optional)", placeholder="e.g. Soaps, Covalent Bonding"
)

additional_instructions = st.sidebar.text_area(
    "📝 Additional Instructions",
    placeholder="e.g. Use lots of rhyming slang, make the bridge about a specific formula...",
    height=100,
)

# --- MAIN UI ---
st.title("🎹 BTN Originals AI Pro")
st.markdown("Transform NCERT Chapters into custom songs, beyond the notz.")

if "song_data" not in st.session_state:
    st.session_state.song_data = None

uploaded_file = st.file_uploader("📂 Upload Chapter PDF", type=["pdf"])

if uploaded_file is not None:
    generate_btn = st.button("🚀 Generate Tracks", type="primary")

    if generate_btn:
        final_styles = selected_styles.copy()
        if custom_style_input and custom_style_input.strip() != "":
            if custom_style_input not in final_styles:
                final_styles.append(custom_style_input)

        if not api_key:
            st.warning("Please provide a Google API Key in the sidebar.")

        elif not final_styles:
            st.warning("Please select a style or add a custom one.")

        else:
            with st.spinner("📄 Extracting chapter text..."):
                chapter_text = extract_text_from_pdf(uploaded_file, max_pages=15)

            if chapter_text:
                with st.spinner("🎧 Composing tracks..."):
                    data = generate_songs(
                        chapter_text,
                        final_styles,
                        lang_mix,
                        artist_ref,
                        focus_topic,
                        additional_instructions,
                        duration_minutes,
                    )
                if data:
                    st.session_state.song_data = data
                    st.rerun()

# --- DISPLAY RESULTS ---
if st.session_state.song_data:
    st.divider()
    st.subheader("🎵 Generated Tracks")

    songs = st.session_state.song_data.get("songs", [])
    if songs:
        tabs = st.tabs([s["type"] for s in songs])

        for i, tab in enumerate(tabs):
            song = songs[i]
            with tab:
                col1, col2 = st.columns([1.5, 1])

                with col1:
                    st.subheader(f"Title: {song['title']}")
                    st.markdown("**Lyrics (beyond the notz)**")
                    # st.code gives a copy button automatically
                    st.code(song["lyrics"], language=None)

                with col2:
                    st.info("🎹 AI Style Prompt")
                    st.markdown("**Style for Suno**")
                    wrapped_vibe = textwrap.fill(song["vibe_description"], width=80)
                    st.code(wrapped_vibe, language=None)

                    st.markdown("---")
                    st.success("✨ Tip: Paste this directly into Suno.ai")

                    if st.button("🗑️ Clear Results", key=f"clear_{i}"):
                        st.session_state.song_data = None
                        st.rerun()
    else:
        st.error("No songs generated. Try specific topics.")
