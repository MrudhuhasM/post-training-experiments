"""The single ChatML template used for every chat-formatted run and for SFT training.

The base SmolLM2-135M tokenizer ships with no chat template, and later checkpoints may ship a
different one. Passing this template explicitly keeps the prompt bytes identical across stages,
so a base-vs-SFT comparison under ChatML changes only the weights.

No default system message is injected (unlike SmolLM2-135M-Instruct's template).
"""

CHATML_TEMPLATE = (
    "{% for message in messages %}"
    "{{ '<|im_start|>' + message['role'] + '\n' + message['content'] + '<|im_end|>' + '\n' }}"
    "{% endfor %}"
    "{% if add_generation_prompt %}{{ '<|im_start|>assistant\n' }}{% endif %}"
)

# Generation stops on either token; the stop reason records which one.
STOP_TOKENS = ["<|endoftext|>", "<|im_end|>"]
