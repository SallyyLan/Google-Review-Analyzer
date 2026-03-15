"""
Pytest configuration. Use in-memory SQLite for tests so the main app.db is not touched.
"""
import os
import sys

# Use in-memory SQLite for tests (set before app/core are imported)
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
