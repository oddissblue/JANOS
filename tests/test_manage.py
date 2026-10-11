"""Check that bootstrap configuration creates unique secrets and preserves edits."""

from scripts.manage import configure


def test_configuration_is_safe_and_idempotent(tmp_path):
    (tmp_path / ".env.example").write_text("SECRET_KEY=change-me\nPOSTGRES_PASSWORD=change-me\n")
    path = configure(tmp_path)
    contents = path.read_text()
    assert "change-me" not in contents
    assert len(contents.splitlines()[0].split("=")[1]) == 64
    path.write_text(contents + "WEB_PORT=9000\n")
    configure(tmp_path)
    assert path.read_text().endswith("WEB_PORT=9000\n")
