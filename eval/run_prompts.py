"""Run the fixed coding prompts through a model and save the outputs.

The same prompts are used at every stage (base -> SFT -> reward model -> RLHF)
so the outputs can be compared side by side.

Usage:
    uv run python eval/run_prompts.py --model HuggingFaceTB/SmolLM2-135M --tag 00_base
    uv run python eval/run_prompts.py --model checkpoints/sft --tag 01_sft --chat
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

EVAL_DIR = Path(__file__).parent
PROMPTS_FILE = EVAL_DIR / "coding_prompts.json"
RESULTS_DIR = EVAL_DIR / "results"


def build_input(tokenizer, prompt, chat):
    if chat:
        messages = [{"role": "user", "content": prompt}]
        return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    # Base models have no notion of turns, so feed the raw prompt plus a newline.
    return prompt + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="HuggingFaceTB/SmolLM2-135M")
    parser.add_argument("--tag", required=True, help="Name for this run, e.g. 00_base")
    parser.add_argument("--chat", action="store_true", help="Wrap prompts in the tokenizer's chat template")
    parser.add_argument("--max-new-tokens", type=int, default=200)
    args = parser.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    tokenizer = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForCausalLM.from_pretrained(args.model).to(device).eval()

    prompts = json.loads(PROMPTS_FILE.read_text(encoding="utf-8"))
    results = []
    for item in prompts:
        text = build_input(tokenizer, item["prompt"], args.chat)
        inputs = tokenizer(text, return_tensors="pt").to(device)
        with torch.no_grad():
            # Greedy decoding keeps runs deterministic, so changes between stages come from the weights.
            output = model.generate(
                **inputs,
                max_new_tokens=args.max_new_tokens,
                do_sample=False,
                pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
            )
        completion = tokenizer.decode(output[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
        results.append({"id": item["id"], "prompt": item["prompt"], "completion": completion})
        print(f"\n===== {item['id']} =====\n{item['prompt']}\n----- completion -----\n{completion}")

    RESULTS_DIR.mkdir(exist_ok=True)
    meta = {
        "tag": args.tag,
        "model": args.model,
        "chat": args.chat,
        "max_new_tokens": args.max_new_tokens,
        "decoding": "greedy",
    }
    out = {"meta": meta, "results": results}
    (RESULTS_DIR / f"{args.tag}.json").write_text(json.dumps(out, indent=2), encoding="utf-8")

    lines = [f"# {args.tag}", "", f"Model: `{args.model}` | chat template: {args.chat} | greedy, {args.max_new_tokens} new tokens", ""]
    for r in results:
        lines += [f"## {r['id']}", "", f"**Prompt:** {r['prompt']}", "", "```", r["completion"], "```", ""]
    (RESULTS_DIR / f"{args.tag}.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nSaved to {RESULTS_DIR / args.tag}.json/.md")


if __name__ == "__main__":
    main()
