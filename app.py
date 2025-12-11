import streamlit as st
import google.generativeai as genai
import pdfplumber 
from dotenv import load_dotenv
import os
import json

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

def extract_text_from_pdf(pdf_file):
    """
    Extracts raw text from an uploaded PDF file using pdfplumber.
    """
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

def generate_songs(text_content, styles, language_mix, artist_ref, focus_topic, additional_instructions, duration_minutes):
    """
    Generates songs based on custom user parameters including exact duration in minutes.
    (Kept same as original — returns JSON as before)
    """
    model = genai.GenerativeModel('gemini-2.5-flash') 
    
    style_list_str = ", ".join(styles)
    
    language_instruction = "Balanced Hinglish"
    if language_mix < 30:
        language_instruction = "Mostly Hindi (with English scientific terms)"
    elif language_mix > 70:
        language_instruction = "Mostly English (with Hindi slang/connectors)"
        
    focus_instruction = f"Focus specifically on this topic: {focus_topic}" if focus_topic else "Cover the most important exam topics from the chapter."
    artist_instruction = f"Take inspiration from the style of: {artist_ref}" if artist_ref else ""
    custom_instructions = f"USER SPECIAL INSTRUCTIONS: {additional_instructions}" if additional_instructions else ""

    # --- DURATION TO STRUCTURE MAPPING ---
    # AI writes text, not time, so we map minutes to structural complexity
    if duration_minutes <= 1.5:
        structure = "Quick Snippet: Verse 1 -> Chorus -> Outro (Approx 150 words)"
    elif 1.5 < duration_minutes <= 2.5:
        structure = "Standard Radio Edit: Verse 1 -> Chorus -> Verse 2 -> Chorus (Approx 200-250 words)"
    elif 2.5 < duration_minutes <= 3.5:
        structure = "Full Song: Intro -> Verse 1 -> Chorus -> Verse 2 -> Chorus -> Bridge -> Chorus -> Outro (Approx 300-350 words)"
    else: # > 3.5 minutes
        structure = "Extended Anthem: Intro -> Verse 1 -> Chorus -> Verse 2 -> Chorus -> Solo/Bridge -> Verse 3 -> Chorus -> Outro (Approx 400+ words)"

    prompt = f"""
    You are an expert musical edu-tainer for Gen Z Indian students (Class 10 CBSE).
    
    SOURCE MATERIAL (TEXTBOOK CHAPTER):
    {text_content[:25000]} 

    USER REQUEST PARAMETERS:
    - **Target Styles:** {style_list_str} (Generate one song for each selected style).
    - **Language Mix:** {language_instruction}.
    - **Content Focus:** {focus_instruction}.
    - **Artist Inspiration:** {artist_instruction}.
    - **Target Duration:** {duration_minutes} Minutes.
    - **Required Structure:** {structure}
    - **Special Instructions:** {custom_instructions}

    TASK:
    Create distinct musical lyrics for the selected styles to help students memorize the content. Do not mention book name.

    REQUIREMENTS:
    1. **Educational Accuracy:** You may include specific formulas, definitions, keywords and lists from the text.
    2. **Structure:** Strictly follow the "{structure}" outlined above to match the requested time length.
    3. **The Hook:** The chorus must be extremely catchy, groovy and repeat 5 times atleast.
    4. **Signature Intro (MANDATORY):**  
       - Every song MUST begin with aesthetic vocal ad-libs (e.g., “yeahh”, “okay”, “mmm-hmm”, “uh-huh”, “aye vibe”, etc.)  
       - These MUST be followed IMMEDIATELY by the line containing the exact phrase **“beyond the notz”**.  
       - This appears **only once** at the beginning unless the hook repeats it naturally.
    5. **Signature Phrase in Hook:** The phrase “beyond the notz” must appear **once more** inside the CHORUS of the song.

    OUTPUT FORMAT:
    Return ONLY a raw JSON object (no markdown) with this structure:
    {{
        "songs": [
            {{
                "type": "Style Name",
                "title": "Creative Song Title",
                "vibe_description": "Detailed prompt for AI Music Generator (Instruments, BPM, Mood, Vocals)",
                "lyrics": "Full lyrics here..."
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

def generate_summary20(text_content):
    """
    Generate a concise 20-line summary (one line = one short sentence/phrase) that includes the main keywords.
    Returns plain text with exactly up to 20 lines (model asked to return 20 lines).
    """
    model = genai.GenerativeModel('gemini-2.5-flash')
    snippet = text_content[:16000]  # limit size to keep it snappy
    prompt = f"""
Read the SOURCE MATERIAL below and produce a concise, informative summary of the chapter in EXACTLY 20 lines.
Each line should be short (one sentence or phrase), include the main keywords or concepts, and together they should cover the full chapter's key points and keywords.
Return ONLY the 20 lines, each on its own line, numbered or unnumbered — no extra explanation, no JSON, no code block markers.

