import os
import sys
import json
from pathlib import Path
from typing import List, Dict

# Setup paths for backend import
sys.path.append(str(Path(__file__).parent.parent))

from context_engine.core.pipeline import pipeline
from context_engine.retrieval.models import RetrievalQuery
from context_engine.prompt_builder.models import PromptMode

TEST_PROJECT_ROOT = str(Path(__file__).parent.parent.parent / "workspace" / "nexus_test_backend")

TEST_CASES = [
    {
        "id": "TC1",
        "name": "Add transaction fee support",
        "goal": "Add transaction fee support to the payment processing logic",
        "mode": PromptMode.FEATURE,
        "active_file": "api/payment_routes.py",
        "expected_targets": ["services/payment_service.py"]
    },
    {
        "id": "TC2",
        "name": "Extract payment validation",
        "goal": "Extract payment validation into a dedicated validator in utils/validators.py",
        "mode": PromptMode.REFACTOR,
        "active_file": "services/payment_service.py",
        "expected_targets": ["utils/validators.py"]
    },
    {
        "id": "TC3",
        "name": "Fix session expiry bug",
        "goal": "Fix bug where session tokens do not expire correctly in auth_service",
        "mode": PromptMode.BUGFIX,
        "active_file": "api/auth_routes.py",
        "expected_targets": ["services/auth_service.py", "utils/cache.py"]
    }
]

def run_evaluation():
    print(f"--- NEXUS RETRIEVAL EVALUATION ---")
    print(f"Project: {TEST_PROJECT_ROOT}")
    
    # Initialize pipeline
    pipeline.initialize_project(TEST_PROJECT_ROOT)
    
    results = []
    
    for tc in TEST_CASES:
        print(f"\nRunning {tc['id']}: {tc['name']}...")
        
        query = RetrievalQuery(
            task=tc['goal'],
            mode=tc['mode'],
            active_file=tc['active_file']
        )
        
        # 1. Retrieval
        candidates = pipeline.retrieval.retrieve(query, limit=5)
        
        # 2. Extraction
        context = pipeline.extraction.extract_context(tc['active_file'], candidates)
        
        # Metrics
        rankings = [c.file_metadata.rel_path for c in candidates]
        
        # Extraction metrics
        all_extracted = []
        if context.active_file: all_extracted.append(context.active_file)
        all_extracted.extend(context.related_files)
        
        total_loc = 0
        full_dumps = 0
        slices = 0
        
        for f in all_extracted:
            file_loc = sum(len(s.content.splitlines()) for s in f.slices)
            total_loc += file_loc
            
            # Heuristic for full dump: if first slice starts at 1 and covers most of the file (proxied by name)
            if any(s.reason == "Active File" or "Retrieved" in s.reason for s in f.slices) and any(s.start_line == 1 for s in f.slices):
                # Simple check: if it's the only slice and reason is generic
                if len(f.slices) == 1 and ("Active File" in f.slices[0].reason or "Retrieved" in f.slices[0].reason):
                    full_dumps += 1
                else:
                    slices += 1
            else:
                slices += 1

        accuracy = 0
        for target in tc['expected_targets']:
            if target in rankings[:3]: # Target in top 3
                accuracy += 1
        accuracy_score = accuracy / len(tc['expected_targets'])
        
        res = {
            "id": tc['id'],
            "accuracy": accuracy_score,
            "rankings": rankings,
            "full_dumps": full_dumps,
            "slices": slices,
            "total_loc": total_loc,
            "avg_loc_per_file": total_loc / len(all_extracted) if all_extracted else 0
        }
        results.append(res)
        
        print(f"  Accuracy (Top 3): {accuracy_score*100:.1f}%")
        print(f"  Top Match: {rankings[0] if rankings else 'N/A'}")
        print(f"  Extraction: {full_dumps} Full Dumps, {slices} Slices")
        print(f"  Total LOC: {total_loc}")

    # Summary
    avg_accuracy = sum(r['accuracy'] for r in results) / len(results)
    total_full = sum(r['full_dumps'] for r in results)
    total_slices = sum(r['slices'] for r in results)
    
    print(f"\n--- FINAL SUMMARY ---")
    print(f"Average Accuracy: {avg_accuracy*100:.1f}%")
    print(f"Full Dump Rate: {total_full / (total_full + total_slices) * 100:.1f}%")
    print(f"Slicing Rate: {total_slices / (total_full + total_slices) * 100:.1f}%")

if __name__ == "__main__":
    run_evaluation()
