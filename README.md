<div id="top"></div>

<!-- PROJECT LOGO -->
<div align="center">
  <picture>
    <source
      srcset="docs/light/icon.png"
      width="128"
      height="128"
      media="(prefers-color-scheme: light)"
    />
    <source
      srcset="docs/dark/icon.png"
      width="128"
      height="128"
      media="(prefers-color-scheme: dark)"
    />
    <img src="docs/light/icon.png" alt="Logo" width="128" height="128">
  </picture>
  <h1 align="center">Audiotext</h1>
  <p align="center">A desktop app to transcribe audio and video from files, URLs, YouTube, or your mic, then edit, translate, summarize, subtitle, and chat with your transcripts.</p>
  <p>
    <a href="https://github.com/HenestrosaDev/audiotext/actions/workflows/code-quality.yml">
      <img
        src="https://github.com/HenestrosaDev/audiotext/actions/workflows/code-quality.yml/badge.svg"
        alt="Code Quality badge status"
      />
    </a>
    <a href="https://github.com/HenestrosaDev/audiotext/actions/workflows/build.yml">
      <img
        src="https://github.com/HenestrosaDev/audiotext/actions/workflows/build.yml/badge.svg"
        alt="Build badge status"
      />
    </a>
    <br>
    <a href="https://github.com/HenestrosaDev/audiotext/releases/latest">
      <img
        src="https://img.shields.io/github/v/release/HenestrosaDev/audiotext"
        alt="Version"
      />
    </a>
    <a href="https://github.com/HenestrosaDev/audiotext/stargazers">
      <img
        src="https://img.shields.io/github/stars/HenestrosaDev/audiotext"
        alt="GitHub stars"
      />
    </a>
    <a href="https://github.com/HenestrosaDev/audiotext/blob/main/LICENSE">
      <img
        src="https://img.shields.io/badge/license-MIT-lightgray"
        alt="License"
      />
    </a>
    <br>
    <a href="https://github.com/HenestrosaDev/audiotext/graphs/contributors">
      <img
        src="https://img.shields.io/github/contributors/HenestrosaDev/audiotext"
        alt="GitHub contributors"
      />
    </a>
    <a href="https://github.com/HenestrosaDev/audiotext/issues">
      <img
        src="https://img.shields.io/github/issues/HenestrosaDev/audiotext"
        alt="Issues"
      />
    </a>
    <a href="https://github.com/HenestrosaDev/audiotext/pulls">
      <img
        src="https://img.shields.io/github/issues-pr/HenestrosaDev/audiotext"
        alt="GitHub pull requests"
      />
    </a>
  </p>
  <p>
    <a href="https://getaudiotext.com">
      <strong>Documentation</strong>
    </a>
    ·
    <a href="https://github.com/HenestrosaDev/audiotext/issues/new/choose">
      Report Bug
    </a>
    ·
    <a href="https://github.com/HenestrosaDev/audiotext/issues/new/choose">
      Request Feature
    </a>
    ·
    <a href="https://github.com/HenestrosaDev/audiotext/discussions">
      Ask Question
    </a>
  </p>
</div>

https://github.com/user-attachments/assets/242e9299-b615-4c48-b627-d3ac08b5eb73

<!-- TABLE OF CONTENTS -->

## Table of Contents

