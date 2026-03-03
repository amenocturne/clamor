"""Tests for pure URL transformation functions."""

import hashlib

import main as link_proxy
from main import build_url_pattern


class TestUrlToPlaceholder:
    def test_basic_url(self):
        url = "https://internal.example.com/path/to/resource"
        placeholder, url_hash = link_proxy.url_to_placeholder(url)
        expected_hash = hashlib.sha256(url.encode()).hexdigest()[:8]
        assert placeholder == f"[InternalLink_internal_{expected_hash}]"
        assert url_hash == expected_hash

    def test_url_without_scheme(self):
        url = "internal.example.com/path"
        placeholder, url_hash = link_proxy.url_to_placeholder(url)
        expected_hash = hashlib.sha256(url.encode()).hexdigest()[:8]
        assert placeholder == f"[InternalLink_internal_{expected_hash}]"

    def test_http_scheme_stripped(self):
        url_http = "http://foo.example.com/bar"
        url_https = "https://foo.example.com/bar"
        _, hash_http = link_proxy.url_to_placeholder(url_http)
        _, hash_https = link_proxy.url_to_placeholder(url_https)
        assert hash_http != hash_https

    def test_deterministic(self):
        url = "https://wiki.corp.net/page"
        p1, h1 = link_proxy.url_to_placeholder(url)
        p2, h2 = link_proxy.url_to_placeholder(url)
        assert p1 == p2
        assert h1 == h2

    def test_prefix_fallback_for_numeric_domain(self):
        url = "https://192.168.1.1/admin"
        placeholder, _ = link_proxy.url_to_placeholder(url)
        assert "[InternalLink_192_" in placeholder


class TestBuildUrlPattern:
    def test_empty_domains(self):
        assert build_url_pattern([]) is None

    def test_single_domain(self):
        pattern = build_url_pattern(["internal.example.com"])
        assert pattern is not None
        assert pattern.search("https://internal.example.com/page")
        assert pattern.search("http://internal.example.com")
        assert pattern.search("internal.example.com/page")

    def test_no_match_outside_domain(self):
        pattern = build_url_pattern(["internal.example.com"])
        assert pattern.search("https://google.com") is None

    def test_subdomain_matching(self):
        pattern = build_url_pattern(["example.com"])
        assert pattern.search("https://sub.example.com/path")
        assert pattern.search("deep.sub.example.com")

    def test_multiple_domains(self):
        pattern = build_url_pattern(["internal.corp.net", "wiki.company.org"])
        assert pattern.search("https://internal.corp.net/page")
        assert pattern.search("https://wiki.company.org/docs")

    def test_invalid_domain_parts(self):
        assert build_url_pattern(["localhost"]) is None


class TestBuildUrlPatternExtended:
    """Tests for percent-encoded, Cyrillic, and special-char URLs."""

    def test_percent_encoded_cyrillic(self):
        pattern = build_url_pattern(["example.com"])
        url = "https://wiki.example.com/docs/%D0%9F%D1%80%D0%B8%D0%B2%D0%B5%D1%82"
        m = pattern.search(url)
        assert m is not None
        assert m.group() == url

    def test_raw_cyrillic_path(self):
        pattern = build_url_pattern(["example.com"])
        url = "https://wiki.example.com/docs/Привет"
        m = pattern.search(url)
        assert m is not None
        assert m.group() == url

    def test_plus_in_path(self):
        pattern = build_url_pattern(["example.com"])
        url = "https://wiki.example.com/search?q=hello+world"
        m = pattern.search(url)
        assert m is not None
        assert m.group() == url

    def test_tilde_in_path(self):
        pattern = build_url_pattern(["example.com"])
        url = "https://wiki.example.com/~user/profile"
        m = pattern.search(url)
        assert m is not None
        assert m.group() == url

    def test_mixed_encoded_and_raw(self):
        pattern = build_url_pattern(["example.com"])
        url = "https://wiki.example.com/docs/%D0%9F%D1%80%D0%B8%D0%B2%D0%B5%D1%82/sub"
        m = pattern.search(url)
        assert m is not None
        assert m.group() == url


class TestTransformText:
    def setup_method(self):
        self.pattern = build_url_pattern(["example.com"])

    def test_no_urls(self):
        text = "This is plain text with no URLs."
        transformed, mappings = link_proxy.transform_text(text, self.pattern)
        assert transformed == text
        assert mappings == {}

    def test_single_url(self):
        text = "Visit https://internal.example.com/page for info."
        transformed, mappings = link_proxy.transform_text(text, self.pattern)
        assert "https://internal.example.com/page" not in transformed
        assert "[InternalLink_" in transformed
        assert len(mappings) == 1

    def test_multiple_urls(self):
        text = "See https://a.example.com/one and https://b.example.com/two for details."
        transformed, mappings = link_proxy.transform_text(text, self.pattern)
        assert "example.com" not in transformed
        assert len(mappings) == 2

    def test_url_with_port(self):
        text = "Service at https://app.example.com:8080/api"
        transformed, mappings = link_proxy.transform_text(text, self.pattern)
        assert "example.com:8080" not in transformed
        assert len(mappings) == 1

    def test_already_transformed_not_double_processed(self):
        placeholder = "[InternalLink_internal_abcd1234]"
        text = f"Already masked: {placeholder}"
        transformed, mappings = link_proxy.transform_text(text, self.pattern)
        assert transformed == text
        assert mappings == {}


class TestRestoreText:
    def test_restore_single(self):
        url = "https://internal.example.com/page"
        _, url_hash = link_proxy.url_to_placeholder(url)
        mappings = {url_hash: url}
        text = f"Visit [InternalLink_internal_{url_hash}] for info."
        restored = link_proxy.restore_text(text, mappings)
        assert restored == f"Visit {url} for info."

    def test_restore_no_matching_hash(self):
        text = "Visit [InternalLink_foo_00000000] for info."
        restored = link_proxy.restore_text(text, {"ffffffff": "https://other.com"})
        assert restored == text

    def test_restore_multiple(self):
        url1 = "https://a.example.com/one"
        url2 = "https://b.example.com/two"
        _, h1 = link_proxy.url_to_placeholder(url1)
        _, h2 = link_proxy.url_to_placeholder(url2)
        mappings = {h1: url1, h2: url2}
        text = f"[InternalLink_a_{h1}] and [InternalLink_b_{h2}]"
        restored = link_proxy.restore_text(text, mappings)
        assert url1 in restored
        assert url2 in restored


class TestRoundTrip:
    def test_roundtrip(self):
        pattern = build_url_pattern(["example.com"])
        original = "Check https://wiki.example.com/doc and https://app.example.com/api/v2"
        transformed, mappings = link_proxy.transform_text(original, pattern)
        restored = link_proxy.restore_text(transformed, mappings)
        assert restored == original

    def test_roundtrip_percent_encoded(self):
        pattern = build_url_pattern(["example.com"])
        original = "See https://wiki.example.com/docs/%D0%9F%D1%80%D0%B8%D0%B2%D0%B5%D1%82 for info"
        transformed, mappings = link_proxy.transform_text(original, pattern)
        assert "example.com" not in transformed
        restored = link_proxy.restore_text(transformed, mappings)
        assert restored == original

    def test_roundtrip_tilde_plus(self):
        pattern = build_url_pattern(["example.com"])
        original = "User https://wiki.example.com/~admin/search?q=a+b page"
        transformed, mappings = link_proxy.transform_text(original, pattern)
        restored = link_proxy.restore_text(transformed, mappings)
        assert restored == original
