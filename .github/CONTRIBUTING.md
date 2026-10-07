<!-- omit in toc -->
# Contributing to audiotext

First off, thanks for taking the time to contribute! ❤️

All types of contributions are encouraged and valued. See the [Table of Contents](#table-of-contents) for different ways to help and details about how this project handles them. Please make sure to read the relevant section before making your contribution. It will make it a lot easier for us maintainers and smooth out the experience for all involved. The community looks forward to your contributions. 🎉

> And if you like the project, but just don't have time to contribute, that's fine. There are other easy ways to support the project and show your appreciation, which we would also be very happy about:
> - Star the project
> - Tweet about it
> - Refer this project in your project's readme
> - Mention the project at local meetups and tell your friends/colleagues

<!-- omit in toc -->
## Table of Contents

- [I Have a Question](#i-have-a-question)
- [I Want To Contribute](#i-want-to-contribute)
  - [Reporting Bugs](#reporting-bugs)
  - [Suggesting Enhancements](#suggesting-enhancements)
- [Setting Up the Development Environment](#setting-up-the-development-environment)
- [Styleguide](#styleguide)
  - [Commit Messages](#commit-messages)
  - [Code Style](#code-style)
- [Building the Installers](#building-the-installers)
- [Releasing a Version](#releasing-a-version)



## I Have a Question

> If you want to ask a question, we assume that you have read the available [documentation](https://getaudiotext.com).

Before you ask a question, it is best to search for existing [Issues](https://github.com/HenestrosaDev/audiotext/issues) that might help you. In case you have found a suitable issue and still need clarification, you can write your question in this issue. It is also advisable to search the internet for answers first.

If you then still feel the need to ask a question and need clarification, we recommend the following:

- Open an [Issue](https://github.com/HenestrosaDev/audiotext/issues/new).
- Provide as much context as you can about what you're running into.
- Provide the version of Audiotext and of your system (Windows, macOS or Linux), and the version of Python if you run it from the source code.

We will then take care of the issue as soon as possible.

<!--
You might want to create a separate issue tag for questions and include it in this description. People should then tag their issues accordingly.

Depending on how large the project is, you may want to outsource the questioning, e.g. to Stack Overflow or Gitter. You may add additional contact and information possibilities:
- IRC
- Slack
- Gitter
- Stack Overflow tag
- Blog
- FAQ
- Roadmap
- E-Mail List
- Forum
-->

## I Want To Contribute

> ### Legal Notice <!-- omit in toc -->
> When contributing to this project, you must agree that you have authored 100% of the content, that you have the necessary rights to the content and that the content you contribute may be provided under the project license.

### Reporting Bugs

<!-- omit in toc -->
#### Before Submitting a Bug Report

A good bug report shouldn't leave others needing to chase you up for more information. Therefore, we ask you to investigate carefully, collect information and describe the issue in detail in your report. Please complete the following steps in advance to help us fix any potential bug as fast as possible.

- Make sure that you are using the latest version.
- Determine if your bug is really a bug and not an error on your side e.g. using incompatible environment components/versions (Make sure that you have read the [documentation](https://getaudiotext.com). If you are looking for support, you might want to check [this section](#i-have-a-question)).
- To see if other users have experienced (and potentially already solved) the same issue you are having, check if there is not already a bug report existing for your bug or error in the [bug tracker](https://github.com/HenestrosaDev/audiotext/issues?q=label%3Abug).
- Also make sure to search the internet (including Stack Overflow) to see if users outside the GitHub community have discussed the issue.
- Collect information about the bug:
  - Stack trace (Traceback)
  - OS, Platform and Version (Windows, Linux, macOS, x86, ARM)
  - Version of the interpreter, compiler, SDK, runtime environment, package manager, depending on what seems relevant.
  - Possibly your input and the output
  - Can you reliably reproduce the issue? And can you also reproduce it with older versions?

<!-- omit in toc -->
#### How Do I Submit a Good Bug Report?

> You must never report security related issues, vulnerabilities or bugs including sensitive information to the issue tracker, or elsewhere in public. Instead, sensitive bugs must be sent by email to <github@henestrosa.dev>.
<!-- You may add a PGP key to allow the messages to be sent encrypted as well. -->

We use GitHub issues to track bugs and errors. If you run into an issue with the project, please use the [bug report template](https://github.com/HenestrosaDev/audiotext/issues/new?template=bug_report_template.md) and read the following points:

- Open an [Issue](https://github.com/HenestrosaDev/audiotext/issues/new/choose). (Since we can't be sure at this point whether it is a bug or not, we ask you not to talk about a bug yet and not to label the issue.)
- Explain the behavior you would expect and the actual behavior.
- Please provide as much context as possible and describe the *reproduction steps* that someone else can follow to recreate the issue on their own. This usually includes your code. For good bug reports you should isolate the problem and create a reduced test case.
- Provide the information you collected in the previous section.

Once it's filed:

- The project team will label the issue accordingly.
- A team member will try to reproduce the issue with your provided steps. If there are no reproduction steps or no obvious way to reproduce the issue, the team will ask you for those steps and mark the issue as `needs-repro`. Bugs with the `needs-repro` tag will not be addressed until they are reproduced.
- If the team is able to reproduce the issue, it will be marked `needs-fix`, as well as possibly other tags (such as `critical`), and the issue will be left to be [implemented by someone](#setting-up-the-development-environment).

<!-- You might want to create an issue template for bugs and errors that can be used as a guide and that defines the structure of the information to be included. If you do so, reference it here in the description. -->


### Suggesting Enhancements

This section guides you through submitting an enhancement suggestion for audiotext, **including completely new features and minor improvements to existing functionality**. Following these guidelines will help maintainers and the community to understand your suggestion and find related suggestions.

<!-- omit in toc -->
#### Before Submitting an Enhancement

- Make sure that you are using the latest version.
- Read the [documentation](https://getaudiotext.com) carefully and find out if the functionality is already covered, maybe by an individual configuration.
- Perform a [search](https://github.com/HenestrosaDev/audiotext/issues) to see if the enhancement has already been suggested. If it has, add a comment to the existing issue instead of opening a new one.
- Find out whether your idea fits with the scope and aims of the project. It's up to you to make a strong case to convince the project's developers of the merits of this feature. Keep in mind that we want features that will be useful to the majority of our users and not just a small subset. If you're just targeting a minority of users, consider writing an add-on/plugin library.

<!-- omit in toc -->
#### How Do I Submit a Good Enhancement Suggestion?

Enhancement suggestions are tracked as [GitHub issues](https://github.com/HenestrosaDev/audiotext/issues). Please use the [feature request template](https://github.com/HenestrosaDev/audiotext/issues/new?template=feature_request_template.md).

Don't forget to follow these principles:

- Use a **clear and descriptive title** for the issue to identify the suggestion.
- Provide a **step-by-step description of the suggested enhancement** in as many details as possible.
- **Describe the current behavior** and **explain which behavior you expected to see instead** and why. At this point you can also tell which alternatives do not work for you.
- **Explain why this enhancement would be useful** to most Audiotext users. You may also want to point out the other projects that solved it better and which could serve as inspiration.


## Setting Up the Development Environment
Audiotext needs Python 3.10 to 3.13 and [FFmpeg](https://ffmpeg.org/). From the root of the project:

```bash
python -m venv venv
source venv/bin/activate        # venv\Scripts\activate on Windows
pip install -r requirements-dev.txt
pre-commit install
```

Installing the hooks with `pre-commit install` is required: they run the same checks as the [Code Quality](workflows/code-quality.yml) workflow on the files of each commit, and stop the commit if any fails, so the problems are fixed before they reach a pull request. Git doesn't install them on its own when cloning, so it must be run once in each clone.

Before opening a pull request, check that the hooks and the tests pass, since the [Code Quality](workflows/code-quality.yml) workflow runs them on each one:

```bash
pre-commit run --all-files
pytest
```

The `main` branch is protected by the `no-commit-to-branch` hook, so work on a branch named after the type of the change (e.g. `feat/folder-watching` or `fix/windows-installer`).

If you change the texts of the interface, run `python .github/scripts/update_translations.py` to update the catalogs of `res/locales` (its docstring explains the steps).

## Styleguide
### Commit Messages
Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/):

```
<type>(<optional scope>): <description>

<optional body>

<optional footer>
```

The **type** is one of the following:

| Type | Use it for |
| --- | --- |
| `feat` | A new feature |
| `fix` | A bug fix |
| `docs` | Changes to the documentation only (README, CONTRIBUTING, docstrings...) |
| `style` | Formatting changes that don't affect the behavior |
| `refactor` | Code changes that neither fix a bug nor add a feature |
| `perf` | Performance improvements |
| `test` | New tests or changes to the existing ones |
| `build` | Changes to the packaging, PyInstaller or the dependencies |
| `ci` | Changes to the GitHub Actions workflows |
| `chore` | Other changes that don't modify the source code or the tests |
| `revert` | Reverting a previous commit |

The **scope** is optional and names the part of the project that changes, such as `ui`, `cli`, `handlers`, `controllers`, `i18n`, `build` or `release`.

The **description** is short, starts with a lowercase verb in the imperative mood and doesn't end with a period. For example:

- `feat(cli): add a command-line interface`
- `fix(i18n): keep the translatable texts out of f-strings`
- `docs: trim the README and link to the documentation website`

Breaking changes add a `!` after the type or scope (e.g. `feat(ui)!: redesign the interface`) and explain the change in a `BREAKING CHANGE:` footer.

The titles of the pull requests follow the same format, since the [PR Labels](workflows/pr-labels.yml) workflow labels each pull request by its type, and the notes of the releases are grouped by those labels (see [release.yml](release.yml)).

Each commit should do only one thing. For example, instead of a single "add contributing guides" commit, split it into:

- `docs: add the contributing guide`
- `chore: add the issue templates`
- `chore: add the pull request template`

### Code Style
The project uses [Ruff](https://docs.astral.sh/ruff/) to lint and format the code and [mypy](https://mypy.readthedocs.io/) in strict mode to check the types. The pre-commit hooks run both of them, and the configuration lives in `pyproject.toml`.

In an attempt to keep consistency and maintainability in the code-base, here are some high-level guidelines for code that might not be enforced by linters.

* Use f-strings, except for the texts to translate: mark them with `_()` and pass the values with `str.format()`, so the translations can reuse the placeholders.
* Keep/cast path variables as `pathlib.Path` objects. Do not use `os.path`. For public-facing functions, cast path arguments immediately to `Path`.
* Use magic-methods when appropriate. It might be better to implement ``MyClass.__call__()`` instead of ``MyClass.run()``.
* Do not return sentinel values for error-states like `-1` or `None`. Instead, raise an exception.
* Avoid deeply nested code. Techniques like returning early and breaking up a complicated function into multiple functions results in easier to read and test code.
* Consider if you are double-name-spacing and how modules are meant to be imported.
  Consider the module name-space and whether it's flattened in `__init__.py`.
* Only use multiple-inheritance if using a mixin. Mixin classes should end in `"Mixin"`.
* Add tests for the changes in `tests/`.

## Building the Installers
The scripts of the `packaging` folder create the file of each system from the app built by PyInstaller. Each one has to be run on its system, from the root of the project, in the virtual environment with the dependencies installed:

```bash
pip install pyinstaller
pyinstaller audiotext.spec --noconfirm   # builds the app in dist/
```

| System | Command | Creates (in `dist/`) | Requires |
| --- | --- | --- | --- |
| macOS | `packaging/macos.sh` | `Audiotext-X.Y.Z-macos-arm64.dmg` | - |
| Windows | `iscc packaging\windows.iss` | `Audiotext-X.Y.Z-windows-x64-setup.exe` | [Inno Setup](https://jrsoftware.org/isinfo.php) 6.5 or later |
| Linux | `packaging/linux.sh` | `Audiotext-X.Y.Z-linux-x86_64.tar.gz` (with `packaging/linux-install.sh` as `install.sh`) | - |

The version is the one of `pyproject.toml`. The installers built this way contain the PyTorch build installed in the virtual environment (CUDA or CPU) and don't offer the GPU add-on, which only the [Release](workflows/release.yml) workflow creates, since it needs both builds and the URL of the release.

## Releasing a Version
The [Release](workflows/release.yml) workflow builds the installers of each system and attaches them to a draft release when a version tag is pushed:

1. Update the `version` in `pyproject.toml` (e.g. `2.4.0`) and commit it.
2. Tag the commit with the same version prefixed by `v` and push the tag:
   ```bash
   git tag v2.4.0
   git push origin v2.4.0
   ```
   For a pre-release, add a suffix (e.g. `v2.4.0-rc.1`), which marks the release as a pre-release. The workflow fails if the tag doesn't match the version of `pyproject.toml`.
3. Once the workflow finishes (it takes a while, since it builds the app with and without CUDA), review the notes of the draft release and publish it. The installers can only download the GPU add-on (the `-gpu-N` files) once the release is published.

<!-- omit in toc -->
## Attribution
This guide is based on the **contributing-gen**. [Make your own](https://github.com/bttger/contributing-gen)!
