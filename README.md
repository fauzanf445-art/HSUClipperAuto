# YouTube Toolkit (Professional)

This project provides three main components:

- `youtube_downloader.py` — download video/audio assets using `yt-dlp`.
- `youtube_summarizer.py` — extract transcript and summarize using Google Gemini.
- `video_clipper.py` — create clips from a master video using a JSON describing segments.
- `orchestrator.py` — orchestrates the full workflow (download -> summarize -> clip).

Quick start

1. Create a `.env` file in the project root with your Gemini API key:

   GEMINI_API_KEY=your_key_here

2. Install dependencies:

   pip install -r requirements.txt

3. Ensure `ffmpeg` is installed and reachable (or place `ffmpeg.exe` in project root).

4. Run the orchestrator and follow prompts:

   python orchestrator.py

Folder layout created by the orchestrator

- `raw_assets/{video_id}/...` — downloaded master video and audio
- `final_output/{video_id}/summaries/` — JSON summaries
- `final_output/{video_id}/final_clips/` — generated clips

Notes

- The summarizer expects the Gemini model to return valid JSON (the prompt requests strict JSON). If the model returns non-JSON, the raw text will be saved under the `summary` JSON under the `raw` key.
- Keep your `.env` out of source control (`.gitignore` already ignores it).

If you want, I can run a smoke test (requires your API key and internet).