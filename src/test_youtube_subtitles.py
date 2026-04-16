import os
from pathlib import Path

from youtube_transcriber import download_youtube_subtitles


class DummyYoutubeDL:
    attempts = []

    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def extract_info(self, youtube_url, download=False):
        return {
            'title': 'Test Video',
            'subtitles': {},
            'automatic_captions': {
                'en-orig': [{'ext': 'vtt'}],
                'en': [{'ext': 'vtt'}],
            },
        }

    def download(self, urls):
        lang = self.opts['subtitleslangs'][0]
        DummyYoutubeDL.attempts.append(lang)
        if lang == 'en-orig':
            raise Exception('ERROR: Unable to download video subtitles for \'en-orig\': ERROR: Did not get any data blocks')

        output_template = self.opts['outtmpl']
        output_path = output_template.replace('%(title)s', 'Test_Video').replace('%(ext)s', f'{lang}.vtt')
        Path(output_path).write_text('WEBVTT\n\n00:00.000 --> 00:01.000\nhello\n', encoding='utf-8')


def test_download_youtube_subtitles_falls_back_to_next_language(tmp_path, monkeypatch):
    import youtube_transcriber

    DummyYoutubeDL.attempts = []
    monkeypatch.setattr(youtube_transcriber.yt_dlp, 'YoutubeDL', DummyYoutubeDL)
    monkeypatch.delenv('PROXY', raising=False)
    monkeypatch.delenv('HTTP_PROXY', raising=False)
    monkeypatch.delenv('HTTPS_PROXY', raising=False)

    files = download_youtube_subtitles(
        'https://www.youtube.com/watch?v=example',
        output_dir=str(tmp_path),
        languages=['en-orig', 'en'],
        download_auto=True,
    )

    assert DummyYoutubeDL.attempts == ['en-orig', 'en']
    assert len(files) == 1
    assert files[0].endswith('.en.vtt')
    assert os.path.exists(files[0])


def test_download_youtube_subtitles_ignores_stale_existing_files(tmp_path, monkeypatch):
    import youtube_transcriber

    class FailingYoutubeDL(DummyYoutubeDL):
        def download(self, urls):
            lang = self.opts['subtitleslangs'][0]
            FailingYoutubeDL.attempts.append(lang)
            raise Exception(f"ERROR: Unable to download video subtitles for '{lang}'")

    stale_file = tmp_path / 'Test Video.en.vtt'
    stale_file.write_text('old subtitle', encoding='utf-8')

    FailingYoutubeDL.attempts = []
    monkeypatch.setattr(youtube_transcriber.yt_dlp, 'YoutubeDL', FailingYoutubeDL)
    monkeypatch.delenv('PROXY', raising=False)
    monkeypatch.delenv('HTTP_PROXY', raising=False)
    monkeypatch.delenv('HTTPS_PROXY', raising=False)

    files = download_youtube_subtitles(
        'https://www.youtube.com/watch?v=example',
        output_dir=str(tmp_path),
        languages=['en-orig', 'en'],
        download_auto=True,
    )

    assert FailingYoutubeDL.attempts == ['en-orig', 'en']
    assert files == []


    best_auto_lang = 'en-orig'
    auto_languages = ['ab', 'aa', 'zh-Hans', 'zh-Hant', 'en-orig', 'en']
    auto_langs = []

    if best_auto_lang:
        auto_langs.append(best_auto_lang)

    fallback_auto_priority = ['en', 'en-orig', 'en-US', 'en-GB', 'zh-Hans', 'zh-CN', 'zh', 'zh-Hant', 'zh-TW']
    for lang in fallback_auto_priority:
        if lang in auto_languages and lang not in auto_langs:
            auto_langs.append(lang)

    max_auto_subtitle_attempts = 4
    auto_langs = auto_langs[:max_auto_subtitle_attempts]

    assert auto_langs == ['en-orig', 'en', 'zh-Hans', 'zh-Hant']
