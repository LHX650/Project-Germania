from __future__ import annotations

from external_intelligence.parsing import (
    discover_feed_url,
    parse_feed,
    parse_semantic_html_news,
    parse_structured_news,
)


def test_rss_parsing_outputs_attributed_dynamic_fields() -> None:
    rss = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Fixture</title>
<item><title>Volkswagen updates the ID.4</title>
<link>https://example.test/id4</link>
<pubDate>Thu, 30 Jul 2026 08:00:00 GMT</pubDate>
<description>German ID.4 product update.</description>
<category>electric vehicles</category></item>
</channel></rss>"""

    articles = parse_feed(
        rss,
        source="Fixture RSS",
        source_url="https://example.test/news",
        country="DE",
        tracked_brands=("Volkswagen",),
        tracked_vehicles=("Volkswagen ID.4",),
        source_brand=None,
        official_brand_news=False,
    )

    assert len(articles) == 1
    article = articles[0]
    assert article.source == "Fixture RSS"
    assert article.published_at.isoformat() == "2026-07-30T08:00:00+00:00"
    assert article.brands == ("Volkswagen",)
    assert article.models == ("Volkswagen ID.4",)
    assert article.country == "DE"
    assert article.tags == ("electric vehicles",)


def test_feed_autodiscovery_and_json_ld_fallback() -> None:
    document = b"""<html><head>
<link rel="alternate" type="application/rss+xml" href="/official.xml">
<script type="application/ld+json">
{"@type":"NewsArticle","headline":"BMW iX1 update",
"datePublished":"2026-07-29T10:00:00Z","url":"/ix1",
"description":"Official BMW product news","keywords":["product"]}
</script></head></html>"""

    assert (
        discover_feed_url(document, "https://example.test/news")
        == "https://example.test/official.xml"
    )
    articles = parse_structured_news(
        document,
        source="BMW fixture",
        source_url="https://example.test/news",
        country="DE",
        tracked_brands=("BMW",),
        tracked_vehicles=("BMW iX1",),
        source_brand="BMW",
        official_brand_news=True,
    )

    assert articles[0].official_brand_news is True
    assert articles[0].brands == ("BMW",)
    assert articles[0].models == ("BMW iX1",)
    assert articles[0].url == "https://example.test/ix1"


def test_semantic_html_news_requires_source_date_and_url() -> None:
    document = b"""<article>
<h2><a href="/model-y">Tesla Model Y update</a></h2>
<time datetime="2026-07-28T09:00:00Z">July 28, 2026</time>
<p>Official Model Y product information.</p>
</article>"""

    articles = parse_semantic_html_news(
        document,
        source="Tesla fixture",
        source_url="https://example.test/blog",
        country="US",
        tracked_brands=("Tesla",),
        tracked_vehicles=("Tesla Model Y",),
        source_brand="Tesla",
        official_brand_news=True,
    )

    assert len(articles) == 1
    assert articles[0].published_at.isoformat() == "2026-07-28T09:00:00+00:00"
    assert articles[0].url == "https://example.test/model-y"
    assert articles[0].models == ("Tesla Model Y",)
