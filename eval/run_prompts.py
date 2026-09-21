"""Run the fixed coding prompts through a model and save the outputs.

The same prompts are used at every stage (base -> SFT -> reward model -> RLHF)
so the outputs can be compared side by side.

Runs for a controlled comparison (B vs C isolates training; A vs C shows the whole change):
    A: uv run python eval/run_prompts.py --tag 00_base_raw --format raw
    B: uv run python eval/run_prompts.py --tag 00_base_chatml --format chatml
    C: uv run python eval/run_prompts.py --model checkpoints/sft --tag 01_sft_chatml --format chatml
"""

import argparse
import json
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from chat_format import CHATML_TEMPLATE, STOP_TOKENS

EVAL_DIR = Path(__file__).parent
PROMPTS_FILE = EVAL_DIR / "coding_prompts.json"
RESULTS_DIR = EVAL_DIR / "results"


def build_input(tokenizer, prompt, fmt):
    if fmt == "chatml":
        messages = [{"role": "user", "content": prompt}]
        # Always our template, never the checkpoint's own, so the format stays fixed across stages.
        return tokenizer.apply_chat_template(
            messages, chat_template=CHATML_TEMPLATE, tokenize=False, add_generation_prompt=True
        )
    # Base models have no notion of turns, so feed the raw prompt plus a newline.
    return prompt + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="HuggingFaceTB/SmolLM2-135M")
    parser.add_argument("--tag", required=True, help="Name for this run, e.g. 00_base_raw")
    parser.add_argument("--format", choices=["raw", "chatml"], required=True, help="Prompt format")
    parser.add_argument("--max-new-tokens", type=int, default=200)
    args = parser.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    tokenizer = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForCausalLM.from_pretrained(args.model).to(device).eval()
    stop_ids = {tokenizer.convert_tokens_to_ids(t): t for t in STOP_TOKENS}

    prompts = json.loads(PROMPTS_FILE.read_text(encoding="utf-8"))
    results = []
    for item in prompts:
        text = build_input(tokenizer, item["prompt"], args.format)
        inputs = tokenizer(text, return_tensors="pt").to(device)
        with torch.no_grad():
            # Greedy decoding keeps runs deterministic, so changes between stages come from the weights.
            output = model.generate(
                **inputs,
                max_new_tokens=args.max_new_tokens,
                do_sample=False,
                eos_token_id=list(stop_ids),
                pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
            )
        new_ids = output[0][inputs["input_ids"].shape[1]:].tolist()
        # A stop token as the last generated id means the model ended on its own; otherwise it hit the cap.
        stop_token = stop_ids.get(new_ids[-1]) if new_ids else None
        stop_reason = "eos" if stop_token else "max_new_tokens"
        completion = tokenizer.decode(new_ids, skip_special_tokens=True)
        results.append({
            "id": item["id"],
            "prompt": item["prompt"],
            "input_text": text,
            "completion": completion,
            "stop_reason": stop_reason,
            "stop_token": stop_token,
            "num_new_tokens": len(new_ids),
        })
        print(f"\n===== {item['id']} =====\n{item['prompt']}\n----- completion ({stop_reason}, {len(new_ids)} tokens) -----\n{completion}")

    terminated = sum(r["stop_reason"] == "eos" for r in results)
    print(f"\nTerminated on a stop token: {terminated}/{len(results)}")

    RESULTS_DIR.mkdir(exist_ok=True)
    meta = {
        "tag": args.tag,
        "model": args.model,
        "format": args.format,
        "max_new_tokens": args.max_new_tokens,
        "decoding": "greedy",
        "stop_tokens": STOP_TOKENS,
        "terminated": f"{terminated}/{len(results)}",
    }
    out = {"meta": meta, "results": results}
    (RESULTS_DIR / f"{args.tag}.json").write_text(json.dumps(out, indent=2), encoding="utf-8")

    lines = [
        f"# {args.tag}",
        "",
        f"Model: `{args.model}` | format: {args.format} | greedy, {args.max_new_tokens} new tokens"
        f" | terminated on a stop token: {terminated}/{len(results)}",
        "",
    ]
    for r in results:
        stop = f"{r['stop_reason']} (`{r['stop_token']}`)" if r["stop_token"] else r["stop_reason"]
        lines += [
            f"## {r['id']}",
            "",
            f"**Prompt:** {r['prompt']}",
            "",
            f"**Stopped:** {stop}, {r['num_new_tokens']} tokens",
            "",
            "```",
            r["completion"],
            "```",
            "",
        ]
    (RESULTS_DIR / f"{args.tag}.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nSaved to {RESULTS_DIR / args.tag}.json/.md")


if __name__ == "__main__":
    main()
