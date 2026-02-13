#!/usr/bin/env python3
"""
Test Taxonomy Engine Setup

Verifies:
1. Ollama is running
2. Model is available
3. PyMuPDF can extract text
4. LLM can generate responses

Usage:
    python -m admin.test_taxonomy_setup
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_ollama():
    """Test Ollama connection and model availability."""
    print("Testing Ollama connection...")
    
    try:
        import requests
        
        # Check if Ollama is running
        try:
            response = requests.get("http://localhost:11434/api/tags", timeout=5)
            if response.status_code != 200:
                print("  ❌ Ollama not responding")
                return False
        except Exception as e:
            print(f"  ❌ Cannot connect to Ollama: {e}")
            print("     Make sure Ollama is running: ollama serve")
            return False
        
        # Check for recommended models
        models_data = response.json()
        models = [m.get("name", "") for m in models_data.get("models", [])]
        
        print(f"  ✅ Ollama is running")
        print(f"  Available models: {', '.join(models) if models else 'none'}")
        
        # Check for recommended models
        recommended = ["llama3.1:8b", "qwen2.5:7b"]
        found = [m for m in recommended if any(m in model for model in models)]
        
        if found:
            print(f"  ✅ Found recommended model: {found[0]}")
            return True
        else:
            print(f"  ⚠️  No recommended models found")
            print(f"     Pull a model: ollama pull llama3.1:8b")
            return False
    
    except ImportError:
        print("  ❌ requests not installed: pip install requests")
        return False


def test_pymupdf():
    """Test PyMuPDF installation."""
    print("\nTesting PyMuPDF...")
    
    try:
        import fitz
        print(f"  ✅ PyMuPDF version: {fitz.version[0]}")
        return True
    except ImportError:
        print("  ❌ PyMuPDF not installed: pip install pymupdf")
        return False


def test_llm_generation():
    """Test that LLM can generate a simple response."""
    print("\nTesting LLM generation...")
    
    try:
        from admin.taxonomy_engine import OllamaClient
        
        llm = OllamaClient(model="llama3.1:8b")
        
        if not llm.check_available():
            print("  ❌ Model llama3.1:8b not available")
            print("     Try: ollama pull llama3.1:8b")
            return False
        
        print("  Generating test response...")
        response = llm.generate("Say 'Hello' if you can read this.", max_tokens=10)
        
        if response and len(response) > 0:
            print(f"  ✅ LLM responded: {response[:50]}...")
            return True
        else:
            print("  ❌ LLM returned empty response")
            return False
    
    except Exception as e:
        print(f"  ❌ Error testing LLM: {e}")
        return False


def test_pdf_extraction():
    """Test PDF text extraction."""
    print("\nTesting PDF extraction...")
    
    # Look for a test PDF
    pdf_dirs = [
        Path(__file__).parent.parent / "batch1books",
        Path(__file__).parent.parent / "templates" / "cleanbooks"
    ]
    
    test_pdf = None
    for pdf_dir in pdf_dirs:
        if pdf_dir.exists():
            pdfs = list(pdf_dir.glob("*.pdf"))
            if pdfs:
                test_pdf = pdfs[0]
                break
    
    if not test_pdf:
        print("  ⚠️  No PDF found to test (this is OK)")
        return True
    
    try:
        from admin.taxonomy_engine import extract_text_with_pymupdf
        
        text, pages, toc = extract_text_with_pymupdf(test_pdf)
        
        if text and len(text) > 100:
            print(f"  ✅ Extracted {len(text)} chars, {pages} pages from {test_pdf.name}")
            return True
        else:
            print(f"  ⚠️  Extracted text seems short: {len(text)} chars")
            return False
    
    except Exception as e:
        print(f"  ❌ Error extracting PDF: {e}")
        return False


def main():
    print("=" * 70)
    print("TAXONOMY ENGINE SETUP TEST")
    print("=" * 70)
    print()
    
    tests = [
        ("Ollama", test_ollama),
        ("PyMuPDF", test_pymupdf),
        ("LLM Generation", test_llm_generation),
        ("PDF Extraction", test_pdf_extraction)
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"  ❌ Test failed with exception: {e}")
            results.append((name, False))
    
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    
    all_passed = True
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{name:20} {status}")
        if not passed:
            all_passed = False
    
    print()
    if all_passed:
        print("✅ All tests passed! Ready to run taxonomy engine.")
        print("\nNext step:")
        print("  python -m admin.taxonomy_engine batch1books/Meditations.pdf artifacts/")
    else:
        print("❌ Some tests failed. Fix issues above before proceeding.")
    
    print()


if __name__ == '__main__':
    main()
