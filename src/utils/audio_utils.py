import speech_recognition as sr
from pydub import AudioSegment


def save_audio_data(audio_data, filename):
    if audio_data:
        raw_audio_data = b"".join(
            [
                chunk.get_raw_data(convert_rate=None, convert_width=None)
                for chunk in audio_data
            ]
        )
        audio = AudioSegment(
            raw_audio_data,
            sample_width=audio_data[0].sample_width,
            frame_rate=audio_data[0].sample_rate,
            channels=1,
        )

        try:
            audio.export(filename, format="wav")
            print(f"Audio data saved to {filename}")
        except sr.UnknownValueError:
            print("Could not save audio data. Unknown value error.")
        except sr.RequestError as e:
            print(f"Could not request results; {e}")
