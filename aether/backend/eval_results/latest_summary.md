# Evaluation run 20261117T070315Z

9 prompts (7 with a reference answer for BLEU/ROUGE, 9 scored for perplexity) × 6 sampling strategies.

| Strategy | Mean perplexity (n) | Mean BLEU (n) | Mean ROUGE-L (n) |
|---|---|---|---|
| Greedy decoding | 1539.82 (9) | 32.89 (7) | 0.761 (7) |
| Low-temperature sampling | 1540.28 (9) | 32.78 (7) | 0.744 (7) |
| Nucleus (top-p) sampling | 1512.81 (9) | 31.42 (7) | 0.685 (7) |
| High-temperature random sampling | 815.72 (9) | 35.08 (7) | 0.677 (7) |
| Top-k sampling | 19.61 (9) | 4.14 (7) | 0.121 (7) |
| Beam search | 8.82 (9) | 5.31 (7) | 0.168 (7) |

Perplexity is scored by a fixed local reference model (distilgpt2), independent of which provider generated the text - see `app/eval/metrics.py`. BLEU/ROUGE-L are scored only against prompts that have one reasonably correct reference answer; open-ended prompts (essay, poem) are excluded from those two columns by design, not because they failed.