#!/bin/bash
# Run the Pricing Intelligence Dashboard
# This provides a real-time visualization of competitor prices and pricing recommendations

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Install/update dashboard dependencies
echo "Installing dependencies..."
pip install -q streamlit>=1.28.0 plotly>=5.17.0 pandas>=2.0.0

# Run dashboard
echo ""
echo "=========================================="
echo "Starting Pricing Intelligence Dashboard"
echo "=========================================="
echo ""
echo "The dashboard will open in your browser."
echo "URL: http://localhost:8501"
echo ""
echo "Press Ctrl+C to stop the server."
echo ""

streamlit run dashboard.py --logger.level=error
