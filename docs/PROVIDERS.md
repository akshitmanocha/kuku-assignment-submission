# Model providers


The API adapter uses the OpenAI-compatible `/chat/completions` protocol, JSON mode, explicit source-ID validation, and bounded retries. The model is configured on the server, not embedded in browser code.

The default configuration uses `nvidia/nemotron-3-ultra-550b-a55b:free` through `https://openrouter.ai/api/v1`. Copy `.env.example` to `.env`, set `PROMO_API_KEY`, and restart. Verify it on the original public demo:

```bash
python3 -m promo_lab run promo_lab/examples --provider openai --output output/runs/nemotron-public-demo
```

The [NVIDIA free-endpoint notice](https://openrouter.ai/nvidia/nemotron-3-ultra-550b-a55b%3Afree) says not to upload confidential information and describes logging for improvement. The app therefore defaults to public/non-confidential inputs on this route: the original demo is recognized automatically; other public uploads require an explicit declaration (`--public-input` in the CLI). By default the known supplied Kuku pack is blocked on this route, including matching renamed content. An owner who explicitly authorizes processing can set `PROMO_ALLOW_CONFIDENTIAL=1` in the local `.env`; this records an authorization override without declaring the source public. It is disabled in `.env.example`. This is an input declaration and known-pack check, not a general-purpose confidentiality classifier. Existing Qwen full-pack results are retained.

The model catalog does not advertise `response_format`, so its adapter requests JSON through the prompt, disables optional reasoning, bounds output, and validates the response locally. No paid model fallback is configured. Free request allowances can be smaller than a 100-call full-pack run; inspect the account's `/api/v1/key` limits rather than assuming unlimited free usage.

A live original-demo run completed both calls, with the provider reporting zero cost. This verifies integration, not superior promo quality.

For a separate Groq option, set `GROQ_API_BASE`, `GROQ_API_KEY`, and `GROQ_MODEL` in `.env`, then select Groq in the app or pass `--provider groq`. Its credentials are independent from the active OpenRouter key. For example:

```dotenv
GROQ_API_BASE=https://api.groq.com/openai/v1
GROQ_API_KEY=your-key-here
GROQ_MODEL=qwen/qwen3.8-27b
```

You can alternatively point the generic compatible route directly at Groq:

```dotenv
PROMO_API_BASE=https://api.groq.com/openai/v1
PROMO_API_KEY=your-key-here
PROMO_MODEL=qwen/qwen3.8-27b
```

Optional CA certificates on Python installations without a configured trust store:

```bash
python3 -m pip install -e '.[ai]'
```

Restart the app after configuring `.env`, or run:

```bash
python3 -m promo_lab run "/path/to/local-screenplays-scripts.zip" \
  --provider groq --output output/runs/full-pack-qwen
```

`--provider openai` means the compatible protocol, not necessarily the OpenAI service. For Ollama, set `OLLAMA_MODEL` and optionally `OLLAMA_BASE_URL`, then use `--provider ollama`. Install/pull the chosen local model separately. The transport never silently switches models. CLI runs fail on provider failure by default. Use `--allow-partial`, or the explicitly labeled checkbox in the browser, to retain completed results: remaining candidates stay unassessed and cannot enter the AI shortlist. The run is marked partial, provider failures are exported, and episode-level AI coverage is visible. Daily token-quota failures stop immediately rather than waiting in a long retry loop. Identical completed requests remain cached for a later resume. A single proposal/assessment object missing only its expected array wrapper is narrowly normalized and noted; its original response is preserved. Other malformed structures are rejected.

AI mode sends screenplay text to the selected provider. The input pack permits assignment use with AI tools, but remains confidential. Do not publish scripts, private run folders, provider caches, or credentials. They are Git-ignored. Raw exports include source text and must be handled as confidential assignment material. Keys are never returned in app status, saved in run manifests, or included in raw requests. Keep `.env` off screenshots and shared archives.
