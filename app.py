# app.py
import io, os, json, random, time
from PIL import Image, ImageDraw, ImageFilter
import streamlit as st
import google.generativeai as genai
import pdfplumber
from dotenv import load_dotenv

# ----- config -----
load_dotenv()
st.set_page_config(page_title="BTN Originals AI Pro 🎧", page_icon="🎹", layout="wide")
API_ENV_KEY = "GOOGLE_API_KEY"
api_key = os.environ.get(API_ENV_KEY) or st.sidebar.text_input("Enter Google API Key", type="password")
if api_key:
    try:
        genai.configure(api_key=api_key)
    except Exception as e:
        st.sidebar.error(f"API Key config error: {e}")
else:
    st.sidebar.warning("Enter Google API key to enable generation.")

# ----- helpers -----
def safe_read_pdf(uploaded_file):
    try:
        uploaded_file.seek(0)
        raw = uploaded_file.read()
        fileobj = io.BytesIO(raw)
        pages = []
        with pdfplumber.open(fileobj) as pdf:
            for p in pdf.pages:
                pages.append((p.extract_text() or "").strip())
        return pages, "\n".join(pages)
    except Exception as e:
        st.error(f"PDF read error: {e}")
        return None, ""

def call_model_text(prompt, max_output_tokens=1200):
    if not api_key:
        st.error("Missing API key.")
        return None
    model = genai.GenerativeModel("gemini-2.5-flash")
    try:
        resp = model.generate_content(prompt)
        return (resp.text or "").strip()
    except Exception as e:
        st.error(f"Model call error: {e}")
        return None

def try_parse_json(raw):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        s = raw.find("{"); e = raw.rfind("}")
        if s!=-1 and e!=-1 and e>s:
            try:
                return json.loads(raw[s:e+1])
            except Exception:
                return None
    return None

def build_song_prompt(text_snippet, styles, lang_mix, artist_ref, focus_topic, extra, duration_minutes):
    style_list = ", ".join(styles)
    lang = "Balanced Hinglish"
    if lang_mix < 30: lang = "Mostly Hindi with English scientific terms"
    if lang_mix > 70: lang = "Mostly English with Hindi connectors"
    artist_txt = f"Take inspiration from: {artist_ref}" if artist_ref else ""
    structure = ("Short" if duration_minutes<=1.5 else "Radio" if duration_minutes<=2.5 else "Full" if duration_minutes<=3.5 else "Extended")
    style_req = ("melodic rap soulmate style; confident; classroom-friendly but powerful; addictive; legendary; viral; catchy; enthusiastic; Hindi+English; melody; cinematic rise; groove; pronounce English words correctly")
    prompt = f"""
You are an expert musical edu-tainer for Gen Z students.

SOURCE (use for accuracy):
{text_snippet[:80000]}

INPUTS:
- Styles: {style_list}
- Language: {lang}
- Focus: {focus_topic or 'general'}
- {artist_txt}
- Duration-type: {structure}
- Extra: {extra}

RULES:
1) FIRST lines: aesthetic ad-libs (e.g., 'yeahh', 'aye vibe'), then a line exactly:
beyond the notz
2) Section order (strict): [CHORUS] [VERSE 1] [CHORUS] [VERSE 2] [CHORUS] [VERSE 3] [CHORUS] [VERSE 4] [CHORUS]
3) Chorus must appear at least 5 times. Verses max 6 lines each. Label sections e.g., [CHORUS], [VERSE 1].
4) Chorus must include 'beyond the notz' at least once inside it.
5) Put formulas/definitions/keywords inside verses only.
6) Keep style: {style_req}

OUTPUT: Return only valid JSON:
{{
  "songs": [
    {{
      "type":"Style",
      "title":"Title",
      "vibe_description":"Production prompt (include style lines).",
      "lyrics":"Full lyrics preserving newlines and section labels."
    }}
  ]
}}
"""
    return prompt

def keywords_per_page(pages, min_k=10, max_k=20, max_pages=5):
    results = []
    model = genai.GenerativeModel("gemini-2.5-flash")
    for i, page in enumerate(pages[:max_pages], start=1):
        if not page.strip():
            results.append((i, []))
            continue
        prompt = f"""Read this PAGE and return a list of {min_k}-{max_k} short keywords/phrases (no sentences), one per line. RETURN ONLY THE LIST.

PAGE:
{page[:6000]}
"""
        try:
            r = model.generate_content(prompt)
            raw = (r.text or "").strip()
            lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
            cnt = min(max_k, max(min_k, len(lines)))
            lines = lines[:cnt]
            results.append((i, lines))
        except Exception as e:
            results.append((i, [f"Error: {e}"]))
    return results

