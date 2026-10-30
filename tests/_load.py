"""Load project modules from hyphenated skill directories for unittest."""
import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def load(directory, module):
    path = ROOT / directory / (module + ".py")
    if not path.is_file():
        raise ImportError("Test module not found: " + str(path))
    name = "test_loaded_" + module
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load test module: " + str(path))
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[name] = loaded
    spec.loader.exec_module(loaded)
    return loaded
