import constants
import os
import shutil
import speech_recognition as sr
import utils
from pathlib import Path
from pydub import AudioSegment
from pydub.silence import split_on_silence
from tkinter import filedialog


def open_file() -> str:
	"""
	Prompts a file explorer to determine the audio file path to transcribe.

	:return str: Filepath.
	"""
	filepath = filedialog.askopenfilename(
		initialdir="/",
		title=utils._("Select a file"),
		filetypes=[(utils._("Audio files"), constants.AUDIO_FILE_EXTENSIONS)]
	)
	return filepath


async def generate_file_transcription(filepath: str, language_code: str) -> str:
	"""
	Splits a large audio file into chunks
	and applies speech recognition on each one.

	:param str filepath: Path of the file to transcribe.
	:param str language_code: Code of the language spoken in the audio.
	:return str: Audio transcription.
	"""
	# Create a speech recognition object
	r = sr.Recognizer()

	# Open the audio file using pydub
	content_type = Path(filepath).suffix

	if "wav" in content_type:
		sound = AudioSegment.from_wav(filepath)
	elif "ogg" in content_type or "opus" in content_type:
		sound = AudioSegment.from_ogg(filepath)
	elif "mp3" in content_type or "mpeg" in content_type:
		sound = AudioSegment.from_mp3(filepath)

	# Split audio sound where silence is 700 miliseconds or more and get chunks
	chunks = split_on_silence(
		sound,
		# Experiment with this value for your target audio file
		min_silence_len=500,
		# Adjust this per requirement
		silence_thresh=sound.dBFS - 14,
		# Keep the silence for 1 second, adjustable as well
		keep_silence=500,
	)

	# Create a directory to store the audio chunks
	folder_name = utils.ROOT_PATH / "audio-chunks"
	folder_name.mkdir(exist_ok=True)

	whole_text = ""
	# Process each chunk
	for i, audio_chunk in enumerate(chunks, start=1):
		# Export audio chunk and save it in the `folder_name` directory.
		chunk_filename = os.path.join(folder_name, f"chunk{i}.wav")
		audio_chunk.export(chunk_filename, format="wav")

		# Recognize the chunk
		with sr.AudioFile(chunk_filename) as source:
			audio_listened = r.record(source)

			# Try converting it to text
			try:
				text = r.recognize_google(audio_listened, language=language_code)
			except Exception:
				shutil.rmtree(folder_name)
				return utils._("Error: Please, try again.")

			text = f"{text.capitalize()}. "
			whole_text += text

	# Delete temporal directory and files
	shutil.rmtree(folder_name)

	# Return the text for all chunks detected
	return whole_text


async def generate_mic_transcription(language_code: str) -> str:
	"""
	Generates the transcription from a microphone as
	the source of the audio.

	:param str language_code: Code of the language spoken.
	:return str: Transcription.
	"""
	with sr.Microphone() as mic:
		try:
			r = sr.Recognizer()
			print(f"{utils._('Say something')}…")
			r.energy_threshold = 300
			r.adjust_for_ambient_noise(mic)
			audio = r.listen(mic, timeout=3, phrase_time_limit=3)
			text = r.recognize_google(audio, language=language_code)
			return text
		except OSError:
			return utils._("Error: Microphone not available.")


def save_transcription(filepath, transcription):
	"""
	Prompts a file explorer to determine the file to save the
	generated transcription.

	:param str | None filepath: Filepath of the audio file, in case that there is one.
	:param str transcription: Text to save in the file.
	"""
	file = filedialog.asksaveasfile(
		mode='w',
		initialdir=Path(filepath).parent,
		initialfile=f'{Path(filepath).stem}.txt',
		title=utils._("Save as"),
		defaultextension='.txt',
		filetypes=[(utils._("Text file"), "*.txt"), (utils._("All Files"), "*.*")],
	)

	if file:
		file.write(transcription)
		file.close()
