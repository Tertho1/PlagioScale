#!/usr/bin/env python3
"""
Complete similarity pipeline test and fix script.
This script will:
1. Verify all dependencies are installed
2. Test text extraction
3. Test vectorization
4. Clear old (wrong) results and re-compute
"""
import sys
import os
sys.path.insert(0, '/app')

print("="*60)
print("SIMILARITY PIPELINE DIAGNOSTIC")
print("="*60)

# Step 1: Verify dependencies
print("\n1. DEPENDENCY CHECK")
print("-" * 60)
deps_ok = True

try:
    import numpy as np
    print(f"✓ numpy {np.__version__}")
except Exception as e:
    print(f"✗ numpy: {e}")
    deps_ok = False

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    print(f"✓ scikit-learn (TfidfVectorizer available)")
except Exception as e:
    print(f"✗ scikit-learn: {e}")
    deps_ok = False

try:
    from pypdf import PdfReader
    print(f"✓ pypdf")
except Exception as e:
    print(f"✗ pypdf: {e}")

try:
    from docx import Document
    print(f"✓ python-docx")
except Exception as e:
    print(f"✗ python-docx: {e}")

if not deps_ok:
    print("\n✗ CRITICAL: Missing dependencies for TF-IDF!")
    sys.exit(1)

# Step 2: Test extraction
print("\n2. EXTRACTION TEST")
print("-" * 60)

from worker_service.worker import Worker
from pathlib import Path

worker = Worker()

# Find the test batch files
batch_id = 'a04e2b60-dcee-4213-9eda-8373c2023fa8'
submissions_dir = '/app/uploads'
test_files = [
    f'/app/uploads/{batch_id}_001_test.txt',
    f'/app/uploads/{batch_id}_002_test.txt',
]

extracted_texts = []
for fpath in test_files:
    fname = Path(fpath).name
    if os.path.exists(fpath):
        try:
            text = worker._extract_text(fpath)
            extracted_texts.append((fpath, text))
            print(f"✓ {fname}: {len(text)} chars")
            if len(text) > 0:
                print(f"  First 80 chars: {repr(text[:80])}")
            else:
                print(f"  WARNING: File is EMPTY")
        except Exception as e:
            print(f"✗ {fname}: {e}")
    else:
        print(f"✗ {fname}: NOT FOUND")

if not extracted_texts:
    print("\n✗ CRITICAL: No files found to extract!")
    sys.exit(1)

# Step 3: Test vectorization
print("\n3. VECTORIZATION TEST")
print("-" * 60)

from shared.vectorizer import TextVectorizer
import json

vec = TextVectorizer()
print(f"TextVectorizer initialized")
print(f"  use_embeddings: {vec.use_embeddings}")

doc_ids = []
for i, (fpath, text) in enumerate(extracted_texts):
    doc_id = f'test_doc_{i}'
    doc_ids.append(doc_id)
    if len(text.strip()) > 0:
        ok = vec.add_document(doc_id, text)
        print(f"✓ Added {doc_id}: {len(text)} chars -> {ok}")
    else:
        print(f"✗ Skipped {doc_id}: text too short")

if len(vec.doc_ids) < 2:
    print("\n✗ CRITICAL: Could not add enough documents to vectorizer!")
    sys.exit(1)

matrix = vec.compute_similarity_matrix()
print(f"\nSimilarity matrix computed:")
print(json.dumps(matrix, indent=2))

# Check if result is correct
if doc_ids:
    d0, d1 = doc_ids[0], doc_ids[1]
    sim = matrix.get(d0, {}).get(d1, None)
    if sim is None:
        print(f"\n✗ ERROR: Matrix does not have expected keys!")
    elif sim > 0.5 and extracted_texts[0][1] == extracted_texts[1][1]:
        print(f"\n✓ SUCCESS: Identical texts show similarity {sim:.2%}")
    else:
        print(f"\n✗ WARNING: Similarity is {sim:.2%} (expected > 50% for identical)")

# Step 4: Re-process batch in the database
print("\n4. DATABASE UPDATE")
print("-" * 60)

from shared.database import get_submissions_by_batch, store_similarity_results
from shared.database import get_session, SessionLocal, SimilarityResult

# Fetch submissions from DB
subs = get_submissions_by_batch(batch_id)
print(f"Found {len(subs)} submissions in batch {batch_id}")
for sub in subs:
    print(f"  - {sub['submission_id']}: {sub.get('name', 'N/A')} ({Path(sub['file_path']).name})")

if len(subs) < 2:
    print("\n✗ ERROR: Expected at least 2 submissions!")
    sys.exit(1)

# Clear old results
print("\nClearing old similarity results...")
with get_session() as session:
    count = session.query(SimilarityResult).filter(SimilarityResult.batch_id == batch_id).delete()
    print(f"Deleted {count} old results")

# Re-compute and store
print("\nRe-computing similarity...")
vec2 = TextVectorizer()
for sub in subs:
    fpath = sub['file_path']
    sub_id = sub['submission_id']
    try:
        text = worker._extract_text(fpath)
        ok = vec2.add_document(sub_id, text)
        print(f"  {Path(fpath).name}: {len(text)} chars -> added={ok}")
    except Exception as e:
        print(f"  {Path(fpath).name}: ERROR - {e}")

new_matrix = vec2.compute_similarity_matrix()
print(f"\nNew matrix:")
print(json.dumps(new_matrix, indent=2))

# Store new results
if new_matrix:
    ok = store_similarity_results(batch_id, new_matrix)
    print(f"\nStored new results: {ok}")
else:
    print("\n✗ ERROR: Could not compute matrix!")

print("\n" + "="*60)
print("DIAGNOSTIC COMPLETE")
print("="*60)
