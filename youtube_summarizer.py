import os
import json
import re
import logging
from datetime import datetime
from typing import Optional
from youtube_transcript_api import YouTubeTranscriptApi
from google import genai
from dotenv import load_dotenv

load_dotenv()

class YouTubeSummarizer:
    """Extract transcript and summarize using Gemini (Google GenAI).

    Example:
        s = YouTubeSummarizer()
        s.summarize_video(url)
    """

    def __init__(self, api_key: Optional[str] = None, model: str = 'gemini-flash-latest', out_dir: Optional[str] = None):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.api_key = api_key or os.getenv('GEMINI_API_KEY')
        if not self.api_key:
            raise RuntimeError('Gemini API key not provided. Set GEMINI_API_KEY in .env or pass api_key.')
        self.client = genai.Client(api_key=self.api_key)
        self.model = model
        # default out_dir => <project>/final_output (keeps in sync with main.prepare_video_dirs)
        self.out_dir = out_dir or os.path.join(base_dir, 'final_output')
        os.makedirs(self.out_dir, exist_ok=True)


    @staticmethod
    def extract_video_id(url: str) -> Optional[str]:
        regex = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
        m = re.search(regex, url)
        return m.group(1) if m else None

    def get_transcript(self, video_url: str, prefer_langs=('id', 'en')) -> str:
        video_id = self.extract_video_id(video_url)
        if not video_id:
            raise ValueError('Invalid YouTube URL or video id not found.')

        last_exc = None
        for lang in prefer_langs:
            try:
                result = YouTubeTranscriptApi().fetch(video_id, languages=[lang])
                raw = result.to_raw_data()
                full_text = ' '.join([item['text'] for item in raw])
                return full_text
            except Exception as e:
                last_exc = e
                continue
        raise RuntimeError(f'Failed to fetch transcript. Detail: {last_exc}')

    def summarize(self, transcript_text: str) -> str:
        prompt = f"""
        Analyze the following YouTube transcript and produce a strictly formatted JSON summary.

        Requirements:
        1) Return JSON only — no markdown or extra text.
        2) Top-level keys: "video_title" and "clips".
        3) Each item in "clips" must have: "title", "start_time", "end_time", "description".
        4) Times use HH:MM:SS format.

        Transcript:
        {transcript_text}

        Output JSON:
        """.strip()

        response = self.client.models.generate_content(model=self.model, contents=prompt)
        raw_text = response.text
        logging.debug('Gemini raw response (first 500 chars): %s', raw_text[:500])
        return raw_text

    def save_summary(self, video_url: str, summary_text: str, prefix: str = 'summary', transcript_text: Optional[str] = None) -> str:
        video_id = self.extract_video_id(video_url) or 'unknown'
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # Try to extract JSON from the response (in case it's wrapped in markdown code blocks)
        parsed = None
        try:
            parsed = json.loads(summary_text)
            logging.info('JSON parsed successfully')
        except Exception as e:
            logging.warning('JSON parse failed: %s', e)
            # Try to extract JSON from markdown code blocks if present
            if '```json' in summary_text:
                try:
                    start = summary_text.index('```json') + 7
                    end = summary_text.index('```', start)
                    json_str = summary_text[start:end].strip()
                    parsed = json.loads(json_str)
                    logging.info('JSON extracted from markdown code block')
                except Exception as e2:
                    logging.warning('Markdown extraction failed: %s', e2)
                    parsed = {'raw': summary_text}
            elif '```' in summary_text:
                try:
                    start = summary_text.index('```') + 3
                    end = summary_text.index('```', start)
                    json_str = summary_text[start:end].strip()
                    parsed = json.loads(json_str)
                    logging.info('JSON extracted from code block')
                except Exception as e2:
                    logging.warning('Code block extraction failed: %s', e2)
                    parsed = {'raw': summary_text}
            else:
                parsed = {'raw': summary_text}

        logging.debug('Parsed structure keys: %s', list(parsed.keys()) if isinstance(parsed, dict) else 'not a dict')
        if isinstance(parsed, dict):
            logging.debug('Has clips key: %s', 'clips' in parsed)

        # out_dir is raw_assets/{video_id} (set by main.py)
        raw_dir = self.out_dir
        os.makedirs(raw_dir, exist_ok=True)

        # Simpan transcripts.json ke raw_assets/{video_id}/ 
        # INI file yang digunakan clipper untuk membuat video segments
        clips_path = os.path.join(raw_dir, 'transcripts.json')
        if isinstance(parsed, dict) and parsed.get('clips'):
            with open(clips_path, 'w', encoding='utf-8') as cf:
                json.dump(parsed, cf, ensure_ascii=False, indent=2)
            logging.info('Clips saved to transcripts.json')
        else:
            logging.warning('No clips found in parsed data')
        
        if transcript_text:
            with open(os.path.join(raw_dir, 'transcript.txt'), 'w', encoding='utf-8') as tf:
                tf.write(transcript_text)

        return clips_path

    def summarize_video(self, video_url: str) -> str:
        """Full workflow: fetch transcript, summarize, save clips data."""
        transcript = self.get_transcript(video_url)
        summary = self.summarize(transcript)
        clips_path = self.save_summary(video_url, summary, transcript_text=transcript)
        return clips_path
