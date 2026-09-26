---
title: Tele-lytics Whisper Service
emoji: 🎙️
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 8001
pinned: false
---

Speech-to-text microservice for [Tele-lytics](https://github.com/akhil1108/tele-lytics) —
Whisper transcription, pyannote speaker diarization, wav2vec2 tone scoring, and
OpenAI-hosted translation for non-English calls. Implements the platform's
`STT_CONTRACT.md` wire contract; not meant to be used standalone.

Deployed automatically by `.github/workflows/whisper-service.yml` on every
push to `whisper_service/` — source of truth is the main repo, not this
Space's own git history.
