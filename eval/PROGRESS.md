# RLHF progress on the fixed coding prompts

Prompts: [coding_prompts.json](coding_prompts.json). Every stage runs them with greedy decoding and 200 new tokens via
[run_prompts.py](run_prompts.py), so differences come from the weights. Full outputs live in [results/](results/).

| Prompt | 00_base |
|---|---|
| reverse_string | Correct `s[::-1]`, then repeats it ~12 times with fake "Python 2/3" headers |
| is_prime | Starts plausibly, then hardcodes `n % 7`, `% 11`, ... `% 51` checks forever; wrong (21, 51 aren't prime; misses most composites) |
| fizzbuzz | Off-topic: writes an article about Fibonacci, no code |
| list_vs_tuple | Wrong (never mentions mutability) and loops the same two sentences |
| fix_bug | Removes the `+ 1` correctly, then repeats the fixed function ~11 times; no explanation |
| binary_search | Clean-looking code with a real bug: the `<` branch moves `end` instead of `start`, so it fails for most targets; then drifts into textbook prose ("In this unit...") |

## 00_base: SmolLM2-135M (no tuning)

- **Never stops.** No prompt ends naturally; every output runs to the 200-token limit. The model has no notion of
  "the answer is done" — this is the main thing SFT should fix (learning to emit EOS after a reply).
- **Loops a lot.** 4/6 outputs degenerate into repetition under greedy decoding.
- **Knows some code patterns.** `s[::-1]`, removing the `+ 1`, and the binary search skeleton are all there; the
  knowledge exists but isn't shaped into an answer.
- **Continues documents rather than following instructions.** It treats the prompt as the start of a tutorial page
  (markdown headers, "In this unit, we have learned..."), and in fizzbuzz it drifts to a different topic entirely.
- **Correctness:** 2/6 contain a correct core answer (reverse_string, fix_bug), 0/6 are a clean usable reply.
