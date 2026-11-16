# Evaluation run 20261116T082744Z

9 prompts (7 with a reference answer for BLEU/ROUGE, 9 scored for perplexity) × 6 sampling strategies.

| Strategy | Mean perplexity (n) | Mean BLEU (n) | Mean ROUGE-L (n) |
|---|---|---|---|
| Greedy decoding | 1542.37 (9) | 32.88 (7) | 0.769 (7) |
| Low-temperature sampling | 867.13 (9) | 33.16 (7) | 0.757 (7) |
| Nucleus (top-p) sampling | 815.26 (9) | 31.6 (7) | 0.673 (7) |
| High-temperature random sampling | 865.08 (9) | 41.46 (7) | 0.803 (7) |
| Top-k sampling | 21.35 (9) | 0.53 (7) | 0.041 (7) |
| Beam search | 9.35 (9) | 5.34 (7) | 0.169 (7) |

Perplexity is scored by a fixed local reference model (distilgpt2), independent of which provider generated the text — see `app/eval/metrics.py`. BLEU/ROUGE-L are scored only against prompts that have one reasonably correct reference answer; open-ended prompts (essay, poem) are excluded from those two columns by design, not because they failed.