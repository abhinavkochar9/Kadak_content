import io, os, json, re, random
from PIL import Image, ImageDraw, ImageFilter
import streamlit as st
import google.generativeai as genai
import pdfplumber
from dotenv import load_dotenv

# --- CONFIG ---
load_dotenv()
st.set_page_config("BTN Originals AI Pro 🎧", "🎹", layout="wide")
API_IN_ENV = "GOOGLE_API_KEY" in os.environ
api_key = os.environ.get("GOOGLE_API_KEY") or st.sidebar.text_input("Enter Google API Key", type="password")
if api_key:
    try: genai.configure(api_key=api_key)
    except Exception as e: st.error(f"API Key Error: {e}")
else:
    st.sidebar.warning("Enter Google API key to enable generation.")

# --- Helpers (concise) ---
def read_pdf(uploaded_file, max_pages=None):
    """Return list of page texts and full combined text."""
    raw = uploaded_file.read()
    fileobj = io.BytesIO(raw)
    pages = []
    try:
        with pdfplumber.open(fileobj) as pdf:
            for i, p in enumerate(pdf.pages):
                if max_pages and i >= max_pages: break
                t = p.extract_text() or ""
                pages.append(t.strip())
    except Exception as e:
        st.error(f"PDF read error: {e}")
        return None, ""
    return pages, "\n".join(pages)

def try_parse_json(raw):
    try: return json.loads(raw)
    except: 
        s = raw.find("{"); e = raw.rfind("}")
        if s!=-1 and e!=-1 and e>s:
            try: return json.loads(raw[s:e+1])
            except: return None
    return None

def call_model(prompt, max_output_tokens=1200):
    if not api_key: return None
    model = genai.GenerativeModel("gemini-2.5-flash")
    try:
        r = model.generate_content(prompt)
        return (r.text or "").strip()
    except Exception as e:
        st.error(f"Model error: {e}")
        return None

# --- Song prompt builder (keeps your rules) ---
def build_song_prompt(text_snippet, styles, lang_mix, artist_ref, focus_topic, extra, duration_minutes):
    style_list = ", ".join(styles)
    lang = "Balanced Hinglish"
    if lang_mix < 30: lang = "Mostly Hindi with English scientific terms"
    if lang_mix > 70: lang = "Mostly English with Hindi connectors"
    if artist_ref: artist_txt = f"Take inspiration from: {artist_ref}"
    else: artist_txt = ""
    structure = ("Short" if duration_minutes<=1.5 else
                 "Radio" if duration_minutes<=2.5 else
                 "Full" if duration_minutes<=3.5 else "Extended")
    style_req = ("melodic rap soulmate style; confident; classroom-friendly but powerful; addictive; "
                 "legendary; viral; catchy; enthusiastic; Hindi+English; melody; cinematic rise; groove; "
                 "pronounce pure English words correctly")
    prompt = f"""
You are an expert musical edu-tainer for Gen Z students.

SOURCE:
{text_snippet[:100000]}

INPUTS:
- Styles: {style_list}
- Language: {lang}
- Focus: {focus_topic or 'general'}
- {artist_txt}
- Duration-type: {structure}
- Extra: {extra}

REQUIREMENTS:
1) FIRST lines: short aesthetic ad-libs (e.g., 'yeahh', 'aye vibe', 'mmm-hmm'), then a line with exactly:
beyond the notz
2) SECTION ORDER (strict): [CHORUS] [VERSE 1] [CHORUS] [VERSE 2] [CHORUS] [VERSE 3] [CHORUS] [VERSE 4] [CHORUS]
   Chorus appears at least 5 times. Verses max 6 lines each.
3) Chorus must include 'beyond the notz' at least once.
4) Label sections like [CHORUS], [VERSE 1], etc.
5) Include formulas/definitions/keywords inside verses only.
6) Maintain style: {style_req}

OUTPUT: Return ONLY valid JSON:
{{
  "songs": [
    {{
      "type": "Style Name",
      "title": "Creative Song Title",
      "vibe_description": "Detailed production prompt (include style requirements).",
      "lyrics": "Full lyrics with labels and newlines preserved."
    }}
  ]
}}
"""
    return prompt

