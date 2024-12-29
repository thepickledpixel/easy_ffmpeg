import av
import json
import re
import csv
import os
import sys
import subprocess

from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

# Set a global RUNPATH variable
if getattr(sys, 'frozen', False):
    RUNPATH = os.path.dirname(sys.executable)
else:
    RUNPATH = os.path.abspath(os.path.dirname(__file__))

class CompatibilityMatrix:

    def __init__(self):
        self.encoders = sorted(av.formats_available)
        self.output_encoders = self.getOutputEncodersList()
        self.codecs = sorted(av.codecs_available)
        self.matrix_file = os.path.join(RUNPATH, "compatibility_matrix.json")
        self.codec_list_video = self.buildCodecList("video", mode='w')
        self.codec_list_audio = self.buildCodecList("audio", mode='w')
        self.no_workers = 200

    def buildCodecList(self, type, mode='w') -> list:
        """
        This returns a list of codecs that are available. Note that mode='w'
        returns a list of codecs which are capable out encoding. mode='r' would
        return a list of encoders which can decode.
        """
        codec_list = []
        for codec_name in self.codecs:
            try:
                cdc = av.codec.Codec(codec_name, mode=mode)
                if cdc.type == type:
                    codec_list.append(codec_name)
            except Exception as e:
                pass
        return codec_list

    def cleanAndSplitText(self, text):
        return re.split(r'[ /]+', re.sub(r'[()]', '', text.lower()))

    def ffmpegOutput(self, command):
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
        )
        return result

    def getMuxers(self) -> list:
        """
        Get a list of available Muxers from the FFmpeg command line.
        """
        result = self.ffmpegOutput(["ffmpeg", "-muxers"])
        output = result.stdout

        muxers = []

        lines = output.splitlines()
        start_index = next(i for i, line in enumerate(lines) if "---" in line) + 1
        muxer_lines = lines[start_index:]

        reader = csv.reader(muxer_lines, delimiter=' ', skipinitialspace=True)
        for row in reader:
            if len(row) < 3:
                continue

            flag = row[0]
            name = row[1]
            description = ' '.join(row[2:]).strip()

            muxers.append({
                "flag": flag,
                "name": name,
                "description": description
            })

        return muxers

    def getEncoder(self, encoder_name, mode='w') -> Optional[av.format.ContainerFormat]:
        """
        Note that pyAV calls Endcoders in ffmpeg "Formats". This function returns a
        Container format object
        """
        try:
            return av.format.ContainerFormat(encoder_name, mode=mode)
        except Exception as e:
            # Many of the encoders listed are not available and will error,
            # ignore these
            return None

    def getEncoderFileExtensions(self, enc) -> list:
        """
        Returns a list of export file extensions which are compatible with the
        Encoder
        """
        file_extensions = list(enc.extensions) if enc.extensions else []
        file_extensions.sort()
        return file_extensions

    def getEncoderOptions(self, enc) -> list:
        """
        Returns a list of options which can be applied to the Encoder
        """
        if enc and hasattr(enc, 'options') and enc.options:
            options = [option.name for option in enc.options]
        else:
            options = []
        options.sort()
        return options

    def getEncoderMuxer(self, enc) -> str:
        """
        Within the Container format object, the descriptor lists the default
        muxer which is compatible with that Encoder
        """
        if enc.descriptor and hasattr(enc.descriptor, 'name') and enc.descriptor.name:
            muxer = enc.descriptor.name
        else:
            muxer = ""
        return muxer

    def getEncoderMuxers(self, enc) -> list:
        """
        This searches the list of available ffmpeg muxers, and finds which
        ones match the muxer listed in the Container format object
        """
        muxers_list = []
        muxer = self.getEncoderMuxer(enc)
        muxer_split = self.cleanAndSplitText(muxer)
        muxers = self.getMuxers()

        for mux in muxers:
            for part in muxer_split:
                if mux['name'].lower() == part:
                    muxers_list.append(mux['name'])

        muxers_list.sort()
        return muxers_list

    def getOutputEncodersList(self) -> list:
        """
        Filter the encoder list to return a list of all encoders capable of
        encoding
        """
        output_formats = []
        for encoder_name in self.encoders:
            enc = self.getEncoder(encoder_name, 'w')
            if not enc:
                continue
            else:
                if enc.is_output:
                    output_formats.append(enc.name)

        return output_formats

    def buildEncoderMatrix(self) -> dict:
        compatibility_matrix = []
        item = 0

        for encoder_name in self.output_encoders:
            item += 1

            print(
                f"({item}/{len(self.output_encoders)})"\
                f" Checking codec compatibility for encoder: {encoder_name}"
            )
            compatible_video_codecs = self.getCompatibleCodecs(
                encoder_name, "video"
            )
            compatible_audio_codecs = self.getCompatibleCodecs(
                encoder_name, "audio"
            )

            compatible_video_codecs.sort()
            compatible_audio_codecs.sort()

            data = {
                encoder_name: {
                    "codecs": {
                        "video": compatible_video_codecs,
                        "audio": compatible_audio_codecs
                    }
                }
            }

            compatibility_matrix.append(data)

        return compatibility_matrix

    def testEncode(self, encoder_format, codec_name, type) -> bool:
        devnull = "NUL" if sys.platform.startswith("win") else "/dev/null"

        command_video = [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-f", "lavfi",
            "-i", "color=c=black:s=64x64:r=25",
            "-frames:v", "1",
            "-c:v", codec_name,
            "-pix_fmt", "yuv420p",
            "-f", encoder_format,
            devnull
        ]

        command_audio = [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-f", "lavfi",
            "-i", "sine=frequency=1000:duration=1:sample_rate=44100",
            "-c:a", codec_name,
            "-f", encoder_format,
            devnull
        ]

        if type == "video":
            command = command_video
        else:
            command = command_audio

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
            )
            if any(msg in result.stderr for msg in [
                "codec not currently supported in container"
            ]):
                return False
            return (result.returncode == 0)

        except Exception:
            print("Unknown reason for incompatibility - investigate")
            # print(result.stderr)
            return False

    def getCompatibleCodecs(self, encoder_name, type)  -> list:
        compatible_codecs = []

        if type == "video":
            codec_list = self.codec_list_video
        else:
            codec_list = self.codec_list_audio

        with ThreadPoolExecutor(max_workers=self.no_workers) as executor:
            future_to_codec = {
                executor.submit(
                    self.testEncode, encoder_name, codec_name, type
                ): codec_name
                for codec_name in codec_list
            }

            for future in as_completed(future_to_codec):
                codec_name = future_to_codec[future]
                try:
                    result = future.result()
                    if result:
                        compatible_codecs.append(codec_name)
                except Exception as e:
                    print(f"\tError testing codec {codec_name}: {e}")

        print(f"\t{type} codecs: {len(compatible_codecs)}")
        return compatible_codecs

    def getCodec(self):
        try:
            return av.codec.Codec(codec_name, mode='w')
        except:
            return None

    def getCodecVideoFormats(self, cdc) -> list:
        if cdc and hasattr(cdc, 'video_formats') and cdc.video_formats:
            video_formats = [format.name for format in cdc.video_formats]
        else:
            video_formats = []
        video_formats.sort()
        return video_formats

    def getCodecAudioFormats(self, cdc) -> list:
        if cdc and hasattr(cdc, 'audio_formats') and cdc.audio_formats:
            audio_formats = [format.name for format in cdc.audio_formats]
        else:
            audio_formats = []
        audio_formats.sort()
        return audio_formats

    def buildCompatibilityMatrix(self):
        compatibility_matrix = self.buildEncoderMatrix()
        formatted_matrix = json.dumps(compatibility_matrix, indent=4)
        with open(self.matrix_file, "w") as f:
            f.write(formatted_matrix)

    def iterateAllEncoders(self):
        if not os.path.exists(self.matrix_file):
            print("Codec compatibility matrix not found, please build")
            return

        with open(self.matrix_file, "r") as json_file:
            codec_matrix = json.load(json_file)

        for encoder_name in self.output_encoders:
            encoder = self.getEncoder(encoder_name)
            muxers = self.getEncoderMuxers(encoder)
            # print(muxers)
            options = self.getEncoderOptions(encoder)
            # print(options)
            file_extensions = self.getEncoderFileExtensions(encoder)
            # print(file_extensions)
            video_codecs = codec_matrix[encoder_name]['codecs']['video']
            print(video_codecs)
            audio_codecs = codec_matrix[encoder_name]['codecs']['audio']
            print(audio_codecs)


if __name__ == "__main__":

    compatibility_matrix = CompatibilityMatrix()
    compatibility_matrix.buildCompatibilityMatrix()
    compatibility_matrix.iterateAllEncoders()
