import gettext
import locale
import sys
from pathlib import Path


def get_path(relative_path: str = ""):
	"""Get absolute path, works for dev and for PyInstaller"""
	try:
		# PyInstaller creates a temp folder and stores path in _MEIPASS
		base_path = Path(sys._MEIPASS)
	except (Exception,):
		base_path = Path(__file__).parent.parent.resolve()

	return (base_path / relative_path).resolve()


ROOT_PATH = get_path("")

_ = None


def load_translation(language_code: str):
	translation = gettext.translation(
		"all",
		localedir=ROOT_PATH / "res/locales",
		languages=[language_code],
		fallback=True
	)
	translation.install()
	global _
	_ = translation.gettext


load_translation(locale.getdefaultlocale()[0])
