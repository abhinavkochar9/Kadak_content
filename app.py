import streamlit as st
import google.generativeai as genai
import pdfplumber  # <--- REPLACED PyPDF2 WITH PDFPLUMBER
from dotenv import load_dotenv
import os
import json

# --- CONFIGURATION & SETUP ---
load_dotenv()

# Page Config
st.set_page_config(
    page_title="StudyBeats AI Pro 🎧",
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
    This is much more robust than PyPDF2 and handles weird characters better.
    """
    text = ""
    try:
        # pdfplumber requires the file to be treated as a path or file-like object
        with pdfplumber.open(pdf_file) as pdf:
            for page in pdf.pages:
                # Extract text and handle potential None returns
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        st.error(f"Error reading PDF: {e}")
        return None
    return text

def generate_songs(text_content, styles, language_mix, artist_ref, focus_topic):
    """
    Generates songs based on custom user parameters.
    """
    model = genai.GenerativeModel('gemini-2.5-pro') 
    
    style_list_str = ", ".join(styles)
    
    language_instruction = "Balanced Hinglish"
    if language_mix < 30:
        language_instruction = "Mostly Hindi (with English scientific terms)"
    elif language_mix > 70:
        language_instruction = "Mostly English (with Hindi slang/connectors)"
        
    focus_instruction = f"Focus specifically on this topic: {focus_topic}" if focus_topic else "Cover the most important exam topics from the chapter."
    artist_instruction = f"Take inspiration from the style of: {artist_ref}" if artist_ref else ""

    prompt = f"""
    You are an expert musical edu-tainer for Gen Z Indian students (Class 10 CBSE).
    
    SOURCE MATERIAL (TEXTBOOK CHAPTER):
    {text_content[:25000]} 

    USER REQUEST PARAMETERS:
    - **Target Styles:** {style_list_str} (Generate one song for each selected style).
    - **Language Mix:** {language_instruction}.
    - **Content Focus:** {focus_instruction}.
    - **Artist Inspiration:** {artist_instruction}.

    TASK:
    Create distinct musical lyrics for the selected styles to help students memorize the content.

    REQUIREMENTS:
    1. **Educational Accuracy:** You MUST include specific formulas, definitions, and lists from the text.
    2. **Structure:** Verse-Chorus-Verse-Bridge-Chorus.
    3. **The Hook:** The chorus must be extremely catchy and repetitive.

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
        # Clean up potential markdown code blocks
        cleaned_text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(cleaned_text)
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
    "Old School 90s Rap"
]
selected_styles = st.sidebar.multiselect(
    "Select Music Styles", 
    options=style_options, 
    default=["Desi Hip-Hop / Trap", "Bollywood Pop Anthem"]
)

st.sidebar.subheader("🗣️ Language Mixer")
lang_mix = st.sidebar.slider("Hindi vs English", 0, 100, 50)

st.sidebar.subheader("✨ Fine Tuning")
artist_ref = st.sidebar.text_input("Artist Inspiration (Optional)", placeholder="e.g. Divine, Arijit Singh")
focus_topic = st.sidebar.text_input("Focus Topic (Optional)", placeholder="e.g. Soaps, Covalent Bonding")

# --- MAIN UI ---
st.title("🎹 StudyBeats AI Pro")
st.markdown("Transform NCERT Chapters into Custom Songs.")

if "song_data" not in st.session_state:
    st.session_state.song_data = None

uploaded_file = st.file_uploader("📂 Upload Chapter PDF", type=["pdf"])

if uploaded_file is not None:
    generate_btn = st.button("🚀 Generate Tracks", type="primary")
    
    if generate_btn:
        if not api_key:
            st.warning("Please provide a Google API Key in the sidebar.")
        elif not selected_styles:
            st.warning("Please select at least one music style.")
        else:
            with st.spinner("🎧 Extraction & Composing... (This may take 30 seconds)"):
                # Extract text using the new robust function
                chapter_text = extract_text_from_pdf(uploaded_file)
                
                if chapter_text:
                    data = generate_songs(chapter_text, selected_styles, lang_mix, artist_ref, focus_topic)
                    if data:
                        st.session_state.song_data = data
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
                    st.text_area("Lyrics", value=song['lyrics'], height=600, key=f"lyrics_{i}")
                with col2:
                    st.info("🎹 **AI Production Prompt**")
                    st.markdown(f"_{song['vibe_description']}_")
                    st.markdown("---")
                    st.success("✨ **Tip:** Use this prompt in Suno.ai")
                    
                    if st.button(f"🗑️ Clear Results", key=f"clear_{i}"):
                        st.session_state.song_data = None
                        st.rerun()
    else:
        st.error("No songs generated. Try specific topics.")