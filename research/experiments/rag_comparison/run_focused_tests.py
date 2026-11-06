"""Run focused research-tool tests and preserve an exclusive local log."""
import io
import unittest
from pathlib import Path

root = Path(__file__).resolve().parent
out = root / "results" / "part2_unit_tests_12.log"
out.parent.mkdir(parents=True, exist_ok=True)
if out.exists():
    raise FileExistsError(f"Refusing to overwrite test log: {out}")
suite = unittest.defaultTestLoader.discover(str(root / "tests"))
stream = io.StringIO()
result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
text = stream.getvalue()
with out.open("x", encoding="utf-8") as handle:
    handle.write(text)
print(text, end="")
print(f"Saved test log: {out}")
raise SystemExit(0 if result.wasSuccessful() else 1)
