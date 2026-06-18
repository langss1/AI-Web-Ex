"""
=============================================================
SYSTEM CHECK — Verify all components before running agent
=============================================================
Run: python check_system.py
=============================================================
"""

import sys

def check(label, fn):
    try:
        result = fn()
        print(f"  ✅ {label}: {result}")
        return True
    except Exception as e:
        print(f"  ❌ {label}: {e}")
        return False


print("\n" + "="*55)
print(" AUTONOMOUS PENTEST AGENT — SYSTEM CHECK")
print("="*55 + "\n")

all_ok = True

# 1. Python version
def check_python():
    v = sys.version_info
    assert v >= (3, 9), f"Python 3.9+ required, got {v.major}.{v.minor}"
    return f"Python {v.major}.{v.minor}.{v.micro}"
all_ok &= check("Python version", check_python)

# 2. requests
def check_requests():
    import requests
    return f"requests {requests.__version__}"
all_ok &= check("requests library", check_requests)

# 3. BeautifulSoup
def check_bs4():
    import bs4
    return f"beautifulsoup4 {bs4.__version__}"
all_ok &= check("beautifulsoup4", check_bs4)

# 4. Ollama running
def check_ollama():
    import requests
    r = requests.get("http://localhost:11434/api/tags", timeout=5)
    models = [m["name"] for m in r.json().get("models", [])]
    qwen = [m for m in models if "qwen2.5" in m]
    if not qwen:
        raise Exception("qwen2.5:7b not found — run: ollama pull qwen2.5:7b")
    return f"Ollama OK | Models: {qwen}"
all_ok &= check("Ollama + Qwen 2.5", check_ollama)

# 5. DVWA
def check_dvwa():
    import requests
    r = requests.get("http://localhost/dvwa/login.php", timeout=5)
    assert r.status_code == 200, f"HTTP {r.status_code}"
    assert "DVWA" in r.text or "Damn" in r.text, "DVWA HTML not detected"
    return "DVWA reachable at localhost/dvwa"
all_ok &= check("DVWA (localhost)", check_dvwa)

# 6. ChromaDB (optional)
def check_chromadb():
    import chromadb
    return f"chromadb {chromadb.__version__} (RAG enabled)"
chroma_ok = check("chromadb (optional)", check_chromadb)
if not chroma_ok:
    print("    → RAG will use keyword fallback (still works)")

# 7. sentence-transformers (optional)
def check_st():
    import sentence_transformers
    return f"sentence-transformers {sentence_transformers.__version__}"
st_ok = check("sentence-transformers (optional)", check_st)
if not st_ok:
    print("    → Will use default ChromaDB embedding if ChromaDB available")

print("\n" + "="*55)
if all_ok:
    print(" ✅ ALL CRITICAL CHECKS PASSED — Ready to run!")
    print(" Run: python orchestrator.py")
else:
    print(" ⚠️  Some checks failed — fix errors above first.")
    print(" Then re-run: python check_system.py")
print("="*55 + "\n")
