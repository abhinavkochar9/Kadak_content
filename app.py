import streamlit as st

# ====== HARDENED IMPORT BLOCK (NEVER CRASHES) ======
def safe_import(name):
    try:
        return __import__(name)
    except Exception as e:
        st.write(f"⚠️ Optional module '{name}' failed to import:", e)
        return None

os = safe_import("os")
io = safe_import("io")
json = safe_import("json")
re = safe_import("re")
traceback = safe_import("traceback")
Counter = None
try:
    from collections import Counter
except:
    st.write("⚠️ Counter unavailable")

dotenv = safe_import("dotenv")
if dotenv:
    dotenv.load_dotenv()

genai = safe_import("google.generativeai")
pdfplumber = safe_import("pdfplumber")

# ====== ALWAYS SETUP STREAMLIT (NEVER FAILS) ======
st.set_page_config(page_title="BTN Originals", page_icon="🎵", layout="wide")
st.title("🎹 BTN Originals — SAFE MODE (Never Crashes)")

# ====== API KEY HANDLING (NEVER FAILS) ======
api_key = None
if os:
    api_key = os.getenv("GOOGLE_API_KEY")

api_key = api_key or st.sidebar.text_input("Google API Key (optional)", type="password")

if api_key and genai:
    try:
        genai.configure(api_key=api_key)
    except Exception as e:
        st.sidebar.error("⚠️ Gemini configure failed: " + str(e))

# ====== SAFE PDF TEXT EXTRACTOR (NEVER CRASHES) ======
def extract_text(uploaded):
    if not uploaded:
        return None
    if not pdfplumber:
        st.error("pdfplumber missing.")
        return None
    try:
        uploaded.seek(0)
        raw = uploaded.read()
        f = io.BytesIO(raw)
        out = []
        with pdfplumber.open(f) as pdf:
            for pg in pdf.pages[:20]:
                txt = pg.extract_text()
                if txt: out.append(txt)
        return "\n\n".join(out)
    except Exception as e:
        st.error("PDF ERROR:\n" + str(e))
        return None

# ====== ULTRA-SAFE AI CALL (NEVER CRASHES) ======
def safe_ai_song(text):
    # If no SDK → fallback
    if not (api_key and genai):
        return "fallback song:\nyeahh\nbeyond the notz\n[CHORUS]\nrevision on repeat"

    # Try both Gemini APIs safely
    prompt = f"Write a JSON song with 'beyond the notz'. Text:\n{text[:3000]}"

    # path 1
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        resp = model.generate_content(prompt)
        raw = getattr(resp, "text", "")
        return raw
    except Exception as e:
        st.write("⚠️ model path1 fail:", e)

    # path 2
    try:
        resp = genai.generate(model="gemini-pro", prompt=prompt)
        return resp.get("text", "")
    except Exception as e:
        st.write("⚠️ model path2 fail:", e)

    # final fallback
    return "yeahh\nbeyond the notz\n[CHORUS]\nlocal fallback"

# ====== UI ======
uploaded = st.file_uploader("Upload PDF")
if uploaded and st.button("Generate"):
    text = extract_text(uploaded)
    if text:
        st.success("PDF extracted!")
        song = safe_ai_song(text)
        st.subheader("Song Output")
        st.code(song)
    else:
        st.error("Could not read PDF.")

st.info("This SAFE MODE app **cannot crash**. If something fails, it shows a message instead of the black 'Oh no' screen.")
