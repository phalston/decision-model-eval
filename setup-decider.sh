#!/bin/bash
# Install a Strands decider (github.com/strands-labs/strands-decider) for ask.py, pinned and checked. Apple silicon + MLX.
#   bash setup-decider.sh 2b     # strands-decider-2B-qwen3.5-v1-2610: ~0.2 GB + base Qwen/Qwen3.5-2B-Base ~4.3 GB
#   bash setup-decider.sh e4b    # strands-decider-E4B-gemma4-v1-2610: ~0.5 GB + base google/gemma-4-E4B-it ~16 GB (~15 GB in memory)
# Needs git, uv and network. Everything goes in .decider/ (gitignored); base models go in the Hugging Face cache.
set -uo pipefail
cd "$(dirname "$0")" || exit 1
D="$PWD/.decider"
CODE_SHA=930e6d5de16309be32579f5631a7369a3322140c
case "${1:-}" in
  2b)  MODEL=strands-decider-2B-qwen3.5-v1-2610;  MODEL_SHA=216d1ccb46a9e9b036eb9187b248db98480f77d4
       BASE=Qwen/Qwen3.5-2B-Base;  BASE_SHA=b1485b2fa6dfa1287294f269f5fb618e03d52d7c; BASE_SIZE="~4.3 GB" ;;
  e4b) MODEL=strands-decider-E4B-gemma4-v1-2610;  MODEL_SHA=1344d44397c457f3be34b8ff15c593b41248c6bf  # tag 261009
       BASE=google/gemma-4-E4B-it; BASE_SHA=ee0ef6023621cff504d758262d4e04895a5af4a2; BASE_SIZE="~16 GB" ;;
  *)   sed -n '2,5p' "$0"; exit 2 ;;
esac
m="$D/models/$MODEL"
mkdir -p "$D/src" || exit 1
echo "== 1/6 decider code at $CODE_SHA"
[ -d "$D/src/strands-decider" ] || git clone https://github.com/strands-labs/strands-decider "$D/src/strands-decider" || exit 1
git -C "$D/src/strands-decider" fetch origin "$CODE_SHA" && git -C "$D/src/strands-decider" checkout "$CODE_SHA" || exit 1
echo "== 2/6 Python 3.12 venv in $D/venv"
[ -x "$D/venv/bin/python" ] || uv venv --python 3.12 "$D/venv" || exit 1
echo "== 3/6 install strands-decider[mlx]"
VIRTUAL_ENV="$D/venv" uv pip install "$D/src/strands-decider[mlx]" || exit 1
echo "== 4/6 model $MODEL at $MODEL_SHA"
"$D/venv/bin/hf" download "StrandsAgents/$MODEL" --revision "$MODEL_SHA" --local-dir "$m" --exclude 'eval/*' --exclude 'training/*' || exit 1
echo "== 5/6 check model files against MANIFEST.sha256 and provenance.json"
(cd "$m" && grep -E '  (head.safetensors|lora/.*|strands_decider_config.json|provenance.json|tokenizer.*)$' MANIFEST.sha256 | shasum -a 256 -c -) || exit 1
grep -q "\"base_model\": \"$BASE\"" "$m/provenance.json" || { echo "provenance.json names a different base model"; exit 1; }
grep -q "\"base_model_revision\": \"$BASE_SHA\"" "$m/provenance.json" || { echo "provenance.json names a different base revision"; exit 1; }
# force_bos models read text badly without BOS, and the MLX loader does not add one: check the saved tokenizer does.
if grep -q '"force_bos": true' "$m/strands_decider_config.json"; then
  "$D/venv/bin/python" -I -c 'import sys; from transformers import AutoTokenizer; t = AutoTokenizer.from_pretrained(sys.argv[1]); ids = t("DNS hostname: example.com", add_special_tokens=True)["input_ids"]; ok = t.bos_token_id is not None and ids[0] == t.bos_token_id; print("   tokenizer adds BOS:", ok); sys.exit(0 if ok else 1)' "$m" || { echo "the saved tokenizer adds no BOS; stopping before the base download"; exit 1; }
fi
echo "== 6/6 base model $BASE at $BASE_SHA ($BASE_SIZE)"
"$D/venv/bin/hf" download "$BASE" --revision "$BASE_SHA" || exit 1
echo "done. Run: HF_HUB_OFFLINE=1 .decider/venv/bin/python ask.py decider --model-dir .decider/models/$MODEL --device mlx"
