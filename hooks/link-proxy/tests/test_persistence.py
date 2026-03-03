"""Tests for mappings and domain config persistence."""

import main as link_proxy


class TestMappings:
    def test_save_and_load(self, tmp_path, monkeypatch):
        monkeypatch.setattr(link_proxy, "MAPPINGS_FILE", tmp_path / "mappings.json")
        link_proxy.save_mappings({"abc123": "https://example.com"})
        assert link_proxy.load_mappings() == {"abc123": "https://example.com"}

    def test_load_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(link_proxy, "MAPPINGS_FILE", tmp_path / "mappings.json")
        assert link_proxy.load_mappings() == {}

    def test_load_corrupt(self, tmp_path, monkeypatch):
        mappings_file = tmp_path / "mappings.json"
        mappings_file.write_text("not json!!!")
        monkeypatch.setattr(link_proxy, "MAPPINGS_FILE", mappings_file)
        assert link_proxy.load_mappings() == {}


class TestLoadDomains:
    def test_with_comments(self, tmp_path, monkeypatch):
        domains_file = tmp_path / "domains.txt"
        domains_file.write_text("# comment\nexample.com\n\ncorp.net\n")
        monkeypatch.setattr(link_proxy, "DOMAINS_FILE", domains_file)
        assert link_proxy.load_domains() == ["example.com", "corp.net"]

    def test_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(link_proxy, "DOMAINS_FILE", tmp_path / "domains.txt")
        assert link_proxy.load_domains() == []
