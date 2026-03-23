# Nexus - Fully Local AI Command Center

100% offline. No API keys. No cloud. No subscriptions.
Voice control, screen awareness, persistent memory, proactive briefings.

## Quick Start

1. Install Ollama from https://ollama.com then:
   ollama pull llama3.2:3b

2. Install Python dependencies:
   pip install -r requirements.txt
   python -m playwright install chromium

3. (Optional) For voice control, also install ffmpeg:
   winget install ffmpeg

4. Run:
   python main.py

5. Log into your accounts in the browser that opens (one-time).

## Features

- Email (Gmail): Read inbox, send emails, search
- WhatsApp: Send/read messages, list chats
- Discord: Check DMs, send messages, browse servers
- GitHub: Notifications, repos, issues, PRs
- File Manager: Search, organize, disk usage, duplicates
- Voice Control: Say "Nexus" + command, it talks back
- Screen Awareness: Nexus can read what's on your screen
- Memory: Remembers contacts, preferences, tasks across sessions
- Proactive Briefings: "Good morning" for full status across everything

## Voice Setup

TTS uses Windows built-in voices (pyttsx3/SAPI5) - no downloads.
STT uses Whisper "tiny" model (~75MB, auto-downloads on first run).
Needs ffmpeg on PATH: winget install ffmpeg

In settings.json you can adjust:
- "whisper_model": "tiny" (or "base" for better accuracy, slower)
- "voice_rate": 175 (words per minute)
- "voice_id": null (auto-picks David; set "Zira" for female)

## System Requirements

- Windows 10/11
- Python 3.10+
- 8GB RAM minimum
- Ollama running locally
