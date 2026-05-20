#!/usr/bin/env python3
"""Copy files from container and test extraction locally."""

import subprocess
import os
from pathlib import Path

# Files to check
files_to_check = [
    "a04e2b60-dcee-4213-9eda-8373c2023fa8_001_test.txt",
    "a04e2b60-dcee-4213-9eda-8373c2023fa8_002_test.txt"
]

work_dir = Path("d:/temp/uploads_debug")
work_dir.mkdir(parents=True, exist_ok=True)

print(f"Working directory: {work_dir}")

# Copy files from api-service container
for fname in files_to_check:
    src = f"plagioscale-api-service:/app/uploads/{fname}"
    dst = work_dir / fname
    print(f"\nCopying {fname}...")
    result = subprocess.run(
        ["docker", "cp", src, str(dst)],
        capture_output=True,
        text=True
    )
    if result.returncode == 0:
        if dst.exists():
            with open(dst, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            print(f"  ✓ {fname}: {len(content)} bytes")
            print(f"  Content: {content[:200]!r}")
        else:
            print(f"  ✗ File copy reported success but file doesn't exist")
    else:
        print(f"  ✗ Copy failed: {result.stderr}")

# Now test extraction and vectorization locally
print("\n" + "="*60)
print("Testing extraction and vectorization locally")
print("="*60)

import sys
sys.path.insert(0, str(Path(__file__).parent))

from shared.vectorizer import TextVectorizer

# Create test files if they don't exist
if not (work_dir / files_to_check[0]).exists():
    print("\nCreating test files...")
    (work_dir / files_to_check[0]).write_text("This is a test document with some content for plagiarism detection.")
    (work_dir / files_to_check[1]).write_text("This is a test document with some content for plagiarism detection.")

vec = TextVectorizer()
texts_added = 0

for fname in files_to_check:
    fpath = work_dir / fname
    if fpath.exists():
        with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
            text = f.read()
        doc_id = fname.replace('.txt', '')
        if vec.add_document(doc_id, text):
            texts_added += 1
            print(f"✓ Added {doc_id}: {len(text)} chars")
        else:
            print(f"✗ Rejected {doc_id}: text too short ({len(text)} < 10)")

print(f"\nTotal documents added to vectorizer: {texts_added}")

if texts_added >= 2:
    import json
    matrix = vec.compute_similarity_matrix()
    print("Similarity matrix:")
    print(json.dumps(matrix, indent=2))
else:
    print("Not enough documents to compute similarity")
