import constants
import os
import moviepy.editor as mp
import shutil
import speech_recognition as sr
import traceback
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
	audio_file_extensions_list = [
		ext for value in constants.AUDIO_FILE_EXTENSIONS.values() for ext in value
	]

	filepath = filedialog.askopenfilename(
		initialdir="/",
		title=utils._("Select a file"),
		filetypes=[
			(utils._("Audio files"), audio_file_extensions_list),
			(utils._("Video files"), constants.VIDEO_FILE_EXTENSIONS)
		]
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
	# Can be the transcription or an error text
	text_to_return = ""

	# Create a directory to store the audio chunks
	chunks_directory = utils.ROOT_PATH / "audio-chunks"
	chunks_directory.mkdir(exist_ok=True)

	try:
		# Create a speech recognition object
		r = sr.Recognizer()

		# Get file extension
		content_type = Path(filepath).suffix

		# Open the audio file using pydub
		if content_type in constants.AUDIO_FILE_EXTENSIONS["wav"]:
			sound = AudioSegment.from_wav(filepath)
		elif content_type in constants.AUDIO_FILE_EXTENSIONS["ogg"]:
			sound = AudioSegment.from_ogg(filepath)
		elif content_type in constants.AUDIO_FILE_EXTENSIONS["mp3"]:
			sound = AudioSegment.from_mp3(filepath)
		elif content_type in constants.VIDEO_FILE_EXTENSIONS:
			clip = mp.VideoFileClip(filepath)
			video_audio_path = chunks_directory / f"{Path(filepath).stem}.wav"
			clip.audio.write_audiofile(video_audio_path)
			sound = AudioSegment.from_wav(video_audio_path)

		# Split audio sound where silence is 500 milliseconds or more and get chunks
		chunks = split_on_silence(
			sound,
			# Experiment with this value for your target audio file
			min_silence_len=500,
			# Adjust this per requirement
			silence_thresh=sound.dBFS - 14,
			# Keep the silence for 1 second, adjustable as well
			keep_silence=500,
		)

		# Process each chunk
		for i, audio_chunk in enumerate(chunks, start=1):
			# Export audio chunk and save it in the `chunks_directory` directory.
			chunk_filename = os.path.join(chunks_directory, f"chunk{i}.wav")
			audio_chunk.export(chunk_filename, format="wav")

			# Recognize the chunk
			with sr.AudioFile(chunk_filename) as source:
				audio_listened = r.record(source)

				# Try converting it to text
				text = r.recognize_google(audio_listened, language=language_code)

				text = f"{text.capitalize()}. "
				text_to_return += text
	except Exception:
		print(traceback.format_exc())
		text_to_return = utils._("Error: Please, try again.")
	finally:
		# Delete temporal directory and files
		shutil.rmtree(chunks_directory)

		# Return the text for all chunks detected
		return text_to_return


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
