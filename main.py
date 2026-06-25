"""
ENTRY POINT
Run: python main.py
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

if __name__ == "__main__":
    from core.orchestrator import main
    main()
