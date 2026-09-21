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

EVAL_DIR = Path(__file__).parent
PROMPTS_FILE = EVAL_DIR / "coding_prompts.json"
RESULTS_DIR = EVAL_DIR / "results"

# The chat template SFT training uses too. The base tokenizer ships without one, so every chatml run
# borrows this one rather than the checkpoint's own, keeping the prompt bytes identical across stages.
CHAT_TEMPLATE_SOURCE = "HuggingFaceTB/SmolLM-135M-Instruct"
# Generation stops on either token; the stop reason records which one.
STOP_TOKENS = ["<|endoftext|>", "<|im_end|>"]


# ---------- setup ----------

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="HuggingFaceTB/SmolLM2-135M")
    parser.add_argument("--tag", required=True, help="Name for this run, e.g. 00_base_raw")
    parser.add_argument("--format", choices=["raw", "chatml"], required=True, help="Prompt format")
    parser.add_argument("--max-new-tokens", type=int, default=200)
    return parser.parse_args()


def load_model(model_name):
    device = "cuda" if torch.cuda.is_available() else "cpu"
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForCausalLM.from_pretrained(model_name).to(device).eval()
    return model, tokenizer


def load_chat_template(fmt):
    if fmt != "chatml":
        return None
    return AutoTokenizer.from_pretrained(CHAT_TEMPLATE_SOURCE).chat_template


def load_prompts():
    return json.loads(PROMPTS_FILE.read_text(encoding="utf-8"))


# ---------- generation ----------

def build_input(tokenizer, prompt, chat_template):
    if chat_template:
        messages = [{"role": "user", "content": prompt}]
        return tokenizer.apply_chat_template(
            messages, chat_template=chat_template, tokenize=False, add_generation_prompt=True
        )
    # Base models have no notion of turns, so feed the raw prompt plus a newline.
    return prompt + "\n"


def generate(model, tokenizer, text, max_new_tokens):
    """Greedy-decode one input and report the completion and why generation stopped."""
    stop_ids = {tokenizer.convert_tokens_to_ids(t): t for t in STOP_TOKENS}
    inputs = tokenizer(text, return_tensors="pt").to(model.device)
    with torch.no_grad():
        # Greedy decoding keeps runs deterministic, so changes between stages come from the weights.
        output = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            eos_token_id=list(stop_ids),
            pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
        )
    new_ids = output[0][inputs["input_ids"].shape[1]:].tolist()

    # A stop token as the last generated id means the model ended on its own; otherwise it hit the cap.
    stop_token = stop_ids.get(new_ids[-1]) if new_ids else None
    return {
        "completion": tokenizer.decode(new_ids, skip_special_tokens=True),
        "stop_reason": "eos" if stop_token else "max_new_tokens",
        "stop_token": stop_token,
        "num_new_tokens": len(new_ids),
    }


def run_prompts(model, tokenizer, prompts, chat_template, max_new_tokens):
    results = []
    for item in prompts:
        text = build_input(tokenizer, item["prompt"], chat_template)
        result = {"id": item["id"], "prompt": item["prompt"], "input_text": text}
        result |= generate(model, tokenizer, text, max_new_tokens)
        print_result(result)
        results.append(result)
    return results


def count_terminated(results):
    return f"{sum(r['stop_reason'] == 'eos' for r in results)}/{len(results)}"


# ---------- output ----------

def print_result(r):
    print(f"\n===== {r['id']} =====\n{r['prompt']}")
    print(f"----- completion ({r['stop_reason']}, {r['num_new_tokens']} tokens) -----\n{r['completion']}")


def build_meta(args, results):
    return {
        "tag": args.tag,
        "model": args.model,
        "format": args.format,
        "chat_template_source": CHAT_TEMPLATE_SOURCE if args.format == "chatml" else None,
        "max_new_tokens": args.max_new_tokens,
        "decoding": "greedy",
        "stop_tokens": STOP_TOKENS,
        "terminated": count_terminated(results),
    }


def save_json(path, meta, results):
    out = {"meta": meta, "results": results}
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")


def save_markdown(path, meta, results):
    lines = [
        f"# {meta['tag']}",
        "",
        f"Model: `{meta['model']}` | format: {meta['format']} | greedy, {meta['max_new_tokens']} new tokens"
        f" | terminated on a stop token: {meta['terminated']}",
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
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------- entry point ----------

def main():
    args = parse_args()
    model, tokenizer = load_model(args.model)
    chat_template = load_chat_template(args.format)

    results = run_prompts(model, tokenizer, load_prompts(), chat_template, args.max_new_tokens)
    meta = build_meta(args, results)
    print(f"\nTerminated on a stop token: {meta['terminated']}")

    RESULTS_DIR.mkdir(exist_ok=True)
    save_json(RESULTS_DIR / f"{args.tag}.json", meta, results)
    save_markdown(RESULTS_DIR / f"{args.tag}.md", meta, results)
    print(f"\nSaved to {RESULTS_DIR / args.tag}.json/.md")


if __name__ == "__main__":
    main()
