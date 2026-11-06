import unittest
from ai_brief import summarize_news

NEWS = [{'title': 'Synthetic report: 3 ships delayed', 'description': '',
         'link': 'https://example.com', 'pub_date': 'demo'}]


def valid(sources):
    return {'items': [{'en': 'Report: 3 ships delayed.', 'zh': '报道称3艘船延误。',
                       'source_ids': ['S1'], 'evidence': [
                           {'source_id': 'S1', 'quote': '3 ships delayed'}]}]}


class AITests(unittest.TestCase):
    def test_valid(self):
        result = summarize_news(NEWS, valid)
        self.assertEqual(result['status'], 'ok')
        self.assertIn('[S1]', result['items'][0]['en'])

    def test_unknown_source(self):
        def provider(sources):
            result = valid(sources)
            result['items'][0]['source_ids'] = ['S99']
            return result
        self.assertEqual(summarize_news(NEWS, provider)['status'], 'unavailable_or_invalid')

    def test_invented_number(self):
        def provider(sources):
            result = valid(sources)
            result['items'][0]['zh'] = '30艘船延误'
            return result
        self.assertEqual(summarize_news(NEWS, provider)['items'], [])

    def test_invented_quote(self):
        def provider(sources):
            result = valid(sources)
            result['items'][0]['evidence'][0]['quote'] = 'not present'
            return result
        self.assertEqual(summarize_news(NEWS, provider)['items'], [])

    def test_provider_failure(self):
        def provider(sources):
            raise TimeoutError()
        self.assertEqual(summarize_news(NEWS, provider)['status'], 'unavailable_or_invalid')

    def test_abstention_and_no_input(self):
        self.assertEqual(summarize_news(NEWS, lambda _: {'items': []})['status'], 'insufficient_evidence')
        self.assertEqual(summarize_news([], valid)['status'], 'no_sources')
