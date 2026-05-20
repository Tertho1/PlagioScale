#!/usr/bin/env python3
"""Test if dependencies are installed in current environment."""

import sys

results = []

# Test numpy
try:
    import numpy
    results.append(f"✓ numpy {numpy.__version__}")
except ImportError as e:
    results.append(f"✗ numpy: {e}")

# Test sklearn
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    import sklearn
    results.append(f"✓ scikit-learn {sklearn.__version__}")
except ImportError as e:
    results.append(f"✗ scikit-learn: {e}")

# Test pypdf
try:
    from pypdf import PdfReader
    results.append(f"✓ pypdf imported")
except ImportError as e:
    results.append(f"✗ pypdf: {e}")

# Test python-docx
try:
    from docx import Document
    results.append(f"✓ python-docx imported")
except ImportError as e:
    results.append(f"✗ python-docx: {e}")

output = "\n".join(results)
print(output)

# Also write to file
with open("/tmp/import_test_results.txt", "w") as f:
    f.write(output)
