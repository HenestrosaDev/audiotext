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
  <p align="center">A desktop app that transcribes audio and video files, YouTube videos and microphone recordings on your computer, and translates, summarizes and subtitles them.</p>
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

https://github.com/user-attachments/assets/31c458cd-25f7-4a58-9854-479dcd77a654

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

**Audiotext** transcribes the audio of files, videos, YouTube videos, links to media files, microphone recordings and whole folders into any of the 100 languages it supports. It transcribes with [**WhisperX**](https://github.com/m-bain/whisperX) on your computer, for free and without sending your audio anywhere, or with the [**Whisper API**](https://platform.openai.com/docs/guides/speech-to-text) and the [**Google Speech-to-Text API**](https://cloud.google.com/speech-to-text). Then you can play the transcription segment by segment, correct it, translate it, summarize it and export it, for example as subtitles.

### Features

- **Any source**: audio and video files, YouTube videos and direct links to media files, the microphone (with a live draft of the text while you speak), the files of a folder and its subfolders, or a folder that is watched to transcribe the files added to it.
- **Private and offline**: WhisperX runs on your computer, on the CPU or, much faster, on an NVIDIA GPU with CUDA.
- **Speaker identification**, word-level timings, speech extraction (to reduce music and background noise), and keywords and context to spell names and terms right.
- **Translation while transcribing**, with Whisper, or afterwards with OpenAI, Claude, Gemini, DeepSeek, Mistral, Grok, Ollama, DeepL or Google Translate.
- **A transcript you can play**: click a segment to play it, change the speed, search the text, watch videos with their subtitles, rename the speakers and correct the text while keeping the timestamps.
- **Summaries** with the key points and the chapters of the transcription.
- **Export** to plain text, Markdown, Word, SRT, VTT, TSV and JSON.
- **History** of all your transcriptions, with search, groups, pins, tags and notes, and a queue to transcribe while you keep working, with a notification when each transcription is ready (or, in a watched folder, each new file).
- **Command-line interface** to transcribe from scripts.
- **The interface in 22 languages**, with a light, dark or system theme.

### Documentation

The full documentation of **Audiotext** is available at [**getaudiotext.com**](https://getaudiotext.com), in all the languages of the interface (Català, Čeština, Deutsch, English, Español, Français, Galego, हिन्दी, Bahasa Indonesia, Italiano, 日本語, 한국어, Nederlands, Polski, Português, Română, Русский, Svenska, Türkçe, Українська, Tiếng Việt and 简体中文). The website opens in the language of your browser, and the app opens it in the language of its interface from `Preferences` → `About` → `Documentation`.

<!-- LANGUAGES AND FORMATS -->

### Languages and Formats

WhisperX and the Whisper API transcribe about 100 languages and detect them automatically. **Audiotext** transcribes the most common audio and video formats (`.mp3`, `.wav`, `.m4a`, `.mp4`, `.mkv`, `.webm` and many more), and exports to `.txt`, `.md`, `.docx`, `.srt`, `.vtt`, `.tsv` and `.json`. See the full lists in [formats and languages](https://getaudiotext.com/en/reference/formats-and-languages/).

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
  │   requirements-dev.txt
  │   requirements.txt
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
  │   │       use_cpu_torch.py
  │   │
  │   └───workflows
  │           build.yml
  │           code-quality.yml
  │           release.yml
  │
  ├───docs/ (images of this README)
  │
  ├───packaging
  │   │   linux-install.sh
  │   │   linux.sh
  │   │   macos.sh
  │   │   third_party_licenses.py
  │   │   windows.iss
  │   │
  │   ├───languages/ (Inno Setup messages missing from Inno Setup 6)
  │   │
  │   └───licenses/ (license texts of the bundled third-party software)
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
- [WhisperX](https://github.com/m-bain/whisperX) for fast automatic speech recognition on your computer. This product includes software developed by Max Bain. Uses [faster-whisper](https://github.com/SYSTRAN/faster-whisper), which is a reimplementation of [OpenAI's Whisper](https://github.com/openai/whisper) model using [CTranslate2](https://github.com/OpenNMT/CTranslate2/), and [pyannote.audio](https://github.com/pyannote/pyannote-audio) to identify the speakers.
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
- **Windows**: run the installer. SmartScreen may warn you because it isn't signed: click `More info` > `Run anyway`.
- **Linux**: extract the archive and run `./install.sh`.

On Windows and Linux, the installer offers to download GPU acceleration (CUDA) if you have an NVIDIA GPU. The [installation guide](https://getaudiotext.com/en/getting-started/installation/) explains each step and the requirements.

### Setting Up the Project Locally

1. Install the system dependencies: [FFmpeg](https://ffmpeg.org) (required to process audio and video files) and, on Linux, [PortAudio](https://www.portaudio.com/) (required to record from the microphone and play audio; on macOS and Windows, it's included in the `sounddevice` package):
   ```bash
   # macOS
   brew install ffmpeg
   # Ubuntu/Debian
   sudo apt install ffmpeg libportaudio2
   # Windows
   choco install ffmpeg
   ```
2. Clone the repository by running `git clone https://github.com/HenestrosaDev/audiotext.git` and change the current working directory to `audiotext` by running `cd audiotext`.
3. (Optional but recommended) Create a Python virtual environment in the project root. If you're using `virtualenv`, you would run `virtualenv venv`. **Python 3.10 to 3.13** is required (WhisperX doesn't support Python 3.14 yet).
4. (Optional but recommended) Activate the virtual environment:
   ```bash
   # on Windows
   . venv/Scripts/activate
   # if you get the error `FullyQualifiedErrorId : UnauthorizedAccess`, run this:
   Set-ExecutionPolicy Unrestricted -Scope Process
   # and then . venv/Scripts/activate

   # on macOS and Linux
   source venv/bin/activate
   ```
5. Run `pip install -r requirements.txt` to install the dependencies.
   - `requirements.txt` installs PyTorch with CUDA support, which is a large download (several GB) on Linux and Windows. If you don't have an NVIDIA GPU, install the CPU-only build first by running `pip install torch==2.8.0 torchaudio==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cpu`. On macOS, there's no CUDA, so the CPU build is always used.
   - If you use [uv](https://docs.astral.sh/uv/) instead of pip, run `uv pip install --index-strategy unsafe-best-match -r requirements.txt`, since uv only looks for a package in the first index that has it by default.
6. (Optional) If you intend to contribute to the project, run `pip install -r requirements-dev.txt` to install the development dependencies.
7. (Optional) If you followed step 6, run `pre-commit install` to install the pre-commit hooks in your `.git/` directory.
8. (Optional) The API keys can be set from the app. To set them beforehand, copy the `.env.example` file as `.env` to your user configuration folder (see the notes below) and fill them in. They can also be set as environment variables.
9. Run `python src/app.py` to start the program. The first time a **WhisperX** model is used, it's downloaded (from ~75 MB for `tiny` to ~3 GB for `large-v2`), so it may take a while. To try the program quickly, choose the `tiny` model in the `Engine` settings of the transcription.
10. (Optional) If you followed step 6, run `pytest` to run the test suite.

### Notes

- The `config.ini` file of the project contains the default settings and is never modified by the app. Your settings, history and recordings are stored in your user configuration folder (or in `AUDIOTEXT_CONFIG_DIR`), and the API keys in the credential store of your system or in environment variables such as `OPENAI_API_KEY` and `HF_TOKEN`. See [files and data](https://getaudiotext.com/en/reference/files-and-data/).

<p align="right">(<a href="#top">back to top</a>)</p>

<!-- USAGE -->

## Usage

The [documentation](https://getaudiotext.com) explains how to use each feature:

- [Your first transcription](https://getaudiotext.com/en/getting-started/first-transcription/): the window and the keyboard shortcuts.
- [Audio sources](https://getaudiotext.com/en/guides/sources/): files, URLs, the microphone and folders.
- [Transcription settings](https://getaudiotext.com/en/guides/transcription-settings/): the language, the context and the options.
- [Engines](https://getaudiotext.com/en/reference/engines/): WhisperX, the Whisper API and the Google API, and their models.
- [The transcript](https://getaudiotext.com/en/guides/transcript/): playing, searching and correcting the transcription.
- [Summary and translation](https://getaudiotext.com/en/guides/summary-and-translation/): the AI providers and their models.
- [History](https://getaudiotext.com/en/guides/history/) and [preferences](https://getaudiotext.com/en/reference/preferences/).

### Command-Line Interface

When [running it from the source code](#setting-up-the-project-locally), **Audiotext** can also transcribe from the command line:

```bash
# Transcribe a file. The text is also printed, so it can be redirected
python src/cli.py transcribe interview.mp3 --language es --output-types txt,srt

# Transcribe the files of a folder identifying the speakers
python src/cli.py transcribe recordings/ --diarize --speakers 2 --output-dir transcriptions/

# Transcribe the files added to a folder until stopped with Ctrl+C
python src/cli.py watch inbox/ --output-types srt
```

Run `python src/cli.py transcribe --help` to see all the options, or see [the command-line interface](https://getaudiotext.com/en/reference/cli/).

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

The interface is translated with [gettext](https://www.gnu.org/software/gettext/). The texts marked with `_()` (or `N_()`, for the ones defined before the language is set) are in `res/locales/audiotext.pot`, and the translations of each language in `res/locales/<language>/LC_MESSAGES/audiotext.po`, which are compiled into the `audiotext.mo` files that the app loads.

After the texts of the code change, or after editing a `.po` file (e.g. with [Poedit](https://poedit.net/)), run:

```bash
python .github/scripts/update_translations.py
```

It extracts the texts into the template, updates the catalogs, compiles them and lists the texts that are still to translate or review (new texts are empty, and changed ones are marked as `fuzzy`). Those are shown in English until they're translated and their `fuzzy` flag is removed. The tests (`tests/test_translations.py`) fail while a catalog is out of date or a translation doesn't keep the placeholders of the original text (e.g. `{count}`).

To add a language, create its catalog, add it to `UI_LANGUAGES` in `src/utils/i18n.py`, translate it and run the script:

```bash
pybabel init -i res/locales/audiotext.pot -d res/locales -D audiotext -l <code>
python .github/scripts/update_translations.py
```

### Documentation Website

The source of [getaudiotext.com](https://getaudiotext.com) is in the [audiotext-docs](https://github.com/HenestrosaDev/audiotext-docs) repository. It's built with [Astro Starlight](https://starlight.astro.build) and requires [Node.js](https://nodejs.org) 22.12 or later. Each language has its own folder in `src/content/docs` (e.g. `en`, `es` or `zh-cn`), and the root of the website redirects to the language of the browser, or to English.

```bash
git clone https://github.com/HenestrosaDev/audiotext-docs.git
cd audiotext-docs
npm install
npm run dev     # serves the website at http://localhost:4321
npm run build   # builds the website into dist
```

When a feature changes, update the English page and its translations. A page that hasn't been translated yet is shown in English, with a notice, in the other languages.

### Releasing a Version

See [Releasing a Version](https://github.com/HenestrosaDev/audiotext/blob/main/.github/CONTRIBUTING.md#releasing-a-version) in the contributing guide.

<!-- ACKNOWLEDGMENTS -->

## Acknowledgments

I used the following resources to create this project:

- [Buzz](https://github.com/chidiwilliams/buzz), which inspired the folder watching, the transcript viewer, the speaker identification and the command-line interface.
- [Extracting speech from video using Python](https://towardsdatascience.com/extracting-speech-from-video-using-python-f0ec7e312d38)
- [How to translate Python applications with the GNU gettext module](https://phrase.com/blog/posts/translate-python-gnu-gettext/)
- [Speech recognition on large audio files](https://www.geeksforgeeks.org/python-speech-recognition-on-large-audio-files/)

<!-- LICENSE -->

## License

Distributed under the MIT license. See [`LICENSE`](https://github.com/HenestrosaDev/audiotext/blob/main/LICENSE) for more information.

The app includes third-party software under its own licenses, such as FFmpeg (GPL). They are listed in `THIRD_PARTY_LICENSES.txt`, which is included with the app.

<!-- SUPPORT -->

## Support

Would you like to support the project? That's very kind of you! However, I would suggest that you to consider supporting the packages that I've used to build this project first. If you still want to support this particular project, you can go to my Ko-Fi profile by clicking on the button down below!

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/henestrosadev)

<p align="right">(<a href="#top">back to top</a>)</p>
