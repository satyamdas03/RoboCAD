"""Fine-tune a local coder model on RoboCAD Feature-Tree JSON generation.

Uses QLoRA via unsloth (preferred) or peft+bitsandbytes (fallback) to fit a 7B
class model into ~8 GB of VRAM. After training, merges the LoRA adapter into the
base model so it can be quantized to GGUF and imported into Ollama.

Usage:
    # Preferred: unsloth path (fast, memory-efficient)
    python scripts/finetune_model.py --dataset training/feature_tree_train.jsonl --method unsloth --base-model unsloth/Qwen2.5-Coder-7B-Instruct

    # Fallback: peft path
    python scripts/finetune_model.py --dataset training/feature_tree_train.jsonl --method peft --base-model Qwen/Qwen2.5-Coder-7B-Instruct

    # Export to Ollama after training
    python scripts/finetune_model.py --dataset ... --export-ollama --ollama-name robocad-lora
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "models" / "robocad-lora"


def _load_dataset(path: Path) -> tuple[list[str], list[str]]:
    """Return (prompts, completions) from a feature-tree JSONL dataset."""
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")
    prompts: list[str] = []
    completions: list[str] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            prompt = row["prompt"]
            completion = json.dumps(row["feature_tree"], ensure_ascii=False, separators=(",", ":"))
            prompts.append(prompt)
            completions.append(completion)
    return prompts, completions


def _format_alpaca_prompts(prompts: list[str], completions: list[str]) -> list[dict[str, str]]:
    system = "You are a parametric CAD data-modeling assistant. Convert the user's part description into a RoboCAD Feature-Tree JSON object. Output only valid JSON."
    rows: list[dict[str, str]] = []
    for p, c in zip(prompts, completions):
        text = (
            f"Below is an instruction that describes a task, paired with an input that provides further context. "
            f"Write a response that appropriately completes the request.\n\n"
            f"### Instruction:\n{system}\n\n"
            f"### Input:\nPrompt: {p}\n\nOutput the Feature-Tree JSON.\n\n"
            f"### Response:\n{c}"
        )
        rows.append({"text": text})
    return rows


def _finetune_unsloth(
    dataset: list[dict[str, str]],
    base_model: str,
    output_dir: Path,
    epochs: int,
    batch_size: int,
    gradient_accumulation_steps: int,
    lora_rank: int,
    lora_alpha: int,
) -> Path:
    """Run QLoRA fine-tuning with unsloth. Returns path to the saved adapter/merged model."""
    try:
        import torch
        from datasets import Dataset
        from trl import SFTTrainer
        from unsloth import FastLanguageModel
        from transformers import TrainingArguments
    except ImportError as exc:
        raise RuntimeError(
            "unsloth path requires: pip install unsloth trl datasets transformers. "
            f"Missing dependency: {exc}"
        ) from exc

    max_seq_length = 4096
    dtype = None  # auto-detect

    print(f"Loading base model {base_model} with unsloth...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=base_model,
        max_seq_length=max_seq_length,
        dtype=dtype,
        load_in_4bit=True,
    )

    model = FastLanguageModel.get_peft_model(
        model,
        r=lora_rank,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_alpha=lora_alpha,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=42,
    )

    hf_dataset = Dataset.from_list(dataset)

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=hf_dataset,
        dataset_text_field="text",
        max_seq_length=max_seq_length,
        args=TrainingArguments(
            per_device_train_batch_size=batch_size,
            gradient_accumulation_steps=gradient_accumulation_steps,
            num_train_epochs=epochs,
            learning_rate=2e-4,
            fp16=not torch.cuda.is_bf16_supported(),
            bf16=torch.cuda.is_bf16_supported(),
            logging_steps=1,
            optim="adamw_8bit",
            weight_decay=0.01,
            lr_scheduler_type="linear",
            seed=42,
            output_dir=str(output_dir / "trainer_outputs"),
            report_to="none",
        ),
    )

    print("Starting unsloth training...")
    trainer.train()

    adapter_dir = output_dir / "adapter"
    model.save_pretrained_merged(adapter_dir, tokenizer, save_method="lora")
    print(f"Adapter saved to {adapter_dir}")

    merged_dir = output_dir / "merged"
    model.save_pretrained_merged(merged_dir, tokenizer, save_method="merged_16bit")
    print(f"Merged model saved to {merged_dir}")
    return merged_dir


def _finetune_peft(
    dataset: list[dict[str, str]],
    base_model: str,
    output_dir: Path,
    epochs: int,
    batch_size: int,
    gradient_accumulation_steps: int,
    lora_rank: int,
    lora_alpha: int,
) -> Path:
    """Run QLoRA fine-tuning with peft+bitsandbytes as a fallback."""
    try:
        import torch
        from datasets import Dataset
        from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
        from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments, Trainer
        from bitsandbytes import BitsAndBytesConfig
    except ImportError as exc:
        raise RuntimeError(
            "peft path requires: pip install peft bitsandbytes transformers datasets. "
            f"Missing dependency: {exc}"
        ) from exc

    print(f"Loading base model {base_model} with peft+bitsandbytes...")
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16,
    )
    tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )
    model = prepare_model_for_kbit_training(model)

    lora_config = LoraConfig(
        r=lora_rank,
        lora_alpha=lora_alpha,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_config)

    def tokenize(example: dict[str, str]) -> dict[str, Any]:
        return tokenizer(example["text"], truncation=True, padding="max_length", max_length=2048)

    hf_dataset = Dataset.from_list(dataset).map(tokenize, batched=False)

    trainer = Trainer(
        model=model,
        train_dataset=hf_dataset,
        args=TrainingArguments(
            per_device_train_batch_size=batch_size,
            gradient_accumulation_steps=gradient_accumulation_steps,
            num_train_epochs=epochs,
            learning_rate=2e-4,
            fp16=not torch.cuda.is_bf16_supported(),
            bf16=torch.cuda.is_bf16_supported(),
            logging_steps=1,
            optim="adamw_torch",
            save_strategy="no",
            output_dir=str(output_dir / "trainer_outputs"),
            report_to="none",
        ),
        data_collator=lambda data: {"input_ids": torch.stack([torch.tensor(d["input_ids"]) for d in data]),
                                    "attention_mask": torch.stack([torch.tensor(d["attention_mask"]) for d in data]),
                                    "labels": torch.stack([torch.tensor(d["input_ids"]) for d in data])},
    )

    print("Starting peft training...")
    trainer.train()

    adapter_dir = output_dir / "adapter"
    model.save_pretrained(adapter_dir)
    tokenizer.save_pretrained(adapter_dir)
    print(f"Adapter saved to {adapter_dir}")
    return adapter_dir


def _export_to_ollama(merged_dir: Path, ollama_name: str) -> None:
    """Convert a merged Hugging Face model to GGUF and create an Ollama model."""
    try:
        subprocess.run(["python", "-m", "pip", "install", "llama-cpp-python", "-q"], check=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"Failed to install llama-cpp-python: {exc}") from exc

    gguf_dir = merged_dir.parent / "gguf"
    gguf_dir.mkdir(parents=True, exist_ok=True)
    gguf_path = gguf_dir / "model.gguf"

    from llama_cpp import Llama
    # Use the convert script approach via Hugging Face is cleaner, but llama-cpp-python
    # does not expose conversion. Try using the llama.cpp CLI if available.
    convert_script = Path.home() / ".local" / "share" / "llama.cpp" / "convert_hf_to_gguf.py"
    if not convert_script.exists():
        raise RuntimeError(
            "GGUF conversion requires llama.cpp convert_hf_to_gguf.py. "
            "Please clone llama.cpp and run: python convert_hf_to_gguf.py --outfile model.gguf --outtype q4_k_m <merged_dir>"
        )

    subprocess.run(
        [sys.executable, str(convert_script), "--outfile", str(gguf_path), "--outtype", "q4_k_m", str(merged_dir)],
        check=True,
    )

    modelfile_dir = merged_dir.parent / "ollama"
    modelfile_dir.mkdir(parents=True, exist_ok=True)
    modelfile_path = modelfile_dir / "Modelfile"
    modelfile_path.write_text(f'FROM {gguf_path}\nPARAMETER temperature 0.0\nPARAMETER num_predict 4096\n', encoding="utf-8")
    subprocess.run(["ollama", "create", ollama_name, "-f", str(modelfile_path)], check=True)
    print(f"Ollama model created: {ollama_name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fine-tune a local model on RoboCAD feature trees.")
    parser.add_argument("--dataset", type=Path, required=True, help="Path to feature_tree_train.jsonl")
    parser.add_argument("--base-model", type=str, default="unsloth/Qwen2.5-Coder-7B-Instruct", help="Hugging Face base model")
    parser.add_argument("--method", type=str, choices=["unsloth", "peft"], default="unsloth", help="Fine-tuning backend")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR, help="Output directory")
    parser.add_argument("--epochs", type=int, default=3, help="Training epochs")
    parser.add_argument("--batch-size", type=int, default=1, help="Per-device batch size")
    parser.add_argument("--gradient-accumulation-steps", type=int, default=4, help="Gradient accumulation steps")
    parser.add_argument("--lora-rank", type=int, default=8, help="LoRA rank")
    parser.add_argument("--lora-alpha", type=int, default=16, help="LoRA alpha")
    parser.add_argument("--export-ollama", action="store_true", help="Export merged model to Ollama")
    parser.add_argument("--ollama-name", type=str, default="robocad-lora", help="Ollama model name")
    args = parser.parse_args()

    prompts, completions = _load_dataset(args.dataset)
    if len(prompts) < 10:
        raise ValueError(f"Need at least 10 training examples, found {len(prompts)}")

    print(f"Loaded {len(prompts)} training examples")
    args.output.mkdir(parents=True, exist_ok=True)

    dataset = _format_alpaca_prompts(prompts, completions)
    sample_path = args.output / "training_samples.jsonl"
    _write_jsonl(sample_path, dataset)

    if args.method == "unsloth":
        merged_dir = _finetune_unsloth(
            dataset,
            args.base_model,
            args.output,
            args.epochs,
            args.batch_size,
            args.gradient_accumulation_steps,
            args.lora_rank,
            args.lora_alpha,
        )
    else:
        merged_dir = _finetune_peft(
            dataset,
            args.base_model,
            args.output,
            args.epochs,
            args.batch_size,
            args.gradient_accumulation_steps,
            args.lora_rank,
            args.lora_alpha,
        )

    print(f"Fine-tuned model saved under {args.output}")
    print(f"Merged/adapter dir: {merged_dir}")

    if args.export_ollama:
        _export_to_ollama(merged_dir, args.ollama_name)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
