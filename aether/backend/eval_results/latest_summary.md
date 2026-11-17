# Evaluation run 20261117T145607Z

9 prompts (7 with a reference answer for BLEU/ROUGE, 9 scored for perplexity) × 6 sampling strategies.

| Strategy | Mean perplexity (n) | Mean BLEU (n) | Mean ROUGE-L (n) |
|---|---|---|---|

Perplexity is scored by a fixed local reference model (distilgpt2), independent of which provider generated the text - see `app/eval/metrics.py`. BLEU/ROUGE-L are scored only against prompts that have one reasonably correct reference answer; open-ended prompts (essay, poem) are excluded from those two columns by design, not because they failed.