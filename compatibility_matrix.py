import av
import json
import re
import csv
import os
import sys
import subprocess

from concurrent.futures import ThreadPoolExecutor, as_completed

if getattr(sys, 'frozen', False):
    RUNPATH = os.path.dirname(sys.executable)
else:
    RUNPATH = os.path.abspath(os.path.dirname(__file__))

class CompatibilityMatrix:

    def __init__(self):
        self.formats = sorted(av.formats_available)
        self.codecs = sorted(av.codecs_available)
        self.matrix_file = os.path.join(RUNPATH, "compatibility_matrix.json")
        self.codec_matrix_file = os.path.join(RUNPATH, "codec_matrix.json")
        self.codec_list_video = self.buildCodecList("video")
        self.codec_list_audio = self.buildCodecList("audio")
        self.no_workers = 200

    def buildCodecList(self, type):
        codec_list = []
        for codec_name in self.codecs:
            try:
                cdc = av.codec.Codec(codec_name, mode='w')
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

    def getMuxers(self):
        """Get a list of available Muxers from the current FFmpeg installation."""
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

    def buildEncoderMatrix(self):
        compatibility_matrix = []
        muxers = self.getMuxers()
        output_formats = []

        for format_name in self.formats:
            try:
                fmt = av.format.ContainerFormat(format_name, mode='w')
                if fmt.is_output:
                    output_formats.append(format_name)
            except:
                continue

        item = 0
        for format_name in output_formats:
            item += 1

            fmt = av.format.ContainerFormat(format_name, mode='w')

            muxers_list = []

            file_extensions = list(fmt.extensions) if fmt.extensions else []
            file_extensions.sort()

            if fmt and hasattr(fmt, 'options') and fmt.options:
                options = [option.name for option in fmt.options]
            else:
                options = []
            options.sort()

            if fmt.descriptor and hasattr(fmt.descriptor, 'name') and fmt.descriptor.name:
                muxer = fmt.descriptor.name
            else:
                muxer = ""

            muxer_split = self.cleanAndSplitText(muxer)

            for mux in muxers:
                for part in muxer_split:
                    if mux['name'].lower() == part:
                        muxers_list.append(mux['name'])

            muxers_list.sort()

            print(f"({item}/{len(output_formats)}) Checking codec compatibility for encoder: {format_name}")
            compatible_video_codecs = self.getCompatibleCodecs(format_name, "video")
            compatible_audio_codecs = self.getCompatibleCodecs(format_name, "audio")

            compatible_video_codecs.sort()
            compatible_audio_codecs.sort()

            data = {
                "format_name": format_name,
                "format_long_name": fmt.long_name,
                "format_options": options,
                "extensions": file_extensions,
                "muxer": muxer,
                "available_muxers": muxers_list,
                "compatible_video_codecs": compatible_video_codecs,
                "compatible_audio_codecs": compatible_audio_codecs
            }

            compatibility_matrix.append(data)

        return compatibility_matrix

    def testEncode(self, container_format, codec_name, type):
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
            "-f", container_format,
            devnull
        ]

        command_audio = [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-f", "lavfi",
            "-i", "sine=frequency=1000:duration=1:sample_rate=44100",
            "-c:a", codec_name,
            "-f", container_format,
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
                "codec not currently supported in container",
                "Unknown encoder",
                "(incorrect codec parameters ?)"
                "Unable to find a suitable codec"
            ]):
                return False
            return (result.returncode == 0)

        except subprocess.TimeoutExpired:
            return False
        except Exception:
            return False

    def getCompatibleCodecs(self, format_name, type):
        no_codecs = 0
        compatible_codecs = []

        if type == "video":
            codec_list = self.codec_list_video
        else:
            codec_list = self.codec_list_audio

        with ThreadPoolExecutor(max_workers=self.no_workers) as executor:
            future_to_codec = {
                executor.submit(
                    self.testEncode, format_name, codec_name, type
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


    def buildCodecMatrix(self):
        codec_matrix = []
        for codec_name in self.codecs:
            try:
                cdc = av.codec.Codec(codec_name, mode='w')
            except Exception as e:
                continue

            if cdc.is_encoder:

                if cdc and hasattr(cdc, 'video_formats') and cdc.video_formats:
                    video_formats = [format.name for format in cdc.video_formats]
                else:
                    video_formats = []
                video_formats.sort()

                if cdc and hasattr(cdc, 'audio_formats') and cdc.audio_formats:
                    audio_formats = [format.name for format in cdc.audio_formats]
                else:
                    audio_formats = []
                audio_formats.sort()

                data = {
                    "name": codec_name,
                    "long_name": cdc.long_name,
                    "type": cdc.type,
                    "video_formats": video_formats,
                    "audio_formats": audio_formats,
                }

                codec_matrix.append(data)

        formatted_matrix = json.dumps(codec_matrix, indent=4)
        with open(self.codec_matrix_file, "w") as f:
            f.write(formatted_matrix)

    def buildCompatibilityMatrix(self):
        compatibility_matrix = self.buildEncoderMatrix()
        formatted_matrix = json.dumps(compatibility_matrix, indent=4)
        with open(self.matrix_file, "w") as f:
            f.write(formatted_matrix)

if __name__ == "__main__":

    compatibility_matrix = CompatibilityMatrix()
    # compatibility_matrix.buildCompatibilityMatrix()
    compatibility_matrix.buildCodecMatrix()
