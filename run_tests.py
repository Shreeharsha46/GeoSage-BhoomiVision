import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent if '__file__' in globals() else Path.cwd()

# Set up environment for the application
try:
    from app import create_app
    app = create_app('testing')

    # Run tests
    import pytest
    result = pytest.main(['tests/', '-q', '--tb=short'])

    sys.exit(result.retcode if result.retcode is not None else 0)

except ImportError as e:
    print(f"Import error: {e}")
    sys.exit(1)
