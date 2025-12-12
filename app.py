# app.py
import io, os, json, random, time
import streamlit as st
import google.generativeai as genai
import pdfplumber
from dotenv import load_dotenv

# --- CONFIG & API ---
load_dotenv()
st.set_page_config(page_title="BTN Originals AI Pro 🎧", page_icon="🎹", layout="wide")
API_ENV = "GOOGLE_API_KEY"
api_key = os.environ.get(API_ENV) or st.sidebar.text_input("Enter Google API Key", type="password")
if api_key:
    try:
        genai.configure(api_key=api_key)
    except Exception as e:
        st.sidebar.error(f"API key error: {e}")
else:
    st.sidebar.warning("Please enter Google API Key to enable generation.")

# --- HELPERS (concise) ---
def read_pdf_all(uploaded_file):
    """Return list of page texts and combined text (safe)."""
    try:
        uploaded_file.seek(0)
        raw = uploaded_file.read()
        fp = io.BytesIO(raw)
        pages = []
        with pdfplumber.open(fp) as pdf:
            for p in pdf.pages:
                pages.append((p.extract_text() or "").strip())
        return pages, "\n".join(pages)
    except Exception as e:
        st.error(f"PDF read error: {e}")
        return [], ""

def call_model(prompt, model_name="gemini-2.5-flash"):
    """Call Gemini generation and return string or None."""
    if not api_key:
        st.error("Missing API key.")
        return None
    try:
        model = genai.GenerativeModel(model_name)
        r = model.generate_content(prompt)
        return (r.text or "").strip()
    except Exception as e:
        st.error(f"Model call error: {e}")
        return None

def try_json(raw):
    if not raw: return None
    try:
        return json.loads(raw)
    except Exception:
        s = raw.find("{"); e = raw.rfind("}")
        if s != -1 and e != -1 and e > s:
            try:
                return json.loads(raw[s:e+1])
            except Exception:
                return None
    return None

# --- PROMPTS / GENERATION LOGIC ---
def build_song_prompt(full_text, styles, lang_mix, artist_ref, focus_topic, extra_instructions, duration_minutes):
    style_list = ", ".join(styles)
    # language instruction
    language_instruction = "Balanced Hinglish"
    if lang_mix < 30: language_instruction = "Mostly Hindi with English scientific terms"
    if lang_mix > 70: language_instruction = "Mostly English with Hindi connectors"
    artist_txt = f"Artist inspiration: {artist_ref}" if artist_ref else ""
    structure_hint = ("Short" if duration_minutes <= 1.5 else
                      "Radio" if duration_minutes <= 2.5 else
                      "Full" if duration_minutes <= 3.5 else "Extended")
    style_requirements = ("melodic rap soulmate style; confident; classroom-friendly but powerful; addictive; "
                          "legendary; viral; catchy; enthusiastic; Hindi+English; melodic; cinematic rise; groove; "
                          "pronounce English words correctly")
    # allow sending a lot of text (up to ~120k chars)
    snippet = full_text[:120000]
    prompt = f"""
You are an expert musical edu-tainer for Gen Z students.

SOURCE_TEXT:
{snippet}

INPUTS:
- Styles: {style_list}
- Language: {language_instruction}
- Focus: {focus_topic or 'general'}
- {artist_txt}
- Duration type: {structure_hint}
- Extra: {extra_instructions}

STRICT REQUIREMENTS:
1) The very first lines must be short aesthetic ad-libs (e.g., "yeahh", "aye vibe", "mmm-hmm") followed immediately by a line that contains exactly:
beyond the notz
2) After the intro, the lyrics MUST follow this labeled section order exactly:
   [CHORUS]
   [VERSE 1]
   [CHORUS]
   [VERSE 2]
   [CHORUS]
   [VERSE 3]
   [CHORUS]
   [VERSE 4]
   [CHORUS]
   (Chorus appears at least 5 times; you may repeat extra choruses but ensure the above sequence is present.)
3) Every [VERSE] must be no more than 6 lines long.
4) The [CHORUS] must include the phrase "beyond the notz" at least once inside it.
5) Place formulas/definitions/keywords inside VERSES only (not in ad-libs).
6) Maintain the following style: {style_requirements}

OUTPUT:
Return ONLY valid JSON (no markdown) with this structure:
{{
  "songs": [
    {{
      "type": "Style Name",
      "title": "Creative Song Title",
      "vibe_description": "Production prompt (instruments, BPM hint, mood, vocals) — be explicit and include the style requirements above.",
      "lyrics": "Full lyrics with labeled sections and preserved newlines."
    }}
  ]
}}
"""
    return prompt

