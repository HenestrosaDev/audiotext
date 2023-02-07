<div id="top"></div>

<!-- PROJECT SHIELDS -->
<!--
*** I'm using markdown "reference style" links for readability.
*** Reference links are enclosed in brackets [ ] instead of parentheses ( ).
*** See the bottom of this document for the declaration of the reference variables
*** for contributors-url, forks-url, etc. This is an optional, concise syntax you may use.
*** https://www.markdownguide.org/basic-syntax/#reference-style-links
-->

[![Contributors][contributors-shield]][contributors-url]
[![Forks][forks-shield]][forks-url]
[![Stargazers][stars-shield]][stars-url]
[![Issues][issues-shield]][issues-url]

<!-- PROJECT LOGO -->
<br />
<div align="center">
    <a href="https://github.com/othneildrew/Best-README-Template">
        <img src="docs/icon.png" alt="Logo" width="80" height="80">
    </a>
    <h3 align="center">Audiotext</h3>
    <p align="center">
        A program that transcribes audio from a file or microphone to text in any language supported by the Google API.
        <br />
        <a href="https://github.com/HenestrosaConH/audiotext/issues">Report Bug</a> · <a href="https://github.com/HenestrosaConH/audiotext/issues">Request Feature</a>
    </p>
</div>

<!-- TABLE OF CONTENTS -->
<details>
    <summary>Table of Contents</summary>
    <ol>
        <li>
            <a href="#about-the-project">About The Project</a>
            <ul>
                <li><a href="#project-structure">Project Structure</a></li>
                <li><a href="#built-with">Built With</a></li>
            </ul>
        </li>
        <li><a href="#getting-started">Getting Started</a></li>
        <li><a href="#contributing">Contributing</a></li>
        <li><a href="#license">License</a></li>
        <li><a href="#contact">Contact</a></li>
        <li><a href="#acknowledgments">Acknowledgments</a></li>
    </ol>
</details>

<!-- ABOUT THE PROJECT -->

## About The Project

