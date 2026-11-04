import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import requests
from src.meeting.translation import (DeepSeekTranslator, TranslationError, TranslationStore,
                         TranslationRouter, ENDPOINT, MODELS)


class TranslationChecks(unittest.TestCase):
    def response(self, code=200, content='我们需要更多数据。', finish='stop'):
        result = Mock(status_code=code)
        result.json.return_value = {'choices': [{'message': {'content': content}, 'finish_reason': finish}]}
        return result

    def test_cloud_request_is_official_bounded_and_only_current_text(self):
        response = self.response()
        transport = Mock(return_value=response)
        translator = DeepSeekTranslator('fixture-key', transport=transport)
        self.assertEqual(translator.translate('We need more data.'), '我们需要更多数据。')
        args, kwargs = transport.call_args
        self.assertEqual(args, (ENDPOINT,))
        self.assertFalse(kwargs['allow_redirects'])
        self.assertEqual(kwargs['timeout'], (3.05, 10))
        self.assertEqual(kwargs['json']['thinking'], {'type': 'disabled'})
        self.assertEqual(kwargs['json']['model'], MODELS[0])
        self.assertEqual(kwargs['json']['messages'][-1], {'role': 'user', 'content': 'We need more data.'})
        self.assertNotIn('fixture-key', json.dumps(kwargs['json']))
        response.close.assert_called_once()

    def test_errors_do_not_disclose_key_or_response_transcript(self):
        for code in (401, 402, 403, 429, 500, 302):
            with self.subTest(code=code):
                response = self.response(code)
                response.text = 'fixture-key PRIVATE TRANSCRIPT'
                translator = DeepSeekTranslator('fixture-key', transport=Mock(return_value=response))
                with self.assertRaises(TranslationError) as context:
                    translator.translate('PRIVATE TRANSCRIPT')
                self.assertNotIn('fixture-key', str(context.exception))
                self.assertNotIn('PRIVATE TRANSCRIPT', str(context.exception))
                response.close.assert_called_once()

    def test_network_errors_and_empty_or_truncated_response_fail_closed(self):
        for error in (requests.Timeout('fixture-key'), requests.ConnectionError('PRIVATE TRANSCRIPT')):
            translator = DeepSeekTranslator('fixture-key', transport=Mock(side_effect=error))
            with self.assertRaises(TranslationError) as context:
                translator.translate('PRIVATE TRANSCRIPT')
            self.assertNotIn('fixture-key', str(context.exception))
            self.assertNotIn('PRIVATE TRANSCRIPT', str(context.exception))
        for content, finish in (('', 'stop'), ('半句话', 'length'), (None, 'stop')):
            translator = DeepSeekTranslator('fixture-key', transport=Mock(return_value=self.response(content=content, finish=finish)))
            with self.assertRaises(TranslationError):
                translator.translate('text')

    def test_blank_input_never_calls_network(self):
        transport = Mock()
        self.assertEqual(DeepSeekTranslator('fixture-key', transport=transport).translate('  '), '')
        transport.assert_not_called()

    def test_default_store_is_local_and_remote_requires_key(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'DEEPSEEK_API_KEY': ''}):
            store = TranslationStore(temp)
            self.assertEqual(store.load()['provider'], 'local')
            with self.assertRaises(TranslationError):
                store.save('deepseek', MODELS[0])
            self.assertFalse(store.path.exists())
            store.save('local', MODELS[0])
            self.assertNotIn('key', store.path.read_text())

    @unittest.skipUnless(os.name == 'nt', 'Windows user encryption')
    def test_saved_key_is_encrypted_and_survives_settings_change(self):
        with tempfile.TemporaryDirectory() as temp:
            store = TranslationStore(temp)
            store.save('deepseek', MODELS[0], 'fixture-not-a-real-secret')
            for path in Path(temp).iterdir():
                self.assertNotIn(b'fixture-not-a-real-secret', path.read_bytes())
            self.assertEqual(store.key(), 'fixture-not-a-real-secret')
            store.save('local', MODELS[0])
            self.assertEqual(store.key(), 'fixture-not-a-real-secret')

    def test_router_switches_without_transmitting_history(self):
        store = Mock()
        store.load.return_value = {'provider': 'local', 'model': MODELS[0]}
        local = Mock()
        local.translate.return_value = '本地'
        router = TranslationRouter(store, local)
        with patch('src.meeting.translation.DeepSeekTranslator') as remote:
            remote.return_value.translate.return_value = '云端'
            self.assertEqual(router.translate('one'), '本地')
            remote.assert_not_called()
            store.load.return_value = {'provider': 'deepseek', 'model': MODELS[0]}
            store.key.return_value = 'fixture-key'
            self.assertEqual(router.translate('two'), '云端')
            remote.return_value.translate.assert_called_once_with('two')
            store.load.return_value = {'provider': 'local', 'model': MODELS[0]}
            self.assertEqual(router.translate('three'), '本地')

    def test_invalid_stored_config_stops_instead_of_silent_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            store = TranslationStore(temp)
            store.path.write_text('{not-json')
            with self.assertRaises(TranslationError):
                store.load()


if __name__ == '__main__':
    unittest.main(verbosity=2)
