#!/usr/bin/env python3
"""
Migration runner script that handles the import path issues
"""

import sys
import os
from pathlib import Path

# Add the current directory to the Python path to fix import issues
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

# Now import and run the actual migration
if __name__ == "__main__":
    from migrate import main
    sys.exit(main())
