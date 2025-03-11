# ECE226
Study of CPU-Deployable LLMs: Performance Analysis Under Resource Constraints

### To run on a specific benchmark, use the following command template, the final results will be written as a JSON file with the time-stamp in the same directory.
```python eval.py --model <model-name> --token <HF-token> --eval <[gsm8k, gsm1k, MMLU]> --device <CPU-MPS-cuda:i>```