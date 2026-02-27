## Contributing

Thanks for your interest in improving this project!

### Development setup

```bash
git clone https://github.com/yourusername/youtube-lm.git
cd youtube-lm
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
```

Edit `.env` with:

- a test `PLAYLIST_URL` (small playlist is fine),
- `OPENAI_API_KEY` or `GEMINI_API_KEY`,
- optional `OBSIDIAN_VAULT_PATH` if you want to write directly into a vault.

### Running the pipeline

- End‑to‑end:

  ```bash
  ./run_pipeline.sh --resume
  ```

- Or individual steps:

  ```bash
  python pipeline.py --only transcripts
  python pipeline.py --only enrichment --resume
  python pipeline.py --only notebooklm
  python pipeline.py --only obsidian
  ```

### Pull requests

When opening a PR, please:

1. Describe the problem you’re solving or the feature you’re adding.
2. Mention which parts of the pipeline you touched (transcripts / enrichment / notebooklm / obsidian).
3. Include a short note on how you tested it (e.g. “ran `./run_pipeline.sh --resume` on a small playlist”).

Bug reports and ideas for integrations (other LLMs, other note apps) are very welcome.