def generate_suno_style(vibe_description, lyrics):
    prompt = f"""Read the vibe_description and sample lyrics and return a single concise Suno.ai style prompt (1-2 short sentences) that mentions instruments, tempo/bpm hint, mood, and lead vocal type. Return only one short line.

VIBE:
{vibe_description[:2000]}

LYRICS:
{lyrics[:2000]}
"""
    return call_model(prompt) or "modern melodic-rap: warm synths, groovy drums, mid-tempo, emotive lead."

def keywords_for_all_pages(pages, min_k=10, max_k=20):
    """Extract 10-20 keywords per page for every page (may be slow)."""
    results = []
    model_name = "gemini-2.5-flash"
    for idx, page in enumerate(pages, start=1):
        if not page.strip():
            results.append((idx, []))
            continue
        # prompt per page
        prompt = f"""Read this PAGE and return a list of {min_k}-{max_k} short keywords or short phrases (NOT sentences), one per line. Return ONLY the list.

PAGE:
{page[:8000]}
"""
        try:
            model = genai.GenerativeModel(model_name)
            resp = model.generate_content(prompt)
            raw = (resp.text or "").strip()
            lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
            # trim or pad to requested count
            desired = min(max_k, max(min_k, len(lines)))
            lines = lines[:desired]
            results.append((idx, lines))
        except Exception as e:
            results.append((idx, [f"Error: {e}"]))
    return results

# --- UI & Flow (minimal changes) ---
st.title("🎹 BTN Originals AI Pro")
st.markdown("Transform NCERT chapters into custom songs — full-feature mode (may take minutes).")

# Sidebar inputs
styles_list = ["Desi Hip-Hop / Trap","HOOKY & VIRAL MELODIC RAP","Punjabi Drill","Bollywood Pop Anthem","Lofi Study Beats","Sufi Rock","EDM / Party","Old School 90s Rap"]
selected_styles = st.sidebar.multiselect("Select Music Styles", styles_list, default=[styles_list[0]])
custom_style = st.sidebar.text_input("➕ Add Custom Style (optional)")
if custom_style.strip() and custom_style not in selected_styles:
    selected_styles.append(custom_style)
lang_mix = st.sidebar.slider("Hindi vs English", 0,100,50)
duration_minutes = st.sidebar.slider("Length (min)", 1.0,5.0,2.5,0.5)
artist_ref = st.sidebar.text_input("Artist inspiration (optional)")
focus_topic = st.sidebar.text_input("Focus topic (optional)")
extra_instructions = st.sidebar.text_area("Additional instructions (optional)", height=90)

uploaded = st.file_uploader("📂 Upload Chapter PDF (pdf)", type=["pdf"])
generate = st.button("🚀 Generate Tracks")

# session state guards (prevent duplicate runs)
if "running" not in st.session_state: st.session_state.running = False
if "song_data" not in st.session_state: st.session_state.song_data = None
if "page_keywords" not in st.session_state: st.session_state.page_keywords = None
if "suno_style" not in st.session_state: st.session_state.suno_style = None
if "summary20" not in st.session_state: st.session_state.summary20 = None

