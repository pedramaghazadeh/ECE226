# ECE226
Study of CPU-Deployable LLMs: Performance Analysis Under Resource Constraints

### Using lm-eval on GPU
```lm_eval --model hf --model_args pretrained=meta-llama/Llama-3.2-1B-Instruct --tasks gsm8k,mathqa,mmlu_elementary_mathematics --device cuda:0 --batch_size 8```


### Using lm-eval on GPU with 4bit quantization
```lm_eval --model hf --model_args pretrained=meta-llama/Llama-3.2-1B-Instruct,load_in_4bit=True --tasks gsm8k,mathqa,mmlu_elementary_mathematics --device cuda:0 --batch_size 8```


### Using lm-eval on GPU with 8bit quantization
```lm_eval --model hf --model_args pretrained=meta-llama/Llama-3.2-1B-Instruct,load_in_8bit=True --tasks gsm8k,mathqa,mmlu_elementary_mathematics --device cuda:0 --batch_size 8```

### Running docker interactively with memory limited
```docker run ```

### Using lm-eval on CPU
```lm_eval --model hf --model_args pretrained=meta-llama/Llama-3.2-1B --tasks gsm8k,mathqa,mmlu_elementary_mathematics --
device cpu --batch_size 1 --trust_remote_code```

### To run on a specific benchmark, use the following command template, the final results will be written as a JSON file with the time-stamp in the same directory.
```python eval.py --model <model-name> --token <HF-token> --eval <[gsm8k, gsm1k, MMLU]> --device <CPU-MPS-cuda:i>```