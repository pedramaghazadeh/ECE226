import argparse
import resource
import transformers
import torch
import random
import json
import datetime


import numpy as np

from transformers import AutoModelForCausalLM, AutoTokenizer
from datasets import load_dataset
from tqdm import tqdm

NUMBER_SHOT = 8
NUMBER_SAMPLES = 300

# # Limit memory usage (e.g., 1 GB)
# resource.setrlimit(resource.RLIMIT_AS, (1 * 1024**3, 1 * 1024**3))

# # CPU time limit (e.g., 60 seconds)
# resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
def generate_unique_time_id():
    return datetime.datetime.now().strftime("%Y%m%d%H%M%S%f")

unique_id = generate_unique_time_id()

def measure_flops(model, sequence_length=50):
    """
    Measure FLOPs and parameter count using ptflops.
    Note: For quantized models, reported FLOPs might not fully reflect low-precision ops.
    """
    from ptflops import get_model_complexity_info

    dummy_input_shape = (1, sequence_length)  
    macs, params = get_model_complexity_info(
        model, dummy_input_shape, as_strings=True,
        print_per_layer_stat=True, verbose=True
    )
    print("=== FLOPs and Parameter Count ===")
    print("MACs:", macs)
    print("Params:", params)


def measure_memory(model, tokenizer, prompt="Test prompt"):
    """
    Measure memory usage during a forward pass using torch.profiler.
    """
    import torch.profiler

    # Create a dummy input
    inputs = tokenizer(prompt, return_tensors="pt")
    inputs = {key: value.to("cpu") for key, value in inputs.items()}

    with torch.profiler.profile(
        activities=[torch.profiler.ProfilerActivity.CPU],
        profile_memory=True,
        record_shapes=True,
    ) as prof:
        model(**inputs)

    print("=== Memory Usage (sorted by CPU memory consumption) ===")
    print(prof.key_averages().table(sort_by="cpu_memory_usage", row_limit=10))


def nshot_chats(nshot_data: list, n: int, question: str, task="gsm8k") -> dict:

    def question_prompt(s):
        return f'Question: {s}'

    def answer_prompt(s):
        return f'Answer: {s}'

    chats = []

    random.seed(42)
    for qna in random.sample(nshot_data, n):
        chats.append(
            {"role": "user", "content": question_prompt(qna["question"])})
        if task == "mmlu":
            chats.append(
                {"role": "assistant", "content": answer_prompt(qna["ans"])})
        else:
            chats.append(
                {"role": "assistant", "content": answer_prompt(qna["answer"])})

    if task == "gsm8k":
        chats.append({"role": "user", "content": question_prompt(question)+" Let's think step by step. At the end, you MUST finish the sentence with '####' followed by the answer as an integer."})
    if task == "mathqa" or task == "mmlu":
        chats.append({"role": "user", "content": question_prompt(question)+" Let's think step by step. At the end, you MUST finish the sentence with '####' followed by a letter as the correct answer."})
    return chats


def extract_answer(answer: str, eos=None):
    if eos:
        answer = answer.split(eos)[0].strip()

    answer = answer.split('####')[-1].strip()
    # Removing possible non-numeric characters generated by the LLM
    for remove_char in [',', '$', '%', 'g']:
        answer = answer.replace(remove_char, '')

    try:
        return int(answer)
    except ValueError:
        return answer


def int_to_option(n: int):
    return chr(n + 97)


def preprocess_mathqa(example):
    options = example['options']
    prompt = f"Question: {example['Problem']}\nOptions: {options}"
    return {"question": prompt, "answer": example['Rationale'] + "\n####" + example['correct']}


def preprocess_mmlu(example):
    options = "a)" + example['choices'][0] + " b)" + example['choices'][1] + " c)" + example['choices'][2] + " d)" + example['choices'][3]
    prompt = f"Question: {example['question']}\nOptions: {options}"
    return {"question": prompt, "ans": "#### " + int_to_option(example['answer'])}


# Load GSM1K dataset (from a URL or local file)
def load_gsm1k_dataset(dataset_url="https://raw.githubusercontent.com/scaleapi/gsm1k_eval/main/data/gsm1k_test.json"):
    import requests

    response = requests.get(dataset_url)
    data = response.json()

    return data