SOURCE MATERIAL:
{snippet}
"""
    try:
        resp = model.generate_content(prompt)
        raw = (resp.text or "").strip()
        # Try to normalize into 20 lines:
        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        # If model returned a numbered list like "1. ..." remove numbers but keep lines
        processed = []
        for ln in lines:
            # strip leading numbering like "1.", "1)" or "1 -"
            stripped = ln
            if len(ln) > 2 and ln[0].isdigit():
                # remove leading numeric bullet if present
                import re
                stripped = re.sub(r'^\s*\d+[\.\)\-\:]*\s*', '', ln)
            processed.append(stripped)
        # If fewer than 20 lines, leave as-is (user can see). If more, take first 20.
        if len(processed) >= 20:
            processed = processed[:20]
        # If less than 20, attempt to pad by splitting long lines (simple fallback)
        if len(processed) < 20:
            extra_needed = 20 - len(processed)
            # naive split: take the longest lines and split them by comma
            longs = sorted(((i, len(l)) for i, l in enumerate(processed)), key=lambda x: -x[1])
            i = 0
            while extra_needed > 0 and i < len(longs):
                idx = longs[i][0]
                parts = [p.strip() for p in processed[idx].split(",") if p.strip()]
                if len(parts) > 1:
                    # replace the original with first part, insert rest
                    processed[idx:idx+1] = parts
                    extra_needed = 20 - len(processed)
                    longs = sorted(((i, len(l)) for i, l in enumerate(processed)), key=lambda x: -x[1])
                    i = 0
                    continue
                i += 1
            # if still short, append empty placeholders (should be rare)
            while len(processed) < 20:
                processed.append("—")
        # join back to text
        final_text = "\n".join(processed[:20])
        return final_text
    except Exception as e:
        st.error(f"Summary Generation Error: {e}")
        return None

# --- SIDEBAR: CUSTOMIZATION ---
st.sidebar.header("🎛️ Studio Controls")

style_options = [
    "Desi Hip-Hop / Trap", "HOOKY & VIRAL MELODIC RAP", 
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
    "➕ Add Custom Style (Optional)", 
    placeholder="e.g. K-Pop, Heavy Metal, Ghazal"
)

st.sidebar.subheader("🗣️ Language Mixer")
lang_mix = st.sidebar.slider("Hindi vs English", 0, 100, 50)

# --- NEW: MINUTE SLIDER ---
st.sidebar.subheader("⏱️ Track Duration")
duration_minutes = st.sidebar.slider(
    "Length (Minutes)", 
    min_value=1.0, 
    max_value=5.0, 
    value=2.5, 
    step=0.5,
    format="%f min"
)
# --------------------------

st.sidebar.subheader("✨ Fine Tuning")
artist_ref = st.sidebar.text_input("Artist Inspiration (Optional)", placeholder="e.g. Divine, Arijit Singh")
focus_topic = st.sidebar.text_input("Focus Topic (Optional)", placeholder="e.g. Soaps, Covalent Bonding")

additional_instructions = st.sidebar.text_area(
    "📝 Additional Instructions",
    placeholder="e.g. Use lots of rhyming slang, make the bridge about a specific formula...",
    height=100
)

# --- MAIN UI ---
st.title("🎹 BTN Originals AI Pro")
st.markdown("Transform NCERT Chapters into Custom Songs.")

if "song_data" not in st.session_state:
    st.session_state.song_data = None
if "summary20_text" not in st.session_state:
    st.session_state.summary20_text = None

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
            with st.spinner("🎧 Extraction & Composing... (This may take 30 seconds)"):
                chapter_text = extract_text_from_pdf(uploaded_file)
                
                if chapter_text:
                    # Pass duration_minutes to the generator
                    data = generate_songs(
                        chapter_text, 
                        final_styles, 
                        lang_mix, 
                        artist_ref, 
                        focus_topic, 
                        additional_instructions,
                        duration_minutes  # <--- NEW ARGUMENT
                    )
                    if data:
                        st.session_state.song_data = data
                        # generate 20-line summary to verify PDF read
                        summary_text = generate_summary20(chapter_text)
                        st.session_state.summary20_text = summary_text
                        st.rerun()

# --- DISPLAY RESULTS ---
if st.session_state.song_data:
    st.divider()
    st.subheader("🎵 Generated Tracks")
    
    songs = st.session_state.song_data.get("songs", [])
    if songs:
        tabs = st.tabs([s['type'] for s in songs])
        
        for i, tab in enumerate(tabs):
            song = songs[i]
            with tab:
                col1, col2 = st.columns([1.5, 1])
                with col1:
                    st.subheader(f"Title: {song['title']}")
                    # COPY-FRIENDLY LYRICS (built-in copy icon)
                    st.markdown("**Lyrics**")
                    st.code(song['lyrics'], language=None)
                with col2:
                    st.info("🎹 Suno AI Style Prompt")
                    st.markdown("**Prompt for Suno / AI DAW**")
                    # COPY-FRIENDLY PRODUCTION PROMPT
                    st.code(song['vibe_description'], language=None)

                    st.markdown("---")
                    st.success("✨ Tip: Use this prompt in Suno.ai")
                    
                    if st.button(f"🗑️ Clear Results", key=f"clear_{i}"):
                        st.session_state.song_data = None
                        st.session_state.summary20_text = None
                        st.rerun()
    else:
        st.error("No songs generated. Try specific topics.")
    
    # --- 20-line summary block shown after the songs ---
    st.divider()
    st.subheader("🔎 Chapter check: Concise 20-line summary with keywords")
    st.markdown("This helps verify the PDF content the model read. Copyable below.")
    if st.session_state.summary20_text:
        st.code(st.session_state.summary20_text, language=None)
    else:
        st.info("Summary not generated. Re-run generation to create the 20-line summary.")