# --- Keywords per page (10-20 per page) ---
def keywords_per_page(pages, per_page_min=10, per_page_max=20, max_pages=20):
    results = []
    model = genai.GenerativeModel("gemini-2.5-flash")
    for i, page in enumerate(pages[:max_pages], start=1):
        if not page.strip(): 
            results.append((i, [])); continue
        prompt = f"""Read the PAGE text below and return a list of {per_page_min}-{per_page_max} short keywords or short phrases (no sentences), one per line, that capture the main terms/concepts on this page. Return ONLY the list, nothing else.

PAGE:
{page[:8000]}
"""
        try:
            r = model.generate_content(prompt)
            raw = (r.text or "").strip()
            lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
            # trim/pad to requested count
            count = min(per_page_max, max(per_page_min, len(lines)))
            lines = lines[:count]
            results.append((i, lines))
        except Exception as e:
            results.append((i, [f"Error generating keywords: {e}"]))
    return results

# --- Auto Suno style extractor (one-line) ---
def generate_suno_style(vibe_description, lyrics):
    prompt = f"""Read the vibe_description and lyrics below. Suggest a single concise Suno.ai style prompt (1-2 sentences) that fits the song perfectly, mentioning instruments, tempo/bpm hint, mood, and lead vocal type. Return ONLY the single line.

VIBE:
{vibe_description[:2000]}

LYRICS:
{lyrics[:2000]}
"""
    return call_model(prompt) or "Suno style: modern melodic-rap, mid-tempo, warm synths, groovy drums, emotive male lead."

