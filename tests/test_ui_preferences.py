from PyQt6.QtCore import QSettings

from src.ui_preferences import ONLINE_VIDEO_CHECKBOX_DEFAULTS, UIPreferences


def test_online_video_preferences_include_all_checkboxes():
    assert len(ONLINE_VIDEO_CHECKBOX_DEFAULTS) == 8
    assert ONLINE_VIDEO_CHECKBOX_DEFAULTS["online_video/download_video"] is False
    assert ONLINE_VIDEO_CHECKBOX_DEFAULTS["online_video/enable_transcription"] is True


def test_boolean_preferences_persist_across_instances(tmp_path):
    settings_path = tmp_path / "ui-preferences.ini"
    first = UIPreferences(
        QSettings(str(settings_path), QSettings.Format.IniFormat)
    )
    first.set_bool("online_video/download_video", True)
    first.set_bool("online_video/enable_transcription", False)
    first.set_bool("online_video/generate_subtitles", True)

    reopened = UIPreferences(
        QSettings(str(settings_path), QSettings.Format.IniFormat)
    )

    assert reopened.get_bool("online_video/download_video") is True
    assert reopened.get_bool("online_video/enable_transcription") is False
    assert reopened.get_bool("online_video/generate_subtitles") is True
    assert reopened.get_bool("online_video/generate_article", True) is True