def generate_suno_style(vibe_desc, lyrics):
    prompt = f"""Read the vibe and lyrics. Suggest ONE concise Suno.ai style prompt (1-2 short sentences) mentioning instruments, bpm hint, mood, and lead vocal type. RETURN ONLY THE LINE.

VIBE:
{vibe_desc[:1600]}

LYRICS:
{lyrics[:1600]}
"""
    return call_model_text(prompt) or "modern melodic-rap, mid-tempo, warm synths, groovy drums, emotive male lead."

def create_cover(theme_kw, size=1024):
    seed = sum(ord(c) for c in (" ".join(theme_kw) or "btn"))
    random.seed(seed)
    def randc(): return tuple(int(random.random()*160+40) for _ in range(3))
    c1, c2 = randc(), randc()
    img = Image.new("RGB", (size,size), c1)
    draw = ImageDraw.Draw(img)
    for y in range(size):
        r = int(c1[0] + (c2[0]-c1[0])*(y/size))
        g = int(c1[1] + (c2[1]-c1[1])*(y/size))
        b = int(c1[2] + (c2[2]-c1[2])*(y/size))
        draw.line([(0,y),(size,y)], fill=(r,g,b))
    for _ in range(5):
        ell = Image.new("RGBA",(size,size))
        d = ImageDraw.Draw(ell)
        x0 = random.randint(-size//4, size//2); y0 = random.randint(-size//4, size//2)
        w = random.randint(size//3, size*2//3)
        d.ellipse([x0,y0,x0+w,y0+w], fill=randc()+(120,))
        img = Image.alpha_composite(img.convert("RGBA"), ell).convert("RGB")
    img = img.filter(ImageFilter.GaussianBlur(6))
    return img

# ----- UI inputs -----
st.title("🎹 BTN Originals AI Pro")
st.markdown("Transform NCERT chapters → viral songs. (May take 1–3 minutes)")

styles_default = ["Desi Hip-Hop / Trap","HOOKY & VIRAL MELODIC RAP","Bollywood Pop Anthem","Lofi Study Beats"]
selected = st.sidebar.multiselect("Select styles", styles_default, default=[styles_default[0]])
custom = st.sidebar.text_input("Add custom style")
if custom.strip() and custom not in selected: selected.append(custom)
lang_mix = st.sidebar.slider("Hindi vs English", 0,100,50)
duration_minutes = st.sidebar.slider("Length (min)", 1.0,5.0,2.5,0.5)
artist_ref = st.sidebar.text_input("Artist inspiration")
focus_topic = st.sidebar.text_input("Focus topic")
extra_instr = st.sidebar.text_area("Extra instructions", height=80)
max_keyword_pages = st.sidebar.slider("Keyword pages (per-page calls)", 1,20,5)  # default 5 to speed up
uploaded = st.file_uploader("Upload Chapter PDF", type=["pdf"])
gen_btn = st.button("🚀 Generate Tracks")

# session guards
if "running" not in st.session_state: st.session_state.running = False
if "song_data" not in st.session_state: st.session_state.song_data = None
if "page_keywords" not in st.session_state: st.session_state.page_keywords = None
if "summary20" not in st.session_state: st.session_state.summary20 = None
if "auto_suno" not in st.session_state: st.session_state.auto_suno = None
if "cover_bytes" not in st.session_state: st.session_state.cover_bytes = None

# ----- generation logic -----
if gen_btn and uploaded:
    if st.session_state.running:
        st.info("Generation already running — please wait.")
    else:
        st.session_state.running = True
        st.session_state.song_data = None
        st.session_state.page_keywords = None
        st.session_state.summary20 = None
        st.session_state.auto_suno = None
        st.session_state.cover_bytes = None

        pages, full_text = safe_read_pdf := (None, "")
        try:
            pages, full_text = safe_read_pdf(uploaded)
        except Exception:
            pages, full_text = safe_read_pdf(uploaded)
        if not full_text:
            st.error("Failed to extract text from PDF.")
            st.session_state.running = False
        else:
            progress = st.progress(0)
            step = 0

            # 1) generate songs (heavy)
            step += 1; progress.progress(step/5)
            with st.spinner("Composing songs (this may take 60-180s depending on pages)..."):
                song_prompt = build_song_prompt(full_text, selected, lang_mix, artist_ref, focus_topic, extra_instr, duration_minutes)
                raw = call_model_text(song_prompt, max_output_tokens=1800)
                parsed = try_parse_json(raw or "")
                if parsed and parsed.get("songs"):
                    songs = parsed["songs"]
                else:
                    songs = [{
                        "type": selected[0] if selected else "Custom",
                        "title": "BTN fallback - raw output",
                        "vibe_description": raw or "No vibe returned.",
                        "lyrics": raw or "No lyrics returned."
                    }]
                    st.warning("Model output not valid JSON; showing fallback raw output.")
                st.session_state.song_data = {"songs": songs}
            step += 1; progress.progress(step/5)

            # 2) per-page keywords (limited pages)
            with st.spinner("Extracting keywords per page..."):
                kws = keywords_per_page(pages, 10, 20, max_pages=max_keyword_pages)
                st.session_state.page_keywords = kws
            step += 1; progress.progress(step/5)

            # 3) 20-line summary
            with st.spinner("Generating 20-line summary..."):
                sum_prompt = f"Summarize the SOURCE into exactly 20 short lines. SOURCE:\n{full_text[:120000]}"
                sraw = call_model_text(sum_prompt, max_output_tokens=1000) or ""
                s_lines = [ln.strip() for ln in sraw.splitlines() if ln.strip()][:20]
                while len(s_lines) < 20: s_lines.append("—")
                st.session_state.summary20 = "\n".join(s_lines)
            step += 1; progress.progress(step/5)

            # 4) auto suno style + cover
            first = st.session_state.song_data["songs"][0]
            with st.spinner("Generating Suno style & cover..."):
                st.session_state.auto_suno = generate_suno_style(first.get("vibe_description",""), first.get("lyrics",""))
                theme = [kw for _, kws in st.session_state.page_keywords for kw in kws][:6]
                cover = create_cover(theme, size=1024)
                buf = io.BytesIO(); cover.save(buf, format="PNG"); buf.seek(0)
                st.session_state.cover_bytes = buf
            step += 1; progress.progress(step/5)

            # done
            st.session_state.running = False
            progress.empty()
            st.success("Done — scroll to results below.")

# ----- display results -----
if st.session_state.song_data:
    st.divider()
    st.subheader("🎵 Generated Tracks")
    songs = st.session_state.song_data["songs"]
    tabs = st.tabs([s.get("type", f"Track {i+1}") for i,s in enumerate(songs)])
    for i, tab in enumerate(tabs):
        s = songs[i]
        with tab:
            c1, c2 = st.columns([1.6, 1])
            with c1:
                st.subheader(s.get("title","Untitled"))
                st.markdown("**Lyrics**")
                with st.expander("Show lyrics (copy)"):
                    st.code(s.get("lyrics",""), language=None)
            with c2:
                st.info("🎹 Auto Suno Style")
                with st.expander("Suno.ai style (copyable)"):
                    st.code(st.session_state.auto_suno or s.get("vibe_description",""), language=None)
                st.markdown("")
                st.success("Tip: paste into Suno.ai; tweak bpm/instruments.")
                if st.button(f"🗑 Clear Results", key=f"clear_{i}"):
                    st.session_state.song_data = None
                    st.session_state.page_keywords = None
                    st.session_state.summary20 = None
                    st.session_state.auto_suno = None
                    st.session_state.cover_bytes = None
                    st.experimental_rerun()

    st.divider()
    st.subheader("🖼 Auto-generated 1:1 cover (no text/formula)")
    if st.session_state.cover_bytes:
        st.image(st.session_state.cover_bytes.getvalue(), width=320)
        st.download_button("Download cover (PNG)", st.session_state.cover_bytes.getvalue(), file_name="cover.png", mime="image/png")

    st.divider()
    st.subheader("📝 20-line summary (chapter check)")
    if st.session_state.summary20:
        st.code(st.session_state.summary20, language=None)

    st.divider()
    st.subheader(f"🔎 {len(st.session_state.page_keywords or [])} pages: 10–20 keywords per page")
    if st.session_state.page_keywords:
        for pnum, kws in st.session_state.page_keywords:
            st.markdown(f"**Page {pnum}**")
            st.code("\n".join(kws), language=None)

else:
    st.info("Upload a PDF and press Generate. Tip: set 'Keyword pages' to 5 for faster runs; increase if you want more coverage.")
