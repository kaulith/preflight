import os
import re
from pathlib import Path

SKIP_DIRS = frozenset({".git", "__pycache__", "node_modules", "dist"})
TEST_DIRS = frozenset({"tests", "cypress", "e2e"})
TEST_FILE = re.compile(r"^test_|\.(?:spec|test|cy)\.")
FRONTEND_SUFFIXES = (".js", ".mjs", ".ts", ".jsx", ".tsx", ".vue", ".scss")
LONGEST_WRITTEN_LINE = 2000


def source_files(root: Path, suffix: str | tuple[str, ...], skip_tests: bool = False) -> list[Path]:
	"""Every `suffix` file under `root`, minus vendored, built and minified ones."""
	paths = []
	for directory, dirnames, filenames in os.walk(root):
		dirnames[:] = [
			name for name in dirnames if name not in SKIP_DIRS and not (skip_tests and name in TEST_DIRS)
		]
		paths += [
			Path(directory, name)
			for name in filenames
			if name.endswith(suffix)
			and not name.endswith(".min.js")
			and not (skip_tests and TEST_FILE.search(name))
		]
	return sorted(paths)


def frontend_files(app_root: Path, skip_tests: bool = False) -> list[Path]:
	"""Every JavaScript, TypeScript, Vue and SCSS file in the app's repository, `frontend/` and `desk/`
	included."""
	return source_files(app_root, FRONTEND_SUFFIXES, skip_tests)


def is_bundle(source: str) -> bool:
	"""Built or vendored output, which runs a line out past anything written by hand."""
	return any(len(line) > LONGEST_WRITTEN_LINE for line in source.split("\n"))


def read_source(path: Path, file: str, unreadable: list[str]) -> str | None:
	"""The file's text, or None, with `file` and the reason added to `unreadable`, when it cannot be read."""
	try:
		return path.read_text(encoding="utf-8", errors="replace")
	except OSError as error:
		unreadable.append(f"{file}: {error.strerror}")
		return None
