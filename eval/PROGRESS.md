# RLHF progress on the fixed coding prompts

Prompts: [coding_prompts.json](coding_prompts.json). Every run uses [run_prompts.py](run_prompts.py) with greedy
decoding and 200 new tokens. Full outputs live in [results/](results/).

## Controlled comparison

| Run | Weights | Prompt format | Tag |
|---|---|---|---|
| A | Base | Raw (`prompt + "\n"`) | `00_base_raw` |
| B | Base | ChatML | `00_base_chatml` |
| C | SFT | Same ChatML | `01_sft_chatml` (after SFT) |

- **B vs C** changes only the weights, so it isolates the effect of training.
- **A vs C** shows the whole change from using a raw pretrained model to using an instruction-tuned assistant.

The ChatML template is defined once in [chat_format.py](chat_format.py) and always passed explicitly, never taken from
the checkpoint. The base tokenizer ships with no chat template at all, and an SFT checkpoint could ship a different
one, so this keeps B and C byte-identical. **SFT training must use the same `CHATML_TEMPLATE`** (no default system
message).

## Termination

Generation stops on `<|endoftext|>` or `<|im_end|>`. Each result records `stop_reason` (`eos` / `max_new_tokens`),
which stop token fired, and `num_new_tokens`.

| Run | Ended on a stop token | Mean new tokens |
|---|---|---|
| A `00_base_raw` | 0/6 | 200 |
| B `00_base_chatml` | 0/6 | 200 |

## Per-prompt notes

| Prompt | A: base, raw | B: base, ChatML |
|---|---|---|
| reverse_string | Correct `s[::-1]`, then repeats it ~12 times with fake "Python 2/3" headers | Echoes the prompt, then `## 1.1.1.1`, `## 1.1.1.2`, ... numbering; no code |
| is_prime | Starts plausibly, then hardcodes `n % 7`, `% 11`, ... `% 51` checks; wrong | Echoes prompt, then a **correct** trial-division-to-sqrt version, then repeats it |
| fizzbuzz | Off-topic: writes an article about Fibonacci, no code | Echoes the prompt over and over (and changes "1 to 15" to "1 to 100"); no code |
| list_vs_tuple | Wrong (never mentions mutability) and loops the same two sentences | Echoes prompt, then `1.1.1.1.1...` forever |
| fix_bug | Removes the `+ 1` correctly, then repeats the fixed function ~11 times | No code; repeats "The average of the numbers in the list is 1." |
| binary_search | Clean-looking code with a real bug (the `<` branch moves `end` instead of `start`); then textbook prose | Echoes prompt, then a linear scan labelled binary search, with contradictory comments |

## 00_base: SmolLM2-135M (no tuning)

- **It never stops, in either format.** 0/6 for A and 0/6 for B. The ChatML tokens exist in the vocabulary
  (`<|im_start|>`=1, `<|im_end|>`=2), but the base model has never learned to emit `<|im_end|>` after a reply. This is
  the main measurable thing SFT should change.
- **ChatML alone doesn't help the base model; it mostly hurts.** Under ChatML the model usually echoes the user turn
  and then falls into section-number loops (`## 1.1.1.1`). It treats the template as unfamiliar document structure,
  not as a conversation. Core answers: A gets 2/6 right (reverse_string, fix_bug), B gets 1/6 (is_prime). The prompts
  where each one succeeds don't overlap, which suggests formatting noise rather than a real difference in ability at
  this size.
- **Loops a lot.** Most outputs in both runs degenerate into repetition under greedy decoding.
- **Knows some code patterns.** `s[::-1]`, removing the `+ 1`, the sqrt-bounded prime test, and the binary search
  skeleton all appear somewhere; the knowledge exists but isn't shaped into an answer.
- **Six prompts are only a qualitative baseline.** Numerical claims about coding ability will need a larger held-out
  dataset with executed tests (to be chosen from an existing benchmark later).
