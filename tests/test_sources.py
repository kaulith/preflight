from preflight.sources import frontend_files, is_bundle, read_source, source_files


def write(path, content=""):
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(content)


def test_app_sources_are_found_by_suffix(tmp_path):
	write(tmp_path / "digest" / "public" / "js" / "digest.js")
	write(tmp_path / "digest" / "api.py")
	assert [path.name for path in source_files(tmp_path, ".js")] == ["digest.js"]
	assert [path.name for path in source_files(tmp_path, ".py")] == ["api.py"]


def test_tests_are_kept_unless_skipped(tmp_path):
	write(tmp_path / "digest" / "doctype" / "digest" / "test_digest.py")
	write(tmp_path / "digest" / "tests" / "utils.py")
	write(tmp_path / "digest" / "api.py")
	assert [path.name for path in source_files(tmp_path, ".py")] == [
		"api.py",
		"test_digest.py",
		"utils.py",
	]
	assert [path.name for path in source_files(tmp_path, ".py", skip_tests=True)] == ["api.py"]


def test_vendored_and_built_files_are_skipped(tmp_path):
	write(tmp_path / "node_modules" / "frappe-ui" / "index.js")
	write(tmp_path / "public" / "dist" / "js" / "digest.bundle.js")
	write(tmp_path / "public" / "js" / "digest.min.js")
	write(tmp_path / "public" / "js" / "digest.js")
	assert [path.name for path in source_files(tmp_path, ".js")] == ["digest.js"]


def test_frontend_files_are_found_across_the_repository(tmp_path):
	write(tmp_path / "frontend" / "src" / "pages" / "Lead.vue")
	write(tmp_path / "desk" / "src" / "main.ts")
	write(tmp_path / "digest" / "public" / "js" / "digest.js")
	assert [path.name for path in frontend_files(tmp_path)] == ["main.ts", "digest.js", "Lead.vue"]


def test_scss_files_are_frontend_files(tmp_path):
	write(tmp_path / "digest" / "public" / "scss" / "digest.scss")
	assert [path.name for path in frontend_files(tmp_path)] == ["digest.scss"]


def test_frontend_tests_are_skipped_with_the_python_ones(tmp_path):
	write(tmp_path / "frontend" / "tests" / "unit" / "processField.test.js")
	write(tmp_path / "frontend" / "src" / "Lead.spec.ts")
	write(tmp_path / "frontend" / "src" / "PhoneInput.cy.ts")
	write(tmp_path / "e2e" / "helpers" / "ticket.ts")
	write(tmp_path / "cypress" / "integration" / "form.js")
	write(tmp_path / "frontend" / "src" / "Lead.vue")
	assert [path.name for path in frontend_files(tmp_path, skip_tests=True)] == ["Lead.vue"]


def test_a_line_over_2000_characters_marks_a_bundle():
	assert is_bundle("var a;\n" + "a" * 2001)
	assert not is_bundle("a" * 2000)


def test_file_that_cannot_be_read_is_recorded(tmp_path):
	(tmp_path / "digest.js").symlink_to(tmp_path / "missing.js")
	unreadable = []
	assert read_source(tmp_path / "digest.js", "digest/digest.js", unreadable) is None
	assert unreadable == ["digest/digest.js: No such file or directory"]


def test_bytes_that_are_not_utf8_are_replaced(tmp_path):
	(tmp_path / "digest.js").write_bytes(b"const name = '\xff';")
	assert (
		read_source(tmp_path / "digest.js", "digest/digest.js", [])
		== "const name = '\N{REPLACEMENT CHARACTER}';"
	)
