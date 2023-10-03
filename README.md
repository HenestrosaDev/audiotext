<div id="top"></div>

<!-- PROJECT SHIELDS -->
<!--
*** I am using markdown "reference style" links for readability.
*** Reference links are enclosed in brackets [ ] instead of parentheses ( ).
*** See the bottom of this document for the declaration of the reference variables
*** for contributors-url, forks-url, etc. This is an optional, concise syntax you may use.
*** https://www.markdownguide.org/basic-syntax/#reference-style-links
-->

<!-- PROJECT LOGO -->
<br />
<div align="center">
    <img src="docs/icon.png" alt="Logo" width="128" height="128" style="margin-bottom:-40px">
    <h1 align="center">Audiotext</h1>
    <p align="center">A program that transcribes audio from a file or microphone to text in almost any language.</p>
    <p>
        <a href="https://github.com/HenestrosaConH/audiotext/stargazers">
          <img alt="GitHub Contributors" src="https://img.shields.io/github/stars/HenestrosaConH/audiotext" />
        </a>
        <a href="https://github.com/HenestrosaConH/audiotext/graphs/contributors">
          <img alt="GitHub Contributors" src="https://img.shields.io/github/contributors/HenestrosaConH/audiotext" />
        </a>
        <a href="https://github.com/HenestrosaConH/audiotext/issues">
          <img alt="Issues" src="https://img.shields.io/github/issues/HenestrosaConH/audiotext" />
        </a>
        <a href="https://github.com/HenestrosaConH/audiotext/pulls">
          <img alt="GitHub pull requests" src="https://img.shields.io/github/issues-pr/HenestrosaConH/audiotext" />
        </a>
        <a href="https://github.com/HenestrosaConH/audiotext/blob/main/LICENSE">
          <img alt="GitHub pull requests" src="https://img.shields.io/github/license/HenestrosaConH/audiotext" />
        </a>
    </p>
    <p>
        <a href="https://github.com/HenestrosaConH/audiotext/issues/new/choose">Report Bug</a> · <a href="https://github.com/HenestrosaConH/audiotext/issues/new/choose">Request Feature</a> · <a href="https://github.com/HenestrosaConH/audiotext/discussions">Ask Question</a>
    </p>
</div>

<!-- TABLE OF CONTENTS -->

## Table of Contents

