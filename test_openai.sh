#!/bin/bash
# Quick test script for OpenAI integration
# 
# Usage:
#   ./test_openai.sh           # Run with mock (no API key needed)
#   ./test_openai.sh real      # Run with real OpenAI API

set -e

cd "$(dirname "$0")"

# Activate venv if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Check mode
if [ "$1" == "real" ]; then
    if [ -z "$OPENAI_API_KEY" ]; then
        echo "❌ ERROR: OPENAI_API_KEY not set"
        echo ""
        echo "Set your API key:"
        echo "  export OPENAI_API_KEY='sk-...'"
        echo ""
        echo "Or run in mock mode:"
        echo "  ./test_openai.sh"
        exit 1
    fi
    
    echo "🚀 Running eval harness with REAL OpenAI API"
    echo "⚠️  This will consume tokens"
    echo ""
    export USE_MOCK_AGENTS=false
else
    echo "🎭 Running eval harness in MOCK mode"
    echo "💡 To test with real API: ./test_openai.sh real"
    echo ""
    export USE_MOCK_AGENTS=true
fi

# Run eval harness
python -m app.agents.eval_harness

echo ""
echo "✅ Eval complete"

