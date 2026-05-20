#!/usr/bin/env python3
"""Test similarity pipeline inside worker environment"""
import sys
import os
import json
from pathlib import Path

print('=== IMPORT CHECKS ===')
try:
    import numpy as np
    print('✓ numpy:', np.__version__)
except Exception as e:
    print('✗ numpy:', e)
    sys.exit(1)

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    print('✓ sklearn available')
except Exception as e:
    print('✗ sklearn:', e)
    sys.exit(1)

try:
    from pypdf import PdfReader
    print('✓ pypdf available')
except Exception as e:
    print('✗ pypdf:', e)

try:
    from docx import Document
    print('✓ python-docx available')
except Exception as e:
    print('✗ python-docx:', e)

print()
print('=== FILE LISTING ===')
uploads_dir = '/app/uploads'
if os.path.exists(uploads_dir):
    files = os.listdir(uploads_dir)
    print(f'Files in {uploads_dir}: {len(files)} files')
    for f in sorted(files)[-10:]:
        fpath = os.path.join(uploads_dir, f)
        try:
            size = os.path.getsize(fpath)
            print(f'  {f} ({size} bytes)')
        except:
            pass
else:
    print(f'{uploads_dir} does not exist')

print()
print('=== EXTRACTION TEST ===')
sys.path.insert(0, '/app')

# Test direct file reading first
test_files = [
    '/app/uploads/a04e2b60-dcee-4213-9eda-8373c2023fa8_001_test.txt',
    '/app/uploads/a04e2b60-dcee-4213-9eda-8373c2023fa8_002_test.txt',
]

texts = []
for fpath in test_files:
    if os.path.exists(fpath):
        try:
            with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
            texts.append(text)
            print(f'{Path(fpath).name}: {len(text)} chars')
            if len(text) > 0:
                print(f'  HEAD: {repr(text[:100])}')
            else:
                print(f'  EMPTY FILE')
        except Exception as e:
            print(f'{Path(fpath).name}: ERROR - {e}')
    else:
        print(f'{Path(fpath).name}: NOT FOUND')

print()
print('=== VECTORIZATION TEST ===')
from shared.vectorizer import TextVectorizer

vec = TextVectorizer()
print(f'TextVectorizer.SKLEARN_AVAILABLE = {TfidfVectorizer.__module__}')

for i, text in enumerate(texts):
    doc_id = f'doc{i}'
    if text:
        ok = vec.add_document(doc_id, text)
        print(f'add_document({doc_id}, {len(text)} chars) = {ok}')
    else:
        print(f'add_document({doc_id}, EMPTY) = SKIPPED')

print(f'Total docs in vectorizer: {len(vec.doc_ids)}')

matrix = vec.compute_similarity_matrix()
print('Similarity matrix:')
print(json.dumps(matrix, indent=2))

if len(texts) == 2 and texts[0] == texts[1]:
    if matrix.get('doc0', {}).get('doc1', 0) > 0.5:
        print('\n✓ SUCCESS: Identical documents found with similarity > 0.5')
    else:
        print('\n✗ FAIL: Identical documents but similarity =', matrix.get('doc0', {}).get('doc1', 'NOT FOUND'))
