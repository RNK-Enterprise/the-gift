# Gift Bible chat on atlas

Private (not in the served library). Lives under `~/gift-model/` and `~/bible-train/`.

## Live processes (pm2)

- `gift-bible-llama` — llama.cpp server on `127.0.0.1:8081` (CPU, `-ngl 0`)
- `gift-bible-adapter` — grounded FastAPI on `127.0.0.1:8000` (`verses-pd.db`)
- Domain (`curator-runtime` on `:4000`) — model id `bible-1.7b` → `http://127.0.0.1:8000/v1`

Smoke:

```bash
curl -s http://127.0.0.1:8000/health
# → {"llm": true, "index": true}

curl -s http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Quote John 3:16 (KJV)."}],"max_tokens":256}'
```

## Retrain (GTX 1650, ~17 h capped run)

```bash
# stops competing GPU user first
pm2 stop ld-lore-llm
cd ~/bible-train
nohup ./launch_train.sh >/dev/null 2>&1 &
nohup ./finish_pipeline.sh >/dev/null 2>&1 &
tail -f train.log pipeline.log
```

On success, `finish_pipeline.sh` writes
`~/gift-model/gguf/bible-1.7b-q4_k_m.gguf`, restarts `gift-bible-llama`, and
starts `ld-lore-llm` again.

## Public URL

Tunnel ingress for `gift-chat.rnkstudios.uk` → `:4000` is in
`~/.cloudflared/rnkstudios-web.yml`. Add the Cloudflare public hostname / DNS
in the **rnkstudios.uk** zone. Until then use `https://alpha.rnk-enterprise.us/`
and select **The Gift — Bible Study**.
