import unittest
from unittest.mock import patch
from cloud_iran_brief import render_email, pick_news


class BriefTests(unittest.TestCase):
    def test_external_html_is_escaped(self):
        result = render_email('demo', [{'en':'<script>alert(1)</script>', 'zh':'中文 & <b>',
                                      'link':'javascript:alert(1)'}])
        self.assertNotIn('<script>', result)
        self.assertNotIn('href="javascript:', result)
        self.assertIn('&lt;script&gt;', result)
        self.assertIn('中文 &amp; &lt;b&gt;', result)

    def test_https_source_is_preserved(self):
        result = render_email('demo', [{'en':'News', 'zh':'新闻', 'link':'https://example.com/?a=1&b=2'}])
        self.assertIn('href="https://example.com/?a=1&amp;b=2"', result)

    def test_dedup_and_numeric_filter(self):
        news = [{'title':'Update 3', 'description':'', 'link':'https://example.com', 'bucket':'test'},
                {'title':'No numbers', 'description':'', 'link':'https://example.com/2', 'bucket':'test'}]
        with patch('cloud_iran_brief.fetch_rss', return_value=news):
            self.assertEqual(len(pick_news()), 1)

    def test_unavailable_sources(self):
        with patch('cloud_iran_brief.fetch_rss', side_effect=OSError('offline')):
            self.assertEqual(pick_news(), [])