# --- Simple 1:1 abstract cover generator (no words/formulas) ---
def create_abstract_cover(theme_keywords, size=1024):
    # derive palette from keywords (simple hash -> color)
    seed = sum(ord(c) for c in (" ".join(theme_keywords) or "btn"))
    random.seed(seed)
    def rand_color():
        return tuple(int(random.random()*160 + 60) for _ in range(3))
    c1, c2 = rand_color(), rand_color()
    img = Image.new("RGB", (size, size), c1)
    draw = ImageDraw.Draw(img)
    # gradient + soft ellipse
    for i in range(size):
        r = int(c1[0] + (c2[0]-c1[0]) * (i/size))
        g = int(c1[1] + (c2[1]-c1[1]) * (i/size))
        b = int(c1[2] + (c2[2]-c1[2]) * (i/size))
        draw.line([(0,i),(size,i)], fill=(r,g,b))
    # add blurred shapes
    for _ in range(6):
        ellipse = Image.new("RGBA", (size, size))
        ed = ImageDraw.Draw(ellipse)
        x0 = random.randint(-size//4, size//2); y0 = random.randint(-size//4, size//2)
        w = random.randint(size//3, size*2//3)
        ed.ellipse([x0,y0,x0+w,y0+w], fill=rand_color()+(120,))
        img = Image.alpha_composite(img.convert("RGBA"), ellipse).convert("RGB")
    img = img.filter(ImageFilter.GaussianBlur(radius=6))
    return img

# --- UI / Main (concise) ---
st.title("🎹 BTN Originals AI Pro")
st.markdown("Transform NCERT Chapters into Custom Songs. (May take 2–3 minutes for best results)")

# sidebar inputs (short)
styles_list = ["Desi Hip-Hop / Trap","HOOKY & VIRAL MELODIC RAP","Punjabi Drill","Bollywood Pop Anthem","Lofi Study Beats","Sufi Rock","EDM / Party","Old School 90s Rap"]
selected_styles = st.sidebar.multiselect("Select Styles", styles_list, default=[styles_list[0]])
custom_style = st.sidebar.text_input("➕ Add Custom Style")
if custom_style.strip(): 
    if custom_style not in selected_styles: selected_styles.append(custom_style)
lang_mix = st.sidebar.slider("Hindi vs English", 0,100,50)
duration_minutes = st.sidebar.slider("Length (min)",1.0,5.0,2.5,0.5)
artist_ref = st.sidebar.text_input("Artist Inspiration")
focus_topic = st.sidebar.text_input("Focus Topic")
extra_instr = st.sidebar.text_area("Extra instructions", height=80)
uploaded = st.file_uploader("📂 Upload Chapter PDF", type=["pdf"])
generate = st.button("🚀 Generate Tracks")

if uploaded and generate:
    # read pages (no page limit here, but keywords will limit to first 20 pages)
    pages, full_text = read_pdf(uploaded)
    if not full_text:
        st.error("Could not extract text from PDF.")
    else:
        with st.spinner("Composing songs (this may take up to 2-3 minutes)..."):
            prompt = build_song_prompt(full_text, selected_styles, lang_mix, artist_ref, focus_topic, extra_instr, duration_minutes)
            raw = call_model(prompt)
            parsed = try_parse_json(raw or "")
            if parsed and parsed.get("songs"):
                songs = parsed["songs"]
            else:
                # fallback single raw song
                songs = [{
                    "type": selected_styles[0] if selected_styles else "Custom",
                    "title": "BTN fallback output",
                    "vibe_description": raw or "No vibe returned.",
                    "lyrics": raw or "No lyrics returned."
                }]
                st.warning("Model didn't return clean JSON; showing fallback raw output.")
            st.session_state.song_data = {"songs": songs}
        # generate per-page keywords (may take time)
        with st.spinner("Extracting keywords per page (10-20 each)..."):
            page_keywords = keywords_per_page(pages, 10, 20, max_pages=20)
            st.session_state.page_keywords = page_keywords
        # generate 20-line summary (longer)
        with st.spinner("Generating 20-line summary..."):
            summary_prompt = f"Summarize the SOURCE below into exactly 20 short lines (one line each) covering key points and keywords. SOURCE:\n{full_text[:120000]}"
            summary_raw = call_model(summary_prompt) or ""
            # normalize lines to 20
            lines = [ln.strip() for ln in summary_raw.splitlines() if ln.strip()][:20]
            while len(lines) < 20: lines.append("—")
            st.session_state.summary20_text = "\n".join(lines)
        # auto suno style and cover generation for first song
        first = st.session_state.song_data["songs"][0]
        with st.spinner("Auto-generating Suno style and cover..."):
            suno_style = generate_suno_style(first.get("vibe_description",""), first.get("lyrics",""))
            st.session_state.auto_suno_style = suno_style
            # choose theme keywords for cover from page keywords or summary
            theme_kw = [kw for _, kws in st.session_state.page_keywords for kw in kws][:6] or []
            cover_img = create_abstract_cover(theme_kw, size=1024)
            cover_bytes = io.BytesIO()
            cover_img.save(cover_bytes, format="PNG")
            cover_bytes.seek(0)
            st.session_state.cover_bytes = cover_bytes

# --- Display Results ---
if st.session_state.get("song_data"):
    st.divider()
    st.subheader("🎵 Generated Tracks")
    songs = st.session_state.song_data["songs"]
    tabs = st.tabs([s.get("type", f"Track {i+1}") for i,s in enumerate(songs)])
    for i, tab in enumerate(tabs):
        s = songs[i]
        with tab:
            col1, col2 = st.columns([1.6,1])
            with col1:
                st.subheader(s.get("title","Untitled"))
                st.markdown("**Lyrics**")
                # expanders avoid copy-icon overlap and show full text
                with st.expander("Show lyrics (copy-button included)"):
                    st.code(s.get("lyrics",""), language=None)
            with col2:
                st.info("🎹 Auto Suno Style (AI-suggested)")
                # separate container for style so copy icon doesn't overlap
                with st.expander("Suno.ai style (copyable)"):
                    st.code(st.session_state.get("auto_suno_style", s.get("vibe_description","")), language=None)
                st.markdown("")
                st.success("✨ Tip: Paste this into Suno.ai (or tweak BPM/instruments).")
                if st.button(f"🗑️ Clear Results", key=f"clear_{i}"):
                    st.session_state.pop("song_data", None)
                    st.session_state.pop("summary20_text", None)
                    st.session_state.pop("page_keywords", None)
                    st.session_state.pop("auto_suno_style", None)
                    st.session_state.pop("cover_bytes", None)
                    st.experimental_rerun()

    # cover + summary + page keywords
    st.divider()
    st.subheader("🖼️ Auto-generated 1:1 Spotify-style cover (no words/formula)")
    if st.session_state.get("cover_bytes"):
        st.image(st.session_state["cover_bytes"].getvalue(), use_column_width=False, width=320)
        st.download_button("Download cover (PNG)", st.session_state["cover_bytes"].getvalue(), file_name="cover.png", mime="image/png")
    st.divider()
    st.subheader("📝 20-line summary (chapter check)")
    if st.session_state.get("summary20_text"):
        st.code(st.session_state["summary20_text"], language=None)

    st.divider()
    st.subheader("🔎 10–20 keywords per page (first 20 pages)")
    if st.session_state.get("page_keywords"):
        for pnum, kws in st.session_state["page_keywords"]:
            st.markdown(f"**Page {pnum}**")
            st.code("\n".join(kws), language=None)
    else:
        st.info("No page keywords generated.")

else:
    st.info("Upload a PDF, choose style(s), and press Generate. Note: full-run may take up to 2–3 minutes for best viral output.")
