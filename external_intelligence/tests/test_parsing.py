from __future__ import annotations

import json

from external_intelligence.parsing import (
    discover_feed_url,
    parse_feed,
    parse_semantic_html_news,
    parse_structured_news,
)
from external_intelligence.source_parsing import parse_source_specific_news


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


def test_rss_parser_accepts_official_feed_whitespace_before_declaration() -> None:
    rss = b"""   \n<?xml version="1.0" encoding="UTF-8"?>
    <rss><channel><item><title>BYD ATTO 3 update</title>
    <link>https://example.test/atto-3</link>
    <pubDate>Mon, 03 Aug 2026 09:44:03 GMT</pubDate>
    <description>Official BYD vehicle update.</description>
    </item></channel></rss>"""

    articles = parse_feed(
        rss,
        source="BYD fixture",
        source_url="https://example.test/news",
        country="EU",
        tracked_brands=("BYD",),
        tracked_vehicles=("BYD Atto 3",),
        source_brand="BYD",
        official_brand_news=True,
    )

    assert articles[0].models == ("BYD Atto 3",)


def test_rss_image_priority_prefers_media_content_then_enclosure() -> None:
    rss = b"""<rss xmlns:media="http://search.yahoo.com/mrss/"><channel>
    <item><title>Official market update</title>
    <link>https://example.test/update</link>
    <pubDate>Thu, 30 Jul 2026 08:00:00 GMT</pubDate>
    <description>Official metadata.</description>
    <media:content url="https://cdn.example.test/official-cover.jpg" type="image/jpeg"/>
    <enclosure url="https://cdn.example.test/secondary.jpg" type="image/jpeg"/>
    </item></channel></rss>"""

    article = parse_feed(
        rss,
        source="Official fixture",
        source_url="https://example.test/news",
        country="DE",
        tracked_brands=(),
        tracked_vehicles=(),
        source_brand=None,
        official_brand_news=False,
    )[0]

    assert article.image_url == "https://cdn.example.test/official-cover.jpg"
    assert article.image_source == "rss_media_content"


def test_invalid_rss_image_is_ignored_without_losing_article() -> None:
    rss = b"""<rss><channel><item><title>Official market update</title>
    <link>https://example.test/update</link>
    <pubDate>Thu, 30 Jul 2026 08:00:00 GMT</pubDate>
    <description>Official metadata.</description>
    <enclosure url="javascript:invalid" type="image/jpeg"/>
    </item></channel></rss>"""

    article = parse_feed(
        rss,
        source="Official fixture",
        source_url="https://example.test/news",
        country="DE",
        tracked_brands=(),
        tracked_vehicles=(),
        source_brand=None,
        official_brand_news=False,
    )[0]

    assert article.image_url is None
    assert article.image_source is None


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


def test_bmw_semantic_card_accepts_pressclub_cest_date() -> None:
    document = b"""<article class="newsfeed"><h3>
    <a href="/global/article/detail/T1EN/bmw-x3-update">BMW X3 update</a>
    </h3><span class="date">Thu Jul 30 07:34:37 CEST 2026</span>
    <p class="serif">Official BMW X3 product information.</p></article>"""

    articles = parse_semantic_html_news(
        document,
        source="BMW Group PressClub Global",
        source_url="https://www.press.bmwgroup.com/global/article/search/index.html",
        country="DE",
        tracked_brands=("BMW",),
        tracked_vehicles=("BMW X3",),
        source_brand="BMW",
        official_brand_news=True,
    )

    assert len(articles) == 1
    assert articles[0].published_at.isoformat() == "2026-07-30T05:34:37+00:00"
    assert articles[0].models == ("BMW X3",)


def test_bmw_source_parser_keeps_title_separate_from_card_metadata() -> None:
    document = b"""<article class="newsfeed">
    <div style="background-image:url('https://cdn.example.test/bmw.jpg')"></div>
    <h3><a href="/global/article/detail/T1EN/bmw-x3-update">
    BMW X3 update</a></h3>
    <span class="date">Thu Jul 30 07:34:37 CEST 2026</span>
    <p class="serif">Official BMW X3 product information.</p>
    </article>"""

    articles = _source_articles(
        document,
        source_id="bmw_official_news",
        brand="BMW",
        vehicles=("BMW X3",),
    )

    assert len(articles) == 1
    assert articles[0].title == "BMW X3 update"
    assert articles[0].summary == "Official BMW X3 product information."
    assert articles[0].url.endswith("/global/article/detail/T1EN/bmw-x3-update")
    assert articles[0].image_url == "https://cdn.example.test/bmw.jpg"
    assert articles[0].models == ("BMW X3",)


