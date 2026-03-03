"""Shared fixtures for link-proxy tests."""

import pytest

import main as link_proxy


@pytest.fixture
def example_url():
    """A test internal URL and its placeholder/hash."""
    url = "https://wiki.example.com/page"
    placeholder, url_hash = link_proxy.url_to_placeholder(url)
    return url, placeholder, url_hash