- [About the Project](#about-the-project)
    - [Project Structure](#project-structure)
    - [Built With](#built-with)
- [Getting Started](#getting-started)
    - [Notes](#notes) 
    - [To Execute the Program](#to-execute-the-program)
    - [To Get the Code](#to-get-the-code)
- [Usage](#usage)
    - [Select Audio File](#select-audio-file)
    - [Transcribe From Microphone](#transcribe-from-microphone)
    - [Save Transcription](#save-transcription)
    - [Appearance Mode](#appearance-mode)
    - [API Usage](#api-usage)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)
- [Authors](#authors)
- [Acknowledgments](#acknowledgments)
- [Support](#support)

<!-- ABOUT THE PROJECT -->

## About the Project

[![Main screenshot light][demo]](https://github.com/HenestrosaConH/audiotext)

The project is available in Spanish and English. It supports 69 different languages, along with some of their dialects, and can take the audio from an audio file, video file or microphone. 
You can also select the theme you like best. It can be dark, light or the one configured in the system.

<details>
  <summary>List of supported languages</summary>

Afrikaans    
አማርኛ    
لعربية  
(العربية (الإمارات  
(العربية (البحرين  
(العربية (الجزائر  
(العربية (مصر  
العربية (إسرائيل  
(العربية (الأردن  
(العربية (الكويت  
(العربية (لبنان  
(العربية (المغرب  
(العربية (عُمان  
(العربية (فلسطين  
(العربية (قطر  
(العربية (السعودية  
(العربية (تونس  
Azərbaycan  
беларуская  
Български  
বাংলা  
বাংলা (বাংলাদেশ)  
বাংলা (ভারত)  
Català  
Čeština  
Dansk  
Deutsch  
Schweizer Hochdeutsch  
Ελληνικά  
English  
Español  
Eesti  
Euskara  
فارسی  
Suomi  
Filipino  
Français  
Galego  
ગુજરાતી  
हिन्दी  
Hrvatski  
Magyar  
հայերեն  
Bahasa Indonesia  
Íslenska  
Italiano  
עברית  
日本語  
Basa Jawa  
ქართულად  
Қазақ  
ខ្មែរ  
ಕನ್ನಡ  
한국어  
ລາວ  
Lietuvių  
Latviešu  
മലയാളം  
Монгол  
मराठी  
Bahasa Melayu  
Malti  
नेपाली  
Nederlands  
Norsk (Nynorsk)  
Norsk (Bokmål)  
ਪੰਜਾਬੀ  
Polski  
Português  
Română  
Русский  
සිංහල  
Slovenčina  
Slovenščina  
Српски  
Basa Sunda  
Svenska  
Kiswahili  
தமிழ்  
தமிழ் (இந்தியா)  
தமிழ் (இலங்கை)  
தமிழ் (மலேஷியா)  
தமிழ் (சிங்கப்பூர்)  
తెలుగు  
ไทย  
Türkçe  
Українська  
اردو  
(اردو (بھارت  
(اردو (پاکستان  
Tiếng Việt  
中文（中国）  
中文（香港）  
中文（台灣）  
Isizulu  
</details>

<!-- PROJECT STRUCTURE -->

### Project Structure

<details>
  <summary>ASCII folder structure</summary>

  ```
  │   .gitignore
  │   audiotext.spec
  │   LICENSE
  │   README.md
  │   requirements.txt
  │
  ├───.github
  │   │   CONTRIBUTING.md
  │   │
  │   ├───ISSUE_TEMPLATE
  │   │       bug_report_template.md
  │   │       feature_request_template.md
  │   │
  │   └───PULL_REQUEST_TEMPLATE
  │           pull_request_template.md
  │
  ├───docs
  │       demo.gif
  │       file-explorer.png
  │       generated-transcription.png
  │       icon.png
  │       main-light.png
  │       main-system.png
  │
  ├───res
  │   ├───img
  │   │       icon.ico
  │   │
  │   └───locales
  │       │   main_controller.pot
  │       │   main_window.pot
  │       │
  │       ├───en
  │       │   └───LC_MESSAGES
  │       │           app.mo
  │       │           app.po
  │       │           main_controller.po
  │       │           main_window.po
  │       │
  │       └───es
  │           └───LC_MESSAGES
  │                   app.mo
  │                   app.po
  │                   main_controller.po
  │                   main_window.po
  │
  └───src
      │   app.py
      │
      ├───controller
      │       main_controller.py
      │       __init__.py
      │
      ├───model
      │       transcription.py
      │       __init__.py
      │
      ├───utils
      │       constants.py
      │       i18n.py
      │       path_helper.py
      │       __init__.py
      │
      └───view
              main_window.py
              __init__.py   
  ```
</details>

<!-- BUILT WITH -->

### Built With

- [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter): For the creation of the GUI.
- [moviepy](https://pypi.org/project/moviepy/): For video processing, from which the program extracts the audio to be transcribed.
- [PyAudio](https://pypi.org/project/PyAudio/): For recording microphone audio.
- [pydub](https://github.com/jiaaro/pydub): For audio processing.
- [SpeechRecognition](https://pypi.org/project/SpeechRecognition/): For converting audio into text.

<p align="right">(<a href="#top">back to top</a>)</p>

<!-- GETTING STARTED -->

## Getting Started

### Notes
- Please bear in mind that you cannot generate a single executable file for this project with PyInstaller due to the dependency with the CustomTkinter package (reason [here](https://github.com/TomSchimansky/CustomTkinter/wiki/Packaging)).
- For **Mac M1** users: An error occurs when trying to install the `pyaudio` package. [Here](https://stackoverflow.com/questions/73268630/error-could-not-build-wheels-for-pyaudio-which-is-required-to-install-pyprojec) is a StackOverflow post explaining how to solve this issue.
- You need to install [FFmpeg](https://ffmpeg.org) to execute the program. Otherwise, it won't be able to process the audio files. You can download it using the following commands:

  ```
  # on Ubuntu or Debian
  sudo apt update && sudo apt install ffmpeg
  
  # on Arch Linux
  sudo pacman -S ffmpeg
  
  # on MacOS using Homebrew (https://brew.sh/)
  brew install ffmpeg
  
  # on Windows using Chocolatey (https://chocolatey.org/)
  choco install ffmpeg
  
  # on Windows using Scoop (https://scoop.sh/)
  scoop install ffmpeg
  ```

### To Execute the Program
1. Go to [releases](https://github.com/HenestrosaConH/audiotext/releases).
2. Download the latest release. 
3. Uncompress the downloaded file.
4. Open the `audiotext` folder.
5. Open the `audiotext.exe` file if you use **Windows** or the `audiotext` file if you use **GNU-Linux** or **macOS**.

### To Get the Code
1. Clone the project with the `git clone https://github.com/HenestrosaConH/audiotext.git` command.

<p align="right">(<a href="#top">back to top</a>)</p>

<!-- USAGE -->

## Usage

Once you open the Audiotext executable file (explained in the [getting started](#getting-started) section), you will see something like this:

![main-system][main-system]

### Select Audio File

Click on the `Select audio file` button and select a file from the file explorer. Please note that audio files are selected by default. To select video files, you will have to click on the combo box in the bottom right corner of the file explorer to change the file type, as indicated in red in the following image:

![file-explorer][file-explorer]

Once you select the file, a green button named `Generate transcription` will show up. Click on it to start generating the transcription.

If there is no error, you will see the audio's transcription in the text box, as shown in the [About the Project's gif](#about-the-project).

Please bear in mind that this process may take some time to complete, depending on the length of the file and whether it is an audio or video file.

### Transcribe From Microphone

You just have to click on the `Transcribe from microphone` button and say whatever you want to be transcribed.
Please keep in mind that your Operating System needs to recognize an input source. Otherwise, an error will be shown in the text box indicating that no microphone was detected.

It is also worth noting that you have 3 seconds to speak from the moment you click the button to the timeout. In case that no input was received, you will see an error in the text box notifying it. I might add a setting in the program to change it to let the user change it. 

### Save Transcription

Once the program has generated the transcription, you will see a green button named `Save transcription` below the text box.

![generated-transcription][generated-transcription]

To save it, you just have to click on the mentioned button. A file explorer will be prompted. You have to give the file a name and select the path where you want to store it. By default, the extension of the file is `.txt`, but you can change it to any other file type you want.

### Appearance Mode

The program supports three appearance modes:

<details>
  <summary>System</summary>
  <img src="docs/main-system.png" alt="System theme">
</details>

<details>
  <summary>Dark</summary>
  <img src="docs/main-system.png" alt="Dark theme">
</details>

<details>
  <summary>Light</summary>
  <img src="docs/main-light.png" alt="Light theme">
</details>

### API Usage

Since the program makes use of Google's Speech-To-Text API free tier, which can transcribe up to 60 minutes of audio per month at no cost,
you might have to add an API key if you want to make extensive use of this functionality.

However, there is no option in the GUI to add it, so you have to add it manually. This can be done by adding the `key=<ACTUAL API KEY>` argument to both `recognize_google()` methods in the file `src/controller/main_controller.py`.

Notwithstanding, I have the intention to move from **speech_recognition** package to [whispercpp](https://github.com/aarnphm/whispercpp). This change would allow the user to generate audio transcriptions unlimitedly and offline, which is a major step forward for the program. 

<p align="right">(<a href="#top">back to top</a>)</p>

<!-- ROADMAP -->

## Roadmap

- [ ] Move from **speech_recognition** package to [whispercpp](https://github.com/aarnphm/whispercpp).
- [ ] Add pre-commit config.
- [ ] Add unit tests.
- [ ] Generate `.srt` files with the text along with timestamps. 
- [ ] Add a percentage to the progress bar.

You can propose a new feature creating an [issue](https://github.com/HenestrosaConH/audiotext/issues/new/choose).

<p align="right">(<a href="#top">back to top</a>)</p>

<!-- CONTRIBUTING -->

## Contributing  

Contributions are what make the open source community such an amazing place to learn, inspire, and create. Any contributions you make are **greatly appreciated**.
Please, read the [CONTRIBUTING.md](https://github.com/HenestrosaConH/audiotext/blob/main/.github/CONTRIBUTING.md) file, where you can find more detailed information about how to contribute to the project.

<p align="right">(<a href="#top">back to top</a>)</p>

<!-- LICENSE -->

## License

Distributed under the MIT License. See `LICENSE` for more information.

<p align="right">(<a href="#top">back to top</a>)</p>

<!-- AUTHORS -->

## Authors

- HenestrosaConH <henestrosaconh@gmail.com> (José Carlos López Henestrosa)

See also the list of [contributors](https://github.com/HenestrosaConH/audiotext/contributors) who participated in this project.

<p align="right">(<a href="#top">back to top</a>)</p>

<!-- ACKNOWLEDGMENTS -->

## Acknowledgments

I have made use of the following resources to make this project:

- [Extracting Speech from Video using Python](https://towardsdatascience.com/extracting-speech-from-video-using-python-f0ec7e312d38)
- [How to Translate Python Applications with the GNU gettext Module](https://phrase.com/blog/posts/translate-python-gnu-gettext/)
- [How to Convert Speech to Text in Python](https://www.thepythoncode.com/article/using-speech-recognition-to-convert-speech-to-text-python)
- [Best-README-Template](https://github.com/othneildrew/Best-README-Template/)
- [Img Shields](https://shields.io)

<p align="right">(<a href="#top">back to top</a>)</p>

<!-- SUPPORT -->

## Support

Would you like to support the project? That's very kind of you! However, I would suggest you to consider supporting the packages that I've used to build this project first. If you still want to support this particular project, you can go to my Ko-Fi profile by clicking on the button down below!

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/U7U5J6COZ)

<p align="right">(<a href="#top">back to top</a>)</p>

<!-- MARKDOWN LINKS & IMAGES -->
<!-- https://www.markdownguide.org/basic-syntax/#reference-style-links -->

[demo]: docs/demo.gif
[icon]: docs/icon.png
[main-system]: docs/main-system.png
[main-light]: docs/main-light.png
[file-explorer]: docs/file-explorer.png
[generated-transcription]: docs/generated-transcription.png
