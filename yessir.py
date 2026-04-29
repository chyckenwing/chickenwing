from __future__ import annotations

import ctypes
import os
import re
import shutil
import socket
import sys
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Iterable, Optional

import yt_dlp

BASE_DOWNLOAD_DIR = Path.home() / "Downloads" / "Chickenwing Downloads"
VIDEO_DIR = BASE_DOWNLOAD_DIR / "videos"
AUDIO_DIR = BASE_DOWNLOAD_DIR / "audio"
DOWNLOAD_ARCHIVE = BASE_DOWNLOAD_DIR / "download_archive.txt"
ANSI_RESET = "\033[0m"
SEARCH_RESULT_LIMIT = 5


@dataclass(frozen=True)
class QualityPreset:
    code: str
    label: str
    format_selector: str
    output_dir: Path
    is_audio: bool


@dataclass(frozen=True)
class DownloadTarget:
    source_text: str
    url: str
    is_playlist: bool


@dataclass
class SessionConfig:
    audio_only: bool = False
    concurrency_level: int = 1  # 0=safe, 1=fast, 2=beast
    archive_enabled: bool = False
    archive_path: Optional[Path] = None


@dataclass
class DownloadOutcome:
    success: bool
    strategy: Optional[str] = None
    files: list[Path] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    network_issue: bool = False
    message: Optional[str] = None


class UserRequestedExit(Exception):
    """Raised when the user chooses to exit gracefully."""


QUALITY_PRESETS = {
    "1": QualityPreset(
        code="1",
        label="Best (1080p)",
        format_selector="bestvideo[height<=1080]+bestaudio/best",
        output_dir=VIDEO_DIR,
        is_audio=False,
    ),
    "2": QualityPreset(
        code="2",
        label="720p",
        format_selector="bestvideo[height<=720]+bestaudio/best",
        output_dir=VIDEO_DIR,
        is_audio=False,
    ),
    "3": QualityPreset(
        code="3",
        label="Audio (MP3)",
        format_selector="bestaudio/best",
        output_dir=AUDIO_DIR,
        is_audio=True,
    ),
    "4": QualityPreset(
        code="4",
        label="Safe (360p)",
        format_selector="bestvideo[height<=360]+bestaudio/best",
        output_dir=VIDEO_DIR,
        is_audio=False,
    ),
    "5": QualityPreset(
        code="5",
        label="Best available",
        format_selector="bestvideo+bestaudio/best",
        output_dir=VIDEO_DIR,
        is_audio=False,
    ),
}


