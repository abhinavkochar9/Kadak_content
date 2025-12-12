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

# Page Config
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

# --- HELPER FUNCTIONS ---

def extract_text_from_pdf(pdf_file, max_pages=35):
    """
    Extracts raw text from an uploaded PDF file using pdfplumber.
    Reads up to `max_pages` pages (default 35).
    Uses BytesIO to be safe with uploaded files from Streamlit.
    """
    text = ""
    try:
        # ensure we can read from start
        try:
            pdf_file.seek(0)
        except Exception:
            pass
        raw_bytes = pdf_file.read()
        file_obj = io.BytesIO(raw_bytes)
        with pdfplumber.open(file_obj) as pdf:
            total_pages = len(pdf.pages)
            pages_to_read = min(total_pages, max_pages)
            for idx in range(pages_to_read):
                page = pdf.pages[idx]
                page_text = page.extract_text()
                if page_text:
                    # add a page break marker to help the model if needed
                    text += page_text + "\n\n"
    except Exception as e:
        tb = traceback.format_exc()
        st.error(f"Error reading PDF: {e}\n\n{tb}")
        return None
    return text

def generate_songs(text_content, styles, language_mix, artist_ref, focus_topic, additional_instructions, duration_minutes):
    """
    Generates songs based on custom user parameters including exact duration in minutes.
    Uses a larger slice of the text (up to ~200k chars) to cover more pages.
    """
    if not api_key:
        st.error("Missing Google API key. Please enter it in the sidebar.")
        return None

    try:
        model = genai.GenerativeModel('gemini-2.5-flash') 
    except Exception as e:
        st.error(f"Model initialization error: {e}")
        return None
    
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
    if duration_minutes <= 1.5:
        structure = "Quick Snippet: Verse 1 -> Chorus -> Outro (Approx 150 words)"
    elif 1.5 < duration_minutes <= 2.5:
        structure = "Standard Radio Edit: Verse 1 -> Chorus -> Verse 2 -> Chorus (Approx 200-250 words)"
    elif 2.5 < duration_minutes <= 3.5:
        structure = "Full Song: Intro -> Verse 1 -> Chorus -> Verse 2 -> Chorus -> Bridge -> Chorus -> Outro (Approx 300-350 words)"
    else: # > 3.5 minutes
        structure = "Extended Anthem: Intro -> Verse 1 -> Chorus -> Verse 2 -> Chorus -> Solo/Bridge -> Verse 3 -> Chorus -> Outro (Approx 400+ words)"

    # Use a larger slice so model sees more content (up to ~200k chars)
    # The extract_text_from_pdf already limits pages; slicing here is an additional safety.
    source_snippet = text_content[:200000]

    prompt = f"""
    You are an expert musical edu-tainer for Gen Z Indian students (Class 10 CBSE).
    
    SOURCE MATERIAL (TEXTBOOK CHAPTER) - up to 35 pages:
    {source_snippet}

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
    1. Educational Accuracy: Include specific formulas, definitions, and lists from the text (where relevant).
    2. Structure: Strictly follow the structure specified above.
    3. Hook: Chorus must be catchy and repetitive.

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
    except Exception as e:
        tb = traceback.format_exc()
        st.error(f"AI call error: {e}\n\n{tb}")
        return None

    # Safely get text
    raw_text = ""
    try:
        raw_text = response.text if hasattr(response, "text") else str(response)
    except Exception:
        raw_text = str(response)

    cleaned_text = raw_text.replace("```json", "").replace("```", "").strip()

    # Try to parse JSON; fallback to safe structure if parsing fails
    try:
        return json.loads(cleaned_text)
    except Exception:
        st.warning("Model output was not valid JSON — returning raw output in a fallback song. Check the 'Style Prompt' box for details.")
        fallback = {
            "songs": [
                {
                    "type": styles[0] if styles else "Custom Style",
                    "title": "BTN Originals - fallback (raw output)",
                    "vibe_description": "Fallback: raw model output; please inspect.",
                    "lyrics": cleaned_text
                }
            ]
        }
        return fallback

# --- SIDEBAR: CUSTOMIZATION ---
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
st.title("🎹 BTN Originals")
st.markdown("Transform NCERT Chapters into Custom Songs.")

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
            with st.spinner("🎧 Extraction & Composing... (This may take longer for many pages)"):
                # Read up to 35 pages end-to-end
                chapter_text = extract_text_from_pdf(uploaded_file, max_pages=35)
                
                if chapter_text:
                    # Pass duration_minutes to the generator
                    data = generate_songs(
                        chapter_text, 
                        final_styles, 
                        lang_mix, 
                        artist_ref, 
                        focus_topic, 
                        additional_instructions,
                        duration_minutes
                    )
                    if data:
                        st.session_state.song_data = data
                        st.rerun()

# --- utility: tiny html for copy button ---
def copy_button_html(text_to_copy, element_id):
    # Use json.dumps to safely escape text for JS
    js_text = json.dumps(text_to_copy)
    html = f"""
    <div style="display:flex; gap:8px; align-items:center;">
      <button onclick='navigator.clipboard.writeText({js_text})' 
              style="
                padding:6px 10px; border-radius:6px; border:1px solid #ddd; 
                background:#fff; cursor:pointer; font-weight:600;">
        📋 Copy
      </button>
    </div>
    """
    return html

# --- DISPLAY RESULTS ---
if st.session_state.song_data:
    st.divider()
    st.subheader("🎵 Generated Tracks")
    
    songs = st.session_state.song_data.get("songs", [])
    if songs:
        tabs = st.tabs([s.get('type', f"Track {i+1}") for i, s in enumerate(songs)])
        
        for i, tab in enumerate(tabs):
            song = songs[i]
            with tab:
                col1, col2 = st.columns([1.5, 1])
                with col1:
                    st.subheader(f"Title: {song.get('title','Untitled')}")
                    st.markdown("**Lyrics**")
                    st.code(song.get('lyrics', ''), language=None)
                    # copy button html
                    lyrics_text = song.get('lyrics', '')
                    chtml = copy_button_html(lyrics_text, f"lyrics_copy_{i}")
                    components.html(chtml, height=44)
                with col2:
                    st.info("🎹 ** Suno AI Style Prompt**")
                    st.markdown(f"_{song.get('vibe_description','')}_")
                    # copy button for vibe description
                    vibe_text = song.get('vibe_description', '')
                    vhtml = copy_button_html(vibe_text, f"vibe_copy_{i}")
                    components.html(vhtml, height=44)
                    st.markdown("---")
                    st.success("✨ Tip: Use this prompt in Suno.ai")
                    
                    if st.button(f"🗑️ Clear Results", key=f"clear_{i}"):
                        st.session_state.song_data = None
                        st.rerun()
    else:
        st.error("No songs generated. Try specific topics.")
