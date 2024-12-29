import av
import json
import re
import csv
import os
import sys
import subprocess
import curses
import argparse
import textwrap

from textwrap import fill
from tabulate import tabulate
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

################################################################################
# Easy FFMPEG - Compatibility Matrix - E. Spencer 2024                         #
# The following script is designed to build a compatibility matrix between     #
# encoders and codecs with ffmpeg. Such a matrix is not available from the     #
# ffmpeg CLI or API. When you normally submit a CLI job to ffmpeg, a           #
# function dynamically calculates which codec is suitable (if you do not       #
# specify one.)                                                                #
#                                                                              #
# Using the matrix, we can display a list of encoders, muxers, valid           #
# file extensions and audio/video codecs which can be selected within a GUI    #
# to submit a transcoding task.                                                #
################################################################################

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
        self.codec_matrix = self.loadCodecMatrix()

    def loadCodecMatrix(self):
        """
        Load a previously built codec/encoder matrix from disk
        """
        codec_matrix = None
        if not os.path.exists(self.matrix_file):
            print("Codec compatibility matrix not found, use --build-matrix")
            return None

        with open(self.matrix_file, "r") as json_file:
            codec_matrix = json.load(json_file)
        return codec_matrix

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
            # check=True,
        )
        # print(result.stderr)
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
            return None

    def getEncoderLongName(self, enc) -> str:
        return enc.long_name

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
        compatibility_matrix = {}
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

            compatibility_matrix.update(data)

        return compatibility_matrix

    def testEncode(self, encoder_format, codec_name, type) -> bool:
        devnull = "NUL" if sys.platform.startswith("win") else "/dev/null"

        common_options = ["ffmpeg", "-hide_banner", "-y", "-f", "lavfi"]
        media_specific_options = {
            "video": [
                "-i", "color=c=black:s=64x64:r=25",
                "-frames:v", "1",
                "-c:v", codec_name,
                "-pix_fmt", "yuv420p"
            ],
            "audio": [
                "-i", "sine=frequency=1000:duration=1:sample_rate=44100",
                "-c:a", codec_name
            ]
        }

        command = common_options + media_specific_options[type] + ["-f", encoder_format, devnull]

        try:
            result = self.ffmpegOutput(command)
            # result = subprocess.run(
            #     command,
            #     capture_output=True,
            #     text=True,
            # )
            if any(msg in result.stderr for msg in [
                "codec not currently supported in container"
            ]):
                return False
            return (result.returncode == 0)

        except Exception as e:
            # print("Unknown reason for incompatibility - investigate")
            print(e)
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

    def getCodec(self, codec_name):
        try:
            return av.codec.Codec(codec_name, mode='w')
        except:
            return None

    def getCodecLongName(self, cdc):
        return cdc.long_name

    def getCodecType(self, cdc):
        return cdc.type

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

    def wrapText(self, items, width=20):
        """
        Wrap a list or string into multiple lines.
        """
        if isinstance(items, list):
            # Join the items with commas and wrap the resulting string
            return "\n".join(textwrap.wrap(", ".join(items), width=width))
        elif isinstance(items, str):
            return "\n".join(textwrap.wrap(items, width=width))
        return items

    def getEncoderAttributes(self, encoder_name):
        encoder = self.getEncoder(encoder_name)
        if not encoder:
            return None

        data = {
            "long_name": self.getEncoderLongName(encoder),
            "muxers": self.getEncoderMuxers(encoder),
            "options": self.getEncoderOptions(encoder),
            "file_extensions": self.getEncoderFileExtensions(encoder),
            "video_codecs": self.codec_matrix[encoder_name]['codecs']['video'],
            "audio_codecs": self.codec_matrix[encoder_name]['codecs']['audio']
        }
        return data

    def getCodecAttributes(self, codec_name):
        codec = self.getCodec(codec_name)
        if not codec:
            return None

        data = {
            "long_name": self.getCodecLongName(codec),
            "type": self.getCodecType(codec),
            "video_formats": self.getCodecVideoFormats(codec),
            "audio_formats": self.getCodecAudioFormats(codec)
        }
        return data

    def displayEncoderAttributes(self, encoder_list):
        """
        Display Encoder attributes
        """
        if not self.codec_matrix:
            return

        table_data = []
        headers = [
            "Encoder Name", "Long Name", "Muxers", "Options",
            "File Extensions", "Video Codecs", "Audio Codecs"
        ]

        for encoder_name in encoder_list:
            enc_attributes = self.getEncoderAttributes(encoder_name)
            if enc_attributes:
                table_data.append([
                    encoder_name,
                    self.wrapText(enc_attributes['long_name']),
                    self.wrapText(enc_attributes['muxers']),
                    self.wrapText(enc_attributes['options']),
                    self.wrapText(enc_attributes['file_extensions']),
                    self.wrapText(enc_attributes['video_codecs']),
                    self.wrapText(enc_attributes['audio_codecs']),
                ])
            else:
                print(f"Could not find attributes for: {encoder_name}")

        print(tabulate(table_data, headers=headers, tablefmt="grid"))

    def displayCodecAttributes(self, codec_list):
        """
        Display codec attributes
        """
        table_data = []
        headers = [
            "Codec Name", "Long Name", "Type", "Video Formats", "Audio Formats"
        ]

        for codec_name in codec_list:
            cdc_attributes = self.getCodecAttributes(codec_name)
            if cdc_attributes:
                table_data.append([
                    codec_name,
                    self.wrapText(cdc_attributes['long_name']),
                    self.wrapText(cdc_attributes['type']),
                    self.wrapText(cdc_attributes['video_formats']),
                    self.wrapText(cdc_attributes['audio_formats']),
                ])
            else:
                print(f"Could not find attributes for: {codec_name}")

        print(tabulate(table_data, headers=headers, tablefmt="grid"))

    def configureCliArguments(self):
        """
        Parse command line arguments
        """
        parser = argparse.ArgumentParser(
            description=f"Easy FFMpeg Encoder Compatibility Matrix"
        )
        parser.add_argument(
            '--encoder', metavar='<Encoder>', help="Display Encoder details"
        )
        parser.add_argument(
            '--codec', metavar='<Codec>', help="Display Codec details"
        )
        parser.add_argument(
            '--all', action='store_true',
            help='Display details for all Encoders'
        )
        parser.add_argument(
            '--build-matrix', action='store_true',
            help='Build compatibility matrix'
        )
        return parser.parse_args()

if __name__ == "__main__":
    compatibility_matrix = CompatibilityMatrix()
    args = compatibility_matrix.configureCliArguments()

    if args.build_matrix:
        compatibility_matrix.buildCompatibilityMatrix()

    if args.encoder:
        compatibility_matrix.displayEncoderAttributes(
            [args.encoder]
        )

    if args.codec:
        compatibility_matrix.displayCodecAttributes(
            [args.codec]
        )

    if args.all:
        compatibility_matrix.displayEncoderAttributes(
            compatibility_matrix.output_encoders
        )