class TerminalUI:
    def __init__(self) -> None:
        self.use_color = self._should_use_color()
        self.workspace_active = False

    def _enable_windows_ansi(self) -> bool:
        try:
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)
            mode = ctypes.c_uint32()
            if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                return False
            return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))
        except Exception:
            return False

    def _should_use_color(self) -> bool:
        if os.environ.get("NO_COLOR"):
            return False
        if not sys.stdout.isatty():
            return False
        if os.name == "nt":
            return self._enable_windows_ansi()
        return True

    def color(self, text: str, ansi_code: str) -> str:
        if not self.use_color:
            return text
        return f"\033[{ansi_code}m{text}{ANSI_RESET}"

    def title(self, text: str) -> None:
        print(self.color(text, "1;36"))

    def info(self, text: str) -> None:
        print(self.color(text, "1;34"))

    def ok(self, text: str) -> None:
        print(self.color(text, "1;32"))

    def warn(self, text: str) -> None:
        print(self.color(text, "1;33"))

    def err(self, text: str) -> None:
        print(self.color(text, "1;31"))

    def prompt(self, text: str) -> str:
        return self.color(text, "1;35")

    def enter_workspace(self) -> None:
        if not sys.stdout.isatty() or self.workspace_active:
            return
        self._set_console_title("CHICKEN WING BEAST MODE")
        sys.stdout.write("\033[?1049h\033[2J\033[H\033[?25l")
        sys.stdout.flush()
        self.workspace_active = True

    def exit_workspace(self) -> None:
        if not self.workspace_active:
            return
        sys.stdout.write("\033[?25h\033[?1049l")
        sys.stdout.flush()
        self.workspace_active = False

    def _set_console_title(self, title: str) -> None:
        try:
            if os.name == "nt":
                ctypes.windll.kernel32.SetConsoleTitleW(str(title))
            else:
                sys.stdout.write(f"\033]0;{title}\007")
                sys.stdout.flush()
        except Exception:
            return

    def print_loader(self) -> None:
        if not sys.stdout.isatty():
            return

        phases = [
            ("arming yt-dlp", 3),
            ("spinning up parsers", 6),
            ("locking target flow", 9),
            ("beast mode ready", 12),
        ]
        for label, count in phases:
            pattern = "./" + "\\/" * count
            line = f"{pattern}  {label}"
            sys.stdout.write("\r" + self.color(line, "1;32"))
            sys.stdout.flush()
            time.sleep(0.09)
        sys.stdout.write("\r" + (" " * 96) + "\r")
        sys.stdout.flush()

    def print_banner(self) -> None:
        banner = r"""
   ____ _                 __                  __        __         __
  / __ (_)___  ____  ____/ /___  ____  ___  / /_____  / /_  ___  / /
 / /_/ / / __ \/ __ \/ __  / __ \/ __ \/ _ \/ __/ __ \/ __ \/ _ \/ /
/ __/ / / /_/ / /_/ / /_/ / /_/ / /_/ /  __/ /_/ /_/ / /_/ /  __/_/
/_/ /_/_/\____/ .___/\__,_/\____/\____/\___/\__/\____/\____/\___(_)
               /_/
        """
        print(self.color(banner + "CHICKEN WING BEAST MODE v2.0\n", "1;32"))
        self.info("[*] Status: chickenwing online.\n")

    def print_rule(self, label: str = "") -> None:
        width = shutil.get_terminal_size((100, 20)).columns
        line_width = max(40, min(96, width))
        if not label:
            print(self.color("=" * line_width, "1;30"))
            return

        tag = f" {label.upper()} "
        side = max(2, (line_width - len(tag)) // 2)
        line = "=" * side + tag + "=" * max(2, line_width - len(tag) - side)
        print(self.color(line[:line_width], "1;30"))

    def print_key_values(self, title: str, pairs: list[tuple[str, str]]) -> None:
        self.print_rule(title)
        label_width = max(len(label) for label, _ in pairs)
        for label, value in pairs:
            print(self.color(f"{label.ljust(label_width)} : {value}", "1;36" if label == "Target" else "1;34"))

    def print_choice_list(self, title: str, lines: list[str], accent: str = "1;34") -> None:
        self.print_rule(title)
        for line in lines:
            print(self.color(f"  {line}", accent))

    def print_quickstart(self) -> None:
        self.print_choice_list(
            "Quick Start",
            [
                "Paste a YouTube link to download best video instantly.",
                "Type search words to pick from the top 5 results.",
                "Prefix with 'audio ' to download MP3.",
                "Press Enter or type 'quit' to exit.",
            ],
            accent="1;34",
        )

    def print_offline_message(self) -> None:
        self.err("Check your internet connection, then try again.")
        self.info("Chickenwing needs network access before it can come online.")

    def print_connection_drop_message(self) -> None:
        self.warn("Internet connection was interrupted during the download.")
        self.info("Reconnect, then retry the target when you are ready.")

    def print_interrupt_message(self) -> None:
        self.warn("Download interrupted.")

    def print_unexpected_error(self, message: str) -> None:
        self.err("Chickenwing hit an unexpected error and closed safely.")
        self.info(message)

    def print_toolkit_ui(self, target_desc: str, config: SessionConfig) -> None:
        mode_name = "AUDIO (MP3)" if config.audio_only else "VIDEO"
        conc_name = ["SAFE", "FAST", "BEAST"][config.concurrency_level]
        ffmpeg_name = "OK" if shutil.which("ffmpeg") else "MISSING"
        archive_name = "ON" if config.archive_enabled else "OFF"
        output_name = str(AUDIO_DIR if config.audio_only else VIDEO_DIR)

        self.print_key_values(
            "Session",
            [
                ("Target", truncate_middle(target_desc, 72)),
                ("Mode", mode_name),
                ("Output", output_name),
                ("Concurrency", conc_name),
                ("Archive", archive_name),
                ("ffmpeg", ffmpeg_name),
            ],
        )

    def _panel(self, title: str, lines: Iterable[str], width: int = 52, min_body_lines: int = 2) -> str:
        title = str(title or "").upper()
        body = []
        for raw_line in lines:
            line = str(raw_line)
            if len(line) > width - 4:
                line = line[: width - 7] + "..."
            body.append(line)

        while len(body) < min_body_lines:
            body.append("")

        width = max(width, len(title) + 4)
        top = "+" + "-" * (width - 2) + "+"
        middle = f"| {title.center(width - 4)} |"
        output = [top, middle]
        for line in body:
            output.append(f"| {line.ljust(width - 4)} |")
        output.append(top)
        return "\n".join(output)

    def print_menu(self, audio_only: bool) -> None:
        mode_name = "AUDIO" if audio_only else "VIDEO"
        self.print_choice_list(
            "Command Deck",
            [
                "1. Audio download mode",
                "2. Video download mode",
                "3. Batch run (multiple targets)",
                "4. Settings",
                "5. Exit",
                f"Current default mode: {mode_name}",
            ],
            accent="1;36",
        )

    def print_quality_menu(self) -> None:
        self.print_choice_list(
            "Quality",
            [
                "1. Best (1080p)",
                "2. 720p",
                "3. Audio (MP3)",
                "4. Safe (360p)",
                "5. Best available",
            ],
        )

    def print_search_results(self, results: list[dict]) -> None:
        clean_results = [video for video in results if video]
        self.print_rule(f"Top {len(clean_results)} Results")
        for index, video in enumerate(clean_results, start=1):
            title = truncate_middle(video.get("title", "Unknown"), 50)
            duration = format_time(video.get("duration"))
            uploader = truncate_middle(video.get("uploader", "Unknown"), 20)
            print(self.color(f"  {index}. {title}", "1;34"))
            print(self.color(f"     {duration} | {uploader}", "1;30"))

    def print_settings_menu(self, config: SessionConfig) -> None:
        mode_name = "AUDIO" if config.audio_only else "VIDEO"
        conc_name = ["SAFE", "FAST", "BEAST"][config.concurrency_level]
        archive_name = "ON" if config.archive_enabled else "OFF"
        self.print_choice_list(
            "Settings",
            [
                f"1. Default mode     : {mode_name}",
                f"2. Concurrency      : {conc_name}",
                f"3. Download archive : {archive_name}",
                "4. Back to main menu",
            ],
            accent="1;33",
        )

    def print_download_summary(
        self,
        target: DownloadTarget,
        preset: QualityPreset,
        config: SessionConfig,
        outcome: DownloadOutcome,
    ) -> None:
        self.print_rule("Download Summary")
        if outcome.success:
            lines = [
                f"STATUS: SUCCESS via {outcome.strategy or 'unknown'}",
                f"PROFILE: {preset.label} | CONCURRENCY: {['SAFE', 'FAST', 'BEAST'][config.concurrency_level]}",
                f"LOCATION: {truncate_middle(str(preset.output_dir.resolve()), 58)}",
            ]
            if outcome.files:
                for index, file_path in enumerate(outcome.files[:3], start=1):
                    size = format_bytes(file_path.stat().st_size) if file_path.exists() else "0B"
                    lines.append(f"{index}. {truncate_middle(file_path.name, 42)} ({size})")
                if len(outcome.files) > 3:
                    lines.append(f"+ {len(outcome.files) - 3} more file(s)")
            else:
                lines.append("No new file detected. Item may already exist or was skipped.")
            for line in lines:
                print(self.color(f"  {line}", "1;32"))
            return

        lines = [
            f"STATUS: FAILED after {len(outcome.errors)} strategy attempt(s)",
            f"TARGET: {truncate_middle(target.url, 58)}",
        ]
        if outcome.message:
            lines.append(truncate_middle(outcome.message, 68))
        for error in outcome.errors[-3:]:
            lines.append(truncate_middle(error, 68))
        for line in lines:
            print(self.color(f"  {line}", "1;31"))

    def print_retry_menu(self, preset: QualityPreset) -> None:
        self.print_rule("Retry Options")
        audio_label = "Audio-only fallback" if not preset.is_audio else "Audio retry (safe)"
        for line in [
            "1. Retry same profile",
            "2. Retry in safe mode",
            f"3. {audio_label}",
            "4. Back / skip",
        ]:
            print(self.color(f"  {line}", "1;33"))


class ProgressRenderer:
    def __init__(self, ui: TerminalUI) -> None:
        self.ui = ui
        self.last_render_len = 0

    def hook(self, event: dict) -> None:
        try:
            status = event.get("status")
            if status not in {"downloading", "finished"}:
                return

            if status == "finished":
                self._clear_line()
                label = self._event_label(event)
                self.ui.ok(f"[OK] Finished: {label}" if label else "[OK] Finished")
                return

            total = event.get("total_bytes") or event.get("total_bytes_estimate") or 0
            downloaded = event.get("downloaded_bytes") or 0
            speed = event.get("speed") or 0
            eta = event.get("eta")
            terminal_width = shutil.get_terminal_size((80, 20)).columns
            bar_width = max(10, min(40, terminal_width - 55))

            if total:
                fraction = min(max(downloaded / total, 0.0), 1.0)
                filled = int(bar_width * fraction)
                percent = f"{fraction * 100:5.1f}%"
                bar = "#" * filled + "-" * (bar_width - filled)
            else:
                percent = "  ?.?%"
                bar = "?" * bar_width

            message = (
                f"{bar} {percent} "
                f"{format_bytes(downloaded)}/{format_bytes(total) if total else '??'} "
                f"{format_bytes(speed) + '/s' if speed else ''}"
            ).rstrip()

            if eta is not None:
                try:
                    message += f" ETA {int(eta)}s"
                except Exception:
                    pass

            label = self._event_label(event)
            if label:
                available = max(0, terminal_width - len(message) - 1)
                if available > 3:
                    label = truncate_middle(label, available)
                    message = f"{message} {label}".rstrip()

            self._render(message)
        except Exception:
            return

    def _render(self, message: str) -> None:
        self._clear_line()
        self.last_render_len = len(message)
        sys.stdout.write("\r" + self.ui.color(message, "1;36"))
        sys.stdout.flush()

    def _clear_line(self) -> None:
        if self.last_render_len > 0:
            sys.stdout.write("\r" + (" " * self.last_render_len) + "\r")
            sys.stdout.flush()
            self.last_render_len = 0

    @staticmethod
    def _event_label(event: dict) -> str:
        info = event.get("info_dict") or {}
        label = info.get("title") or ""
        if label:
            return str(label).replace("\n", " ").strip()
        filename = event.get("filename") or ""
        return os.path.basename(filename) if filename else ""


class DownloaderEngine:
    def __init__(self, ui: TerminalUI) -> None:
        self.ui = ui

    def download(
        self,
        target: DownloadTarget,
        preset: QualityPreset,
        config: SessionConfig,
        playlist_items: Optional[str] = None,
    ) -> DownloadOutcome:
        self.ui.info("\n[>>] Downloading...\n")
        self.warn_if_ffmpeg_missing()

        preset.output_dir.mkdir(parents=True, exist_ok=True)
        snapshot_before = self._snapshot_files(preset.output_dir)
        output_template = self._output_template(preset.output_dir, target.is_playlist)
        progress = ProgressRenderer(self.ui)
        errors: list[str] = []
        network_issue = False

        base_options = {
            "outtmpl": output_template,
            "noplaylist": not target.is_playlist,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "progress_hooks": [progress.hook],
            "continue_dl": True,
            "restrictfilenames": True,
        }
        base_options.update(self._concurrency_options(config.concurrency_level))

        if playlist_items:
            base_options["playlist_items"] = playlist_items
        if config.archive_path:
            base_options["download_archive"] = str(config.archive_path)

        if preset.is_audio:
            base_options.update(
                {
                    "format": preset.format_selector,
                    "postprocessors": [
                        {
                            "key": "FFmpegExtractAudio",
                            "preferredcodec": "mp3",
                            "preferredquality": "192",
                        }
                    ],
                }
            )
            strategies = [
                {"name": "AUDIO-BEST", "options": {}},
                {
                    "name": "AUDIO-ANDROID-FALLBACK",
                    "options": {"extractor_args": {"youtube": {"player_client": ["android"]}}},
                },
            ]
        else:
            base_options["format"] = preset.format_selector
            strategies = [
                {"name": "VIDEO-SELECTED-MP4", "options": {"merge_output_format": "mp4"}},
                {"name": "VIDEO-SELECTED-MKV", "options": {"merge_output_format": "mkv"}},
                {
                    "name": "VIDEO-ANDROID-FALLBACK-MP4",
                    "options": {
                        "extractor_args": {"youtube": {"player_client": ["android"]}},
                        "merge_output_format": "mp4",
                    },
                },
                {
                    "name": "VIDEO-ANDROID-FALLBACK-MKV",
                    "options": {
                        "extractor_args": {"youtube": {"player_client": ["android"]}},
                        "merge_output_format": "mkv",
                    },
                },
                {
                    "name": "VIDEO-SAFE-360-MP4",
                    "options": {
                        "format": QUALITY_PRESETS["4"].format_selector,
                        "merge_output_format": "mp4",
                    },
                },
                {
                    "name": "VIDEO-SAFE-360-MKV",
                    "options": {
                        "format": QUALITY_PRESETS["4"].format_selector,
                        "merge_output_format": "mkv",
                    },
                },
            ]

        for strategy in strategies:
            try:
                self.ui.info(f"[..] Trying {strategy['name']}...")
                options = base_options.copy()
                options.update(strategy["options"])
                with yt_dlp.YoutubeDL(options) as ydl:
                    ydl.download([target.url])
                progress._clear_line()
                self.ui.ok("[OK] Download complete!")
                return DownloadOutcome(
                    success=True,
                    strategy=strategy["name"],
                    files=self._detect_new_files(preset.output_dir, snapshot_before),
                )
            except Exception as exc:
                progress._clear_line()
                friendly_error = self._friendly_error_message(exc)
                self.ui.err(f"[X] Failed in {strategy['name']}: {friendly_error}")
                errors.append(f"{strategy['name']}: {friendly_error}")
                network_issue = network_issue or self._looks_like_network_error(exc)

        self.ui.err("[X] All strategies failed.")
        return DownloadOutcome(
            success=False,
            errors=errors,
            network_issue=network_issue,
            message="Internet connection was interrupted during the download."
            if network_issue
            else "Download failed across all recovery strategies.",
        )

    def warn_if_ffmpeg_missing(self) -> None:
        if shutil.which("ffmpeg") is None:
            self.ui.warn("[!] ffmpeg not found in PATH. Audio/video post-processing may fail.")
            self.ui.warn("    Install ffmpeg and make sure it is available on PATH.")

    @staticmethod
    def _concurrency_options(level: int) -> dict:
        level = max(0, min(2, int(level)))
        if level == 0:
            return {
                "concurrent_fragment_downloads": 5,
                "retries": 10,
                "fragment_retries": 10,
            }
        if level == 1:
            return {
                "concurrent_fragment_downloads": 7,
                "retries": 12,
                "fragment_retries": 12,
            }
        return {
            "concurrent_fragment_downloads": 10,
            "retries": 15,
            "fragment_retries": 15,
        }

    @staticmethod
    def _output_template(output_dir: Path, is_playlist: bool) -> str:
        pattern = "%(playlist_index)s - %(title)s.%(ext)s" if is_playlist else "%(title)s.%(ext)s"
        return str((output_dir / pattern)).replace("\\", "/")

    @staticmethod
    def _snapshot_files(output_dir: Path) -> set[Path]:
        if not output_dir.exists():
            return set()
        return {
            path.resolve()
            for path in output_dir.iterdir()
            if path.is_file() and not DownloaderEngine._is_temp_file(path)
        }

    @staticmethod
    def _detect_new_files(output_dir: Path, before: set[Path]) -> list[Path]:
        if not output_dir.exists():
            return []
        files = [
            path.resolve()
            for path in output_dir.iterdir()
            if path.is_file() and not DownloaderEngine._is_temp_file(path)
        ]
        new_files = [path for path in files if path not in before]
        return sorted(new_files, key=lambda path: path.stat().st_mtime, reverse=True)

    @staticmethod
    def _is_temp_file(path: Path) -> bool:
        name = path.name.lower()
        return name.endswith((".part", ".ytdl", ".temp"))

    @staticmethod
    def _friendly_error_message(exc: Exception) -> str:
        message = str(exc).strip() or exc.__class__.__name__
        if DownloaderEngine._looks_like_network_error(exc):
            return "internet connection lost or unstable"
        return message

    @staticmethod
    def _looks_like_network_error(exc: Exception) -> bool:
        if isinstance(exc, (ConnectionError, TimeoutError, socket.timeout, socket.gaierror)):
            return True
        message = f"{exc.__class__.__name__}: {exc}".lower()
        markers = (
            "timed out",
            "timeout",
            "connection reset",
            "connection aborted",
            "connection refused",
            "name or service not known",
            "network is unreachable",
            "temporary failure in name resolution",
            "failed to resolve",
            "remote end closed connection",
            "unable to download",
            "transport error",
            "ssl",
            "http error 5",
            "i/o operation on closed file",
        )
        return any(marker in message for marker in markers)


class ChickenWingApp:
    def __init__(self) -> None:
        self.ui = TerminalUI()
        self.engine = DownloaderEngine(self.ui)
        self.config = SessionConfig(
            audio_only=False,
            concurrency_level=1,
            archive_enabled=True,
            archive_path=DOWNLOAD_ARCHIVE,
        )
        VIDEO_DIR.mkdir(parents=True, exist_ok=True)
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    def run(self) -> None:
        if not self.is_online():
            self.ui.print_offline_message()
            return

        self.ui.enter_workspace()
        try:
            self.ui.print_loader()
            self.ui.print_banner()
            self.ui.info(f"Archive: {self.config.archive_path}")
            self.ui.print_quickstart()

            while True:
                raw = self.safe_input("Link or search: ")
                if not raw or raw.lower() in {"q", "quit", "exit"}:
                    break
                if raw.lower() in {"help", "?"}:
                    self.ui.print_quickstart()
                    continue
                if raw.lower() in {"settings", "config"}:
                    self.open_settings()
                    continue

                force_audio, target_text = self.parse_quick_input(raw)
                self.process_single(target_text, force_audio=force_audio)
        except UserRequestedExit:
            pass
        except Exception as exc:
            detail = truncate_middle(str(exc).strip() or exc.__class__.__name__, 88)
            self.ui.print_unexpected_error(detail)
        finally:
            self.ui.exit_workspace()

    @staticmethod
    def is_online() -> bool:
        endpoints = (
            ("1.1.1.1", 53),
            ("8.8.8.8", 53),
        )
        for host, port in endpoints:
            try:
                with socket.create_connection((host, port), timeout=2):
                    return True
            except OSError:
                continue
        return False

    def configure_session(self) -> None:
        self.ui.print_rule("Setup")
        raw_concurrency = self.safe_input("Concurrency (1=Safe, 2=Fast, 3=Beast, Enter=2): ")
        self.config.concurrency_level = self._parse_concurrency_level(raw_concurrency)

        archive_enabled = self.safe_input(
            "Enable download archive (skip already-downloaded items)? (y/N): "
        ).lower()
        self.config.archive_enabled = archive_enabled in {"y", "yes"}
        self._sync_archive_path()
        self._show_archive_status()

    def process_single(self, user_input: str, force_audio: bool) -> None:
        target = self.resolve_target(user_input, auto_pick_search=False)
        if not target:
            self.ui.err("[X] No video selected")
            return

        self.ui.print_rule("Target")
        self.ui.info(f"Using: {target.url}")

        playlist_items = None
        if target.is_playlist:
            playlist_raw = self.safe_input("Playlist items to download (Enter=all, e.g. 5 or 1:10): ")
            playlist_items = self.parse_playlist_items(playlist_raw)

        preset = QUALITY_PRESETS["3"] if force_audio else QUALITY_PRESETS["5"]
        self.execute_download_flow(target, preset, playlist_items=playlist_items)

    def process_batch(self, items: list[str]) -> None:
        preset = self.choose_quality(force_audio=self.config.audio_only)

        for index, item in enumerate(items, start=1):
            if not item.strip():
                continue
            self.ui.print_rule(f"Batch item {index}/{len(items)}")
            target = self.resolve_target(item, auto_pick_search=True)
            if not target:
                self.ui.err("[X] Could not resolve target")
                continue

            self.ui.info(f"[->] Using: {target.url}")
            self.ui.print_toolkit_ui(target.url, self.config)

            playlist_items = None
            if target.is_playlist:
                playlist_raw = self.safe_input(
                    "Playlist items to download (Enter=all, e.g. 5 or 1:10): "
                )
                playlist_items = self.parse_playlist_items(playlist_raw)

            self.execute_download_flow(target, preset, playlist_items=playlist_items)

    def choose_quality(self, force_audio: bool) -> QualityPreset:
        if force_audio:
            return QUALITY_PRESETS["3"]

        self.ui.print_quality_menu()
        choice = self.safe_input("Choice (Enter=5): ") or "5"
        return QUALITY_PRESETS.get(choice, QUALITY_PRESETS["5"])

    @staticmethod
    def parse_quick_input(raw_text: str) -> tuple[bool, str]:
        text = raw_text.strip()
        lowered = text.lower()
        for prefix in ("audio ", "mp3 "):
            if lowered.startswith(prefix):
                return True, text[len(prefix):].strip()
        return False, text

    def resolve_target(self, user_input: str, auto_pick_search: bool) -> Optional[DownloadTarget]:
        text = user_input.strip()
        if not text:
            return None

        if text.lower().startswith("search "):
            query = text.split(" ", 1)[1].strip()
            return self._resolve_search(query, auto_pick=auto_pick_search)
        if is_youtube_reference(text):
            return DownloadTarget(
                source_text=text,
                url=normalize_youtube_url(text),
                is_playlist=is_playlist_url(text),
            )
        return self._resolve_search(text, auto_pick=auto_pick_search)

    def _resolve_search(self, query: str, auto_pick: bool) -> Optional[DownloadTarget]:
        results = self.search_videos(query)
        if not results:
            self.ui.err("[X] No results")
            return None

        if auto_pick:
            video = next((entry for entry in results if entry), None)
            if not video:
                self.ui.err("[X] No valid results")
                return None
            title = video.get("title") or ""
            if title:
                self.ui.info(f"Auto-picked: {title}")
            url = get_video_url(video)
            return DownloadTarget(source_text=query, url=url, is_playlist=False) if url else None

        url = self.choose_video(results)
        return DownloadTarget(source_text=query, url=url, is_playlist=False) if url else None

    def search_videos(self, query: str) -> list[dict]:
        options = {
            "quiet": True,
            "extract_flat": True,
            "skip_download": True,
        }
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                results = ydl.extract_info(f"ytsearch{SEARCH_RESULT_LIMIT}:{query}", download=False)
            entries = results.get("entries", []) if results else []
            return [entry for entry in entries if entry][:SEARCH_RESULT_LIMIT]
        except Exception as exc:
            if DownloaderEngine._looks_like_network_error(exc):
                self.ui.print_connection_drop_message()
            else:
                self.ui.err(f"[X] Search error: {exc}")
            return []

    def choose_video(self, results: list[dict]) -> Optional[str]:
        clean_results = [video for video in results if video]
        if not clean_results:
            self.ui.err("[X] No valid results")
            return None

        self.ui.print_search_results(clean_results)

        while True:
            choice = self.safe_input("Select (Enter=1): ")
            if not choice:
                return get_video_url(clean_results[0])
            if choice.isdigit():
                selected = int(choice)
                if 1 <= selected <= len(clean_results):
                    return get_video_url(clean_results[selected - 1])
            self.ui.err("[X] Invalid choice")

    @staticmethod
    def parse_playlist_items(spec: str) -> Optional[str]:
        spec = (spec or "").strip()
        if not spec or spec.lower() in {"all", "a", "*"}:
            return None
        if spec.isdigit():
            number = int(spec)
            if number > 0:
                return f"1:{number}"
            return None
        return spec

    @staticmethod
    def _parse_concurrency_level(raw_value: str) -> int:
        try:
            value = int(raw_value or "2")
        except ValueError:
            value = 2
        return max(1, min(3, value)) - 1

    def execute_download_flow(
        self,
        target: DownloadTarget,
        preset: QualityPreset,
        playlist_items: Optional[str] = None,
    ) -> bool:
        active_preset = preset
        active_config = self._runtime_config_for_preset(active_preset)

        while True:
            try:
                outcome = self.engine.download(target, active_preset, active_config, playlist_items=playlist_items)
            except KeyboardInterrupt:
                print()
                self.ui.print_interrupt_message()
                if self.confirm_exit():
                    raise UserRequestedExit()
                self.ui.info("Returning to prompt.")
                return False

            self.ui.print_download_summary(target, active_preset, active_config, outcome)
            if outcome.network_issue:
                self.ui.print_connection_drop_message()
            if outcome.success:
                return True

            action = self.prompt_retry_action(active_preset)
            if action == "back":
                return False
            if action == "safe":
                active_preset = self._safe_retry_preset(active_preset)
                active_config = self._runtime_config_for_preset(active_preset, concurrency_level=0)
                continue
            if action == "audio":
                active_preset = QUALITY_PRESETS["3"]
                active_config = self._runtime_config_for_preset(active_preset, concurrency_level=0)
                continue

            active_config = self._runtime_config_for_preset(active_preset)

    def show_session(self, target_desc: str) -> None:
        self.ui.print_toolkit_ui(target_desc, self.config)

    def open_settings(self) -> None:
        while True:
            self.ui.print_settings_menu(self.config)
            choice = self.safe_input("SETTINGS: 1) Mode  2) Concurrency  3) Archive  4) Back  > ").lower()

            if not choice:
                continue
            if choice in {"4", "b", "back"}:
                return
            if choice == "1":
                self._configure_default_mode()
                continue
            if choice == "2":
                self._configure_concurrency()
                continue
            if choice == "3":
                self._configure_archive()
                continue

            self.ui.err("Invalid settings option. Use 1/2/3/4.")

    def _configure_default_mode(self) -> None:
        self.ui.print_choice_list(
            "Default Mode",
            [
                "1. Audio mode",
                "2. Video mode",
                "3. Keep current mode",
            ],
            accent="1;35",
        )
        choice = self.safe_input("Select default mode (Enter keeps current): ").lower()
        if not choice:
            return
        if choice in {"1", "audio"}:
            self.config.audio_only = True
            self.ui.ok("[OK] Default mode set to AUDIO.")
            return
        if choice in {"2", "video"}:
            self.config.audio_only = False
            self.ui.ok("[OK] Default mode set to VIDEO.")
            return
        if choice in {"3", "keep", "current"}:
            self.ui.info("Default mode unchanged.")
            return
        self.ui.err("[X] Invalid mode choice.")

    def _configure_concurrency(self) -> None:
        self.ui.print_choice_list(
            "Concurrency",
            [
                "1. Safe  - lower pressure, more conservative",
                "2. Fast  - balanced default",
                "3. Beast - aggressive fragment downloads",
            ],
            accent="1;35",
        )
        choice = self.safe_input("Select concurrency (Enter keeps current): ")
        if not choice:
            return
        self.config.concurrency_level = self._parse_concurrency_level(choice)
        conc_name = ["SAFE", "FAST", "BEAST"][self.config.concurrency_level]
        self.ui.ok(f"[OK] Concurrency set to {conc_name}.")

    def _configure_archive(self) -> None:
        self.ui.print_choice_list(
            "Archive",
            [
                f"Current state: {'ON' if self.config.archive_enabled else 'OFF'}",
                "1. Turn archive ON",
                "2. Turn archive OFF",
                "3. Keep current setting",
            ],
            accent="1;35",
        )
        choice = self.safe_input("Select archive mode (Enter keeps current): ").lower()
        if not choice or choice in {"3", "keep", "current"}:
            self.ui.info("Archive setting unchanged.")
            return
        if choice in {"1", "on"}:
            self.config.archive_enabled = True
        elif choice in {"2", "off"}:
            self.config.archive_enabled = False
        else:
            self.ui.err("[X] Invalid archive choice.")
            return
        self._sync_archive_path()
        self._show_archive_status()

    def prompt_retry_action(self, preset: QualityPreset) -> str:
        while True:
            self.ui.print_retry_menu(preset)
            choice = self.safe_input("RECOVER: 1) Retry  2) Safe  3) Audio  4) Back  > ").lower()

            if choice in {"1", "retry", ""}:
                return "retry"
            if choice in {"2", "safe"}:
                return "safe"
            if choice in {"3", "audio"}:
                return "audio"
            if choice in {"4", "back", "skip", "b"}:
                return "back"
            self.ui.err("[X] Invalid recovery option.")

    def _runtime_config_for_preset(
        self,
        preset: QualityPreset,
        concurrency_level: Optional[int] = None,
    ) -> SessionConfig:
        return replace(
            self.config,
            audio_only=preset.is_audio,
            concurrency_level=self.config.concurrency_level if concurrency_level is None else concurrency_level,
            archive_enabled=self.config.archive_enabled,
            archive_path=self.config.archive_path,
        )

    @staticmethod
    def _safe_retry_preset(preset: QualityPreset) -> QualityPreset:
        if preset.is_audio:
            return QUALITY_PRESETS["3"]
        return QUALITY_PRESETS["4"]

    def _sync_archive_path(self) -> None:
        self.config.archive_path = DOWNLOAD_ARCHIVE if self.config.archive_enabled else None

    def _show_archive_status(self) -> None:
        if self.config.archive_path:
            self.ui.info(f"Archive: {self.config.archive_path}")
        else:
            self.ui.info("Archive: OFF")

    def safe_input(self, prompt: str) -> str:
        while True:
            try:
                return input(self.ui.prompt(prompt)).strip()
            except EOFError:
                raise UserRequestedExit()
            except KeyboardInterrupt:
                print()
                if self.confirm_exit():
                    raise UserRequestedExit()
                self.ui.info("Continuing.")

    def confirm_exit(self) -> bool:
        while True:
            try:
                choice = input(self.ui.prompt("Quit Chickenwing? (Y/n): ")).strip().lower()
            except EOFError:
                return True
            except KeyboardInterrupt:
                print()
                return True

            if choice in {"", "y", "yes"}:
                return True
            if choice in {"n", "no"}:
                return False
            self.ui.warn("Please answer with y or n.")


def truncate_middle(text: str, max_length: int) -> str:
    text = str(text or "")
    if len(text) <= max_length:
        return text
    if max_length <= 3:
        return text[:max_length]
    keep = max_length - 3
    left = keep // 2
    right = keep - left
    return text[:left] + "..." + text[-right:]


def format_bytes(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "0B"

    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if number < 1024.0 or unit == "TiB":
            return f"{int(number)}B" if unit == "B" else f"{number:.2f}{unit}"
        number /= 1024.0
    return "0B"


def format_time(seconds: object) -> str:
    if not seconds:
        return "??:??"
    try:
        total_seconds = int(seconds)
    except (TypeError, ValueError):
        return "??:??"
    minutes, remainder = divmod(total_seconds, 60)
    return f"{minutes}:{remainder:02d}"


def is_playlist_url(url: str) -> bool:
    return bool(url) and "list=" in url.lower()


def is_youtube_reference(text: str) -> bool:
    lowered = (text or "").lower()
    return "youtube.com" in lowered or "youtu.be" in lowered


def extract_youtube_video_id(text: str) -> Optional[str]:
    if not text:
        return None

    text = str(text)
    for pattern in (
        r"(?:\bv=)([0-9A-Za-z_-]{11})",
        r"(?:youtu\.be/)([0-9A-Za-z_-]{11})",
        r"(?:shorts/)([0-9A-Za-z_-]{11})",
    ):
        matches = re.findall(pattern, text)
        if matches:
            return matches[-1]
    return None


def normalize_youtube_url(text: str) -> str:
    video_id = extract_youtube_video_id(text)
    if not video_id:
        return text

    playlist_match = re.search(r"(?:\blist=)([0-9A-Za-z_-]+)", str(text))
    if playlist_match:
        return f"https://www.youtube.com/watch?v={video_id}&list={playlist_match.group(1)}"
    return f"https://www.youtube.com/watch?v={video_id}"


def get_video_url(video: dict) -> Optional[str]:
    if not video:
        return None
    if "webpage_url" in video:
        return video["webpage_url"]
    if "url" not in video:
        return None

    value = video["url"]
    video_id = extract_youtube_video_id(value)
    if video_id:
        return f"https://www.youtube.com/watch?v={video_id}"
    if isinstance(value, str) and value.startswith("http"):
        return value
    return f"https://www.youtube.com/watch?v={value}"


def main() -> None:
    ChickenWingApp().run()


if __name__ == "__main__":
    main()