def main(args):
    # Load model and tokenizer
    model = AutoModelForCausalLM.from_pretrained(args.model, token=args.token).to(args.device)
    if args.quantize:
        model = torch.quantization.quantize_dynamic(model, {torch.nn.Linear}, dtype=torch.qint8)

    tokenizer = AutoTokenizer.from_pretrained(args.model, token=args.token, return_dict=True)
    if args.model == "EleutherAI/gpt-neo-2.7B":
        tokenizer.chat_template = """
        {% for message in messages %}
        {% if message['role'] == 'user' %}
        User: {{ message['content'] }}
        {% elif message['role'] == 'assistant' %}
        Assistant: {{ message['content'] }}
        {% endif %}
        {% endfor %}
        Assistant:
        """
    tokenizer.pad_token = tokenizer.eos_token
    model.config.pad_token_id = tokenizer.eos_token_id
    generator = transformers.pipeline("text-generation", model=model, tokenizer=tokenizer, device=args.device, max_new_tokens=512)

    def get_response(chats):
        gen_text = generator(chats)  # First return sequence
        return gen_text[0]["generated_text"][-1]["content"]

    # Measure FLOPs and parameter count
    # print(f"Model {args.model} has FLOPs of {measure_flops(model)}")
    results = {"Model": args.model, "Device": args.device, "Quantized": args.quantize, "Timestamp": unique_id}
    
    if "gsm8k" in args.eval:
        correct = 0
        train_data = list(load_dataset("gsm8k", "main", split="test[:20]"))
        test_data = list(load_dataset("gsm8k", "main", split=f"test[20:{NUMBER_SAMPLES}]"))

        for i in tqdm(range((len(test_data)))):
            messages = nshot_chats(nshot_data=train_data, n=NUMBER_SHOT, question=test_data[i]['question'], task="gsm8k")
            response = get_response(messages)

            if extract_answer(response) == extract_answer(test_data[i]['answer']):
                correct += 1
        print(f"Accuracy of {args.model} on gsm8k: {correct/len(test_data)}")
        results["gsm8k"] = correct/len(test_data)

    if "mathqa" in args.eval:
        correct = 0
        mathqa = load_dataset("math_qa", split=f"train[:{NUMBER_SAMPLES}]")
        mathqa = mathqa.map(preprocess_mathqa)
        train_data = list(mathqa)[:20]
        test_data = list(mathqa)[20:]

        for i in tqdm(range(len(test_data))):
            messages = nshot_chats(nshot_data=train_data, n=NUMBER_SHOT, question=mathqa[i]['Problem'], task="mathqa")
            response = get_response(messages)
            if extract_answer(response) == extract_answer(test_data[i]['answer']):
                correct += 1
        print(f"Accuracy of {args.model} on math-qa: {correct/len(test_data)}")
        results["mathqa"] = correct/len(test_data)

    if "mmlu" in args.eval:
        correct = 0
        # Topics ['abstract_algebra', 'all', 'anatomy', 'astronomy', 'auxiliary_train', 'business_ethics', 'clinical_knowledge', 'college_biology', 
        # 'college_chemistry', 
        # 'college_computer_science', 
        # 'college_mathematics', 
        # 'college_medicine', 
        # 'college_physics', 
        # 'computer_security', 
        # 'conceptual_physics', 
        # 'econometrics', 
        # 'electrical_engineering', '
        # elementary_mathematics']
        mmlu = load_dataset("cais/mmlu", "elementary_mathematics", split=f"test[:{NUMBER_SAMPLES}]")
        mmlu = mmlu.map(preprocess_mmlu)
        train_data = list(mmlu)[:20]
        test_data = list(mmlu)[20:]

        for i in tqdm(range(len(test_data))):
            messages = nshot_chats(nshot_data=train_data, n=NUMBER_SHOT, question=test_data[i]['question'], task="mmlu")
            response = get_response(messages)
            if extract_answer(response) == extract_answer(test_data[i]['ans']):
                correct += 1
        print(f"Accuracy of {args.model} on mmlu-elemantary-mathematics: {correct/len(test_data)}")
        results["mmlu"] = correct/len(test_data)
    
    # Writing the results as a json file with the timestamp
    with open(f"results_{unique_id}.json", "w") as f:
        json.dump(results, f, indent=4)
    return

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test")

    parser.add_argument("--model", type=str, default="meta-llama/Llama-3.2-1B-instruct", help="Model name")
    parser.add_argument("--token", type=str, default="", help="Hugging Face API token")
    parser.add_argument("--device", type=str, default="cpu", help="Device to use (cpu, cuda)")
    parser.add_argument("--quantize", action="store_true", help="Quantize the model")
    parser.add_argument("--eval", type=list, default=["gsm8k", "mathqa", "mmlu"], help="List of evaluation datasets")

    args = parser.parse_args()
    main(args)