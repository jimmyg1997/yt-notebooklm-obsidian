# Cost estimate: 51 videos enrichment

Based on your actual transcript data (~2.65M chars total, ~687k input tokens + ~41k output tokens).

## Pricing (OpenAI, standard)

| Model           | Input (per 1M tokens) | Output (per 1M tokens) | Context |
|----------------|------------------------|------------------------|--------|
| gpt-3.5-turbo  | $0.50                  | $1.50                  | 16k    |
| gpt-4o-mini    | $0.15                  | $0.60                  | 128k   |

## Option A: gpt-3.5-turbo (current)

- Transcripts **truncated** to 50k chars (~12.5k tokens) per video to fit 16k context.
- Input: ~663k tokens (51 × truncated transcript + prompt)
- Output: ~41k tokens

**Cost:** 0.663 × $0.50 + 0.041 × $1.50 ≈ **$0.39**

## Option B: gpt-4o-mini (recommended)

- **Full transcripts** (no truncation); 128k context fits your longest videos.
- Input: ~687k tokens
- Output: ~41k tokens

**Cost:** 0.687 × $0.15 + 0.041 × $0.60 ≈ **$0.13**

## Summary

| Option | Cost (51 videos) | Truncation      |
|--------|------------------|-----------------|
| gpt-3.5-turbo | ~**$0.39** | Yes (first 50k chars) |
| gpt-4o-mini   | ~**$0.13** | No (full transcript)  |

**gpt-4o-mini is about 3× cheaper and uses the full transcript.** Recommendation: use `OPENAI_MODEL=gpt-4o-mini`.
