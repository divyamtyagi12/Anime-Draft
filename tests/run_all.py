"""Dependency-free runner (pytest also works): python -m tests.run_all"""
import importlib, pkgutil, sys, traceback
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
fails = total = 0
for mod in sorted(m.name for m in pkgutil.iter_modules([str(Path(__file__).parent)]) if m.name.startswith("test_")):
    module = importlib.import_module(f"tests.{mod}")
    for name in dir(module):
        if name.startswith("test_"):
            total += 1
            try:
                getattr(module, name)()
                print("PASS", mod, name)
            except Exception:
                fails += 1
                print("FAIL", mod, name); traceback.print_exc()
print(f"{total - fails}/{total} passed")
sys.exit(1 if fails else 0)