- [About the Project](#about-the-project)
  - [Features](#features)
  - [Documentation](#documentation)
  - [Languages and Formats](#languages-and-formats)
  - [Project Structure](#project-structure)
  - [Built With](#built-with)
- [Getting Started](#getting-started)
  - [Installation](#installation)
  - [Setting Up the Project Locally](#setting-up-the-project-locally)
  - [Notes](#notes)
- [Usage](#usage)
  - [Command-Line Interface](#command-line-interface)
- [Troubleshooting](#troubleshooting)
- [Roadmap](#roadmap)
- [Authors](#authors)
- [Contributing](#contributing)
  - [Translations](#translations)
  - [Documentation Website](#documentation-website)
  - [Releasing a Version](#releasing-a-version)
- [Acknowledgments](#acknowledgments)
- [License](#license)
- [Support](#support)

<!-- ABOUT THE PROJECT -->

## About the Project

**Audiotext** transcribes audio files, videos, YouTube videos, media file links, microphone recordings, and entire folders into any of its 100 supported languages. You can transcribe files with [**WhisperX**](https://github.com/m-bain/whisperX) on your computer, for free and without sending your audio anywhere. Alternatively, you can transcribe files with the [**Whisper API**](https://platform.openai.com/docs/guides/speech-to-text) and the [**Google Speech-to-Text API**](https://cloud.google.com/speech-to-text). You can then play the transcription segment by segment, correct it, translate it, summarize it, and export it.

### Features

- **Any source**: sources can include audio and video files, YouTube videos, direct links to media files, live text transcription of your speech via the microphone, files from a folder (with or without subfolders) excluding those you choose, and a folder that transcribes files added to it even after the app has been restarted.
- **All the files in a folder in one place**: each file is displayed with its status, duration and size, as well as a preview of the text. You can then search, filter and sort the files, transcribe them again with different settings or export several files to a single TXT, Markdown or Word file.
- **Private and offline**: WhisperX can run run on your computer's CPU, or much faster on an NVIDIA GPU with CUDA, or on a Mac's Apple Silicon GPU using [MLX Whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper)).
- **Speaker identification**, word-level timings, background noise reduction for quiet speakers and hum, and keywords and context to spell names and terms correctly.
- **Translation while transcribing**, with Whisper, or afterwards with OpenAI, Claude, Gemini, DeepSeek, Mistral, Grok, Ollama, DeepL, or Google Translate.
- **A transcript you can play**: click a subtitle to play it, change the speed, search (and replace) the text, watch videos with their subtitles, rename the speakers, and edit the text while maintaining the timestamps.
- **Summaries** with the key points and the chapters of the transcription.
- **Questions about the transcription**, answered by the language model you choose for them, with links to where the answer is said.
- **Export** to plain text, Markdown, Word, SRT, VTT, ASS (with a color per speaker), TSV, or JSON.
- **Burn subtitles into the video** to share it where subtitle files can't be loaded.
- **History** of all your transcriptions, with search, groups, pins, tags and notes. There is also a queue for transcribing while you continue working, and you will receive a notification when each transcription is ready or when a new file is added to a watched folder.
- **Command-line interface** for transcribing scripts.
- **The interface in 22 languages**, with a light, dark or system theme.

### Documentation

The full **Audiotext** documentation is available at [**getaudiotext.com**](https://getaudiotext.com), in all the interface languages (Català, Čeština, Deutsch, English, Español, Français, Galego, हिन्दी, Bahasa Indonesia, Italiano, 日本語, 한국어, Nederlands, Polski, Português, Română, Русский, Svenska, Türkçe, Українська, Tiếng Việt and 简体中文). The website opens in the language of your browser, and the app opens it in the language of its interface under `Preferences` → `About` → `Documentation`.

<!-- LANGUAGES AND FORMATS -->

### Languages and Formats

Both WhisperX and the Whisper API can transcribe and automatically detect about 100 languages. **Audiotext** transcribes the most common audio and video formats, including `.mp3`, `.wav`, `.m4a`, `.mp4`, `.mkv`, `.webm`, and exports to `.txt`, `.md`, `.docx`, `.srt`, `.vtt`, `.ass`, `.tsv` and `.json`. See the full lists in [formats and languages](https://getaudiotext.com/en/reference/formats-and-languages/).

<!-- PROJECT STRUCTURE -->

### Project Structure

<details>
  <summary>ASCII folder structure</summary>

  ```
  │   .env.example
  │   .gitignore
  │   .pre-commit-config.yaml
  │   audiotext.spec
  │   config.ini
  │   LICENSE
  │   pyproject.toml
  │   README.md
  │   uv.lock
  │
  ├───.github
  │   │   CONTRIBUTING.md
  │   │   dependabot.yml
  │   │   FUNDING.yml
  │   │
  │   ├───ISSUE_TEMPLATE
  │   │       bug_report_template.md
  │   │       feature_request_template.md
  │   │
  │   ├───PULL_REQUEST_TEMPLATE
  │   │       pull_request_template.md
  │   │
  │   ├───scripts
  │   │       build_bundle.sh
  │   │       compile_translations.py
  │   │       make_gpu_addon.py
  │   │       smoke_test_app.py
  │   │       update_translations.py
  │   │   │
  │   └───workflows
  │           build.yml
  │           code-quality.yml
  │           release.yml
  │
  ├───docs/ (images of this README)
  │
  ├───packaging
  │   ├───licenses
  │   │       third_party_licenses.py
  │   │       <license>.txt (license texts of the bundled third-party software)
  │   │
  │   ├───linux
  │   │       install.sh
  │   │       make_archive.sh
  │   │
  │   ├───macos
  │   │       dmg-background.png
  │   │       dmg-background@2x.png
  │   │       dmg_settings.py
  │   │       make_dmg.sh
  │   │       make_dmg_background.py
  │   │
  │   └───windows
  │           ChineseSimplified.isl (Inno Setup messages missing from Inno Setup 6)
  │           installer.iss
  │
  ├───res
  │   ├───img
  │   │       file-explorer.png
  │   │       icon-dark.png
  │   │       icon-light.png
  │   │
  │   ├───locales
  │   │   │   audiotext.pot
  │   │   │
  │   │   └───<language>
  │   │       └───LC_MESSAGES
  │   │               audiotext.mo
  │   │               audiotext.po
  │   │
  │   ├───macos
  │   │       entitlements.plist
  │   │       icon.icns
  │   │
  │   └───windows
  │           icon.ico
  │
  ├───src
  │   │   app.py
  │   │   cli.py
  │   │   launcher.py
  │   │
  │   ├───controllers
  │   │       __init__.py
  │   │       directory_report.py
  │   │       folder_transcriber.py
  │   │       main_controller.py
  │   │       mic_recorder.py
  │   │       transcription_saver.py
  │   │       transcription_validator.py
  │   │
  │   ├───handlers
  │   │       __init__.py
  │   │       ai_providers.py
  │   │       audio_handler.py
  │   │       google_api_handler.py
  │   │       live_transcriber.py
  │   │       openai_api_handler.py
  │   │       summary_handler.py
  │   │       transcribers.py
  │   │       translation_handler.py
  │   │       url_handler.py
  │   │       whisperx_handler.py
  │   │       youtube_handler.py
  │   │
  │   ├───interfaces
  │   │       __init__.py
  │   │       transcribable.py
  │   │       transcriber.py
  │   │       transcription_view.py
  │   │
  │   ├───models
  │   │   │   __init__.py
  │   │   │   history.py
  │   │   │   summary.py
  │   │   │   transcript_segment.py
  │   │   │   transcription.py
  │   │   │   transcription_settings.py
  │   │   │   translation.py
  │   │   │
  │   │   └───config
  │   │           __init__.py
  │   │           config_ai.py
  │   │           config_subtitles.py
  │   │           config_system.py
  │   │           config_transcription.py
  │   │           config_whisper_api.py
  │   │           config_whisperx.py
  │   │
  │   ├───utils
  │   │       __init__.py
  │   │       audio_player.py
  │   │       audio_utils.py
  │   │       cancellation.py
  │   │       config_manager.py
  │   │       constants.py
  │   │       enums.py
  │   │       env_keys.py
  │   │       errors.py
  │   │       exporters.py
  │   │       folder_watcher.py
  │   │       history_store.py
  │   │       i18n.py
  │   │       media.py
  │   │       notifications.py
  │   │       path_helper.py
  │   │       progress.py
  │   │       subtitle_cues.py
  │   │       system.py
  │   │       time_format.py
  │   │       transcript_editing.py
  │   │       update_checker.py
  │   │       validators.py
  │   │
  │   └───views
  │       │   __init__.py
  │       │
  │       ├───entries
  │       │       __init__.py
  │       │       delegates.py
  │       │       entry_header.py
  │       │       folder_view.py
  │       │       progress_card.py
  │       │       status_view.py
  │       │
  │       ├───history
  │       │       __init__.py
  │       │       formatting.py
  │       │       history_row.py
  │       │       history_sidebar.py
  │       │
  │       ├───main_window
  │       │       __init__.py
  │       │       entry_actions.py
  │       │       main_window.py
  │       │       top_bar.py
  │       │       transcription_jobs.py
  │       │       welcome_view.py
  │       │
  │       ├───new_transcription
  │       │       __init__.py
  │       │       microphone_view.py
  │       │       new_transcription_view.py
  │       │
  │       ├───settings
  │       │   │   __init__.py
  │       │   │   option_labels.py
  │       │   │   preferences_dialog.py
  │       │   │   settings_form.py
  │       │   │
  │       │   └───cards
  │       │           __init__.py
  │       │           base.py
  │       │           context_card.py
  │       │           engine_card.py
  │       │           folder_card.py
  │       │           language_card.py
  │       │           live_card.py
  │       │           options_card.py
  │       │           output_card.py
  │       │
  │       ├───style
  │       │       __init__.py
  │       │       icons.py
  │       │       theme.py
  │       │
  │       ├───transcript
  │       │       __init__.py
  │       │       corrections.py
  │       │       edit_dialogs.py
  │       │       media_layout.py
  │       │       player_bar.py
  │       │       summary_panel.py
  │       │       transcript_text.py
  │       │       transcript_view.py
  │       │       translation_panel.py
  │       │       video_pane.py
  │       │
  │       └───widgets
  │               __init__.py
  │               bindings.py
  │               button.py
  │               level_meter.py
  │               option_menu.py
  │               pill.py
  │               placeholder.py
  │               scrollable_frame.py
  │               search_entry.py
  │               searchable_option_menu.py
  │               splitter.py
  │               stepper.py
  │               text_dialog.py
  │               textbox.py
  │
  └───tests/ (the test suite (pytest))
  ```
</details>

<!-- BUILT WITH -->

### Built With

- [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) for the interface, and [tkinterdnd2](https://github.com/Eliav2/tkinterdnd2) for dropping files and folders on the window.
- [WhisperX](https://github.com/m-bain/whisperX) for fast automatic speech recognition on your computer. Uses [faster-whisper](https://github.com/SYSTRAN/faster-whisper), which is a reimplementation of [OpenAI's Whisper](https://github.com/openai/whisper) model using [CTranslate2](https://github.com/OpenNMT/CTranslate2/), and [pyannote.audio](https://github.com/pyannote/pyannote-audio) to identify the speakers.
- [MLX Whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper), which runs Whisper on the GPU of Apple Silicon with [MLX](https://github.com/ml-explore/mlx).
- [PyTorch](https://github.com/pytorch/pytorch) and [Torchaudio](https://pytorch.org/audio/stable/index.html), which WhisperX runs on, with [CUDA](https://pytorch.org/docs/stable/cuda.html) for NVIDIA GPUs.
- [OpenAI Python API library](https://pypi.org/project/openai/) for the **Whisper API**, and for the summaries and translations with OpenAI, DeepSeek, Gemini, Mistral, Grok and Ollama.
- [Anthropic Python API library](https://pypi.org/project/anthropic/) for the summaries and translations with Claude.
- [SpeechRecognition](https://pypi.org/project/SpeechRecognition/) for the **Google Speech-to-Text API**.
- [FFmpeg](https://ffmpeg.org/) and [pydub](https://github.com/jiaaro/pydub) to extract and process the audio of the files.
- [python-sounddevice](https://github.com/spatialaudio/python-sounddevice) to record from the microphone and play the audio of the transcriptions.
- [pytubefix](https://github.com/JuanBindez/pytubefix) to download the audio of YouTube videos.
- [python-docx](https://github.com/python-openxml/python-docx) to export Word documents.
- [Babel](https://babel.pocoo.org/) for the translations of the interface and the names of the languages.
- [keyring](https://github.com/jaraco/keyring) to keep the API keys in the credential store of the system, and [python-dotenv](https://pypi.org/project/python-dotenv/) to read them from `.env` files.
- [Astro Starlight](https://starlight.astro.build) for the [documentation website](https://getaudiotext.com).

<p align="right">(<a href="#top">back to top</a>)</p>

<!-- GETTING STARTED -->

## Getting Started

### Installation

Download the file for your system from the [latest release](https://github.com/HenestrosaDev/audiotext/releases/latest). FFmpeg is included, so you don't need to install anything else.

| System | File |
| --- | --- |
| macOS 15 or later (Apple Silicon) | `Audiotext-X.Y.Z-macos-arm64.dmg` |
| Windows (64-bit) | `Audiotext-X.Y.Z-windows-x64-setup.exe` |
| Linux (x86_64) | `Audiotext-X.Y.Z-linux-x86_64.tar.gz` |

- **macOS**: open the `.dmg` and drag `Audiotext` into `Applications`. The app isn't notarized, so allow it the first time in `System Settings` > `Privacy & Security` > `Open Anyway`.
- **Windows**: run the installer. SmartScreen may warn you because the installer isn't signed. Click `More info` > `Run anyway`.
- **Linux**: extract the archive and run `./install.sh`.

If you have an NVIDIA GPU, the installer on Windows and Linux offers to download GPU acceleration with CUDA. The [installation guide](https://getaudiotext.com/en/getting-started/installation/) explains each step and the requirements.

### Setting Up the Project Locally

1. Install the system dependencies: [FFmpeg](https://ffmpeg.org) (required to process audio and video files) and [PortAudio](https://www.portaudio.com/) (required to record from the microphone and play audio). On Linux, PortAudio is requires; on macOS and Windows, it's included in the `sounddevice` package:
   ```bash
   # macOS
   brew install ffmpeg
   # Ubuntu/Debian
   sudo apt install ffmpeg libportaudio2
   # Windows
   choco install ffmpeg
   ```
   Homebrew's FFmpeg can't burn subtitles into videos, since it's built without libass. To burn subtitles into videos on macOS, build the version that the app bundles after cloning the repository, then add it to the `PATH` variable with the command: `packaging/macos/build_ffmpeg.sh && export PATH="$PWD/build/ffmpeg/bin:$PATH"`.
2. Clone the repository by running `git clone https://github.com/HenestrosaDev/audiotext.git` and change the current working directory to `audiotext` by running `cd audiotext`.
3. Install [uv](https://docs.astral.sh/uv/getting-started/installation/), which manages the project's dependencies and virtual environment. It also downloads a supported version of Python (**3.10 to 3.13**, since WhisperX doesn't support Python 3.14 yet) if you don't have one.
4. Run `uv sync` to create the virtual environment (`.venv`) and install the dependencies, including the development ones.
   - `uv sync` installs PyTorch with CUDA support, which is a large download (several GB) on Linux and Windows. If you don't have an NVIDIA GPU, run `uv sync --no-group cuda --group cpu` instead to install the CPU-only build. On macOS, the CPU build is always used because there's no CUDA, and Macs with Apple Silicon transcribe using their GPU with MLX Whisper.
5. If you intend to contribute to the project, run `uv run pre-commit install` to install the pre-commit hooks in your `.git/` directory. These hooks are required to contribute because they perform the same checks as the [Code Quality](.github/workflows/code-quality.yml) workflow on each commit. This ensures that commits that would fail the checks are not created.
6. (Optional) You can set the API keys from the app. To set them in advance, copy the `.env.example` file to the `.env` file in your user configuration folder (see the [notes](#notes) below) and fill in the necessary information. The API keys can also be set as environment variables.
7. Run `uv run src/app.py` to start the program. The first time a **WhisperX** model is used, it's downloaded (from ~75 MB for `tiny` to ~3 GB for `large-v2`), so it may take a while. To try the program quickly, choose the `tiny` model in the `Engine` settings of the transcription.
8. (Optional) Run `uv run pytest` to run the test suite.

### Notes

- The project's `config.ini` file contains the default settings and is never modified by the app. Your settings, history, and recordings are stored in your user configuration folder, or in `AUDIOTEXT_CONFIG_DIR`. The API keys are stored in the credential store of your system, or in environment variables, such as `OPENAI_API_KEY` and `HF_TOKEN`. For more information, see [Files and Data](https://getaudiotext.com/en/reference/files-and-data/).

<p align="right">(<a href="#top">back to top</a>)</p>

<!-- USAGE -->

## Usage

The [documentation](https://getaudiotext.com) explains how to use each feature:

- [Your first transcription](https://getaudiotext.com/en/getting-started/first-transcription/): the window and the keyboard shortcuts.
- [Audio sources](https://getaudiotext.com/en/guides/sources/): files, URLs, the microphone and folders.
- [Transcription settings](https://getaudiotext.com/en/guides/transcription-settings/): the language, the context and the options.
- [Engines](https://getaudiotext.com/en/reference/engines/): WhisperX, the Whisper API and the Google API, and their models.
- [The transcript](https://getaudiotext.com/en/guides/transcript/): playing, searching and correcting the transcription.
- [Summary, questions and translation](https://getaudiotext.com/en/guides/summary-and-translation/): the AI providers and their models.
- [History](https://getaudiotext.com/en/guides/history/) and [preferences](https://getaudiotext.com/en/reference/preferences/).

### Command-Line Interface

**Audiotext** can also transcribe from the command line, e.g. from scripts. The installed app runs it when a command is given:

| System | Command |
| --- | --- |
| Linux | `audiotext` (installed in `~/.local/bin` by `install.sh`) |
| macOS | `/Applications/Audiotext.app/Contents/MacOS/Audiotext` |
| Windows | `audiotext-cli.exe`, in the folder where Audiotext is installed (`%LOCALAPPDATA%\Programs\Audiotext` by default) |

From the source code, run `uv run src/cli.py` instead:

```bash
# Transcribe a file. The text is also printed, so it can be redirected
audiotext transcribe interview.mp3 --language es --output-types txt,srt

# Transcribe the files of a folder identifying the speakers
audiotext transcribe recordings/ --diarize --speakers 2 --output-dir transcriptions/

# Save the subtitles and a Word document, summarize it, and translate it into Spanish
audiotext transcribe talk.mp4 --output-types srt,docx --summarize --translate-to es

# Transcribe the files added to a folder until stopped with Ctrl+C
audiotext watch inbox/ --output-types srt

# The same, transcribing first the files it already contains
audiotext watch inbox/ --existing
```

The transcription method doesn't save output types that it doesn't recognize (e.g., `.md` or `.docx`), so they are exported from its result. The `--summarize` option writes a `*.summary.md` file next to each transcription. The `--translate-to` option writes the translation in one of the output types (e.g., `talk.es.srt`), using the providers configured in the app unless the `--summary-provider` or `--translation-provider` options are specified.

Run `audiotext transcribe --help` to see all the options, or see [the command-line interface](https://getaudiotext.com/en/reference/cli/).

<p align="right">(<a href="#top">back to top</a>)</p>

<!-- TROUBLESHOOTING -->

## Troubleshooting

See [troubleshooting](https://getaudiotext.com/en/help/troubleshooting/) for common problems and their solutions. If yours isn't there, [open an issue](https://github.com/HenestrosaDev/audiotext/issues/new/choose).

<!-- ROADMAP -->

## Roadmap

See the [project backlog](https://github.com/users/HenestrosaDev/projects/1).

You can propose a new feature by creating a [discussion](https://github.com/HenestrosaDev/audiotext/discussions/new?category=ideas)!

<!-- AUTHORS -->

## Authors

- HenestrosaDev <github@henestrosa.dev> (José Carlos López Henestrosa)

See also the list of [contributors](https://github.com/HenestrosaDev/audiotext/contributors) who participated in this project.

<!-- CONTRIBUTING -->

## Contributing

Contributions are what make the open source community such an amazing place to learn, inspire, and create. Any contributions you make are **greatly appreciated**. Please read the [CONTRIBUTING.md](https://github.com/HenestrosaDev/audiotext/blob/main/.github/CONTRIBUTING.md) file, where you can find more detailed information about how to contribute to the project.

### Translations

The interface is translated using [gettext](https://www.gnu.org/software/gettext/). Texts marked with one of the following:
- `_()`, for texts that are translated once, when they are first displayed.
- `L_()` for texts that are translated again when the language changes.
- `P_()` for texts with a plural form.
- `C_()` for texts translated differently in a context.

The translations are in `res/locales/audiotext.pot`. Translations for each language are in `res/locales/<language>/LC_MESSAGES/audiotext.po` and are compiled into `audiotext.mo` files that the app loads.

After changing the text of the code or editing a `.po` file (e.g., with [Poedit](https://poedit.net/)), run the following command:

```bash
uv run .github/scripts/update_translations.py
```

It extracts the text into the template, updates the catalogs, and compile them. Then, it lists the texts that still need to be translated or reviewed. New texts are empty, and changed ones are marked as `fuzzy`. These texts are shown in English until they're translated and the `fuzzy` flag is removed.

Tests (`tests/test_translations.py`) fail when a catalog is out of date or when a translation doesn't keep the placeholders of the original text (e.g., `{count}`).

To add a language, first create its catalog. Then, add the language to the `UI_LANGUAGES` list in the `src/utils/i18n.py` file. Next, translate the language. Finally, run the script.

```bash
uv run pybabel init -i res/locales/audiotext.pot -d res/locales -D audiotext -l <code>
uv run .github/scripts/update_translations.py
```

### Documentation Website

The source for [getaudiotext.com](https://getaudiotext.com) is in the [audiotext-docs](https://github.com/HenestrosaDev/audiotext-docs) repository. It's built with [Astro Starlight](https://starlight.astro.build) and requires [Node.js](https://nodejs.org) 22.12 or later. Each language has its own folder in `src/content/docs` (e.g., `en`, `es` or `zh-cn`), and the website's root redirects to the browser's language or English.

```bash
git clone https://github.com/HenestrosaDev/audiotext-docs.git
cd audiotext-docs
npm install
npm run dev     # serves the website at http://localhost:4321
npm run build   # builds the website into dist
```

Update the English page and its translations when a feature changes. Pages that haven't been translated yet are shown in English with a notice in the other languages.

### Releasing a Version

See [Releasing a Version](https://github.com/HenestrosaDev/audiotext/blob/main/.github/CONTRIBUTING.md#releasing-a-version) in the contributing guide.

<!-- ACKNOWLEDGMENTS -->

## Acknowledgments

The following resources were used to create this project:

- [Buzz](https://github.com/chidiwilliams/buzz), which inspired the folder watching, the transcript viewer, the speaker identification and the command-line interface.
- [Extracting speech from video using Python](https://towardsdatascience.com/extracting-speech-from-video-using-python-f0ec7e312d38)
- [How to translate Python applications with the GNU gettext module](https://phrase.com/blog/posts/translate-python-gnu-gettext/)
- [Speech recognition on large audio files](https://www.geeksforgeeks.org/python-speech-recognition-on-large-audio-files/)

<!-- LICENSE -->

## License

Distributed under the MIT license. See [`LICENSE`](https://github.com/HenestrosaDev/audiotext/blob/main/LICENSE) for more information.

The app includes third-party software under its own licenses. For example, FFmpeg is licensed as GPL on Linux and Windows and as LGPL on macOS. These licenses are listed in `THIRD_PARTY_LICENSES.txt`, which is included with the app.

<!-- SUPPORT -->

## Support

Would you like to support the project? That's very kind of you! However, I would suggest that you to consider supporting the packages that I've used to build this project first. If you still want to support this particular project, you can go to my Ko-Fi profile by clicking on the button down below!

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/henestrosadev)

<p align="right">(<a href="#top">back to top</a>)</p>