def test_mercedes_source_parser_maps_card_fields_and_alias() -> None:
    document = b"""<a class="card-container" href="/en/article/abc-123">
    <source srcset="https://cdn.example.test/c-class.jpg">
    <div class="topline">Stuttgart, July 28, 2026</div>
    <h2 class="headline">The all-new electric C-Class</h2>
    <div class="fuel-label"><p>Official C-Class environmental update.</p></div>
    </a>"""

    articles = _source_articles(
        document,
        source_id="mercedes_official_news",
        brand="Mercedes-Benz",
        vehicles=("Mercedes-Benz C-Class", "Mercedes-Benz GLC"),
    )

    assert len(articles) == 1
    assert articles[0].models == ("Mercedes-Benz C-Class",)
    assert articles[0].url == "https://example.test/en/article/abc-123"


def test_mercedes_official_jsonapi_maps_c_class_and_image() -> None:
    document = json.dumps(
        {
            "results": [
                {
                    "id": "9f9ddd25-7474-476e-b16f-28961098f429",
                    "title": "The all-new electric C-Class: 360° Environmental Check",
                    "fuel_label": "Official electric C-Class information.",
                    "display_date": "2026-07-28T08:00:00Z",
                    "header_image_uuid": "image-uuid",
                    "location": "Stuttgart",
                    "press_release_type": "mb_article",
                }
            ]
        }
    ).encode()

    articles = _source_articles(
        document,
        source_id="mercedes_official_news",
        brand="Mercedes-Benz",
        vehicles=("Mercedes-Benz C-Class", "Mercedes-Benz GLC"),
    )

    assert articles[0].models == ("Mercedes-Benz C-Class",)
    assert articles[0].url.endswith("/9f9ddd25-7474-476e-b16f-28961098f429")
    assert articles[0].image_url == (
        "https://api.media.mercedes-benz.com/jsonapi/image/deliver/"
        "image-uuid/4_3_800"
    )


def test_mg_source_parser_maps_current_press_archive_card() -> None:
    document = b"""<div class="col press"><a href="/press/new-mg4-update/">
    <img src="https://cdn.example.test/mg4.jpg">
    <div class="date"><span>14-07-2026</span><span>Press Release</span></div>
    <h3>New MG4 Electric technology update</h3>
    <p>Official MG4 product information.</p></a></div>"""

    articles = _source_articles(
        document,
        source_id="mg_official_news",
        brand="MG",
        vehicles=("MG MG4", "MG ZS EV"),
    )

    assert len(articles) == 1
    assert articles[0].models == ("MG MG4",)
    assert articles[0].image_url == "https://cdn.example.test/mg4.jpg"


def test_xpeng_next_data_parser_builds_official_detail_url() -> None:
    news_data = [
        "$",
        "$L37",
        None,
        {
            "newsData": {
                "topNews": [
                    {
                        "id": "019f6acdf9b69f64a5748a029c460043",
                        "title": "XPENG G6 technology update",
                        "subTitle": "Official G6 product information.",
                        "date": "2026-07-15",
                        "coverUrl": "https://cdn.example.test/g6.jpg",
                        "regionCode": "GO",
                        "langCode": "en-GO",
                    }
                ]
            }
        },
    ]
    wrapper = [1, "5:" + json.dumps(news_data)]
    document = (
        "<script>self.__next_f.push(" + json.dumps(wrapper) + ")</script>"
    ).encode()

    articles = _source_articles(
        document,
        source_id="xpeng_official_news",
        brand="XPENG",
        vehicles=("XPENG G6",),
    )

    assert len(articles) == 1
    assert articles[0].models == ("XPENG G6",)
    assert articles[0].url.endswith("/019f6acdf9b69f64a5748a029c460043")


def test_vda_public_api_parser_maps_title_path_date_and_summary() -> None:
    document = json.dumps(
        {
            "items": [
                {
                    "path": "/en/press/press-releases/2026/market-july",
                    "title": "Production and Market in July 2026",
                    "text": "Electric vehicle registrations update.",
                    "date": "2026-08-06T00:00:00.000+02:00",
                    "location": "Berlin",
                }
            ]
        }
    ).encode()

    articles = _source_articles(
        document,
        source_id="vda_news",
        brand=None,
        vehicles=(),
    )

    assert len(articles) == 1
    assert articles[0].title == "Production and Market in July 2026"
    assert articles[0].summary == "Electric vehicle registrations update."
    assert articles[0].url == (
        "https://example.test/en/press/press-releases/2026/market-july"
    )


def _source_articles(
    document: bytes,
    *,
    source_id: str,
    brand: str | None,
    vehicles: tuple[str, ...],
):
    return parse_source_specific_news(
        document,
        source_id=source_id,
        source="Official fixture",
        source_url="https://example.test/news",
        country="DE",
        tracked_brands=tuple([brand] if brand else []),
        tracked_vehicles=vehicles,
        source_brand=brand,
        official_brand_news=brand is not None,
    )
