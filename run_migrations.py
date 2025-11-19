#!/usr/bin/env python
"""
Helper script to run Alembic migrations.
Usage:
    python run_migrations.py upgrade    # Apply all pending migrations
    python run_migrations.py downgrade  # Rollback last migration
    python run_migrations.py current    # Show current version
    python run_migrations.py history    # Show migration history
"""
import os
import sys
import subprocess
from pathlib import Path

def run_alembic_command(command):
    """Run an Alembic command"""
    backend_dir = Path(__file__).parent
    os.chdir(backend_dir)
    
    try:
        result = subprocess.run(
            ["alembic"] + command.split(),
            check=True,
            capture_output=False
        )
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        print(f"Error running Alembic command: {e}")
        return False
    except FileNotFoundError:
        print("Error: Alembic not found. Make sure it's installed:")
        print("  pip install -r requirements.txt")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    command = " ".join(sys.argv[1:])
    success = run_alembic_command(command)
    sys.exit(0 if success else 1)

