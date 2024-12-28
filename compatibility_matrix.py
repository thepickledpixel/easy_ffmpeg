import av
import io
import json
import re
import csv
import sys
from io import StringIO
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

class CompatibilityMatrix:

    def __init__(self):
        self.formats = sorted(av.formats_available)
        self.codecs = sorted(av.codecs_available)
        self.codec_list_video = self.buildCodecList("video")
        self.codec_list_audio = self.buildCodecList("audio")

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

    def buildMatrix(self):
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

            if fmt.descriptor and hasattr(fmt.descriptor, 'options') and fmt.descriptor.options:
                desc_options = [option.name for option in fmt.descriptor.options]
            else:
                desc_options = []
            desc_options.sort()

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

            print(f"({item}/{len(output_formats)}) Checking codec compatibility for {format_name}")
            compatible_video_codecs = self.getCompatibleCodecs(format_name, "video")
            compatible_audio_codecs = self.getCompatibleCodecs(format_name, "audio")

            data = {
                "format_name": format_name,
                "format_long_name": fmt.long_name,
                "format_options": options,
                "extensions": file_extensions,
                "muxer": muxer,
                "available_muxers": muxers_list,
                "muxer_options": desc_options,
                "compatible_video_codecs": compatible_video_codecs,
                "compatible_audio_codecs": compatible_audio_codecs
            }

            compatibility_matrix.append(data)

        return compatibility_matrix

    def testEncode(self, container_format, codec_name, type):
        devnull = "NUL" if sys.platform.startswith("win") else "/dev/null"

        # timeout_seconds = 10

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
                # timeout=timeout_seconds
            )
            # print(result.stderr)   # <-- Use `stderr` (not `sterr`)
            if any(msg in result.stderr for msg in [
                "codec not currently supported in container",
                "Unknown encoder",
                "(incorrect codec parameters ?)"
                "Unable to find a suitable codec"
            ]):
                # print("CODEC NOT SUPPORTED")
                return False
            return (result.returncode == 0)
        #
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

        with ThreadPoolExecutor(max_workers=100) as executor:
            future_to_codec = {
                executor.submit(self.testEncode, format_name, codec_name, type): codec_name
                for codec_name in codec_list
            }

            for future in as_completed(future_to_codec):
                codec_name = future_to_codec[future]
                try:
                    result = future.result()
                    if result:
                        compatible_codecs.append(codec_name)
                except Exception as e:
                    print(f"Error testing codec {codec_name}: {e}")

        print(f"\t\tCompatible {type} codecs: {compatible_codecs}")
        return compatible_codecs

    def buildCompatibilityMatrix(self):
        compatibility_matrix = self.buildMatrix()
        pretty_settings = json.dumps(compatibility_matrix, indent=4)
        print(pretty_settings)

if __name__ == "__main__":

    compatibility_matrix = CompatibilityMatrix()
    compatibility_matrix.buildCompatibilityMatrix()
