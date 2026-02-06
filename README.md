# Kadak Content — BTN Originals

An AI-powered educational music generator that transforms NCERT chapter PDFs into study songs. Designed to help students learn through music as a mnemonic device.

## Features

- Upload PDF chapters (up to 35 pages) and generate 2-6 minute songs
- Multiple musical styles: Desi Hip-Hop, Punjabi Drill, Bollywood Pop, Lofi, Sufi Rock, EDM, 90s Rap, or custom
- Adjustable Hindi-English language mix (0-100%)
- Artist style references for generation
- Keyword extraction (10 per page)
- Suno.ai-compatible production prompts

## Tech Stack

- **Streamlit** — Web UI
- **Google Generative AI** (Gemini 2.5-flash) — Song/lyric generation
- **pdfplumber** — PDF text extraction
- **python-dotenv** — Environment variable management

## Setup

```bash
pip install -r requirements.txt
echo "GOOGLE_API_KEY=your_key_here" > .env
streamlit run app.py
```

## Structure

```
├── app.py              # Main Streamlit application
├── requirements.txt    # Dependencies
├── .env                # Google API key (not committed)
└── jesc1dd/            # Sample NCERT PDF chapters
```
