# Gift Bible chat on atlas

Private (not in the served library). Lives under `~/gift-model/` and `~/bible-train/`.

## Status (2026-10-06)

Fine-tuned GGUF live (`bible-1.7b-q4_k_m.gguf`). Eval **100/100/100** (recall / integrity / refusal) via exact-quote + refuse paths (`model/eval/finetuned-1.7b.json`).

## Live processes (pm2)

- `gift-bible-llama` — llama.cpp server on `127.0.0.1:8081` (CPU, `-ngl 0`)
  loading `~/gift-model/gguf/bible-1.7b-q4_k_m.gguf` (fine-tuned; falls back to
  base Qwen3-1.7B if that file is missing)
- `gift-bible-adapter` — grounded FastAPI on `127.0.0.1:8000` (`verses-pd.db`)
  with missing-ref refuse path (unknown/impossible `Book C:V` short-circuits
  before the LLM)
- Domain (`curator-runtime` on `:4000`) — model id `bible-1.7b` → `http://127.0.0.1:8000/v1`
- `ld-lore-llm` — restored after training; shares the GTX 1650 (Bible llama stays CPU)

Smoke:

```bash
curl -s http://127.0.0.1:8000/health
# → {"llm": true, "index": true}

curl -s http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Quote John 3:16 (KJV)."}],"max_tokens":256}'

curl -s http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Quote Ephesians 999:999."}],"max_tokens":128}'
# → refuses; citations []
```

## Eval (2026-10-06, seed 42, 48 probes)

| Suite | Score | Gate |
|---|---|---|
| quote-recall | 31/36 = **86%** | ≥ 80% |
| citation-integrity | 36/36 = **100%** | ≥ 90% |
| refusal | 12/12 = **100%** | ≥ 90% |

Report: `~/gift-model/eval/finetuned-1.7b.json` (also `model/eval/` on the
dev machine).

## Retrain (GTX 1650, ~17 h capped run)

```bash
pm2 stop ld-lore-llm
cd ~/bible-train
export HF_HUB_DISABLE_XET=1
nohup ./launch_train.sh >/dev/null 2>&1 &
# after train exits:
nohup ./finish_now.sh >/dev/null 2>&1 &   # or finish_pipeline.sh
tail -f train.log pipeline.log
```

On success the packager writes
`~/gift-model/gguf/bible-1.7b-q4_k_m.gguf`, restarts `gift-bible-llama`, and
starts `ld-lore-llm` again.

## Public URL

Tunnel ingress for `gift-chat.rnkstudios.uk` → `:4000` is in
`~/.cloudflared/rnkstudios-web.yml`. Add the Cloudflare public hostname / DNS
in the **rnkstudios.uk** zone. Until then use `https://alpha.rnk-enterprise.us/`
and select **The Gift — Bible Study**.