[![Main screenshot light][demo]](https://github.com/HenestrosaConH/audiotext)

The project is available in Spanish and English. It supports 71 different languages and can take the audio from an audio file, video file or microphone. 
You can also select the theme you like best. It can be dark, light or the one configured in the system.  

<!-- PROJECT STRUCTURE -->

### Project Structure

Directories:
 
- `docs`: Contains files related to the documentation of the project.
- `res`: Contains all the static resources used by the app, which are the app icon (located in the `img` folder) and the i18n files (located in the `locales` folder).
- `src`:  Contains the source code files of the app.

Besides those directories, there are also these two files in the root (apart from the .gitignore, README.md and LICENSE):

- `audiotext.spec`: Used to generate a .exe file with [PyInstaller](https://pyinstaller.org/en/stable/). Notice that, inside the file, there are is the annotation `PATH TO CUSTOMTKINTER`. You will have to replace it by the actual path in your computer. To get it, you can execute `pip show customtkinter`.  
- `requirements.txt`: Lists the names and versions of each package used to build this project. To install the requirements, execute `pip install -r requirements.txt`.
 
<p align="right">(<a href="#top">back to top</a>)</p>

<!-- BUILT WITH -->

### Built With

- [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter)
- [moviepy](https://pypi.org/project/moviepy/)
- [PyAudio](https://pypi.org/project/PyAudio/)
- [pydub](https://github.com/jiaaro/pydub)
- [SpeechRecognition](https://pypi.org/project/SpeechRecognition/)

<p align="right">(<a href="#top">back to top</a>)</p>

<!-- GETTING STARTED -->

## Getting Started

**Important**: You need to install [FFmpeg](https://ffmpeg.org) to execute the program. Otherwise, it won't be able to process the audio files. You can download FFmpeg from the [official site](https://ffmpeg.org/download.html).

If you want to execute the program:
- Go to [releases](https://github.com/HenestrosaConH/audiotext/releases) and download the latest one. Once you download it and uncompress it, open the `audiotext` folder and open the `audiotext.exe` file. 

If you want to open the code:
- Clone the project with the `git clone https://github.com/HenestrosaConH/audiotext.git` command and then open it with your favourite IDE (mine is [PyCharm](https://www.jetbrains.com/pycharm/)).
- Please bear in mind that you cannot generate a single .exe file for this project with PyInstaller due to the dependency with the CustomTkinter package (reason [here](https://github.com/TomSchimansky/CustomTkinter/wiki/Packaging)).
- It's crucial to note that I've had to comment out the line `pprint(response_text, indent=4)` in the `recognize_google` function from the `__init__.py` file of the `SpeechRecognition` package. If it wasn't commented, the project would need to run a command line along with the GUI. Otherwise, the program wouldn't run when calling this function because the mentioned line throws an error that stops the function from running (in case that the program doesn't run on a console), which cannot be handled within the project code.
- Similar to the point above, the lines 159, 160 and 176 of the file `ffmpeg_audiowriter` from the `moviepy` package are commented for the same reason stated above. There is also a change in the line 169. `logger=logger` has been changed to `logger=None` to avoid more errors related to opening the console.
- For Mac M1 users: There is a problem installing the `pyaudio` library. [Here](https://stackoverflow.com/questions/73268630/error-could-not-build-wheels-for-pyaudio-which-is-required-to-install-pyprojec) is a StackOverflow post explaining how to solve this issue.

<p align="right">(<a href="#top">back to top</a>)</p>

<!-- CONTRIBUTING -->

## Contributing  

Contributions are what make the open source community such an amazing place to learn, inspire, and create. Any contributions you make are **greatly appreciated**.

If you have a suggestion that would make this better, please fork the repo and create a pull request. You can also simply open an issue with the tag `enhancement`.
Don't forget to give the project a star! Thanks again!

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

<p align="right">(<a href="#top">back to top</a>)</p>

<!-- LICENSE -->

## License

Distributed under the Creative Commons 1.0 License. See `LICENSE.txt` for more information.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- CONTACT -->

## Contact

<a href="https://www.linkedin.com/in/henestrosaconh/" target="blank"><img src="https://img.shields.io/badge/LinkedIn-0077B5?style=for-the-badge&logo=linkedin&logoColor=white" alt="LinkedIn"/></a> 
<a href="mailto:henestrosaconh@gmail.com" target="_blank"><img alt="Gmail" src="https://img.shields.io/badge/Gmail-D14836?style=for-the-badge&logo=gmail&logoColor=white" /></a>

<p align="right">(<a href="#top">back to top</a>)</p>

<!-- ACKNOWLEDGMENTS -->

## Acknowledgments

I've made use of the following resources to make this project:

- [Extracting Speech from Video using Python](https://towardsdatascience.com/extracting-speech-from-video-using-python-f0ec7e312d38)
- [How to Translate Python Applications with the GNU gettext Module](https://phrase.com/blog/posts/translate-python-gnu-gettext/)
- [How to Convert Speech to Text in Python](https://www.thepythoncode.com/article/using-speech-recognition-to-convert-speech-to-text-python)
- [Best-README-Template](https://github.com/othneildrew/Best-README-Template/)
- [Img Shields](https://shields.io)

<p align="right">(<a href="#top">back to top</a>)</p>

<!-- MARKDOWN LINKS & IMAGES -->
<!-- https://www.markdownguide.org/basic-syntax/#reference-style-links -->

[contributors-shield]: https://img.shields.io/github/contributors/HenestrosaConH/audiotext.svg?style=for-the-badge
[contributors-url]: https://github.com/HenestrosaConH/audiotext/graphs/contributors
[forks-shield]: https://img.shields.io/github/forks/HenestrosaConH/audiotext.svg?style=for-the-badge
[forks-url]: https://github.com/HenestrosaConH/audiotext/network/members
[stars-shield]: https://img.shields.io/github/stars/HenestrosaConH/audiotext.svg?style=for-the-badge
[stars-url]: https://github.com/HenestrosaConH/audiotext/stargazers
[issues-shield]: https://img.shields.io/github/issues/HenestrosaConH/audiotext.svg?style=for-the-badge
[issues-url]: https://github.com/HenestrosaConH/audiotext/issues
[linkedin-url]: https://linkedin.com/in/henestrosaconh
[demo]: docs/demo.gif
[icon]: docs/icon.png
