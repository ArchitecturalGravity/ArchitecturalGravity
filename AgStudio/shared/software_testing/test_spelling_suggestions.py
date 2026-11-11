"""Persistent suggestion worker remains explicit, bounded and recoverable."""
import os
import time
import unittest

from AgStudio.shared.spelling_suggestions import SuggestionService


def fake_provider(word):
    if word == 'hang':
        time.sleep(30)
    if word == 'crash':
        os._exit(7)
    if word == 'error':
        raise ValueError('unavailable')
    return (str(os.getpid()), word)


class SuggestionServiceTests(unittest.TestCase):
    def service(self, **options):
        service = SuggestionService(provider=fake_provider, **options)
        self.addCleanup(self.shutdown, service)
        return service

    def shutdown(self, service):
        service.close()
        self.assertTrue(service.wait_closed(5))

    def result(self, service, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            outcomes = service.poll()
            if outcomes:
                self.assertEqual(len(outcomes), 1)
                return outcomes[0]
            time.sleep(0.01)
        self.fail('No result before deadline')

    def test_no_child_until_request_and_reuses_child(self):
        service = self.service()
        time.sleep(0.05)
        self.assertIsNone(service._process)
        self.assertEqual(service.poll(), ())
        first = service.submit('first')
        result = self.result(service)
        self.assertEqual(result.request_id, first)
        self.assertIsNone(result.error)
        second = service.submit('second')
        next_result = self.result(service)
        self.assertEqual(next_result.request_id, second)
        self.assertEqual(result.suggestions[0], next_result.suggestions[0])
        self.assertEqual(next_result.suggestions[1], 'second')

    def test_latest_request_supersedes_hung_work_without_blocking_caller(self):
        service = self.service()
        service.submit('first')
        self.result(service)
        service.submit('hang')
        time.sleep(0.1)
        before = time.monotonic()
        latest = service.submit('latest')
        self.assertLess(time.monotonic() - before, 0.1)
        result = self.result(service)
        self.assertEqual(result.request_id, latest)
        self.assertEqual(result.suggestions[1], 'latest')
        self.assertEqual(service.poll(), ())

    def test_cancel_suppresses_results_and_wrong_id_does_not_cancel(self):
        service = self.service()
        request = service.submit('hang')
        time.sleep(0.05)
        service.cancel(request)
        time.sleep(0.1)
        self.assertEqual(service.poll(), ())
        current = service.submit('ok')
        service.cancel(request)
        self.assertEqual(self.result(service).request_id, current)

    def test_timeout_and_crash_are_reported_and_next_request_recovers(self):
        service = self.service(timeout=2.0)
        for word, expected in [('hang', 'timed out'), ('crash', '')]:
            request = service.submit(word)
            result = self.result(service)
            self.assertEqual(result.request_id, request)
            self.assertIsNotNone(result.error)
            self.assertIn(expected, result.error)
            service.submit('recovered')
            self.assertEqual(self.result(service).suggestions[1], 'recovered')

    def test_provider_failure_is_distinct_from_empty_suggestions(self):
        service = self.service()
        service.submit('error')
        outcome = self.result(service)
        self.assertEqual(outcome.suggestions, ())
        self.assertIn('unavailable', outcome.error)
        service.submit('ok')
        self.assertIsNone(self.result(service).error)

    def test_real_hunspell_request_preserves_ranked_corrections(self):
        service = SuggestionService()
        self.addCleanup(self.shutdown, service)
        request = service.submit('recieve')
        outcome = self.result(service)
        self.assertEqual(outcome.request_id, request)
        self.assertIsNone(outcome.error)
        self.assertIn('receive', outcome.suggestions)
        self.assertLessEqual(len(outcome.suggestions), 5)

    def test_invalid_inputs_and_closed_service(self):
        service = self.service()
        for invalid in ('', 'x' * 129, None, 42):
            with self.assertRaises(ValueError):
                service.submit(invalid)
        service.close()
        with self.assertRaises(RuntimeError):
            service.submit('hello')
        self.assertTrue(service.wait_closed(5))
        self.assertEqual(service.poll(), ())

    def test_close_during_native_work_is_nonblocking_and_reaps(self):
        service = self.service()
        service.submit('hang')
        time.sleep(0.1)
        before = time.monotonic()
        service.close()
        self.assertLess(time.monotonic() - before, 0.1)
        self.assertTrue(service.wait_closed(5))
        self.assertIsNone(service._process)


if __name__ == '__main__':
    unittest.main()
