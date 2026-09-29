# Neural-Draft demonstration

- **Neural-Draft-demo.mp4** — 1080p, 24 fps, captioned narrated walkthrough, approximately 2 minutes 37 seconds.
- **Neural-Draft-demo.srt** — matching subtitle file.
- **transcript.txt** — narration text for reuse or a live presentation.

This is an edited walkthrough assembled from genuine captures of the working local prototype, including the actual forging animation and a complete two-player match. It is not an uninterrupted screen recording. Both players' choices were operated for the demonstration. The final score is server-resolved: Nova leads Evidence 6–5 and Response 5–4, with People tied 4–4.

The voice is synthetic, generated offline using the installed Microsoft Catherine voice. The demonstrated assessment is deterministic offline mode; no live LLM was used or implied. No external art, music, or video assets were used.

`scenes.json`, `narrate.ps1`, and `render.py` retain the edit and narration source. The renderer uses Pillow and a local imageio-ffmpeg encoder; these are video-production helpers, separate from the application's dependencies. `captures/` contains source browser screenshots and `build/` contains intermediate frames and timing metadata.
