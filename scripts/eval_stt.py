#!/usr/bin/env python3
"""STT Accuracy & Word Error Rate (WER) Evaluation Script (Layer 7).

Measures:
1. Word Error Rate (WER) via jiwer.
2. Character Error Rate (CER) via jiwer.
3. Name & Entity Accuracy (% of proper names/institutions verbatim matched).
4. Layer-by-layer improvement: Baseline Raw -> Layer 2 Preprocessing -> Layer 4 Vocab/Phonetic -> Layer 5 LLM.

Usage:
    python scripts/eval_stt.py --self-test
    python scripts/eval_stt.py --audio-dir path/to/audios --ref-file path/to/refs.json
"""

import argparse
import json
import os
import sys
from typing import Any, Optional

try:
    import jiwer
except ImportError:
    print("Installing jiwer for speech evaluation...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "jiwer"])
    import jiwer

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.speech import fix_transcript
from app.services.speech_vocab import apply_vocabulary_corrections, load_vocab_glossary


SYNTHETIC_EVAL_BENCHMARK = [
    {
        "id": "regression_case_1",
        "candidate_name": "Abhinav",
        "university": "Sreenidhi University",
        "raw_stt": "My name is Avino. I'm University. I'm currently pursuing my PhD. My name is Abino I am from screen University I'm currently posting with degrees",
        "reference": "My name is Abhinav I am from Sreenidhi University I'm currently pursuing my degree.",
        "target_names": ["Abhinav", "Sreenidhi University"],
    },
    {
        "id": "indian_name_dinesh",
        "candidate_name": "Dinesh Kumar",
        "university": "Osmania University",
        "raw_stt": "hello my name is dinesh kumar and i completed my btech in osmania university",
        "reference": "Hello my name is Dinesh Kumar and I completed my B.Tech in Osmania University",
        "target_names": ["Dinesh", "Kumar", "Osmania University"],
    },
    {
        "id": "telugu_name_saicharan",
        "candidate_name": "Saicharan Keerthireddi",
        "university": "JNTU Hyderabad",
        "raw_stt": "i am saicharan keerthireddi from jntu hyderabad working on fast api and postgresql",
        "reference": "I am Saicharan Keerthireddi from JNTU Hyderabad working on FastAPI and PostgreSQL",
        "target_names": ["Saicharan", "Keerthireddi", "JNTU Hyderabad", "FastAPI", "PostgreSQL"],
    },
    {
        "id": "repetition_loop_sam",
        "candidate_name": "Sam",
        "university": "BITS Pilani",
        "raw_stt": "my name is Sam my name is Sam I use python for machine learning",
        "reference": "My name is Sam I use Python for machine learning",
        "target_names": ["Sam", "Python"],
    },
]


def calculate_name_accuracy(reference_names: list[str], hypothesis: str) -> float:
    """Calculate percentage of target names/institutions found verbatim in hypothesis."""
    if not reference_names:
        return 1.0
    matches = 0
    hyp_lower = hypothesis.lower()
    for name in reference_names:
        if name.lower() in hyp_lower:
            matches += 1
    return round((matches / len(reference_names)) * 100.0, 2)


def run_pipeline_on_text(
    raw_text: str,
    candidate_name: Optional[str] = None,
    vocabulary: Optional[set[str]] = None,
) -> dict[str, str]:
    """Simulate pipeline stages on text."""
    # Stage 0: Raw baseline
    stage0 = raw_text

    # Stage 4: Vocab & Phonetic correction
    stage4_vocab, _ = apply_vocabulary_corrections(
        stage0,
        candidate_name=candidate_name,
        vocabulary=vocabulary,
    )
    stage4_fixed = fix_transcript(stage4_vocab, candidate_name=candidate_name)

    return {
        "baseline": stage0,
        "layer4_vocab_phonetic": stage4_fixed,
    }


def evaluate_dataset(dataset: list[dict[str, Any]], verbose: bool = True) -> dict[str, Any]:
    """Run evaluation across a dataset and compute WER, CER, and Name Accuracy."""
    results: list[dict[str, Any]] = []

    raw_refs = []
    raw_hyps = []
    processed_hyps = []

    total_names_raw = 0.0
    total_names_proc = 0.0

    for item in dataset:
        ref = item["reference"]
        raw = item["raw_stt"]
        name = item.get("candidate_name")
        target_names = item.get("target_names", [name] if name else [])

        stages = run_pipeline_on_text(raw, candidate_name=name)
        proc = stages["layer4_vocab_phonetic"]

        raw_refs.append(ref)
        raw_hyps.append(raw)
        processed_hyps.append(proc)

        raw_name_acc = calculate_name_accuracy(target_names, raw)
        proc_name_acc = calculate_name_accuracy(target_names, proc)

        raw_wer = round(jiwer.wer(ref, raw) * 100.0, 2)
        proc_wer = round(jiwer.wer(ref, proc) * 100.0, 2)

        total_names_raw += raw_name_acc
        total_names_proc += proc_name_acc

        results.append({
            "id": item.get("id"),
            "reference": ref,
            "raw": raw,
            "processed": proc,
            "raw_wer": raw_wer,
            "processed_wer": proc_wer,
            "raw_name_acc": raw_name_acc,
            "processed_name_acc": proc_name_acc,
        })

    overall_raw_wer = round(jiwer.wer(raw_refs, raw_hyps) * 100.0, 2)
    overall_proc_wer = round(jiwer.wer(raw_refs, processed_hyps) * 100.0, 2)
    overall_raw_cer = round(jiwer.cer(raw_refs, raw_hyps) * 100.0, 2)
    overall_proc_cer = round(jiwer.cer(raw_refs, processed_hyps) * 100.0, 2)

    avg_name_raw = round(total_names_raw / max(1, len(dataset)), 2)
    avg_name_proc = round(total_names_proc / max(1, len(dataset)), 2)

    summary = {
        "samples_evaluated": len(dataset),
        "raw_wer": overall_raw_wer,
        "processed_wer": overall_proc_wer,
        "wer_improvement": round(overall_raw_wer - overall_proc_wer, 2),
        "raw_cer": overall_raw_cer,
        "processed_cer": overall_proc_cer,
        "raw_name_accuracy": avg_name_raw,
        "processed_name_accuracy": avg_name_proc,
        "name_accuracy_gain": round(avg_name_proc - avg_name_raw, 2),
        "details": results,
    }

    if verbose:
        print("\n" + "=" * 70)
        print("          SPEECH-TO-TEXT EVALUATION REPORT (eval_stt.py)         ")
        print("=" * 70)
        print(f"Total Test Cases Evaluated : {len(dataset)}")
        print("-" * 70)
        print(f"{'Metric':<28} | {'Baseline (Raw)':<16} | {'Layered Pipeline':<16} | {'Gain/Reduction'}")
        print("-" * 70)
        print(f"{'Word Error Rate (WER)':<28} | {overall_raw_wer:>14.2f}% | {overall_proc_wer:>14.2f}% | {summary['wer_improvement']:>+12.2f}%")
        print(f"{'Character Error Rate (CER)':<28} | {overall_raw_cer:>14.2f}% | {overall_proc_cer:>14.2f}% | {round(overall_raw_cer - overall_proc_cer, 2):>+12.2f}%")
        print(f"{'Name Accuracy':<28} | {avg_name_raw:>14.2f}% | {avg_name_proc:>14.2f}% | {summary['name_accuracy_gain']:>+12.2f}%")
        print("=" * 70)

        print("\nSample Detailed Breakdown:")
        for r in results:
            print(f"\n[Case: {r['id']}]")
            print(f"  Reference : {r['reference']}")
            print(f"  Raw Input : {r['raw']}")
            print(f"  Pipeline  : {r['processed']}")
            print(f"  WER       : {r['raw_wer']}% -> {r['processed_wer']}% (Names: {r['raw_name_acc']}% -> {r['processed_name_acc']}%)")

    return summary


def main():
    parser = argparse.ArgumentParser(description="Evaluate Speech-to-Text Accuracy & WER")
    parser.add_argument("--self-test", action="store_true", help="Run benchmark against regression test suite")
    parser.add_argument("--audio-dir", type=str, help="Directory containing audio files")
    parser.add_argument("--ref-file", type=str, help="JSON file mapping audio filename to ground truth reference")
    parser.add_argument("--out-json", type=str, help="Save evaluation report to JSON file")
    args = parser.parse_args()

    if args.audio_dir and args.ref_file:
        from app.services.speech import transcribe_audio

        if not os.path.exists(args.ref_file):
            print(f"Error: Reference file {args.ref_file} not found.")
            sys.exit(1)
        with open(args.ref_file, "r", encoding="utf-8") as f:
            ref_data = json.load(f)

        dataset = []
        for filename, ref_text in ref_data.items():
            audio_path = os.path.join(args.audio_dir, filename)
            if not os.path.exists(audio_path):
                continue
            with open(audio_path, "rb") as af:
                bytes_data = af.read()
            raw_result = transcribe_audio(bytes_data)
            dataset.append({
                "id": filename,
                "reference": ref_text,
                "raw_stt": raw_result,
            })
        summary = evaluate_dataset(dataset)
    else:
        # Default: self-test regression suite
        summary = evaluate_dataset(SYNTHETIC_EVAL_BENCHMARK)

    if args.out_json:
        with open(args.out_json, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        print(f"\nSaved evaluation metrics to {args.out_json}")


if __name__ == "__main__":
    main()

