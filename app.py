import streamlit as st
import os, io, json, re, traceback
from dotenv import load_dotenv
from collections import Counter

# === SAFE OPTIONAL IMPORTS ===
try:
    import google.generativeai as genai
    GENAI = True
except:
    genai = None
    GENAI = False

try:
    import pdfplumber
except:
    pdfplumber = None

# === BASIC SETUP ===
load_dotenv()
st.set_page_config(page_title="BTN Originals 🎧", page_icon="🎹", layout="wide")

# === API KEY ===
api_key = os.getenv("GOOGLE_API_KEY") or st.sidebar.text_input("Enter Google API Key", type="password")
if api_key and GENAI:
    try:
        genai.configure(api_key=api_key)
    except Exception as e:
        st.sidebar.error("API Key Error: " + str(e))

STOPWORDS = set("the and for with that this from are is was were be by to of in on as an at it its which a an".split())

# === UTILS ===
def extract_pdf_text(file):
    if pdfplumber is None:
        st.error("pdfplumber not installed.")
        return None
    try:
        file.seek(0)
        raw = file.read()
        f = io.BytesIO(raw)
        out = []
        with pdfplumber.open(f) as pdf:
            for p in pdf.pages[:35]:
                txt = p.extract_text()
                if txt:
                    out.append(txt.strip())
        return "\n\n".join(out)
    except Exception as e:
        st.error("PDF error: " + str(e))
        return None

def local_keywords(text):
    txt = re.sub(r"[^A-Za-z0-9\s]", " ", text)
    tokens = [t.lower() for t in txt.split() if len(t) > 3]
    tokens = [t for t in tokens if t not in STOPWORDS]
    return ", ".join([w for w, _ in Counter(tokens).most_common(10)]) or "—"

def get_keywords_per_page(big_text):
    pages = [p.strip() for p in big_text.split("\n\n") if p.strip()]
    out = []
    for p in pages:
        out.append(local_keywords(p))
    return "\n".join(out)

def clean_lyrics(s):
    if not s: return ""
    s = re.sub(r"\$\$.*?\$\$", " [formula] ", s, flags=re.S)
    s = re.sub(r"\$.*?\$", " [formula] ", s, flags=re.S)
    s = re.sub(r"\b\d{4,}\b", " [num] ", s)
    return s.strip()

# === AI SONG GENERATOR (SAFE) ===
def generate_song(text, style, extra):
    snippet = text[:8000]

    prompt = f"""
Write a Hinglish study-friendly song in JSON only.
Must contain:
- an intro with adlibs
- the line "beyond the notz" once after intro
- CHORUS repeated 3 times minimum
- short 4 VERSES
Return JSON:
{{
 "songs": [
   {{
     "type": "{style}",
     "title": "Study Track",
     "vibe_description": "simple vibe",
     "lyrics": "full lyrics text"
   }}
 ]
}}
TEXT:
{snippet}
Extra: {extra}
"""

    # If no API key or no SDK → fallback local
    if not (api_key and GENAI):
        lyrics = """yeahh
beyond the notz
[CHORUS]
study karo, vibe karo
[VERSE 1]
concepts short, points tight
[CHORUS]
study karo, vibe karo
[VERSE 2]
examples yaad, notes light
[CHORUS]
study karo, vibe karo
"""
        return {
            "songs": [{
                "type": style,
                "title": "Fallback Track",
                "vibe_description": "local generator",
                "lyrics": lyrics
            }]
        }

    # Model path 1
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        resp = model.generate_content(prompt)
        raw = getattr(resp, "text", str(resp))
        raw = raw.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(raw)
        parsed["songs"][0]["lyrics"] = clean_lyrics(parsed["songs"][0]["lyrics"])
        return parsed
    except:
        pass

    # Model path 2 fallback
    try:
        resp = genai.generate(model="gemini-pro", prompt=prompt)
        text = resp.get("text", "")
        parsed = json.loads(text)
        return parsed
    except:
        pass

    # Final fallback
    lyrics = """yeahh
beyond the notz
[CHORUS]
fallback mode active
"""
    return {
        "songs": [{
            "type": style,
            "title": "Local Fallback",
            "vibe_description": "AI failed",
            "lyrics": lyrics
        }]
    }

# === UI ===
st.title("🎹 BTN Originals — Stable Edition")

style = st.sidebar.selectbox("Style", ["Desi Hip-Hop", "Lofi", "Trap", "Pop"])
extra = st.sidebar.text_input("Extra instructions")
uploaded = st.file_uploader("Upload PDF", type=["pdf"])

if uploaded and st.button("Generate"):
    text = extract_pdf_text(uploaded)
    if text:
        song_data = generate_song(text, style, extra)
        st.session_state["song"] = song_data
        st.session_state["keys"] = get_keywords_per_page(text)
        st.experimental_rerun()

# === SHOW RESULTS ===
if "song" in st.session_state:
    s = st.session_state["song"]["songs"][0]
    st.subheader(s["title"])
    st.code(s["lyrics"])

if "keys" in st.session_state:
    st.subheader("Keywords per page:")
    st.code(st.session_state["keys"])
