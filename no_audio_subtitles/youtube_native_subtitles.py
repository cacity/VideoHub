import argparse
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from paths_config import NATIVE_SUBTITLES_DIR, SUBTITLES_DIR
from youtube_transcriber import (
    check_youtube_subtitles,
    download_youtube_subtitles,
    translate_subtitle_file,
)


def download_native_subtitles_only(
    youtube_url: str,
    languages: Optional[Iterable[str]] = None,
    download_auto: bool = True,
    cookies_file: Optional[str] = None,
    output_dir: Optional[str] = None,
) -> List[str]:
    """
    Download native subtitles from YouTube without touching audio/video.

    Args:
        youtube_url: YouTube video URL.
        languages: Preferred subtitle languages, e.g. ["zh", "en"].
        download_auto: Whether to also download automatic subtitles.
        cookies_file: Optional cookies file or "browser:chrome"/"browser:edge".
        output_dir: Directory to place the raw subtitle files. Defaults to
            the global NATIVE_SUBTITLES_DIR.

    Returns:
        List of downloaded subtitle file paths (usually .srt).
    """
    langs = list(languages) if languages is not None else ["zh", "en"]
    out_dir = output_dir or NATIVE_SUBTITLES_DIR

    Path(out_dir).mkdir(parents=True, exist_ok=True)

    downloaded = download_youtube_subtitles(
        youtube_url,
        output_dir=out_dir,
        languages=langs,
        download_auto=download_auto,
        cookies_file=cookies_file,
    )

    return downloaded


def translate_native_subtitles(
    subtitle_paths: Iterable[str],
    target_language: str = "zh-CN",
    base_name: Optional[str] = None,
    output_dir: Optional[str] = None,
    keep_lang_suffix: bool = True,
) -> List[str]:
    """
    Translate a batch of subtitle files.

    This is a thin wrapper over `translate_subtitle_file`, mainly to provide
    a convenient batch interface for the "no-audio" workflow.

    Args:
        subtitle_paths: Iterable of subtitle file paths.
        target_language: Target language code (e.g. "zh-CN").
        base_name: Optional base name for output subtitles; if provided,
            output files use this stem so that video/subtitle names match.
        output_dir: Directory for translated subtitles. Defaults to
            the global SUBTITLES_DIR.
        keep_lang_suffix: Whether to keep language suffix (e.g. _zh_CN).

    Returns:
        List of translated subtitle file paths.
    """
    out_dir = output_dir or SUBTITLES_DIR
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    translated_files: List[str] = []
    for path in subtitle_paths:
        translated = translate_subtitle_file(
            subtitle_path=path,
            target_language=target_language,
            base_name=base_name,
            output_dir=out_dir,
            keep_lang_suffix=keep_lang_suffix,
        )
        if translated:
            translated_files.append(translated)

    return translated_files


def process_youtube_native_subtitles(
    youtube_url: str,
    languages: Optional[Iterable[str]] = None,
    download_auto: bool = True,
    cookies_file: Optional[str] = None,
    translate: bool = True,
    target_language: str = "zh-CN",
    native_output_dir: Optional[str] = None,
    translated_output_dir: Optional[str] = None,
) -> Dict[str, object]:
    """
    One-stop "no-audio" pipeline for YouTube:

    1. Inspect available native subtitles.
    2. Download subtitles only (no audio / Whisper).
    3. Optionally translate subtitles (e.g. to Chinese).

    Returns a small dict with all relevant file paths.
    """
    langs = list(languages) if languages is not None else ["zh", "en"]

    print("Checking available subtitles...")
    info = check_youtube_subtitles(youtube_url, cookies_file=cookies_file)
    if info and isinstance(info, dict) and info.get("error"):
        print(f"Failed to inspect subtitles: {info['error']}")

    print("Downloading native subtitles (no audio / no Whisper)...")
    downloaded = download_native_subtitles_only(
        youtube_url=youtube_url,
        languages=langs,
        download_auto=download_auto,
        cookies_file=cookies_file,
        output_dir=native_output_dir,
    )

    translated: List[str] = []
    if translate and downloaded:
        print(f"Translating {len(downloaded)} subtitle file(s) to {target_language}...")
        translated = translate_native_subtitles(
            subtitle_paths=downloaded,
            target_language=target_language,
            base_name=None,
            output_dir=translated_output_dir or SUBTITLES_DIR,
            keep_lang_suffix=True,
        )

    result: Dict[str, object] = {
        "subtitle_info": info,
        "downloaded_files": downloaded,
        "translated_files": translated,
    }
    return result


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Download and optionally translate YouTube native subtitles "
            "(no audio extraction, no Whisper)."
        )
    )
    parser.add_argument(
        "url",
        help="YouTube video URL.",
    )
    parser.add_argument(
        "-l",
        "--lang",
        nargs="+",
        default=["zh", "en"],
        help="Subtitle language codes to download, e.g. -l zh en.",
    )
    parser.add_argument(
        "--no-auto",
        action="store_true",
        help="Do not download automatic subtitles (only manual ones).",
    )
    parser.add_argument(
        "--cookies",
        default=None,
        help=(
            "Optional cookies file path or browser spec "
            '(e.g. "browser:chrome", "browser:edge").'
        ),
    )
    parser.add_argument(
        "--no-translate",
        action="store_true",
        help="Skip translation; only download native subtitles.",
    )
    parser.add_argument(
        "-t",
        "--target-lang",
        default="zh-CN",
        help="Target language for translation (default: zh-CN).",
    )
    parser.add_argument(
        "--native-dir",
        default=None,
        help=(
            "Directory for raw native subtitles. "
            "Defaults to the global NATIVE_SUBTITLES_DIR."
        ),
    )
    parser.add_argument(
        "--translated-dir",
        default=None,
        help=(
            "Directory for translated subtitles. "
            "Defaults to the global SUBTITLES_DIR."
        ),
    )
    return parser


def main(argv: Optional[List[str]] = None) -> None:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    result = process_youtube_native_subtitles(
        youtube_url=args.url,
        languages=args.lang,
        download_auto=not args.no_auto,
        cookies_file=args.cookies,
        translate=not args.no_translate,
        target_language=args.target_lang,
        native_output_dir=args.native_dir or NATIVE_SUBTITLES_DIR,
        translated_output_dir=args.translated_dir or SUBTITLES_DIR,
    )

    print("\n=== No-audio subtitle workflow finished ===")
    print("Downloaded subtitle files:")
    for p in result.get("downloaded_files") or []:
        print(f"  - {p}")

    if not args.no_translate:
        print("\nTranslated subtitle files:")
        for p in result.get("translated_files") or []:
            print(f"  - {p}")


if __name__ == "__main__":
    main()