# Generate action
if generate:
    if not uploaded:
        st.warning("Please upload a PDF first.")
    elif st.session_state.running:
        st.info("Generation already running — wait for it to finish.")
    else:
        st.session_state.running = True
        st.session_state.song_data = None
        st.session_state.page_keywords = None
        st.session_state.suno_style = None
        st.session_state.summary20 = None

        # read PDF
        with st.spinner("Reading PDF..."):
            pages, full_text = read_pdf_all(uploaded)
        if not full_text:
            st.error("Could not extract any text from PDF.")
            st.session_state.running = False
        else:
            # progress feedback
            total_steps = 4
            progress = st.progress(0)
            step = 0

            # 1) Generate songs (send up to ~120k chars)
            step += 1; progress.progress(step/total_steps)
            with st.spinner("Generating songs (this may take 1-3 minutes)..."):
                prompt = build_song_prompt(full_text, selected_styles, lang_mix, artist_ref, focus_topic, extra_instructions, duration_minutes)
                raw_out = call_model(prompt)
                parsed = try_json(raw_out or "")
                if parsed and parsed.get("songs"):
                    songs = parsed["songs"]
                else:
                    # fallback: wrap raw output so UI has something to display
                    songs = [{
                        "type": selected_styles[0] if selected_styles else "Custom",
                        "title": "Fallback raw output",
                        "vibe_description": raw_out or "No vibe returned.",
                        "lyrics": raw_out or "No lyrics returned."
                    }]
                    st.warning("Model did not return valid JSON. Showing fallback raw result.")
                st.session_state.song_data = {"songs": songs}

            # 2) keywords per page — ALL pages (user requested ALL). This is heavy.
            step += 1; progress.progress(step/total_steps)
            with st.spinner("Extracting 10–20 keywords from every page (this can be slow for many pages)..."):
                page_kw = keywords_for_all_pages(pages, min_k=10, max_k=20)
                st.session_state.page_keywords = page_kw

            # 3) generate 20-line summary
            step += 1; progress.progress(step/total_steps)
            with st.spinner("Generating 20-line chapter summary..."):
                summary_prompt = f"Summarize the SOURCE into exactly 20 short lines, covering key points and keywords. SOURCE:\n{full_text[:120000]}"
                sraw = call_model(summary_prompt) or ""
                s_lines = [ln.strip() for ln in sraw.splitlines() if ln.strip()][:20]
                while len(s_lines) < 20: s_lines.append("—")
                st.session_state.summary20 = "\n".join(s_lines)

            # 4) auto Suno style for first song
            step += 1; progress.progress(step/total_steps)
            first_song = st.session_state.song_data["songs"][0]
            with st.spinner("Auto-generating Suno.ai style suggestion..."):
                st.session_state.suno_style = generate_suno_style(first_song.get("vibe_description",""), first_song.get("lyrics",""))

            # done
            progress.empty()
            st.success("Generation completed. Scroll down to inspect results.")
            st.session_state.running = False

# --- RESULTS DISPLAY (keeps copy icons separated in expanders) ---
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
                # put lyrics into expander to avoid overlap of copy icon with other code blocks
                with st.expander("Show lyrics (click to expand; copy icon available)"):
                    st.code(s.get("lyrics",""), language=None)
            with c2:
                st.info("🎹 Auto Suno.ai style (AI-suggested)")
                with st.expander("Show Suno.ai style (copyable)"):
                    # prefer our auto suno style if generated
                    st.code(st.session_state.suno_style or s.get("vibe_description",""), language=None)
                st.markdown("")
                st.success("Tip: paste into Suno.ai and tweak instruments / BPM.")
                if st.button(f"🗑️ Clear Results", key=f"clear_{i}"):
                    st.session_state.song_data = None
                    st.session_state.page_keywords = None
                    st.session_state.suno_style = None
                    st.session_state.summary20 = None
                    st.experimental_rerun()

    st.divider()
    st.subheader("📝 20-line summary (chapter check)")
    if st.session_state.summary20:
        st.code(st.session_state.summary20, language=None)

    st.divider()
    st.subheader(f"🔎 Keywords per page (10–20 each) — {len(st.session_state.page_keywords or [])} pages")
    if st.session_state.page_keywords:
        for pnum, kws in st.session_state.page_keywords:
            st.markdown(f"**Page {pnum}**")
            st.code("\n".join(kws) if kws else "—", language=None)
else:
    st.info("Upload a PDF and press Generate. This full-feature run may take several minutes for long PDFs; progress shows each stage.")
