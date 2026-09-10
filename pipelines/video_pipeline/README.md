# 🎥 Video Pipeline

## Purpose & Scope
The `video_pipeline` processes threat briefings, recorded incident calls with screen shares, webinar intelligence, and terminal screencasts.

## Planned Capabilities (Roadmap)
1. **Audio/Video Demuxing:** Uses `ffmpeg` to extract the master audio track and route it to the audio pipeline.
2. **Keyframe Sampling:** Uses `opencv-python` to extract representative frames (1 frame every 10–15 seconds or on significant scene/slide changes).
3. **Slide / Screen Analysis:** Passes sampled keyframes to vision models to capture visual telemetry (slide text, terminal commands, architecture diagrams) that Whisper audio transcripts miss.
4. **Synchronized Timeline:** Merges timestamped visual scenes with timestamped audio transcript segments into an integrated multimodal transcript bundle.
