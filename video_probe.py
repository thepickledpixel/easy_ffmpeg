import subprocess
import os
import sys
import json
import argparse
from tabulate import tabulate
import textwrap

from deepdiff import DeepDiff
from compatibility_matrix import CompatibilityMatrix

class VideoProbe:
    def __init__(self):
        self.compatibility_matrix = CompatibilityMatrix()
        self.compare_diff = False
        self.compare_matches = False

    def getFfprobeJsonFromFile(self, file_path):
        try:
            command = [
                "ffprobe",
                "-v", "error",
                "-show_format",
                "-show_streams",
                "-of", "json",
                file_path
            ]
            result = subprocess.run(
                command, capture_output=True, text=True, check=True
            )
        except Exception as e:
            # print(e)
            return {}
        return json.loads(result.stdout)

    def getTranscodeSettingsFromFile(self, file_path, input_file=None, output_file=None, run_command=False):
        """
        Uses ffprobe to extract codec and encoder information for the given media file.
        """
        ffprobe_json = self.getFfprobeJsonFromFile(file_path)

        if not ffprobe_json:
            print(f"\nUnable to get metadata for {file_path}\n")
            return

        data = {}

        formatted_data = json.dumps(ffprobe_json, indent=4)
        _, extension = os.path.splitext(file_path)

        search_extension = None
        search_audio_codec = None
        search_video_codec = None

        detected_video = None
        detected_audio = None

        tags = ffprobe_json.get('format', {}).get('tags', None)
        format_bitrate = ffprobe_json.get('format', {}).get('bit_rate', None)

        for stream in ffprobe_json['streams']:
            if stream.get('codec_type') == "audio":
                search_audio_codec = stream.get('codec_name', None)
                data.update({
                    stream.get('index', None): {
                        "codec_name": stream.get('codec_name', None),
                        "codec_type": stream.get('codec_type', None),
                        "sample_rate": stream.get('sample_rate', None),
                        "channels": stream.get('channels', None),
                        "channel_layout": stream.get('channel_layout', None),
                        "bit_rate": stream.get('bit_rate', None)
                    }
                })
            if stream.get('codec_type') == "video":
                search_video_codec = stream.get('codec_name', None)
                data.update({
                    stream.get('index', None): {
                        "codec_name": stream.get('codec_name', None),
                        "codec_type": stream.get('codec_type', None),
                        "width": stream.get('width', None),
                        "height": stream.get('height', None),
                        "pix_fmt": stream.get('pix_fmt', None),
                        "color_space": stream.get('color_space', None),
                        "color_transfer": stream.get('color_transfer', None),
                        "color_range": stream.get('color_range', None),
                        "color_primaries": stream.get('color_primaries', None),
                        "chroma_location": stream.get('chroma_location', None),
                        "level": stream.get('level', None),
                        "has_b_frames": str(stream.get('has_b_frames', None)),
                        "profile": stream.get('profile', None),
                        "bit_rate": stream.get('bit_rate', None),
                        "time_base": stream.get('time_base', None),
                        "r_frame_rate": stream.get('r_frame_rate', None),
                        "field_order": stream.get('field_order', None)
                    }
                })

        search_extension = extension.replace('.', '').lower()

        data.update({
            "container": {
                "extension": search_extension,
                "tags": tags
            }

        })

        formatted_data = json.dumps(data, indent=4)

        transcode_data = {}

        transcode_data.update({
            "extension": data['container']['extension'],
            "tags": data['container']['tags']
        })

        for stream, attributes in data.items():
            if attributes.get('codec_type') == "video":
                detected_video = self.compatibility_matrix.getCodecAttributes(attributes.get('codec_name', None))
                if detected_video:
                    transcode_data.update({
                        "video_codec": attributes.get('codec_name', None),
                        "video_width": attributes.get('width', None),
                        "video_height": attributes.get('height', None),
                        "video_pix_fmt": attributes.get('pix_fmt', None),
                        "video_color_space": attributes.get('color_space', None),
                        "video_color_transfer": attributes.get('color_transfer', None),
                        "video_color_range": attributes.get('color_range', None),
                        "video_profile": (attributes.get('profile', "") or "").lower().replace(" ", ""),
                        "video_color_primaries": attributes.get('color_primaries', None),
                        "video_frame_rate": attributes.get('r_frame_rate', None),
                        "video_bit_rate": attributes.get('bit_rate', None),
                        "video_time_base": attributes.get('time_base', None),
                        "video_chroma_location": attributes.get('chroma_location', None),
                        "video_has_b_frames": str(attributes.get('has_b_frames', None)),
                        "video_level": str(attributes.get('level', None)),
                        "video_field_order": attributes.get('field_order', None)
                    })
                    if not transcode_data['video_bit_rate']:
                        transcode_data['video_bit_rate'] = format_bitrate
            if attributes.get('codec_type') == "audio":
                detected_audio = self.compatibility_matrix.getCodecAttributes(attributes.get('codec_name', None))
                if detected_audio:
                    transcode_data.update({
                        "audio_codec": attributes.get('codec_name', None),
                        "audio_sample_rate": attributes.get('sample_rate', None),
                        "audio_channels": attributes.get('channels', None),
                        "audio_channel_layout": attributes.get('channel_layout', None),
                        "audio_bit_rate": attributes.get('bit_rate', None)
                    })

        if not detected_video and not detected_audio:
            print("Could not detect any video or audio settings")
            return

        codec_settings = [detected_video, detected_audio]

        print("\nDetected Codecs:")
        self.compatibility_matrix.jsonToTable(codec_settings)

        print("\nTranscode Settings:")
        table_data = []
        headers = ['Setting', 'Value']

        self.compatibility_matrix.jsonToTable(self.reformatJsonForTable(transcode_data))

        ffmpeg_command = self.generateFfmpegTranscodeCommand(transcode_data, input_file, output_file)

        command_string = " ".join(ffmpeg_command)
        print("\nffmpeg command line:")
        print(f"\n{command_string}\n")

        if run_command is True:
            print(ffmpeg_command)
            result = self.compatibility_matrix.ffmpegOutput(ffmpeg_command)
            print(result.stdout)

    def generateFfmpegTranscodeCommand(self, json_data, input_file=None, output_file=None):
        """
        Converts a JSON dictionary into an FFmpeg command line.
        """
        # Base command
        command = ["ffmpeg", "-y"]

        if not input_file:
            input_file = "[input_file]"
        if not output_file:
            output_file = f"[output_file.{json_data.get('extension', 'mp4')}]"

        command += ["-i", f"'{input_file}'"]

        input_file_ffprobe_json = None
        if input_file:
            input_file_ffprobe_json = self.getFfprobeJsonFromFile(input_file)
            input_file_interlaced = False
            if input_file_ffprobe_json:
                for stream in input_file_ffprobe_json['streams']:
                    if stream.get('codec_type') == "video":
                        if stream.get('field_order', None).lower() == "progressive":
                            input_file_interlaced = True

        video_filter = ""
        # Video settings
        if json_data.get("video_codec"):
            command += ["-c:v", json_data.get("video_codec")]
        if json_data.get("video_width") and json_data.get("video_height"):
            video_filter += f"scale={json_data.get('video_width')}:{json_data.get('video_height')}"
            # command += ["-vf", f"scale={json_data.get('video_width')}:{json_data.get('video_height')}"]
        if json_data.get("video_pix_fmt"):
            command += ["-pix_fmt", json_data.get("video_pix_fmt")]
        if json_data.get("video_color_space"):
            command += ["-colorspace", json_data.get("video_color_space")]
        if json_data.get("video_color_transfer"):
            command += ["-color_trc", json_data.get("video_color_transfer")]
        if json_data.get("video_color_range"):
            command += ["-color_range", json_data.get("video_color_range")]
        if json_data.get("video_color_primaries"):
            command += ["-color_primaries", json_data.get("video_color_primaries")]
        if json_data.get("video_profile"):
            command += ["-profile:v", json_data.get("video_profile")]
        if json_data.get("video_frame_rate"):
            command += ["-r", json_data.get("video_frame_rate")]
        if json_data.get("video_bit_rate"):
            command += ["-b:v", json_data.get("video_bit_rate")]
        if json_data.get("video_chroma_location"):
            command += ["-chroma_sample_location", json_data.get("video_chroma_location")]
        if json_data.get("video_has_b_frames"):
            command += ["-bf", json_data.get("video_has_b_frames")]
        if json_data.get("video_time_base"):
            command += ["-time_base", json_data.get("video_time_base")]
        if json_data.get("video_level"):
            command += ["-level:v", json_data.get("video_level")]
        if json_data.get("video_field_order"):
            command += ["-field_order", json_data.get("video_field_order")]

        if input_file_interlaced is False:
            if json_data.get("video_field_order") == "progressive":
                print("Input file is Interlaced, and needs de-interlacing")
                if video_filter:
                    video_filter += ","
                video_filter += "yadif=mode=1"
        if input_file_interlaced is True:
            if json_data.get("video_field_order") != "progressive":
                print("Input file is Progressive, and needs interlacing")
                command += ["-flags", "+ildct+ilme"]

        if video_filter:
            command += ["-vf", video_filter]

        # Audio settings
        if json_data.get("audio_codec"):
            command += ["-c:a", json_data.get("audio_codec")]
        if json_data.get("audio_sample_rate"):
            command += ["-ar", json_data.get("audio_sample_rate")]
        if json_data.get("audio_channels"):
            command += ["-ac", str(json_data.get("audio_channels"))]
        if json_data.get("audio_channel_layout"):
            command += ["-channel_layout", json_data.get("audio_channel_layout")]
        if json_data.get("audio_bit_rate"):
            command += ["-b:a", json_data.get("audio_bit_rate")]

        if json_data.get("tags"):
            tags = json_data.get("tags")
            for key, value in tags.items():
                command += ["-metadata", f"'{key}={value}'"]

        command.append(f"'{output_file}'")

        # return " ".join(command)
        return command

    def reformatJsonForTable(self, json_data):
        """
        Reformats a JSON dictionary into a list of dictionaries
        suitable for displaying in a table with 'Setting' and 'Value'.
        """
        flattened_data = self.flattenDict(json_data)
        return self.convertFlattenedDataToTable(flattened_data)

    def flattenDict(self, json_data, parent_key=""):
        """
        Flattens nested dictionaries into a single-level dictionary with dot-separated keys.
        """
        items = []
        for key, value in json_data.items():
            new_key = f"{parent_key}.{key}" if parent_key else key
            if isinstance(value, dict):
                items.extend(self.flattenDict(value, new_key).items())
            else:
                items.append((new_key, value))
        return dict(items)

    def convertFlattenedDataToTable(self, flattened_data):
        """
        Converts a flattened dictionary into a list of dictionaries for table display.
        """
        reformatted = []
        for key, value in flattened_data.items():
            reformatted.append({"setting": key, "value": value})
        return reformatted

    def compareJsonBlobs(self, json1, json2, matches=None, diff=None):
        """
        Compares two JSON objects and displays two tables:
        1. Differences between the objects.
        2. Matches (keys and values that are the same in both objects).
        """
        differences, matches = self.getJsonComparisons(json1, json2)

        if self.compare_diff is True:
            print("\nDifferences:")
            if differences:
                self.compatibility_matrix.jsonToTable(differences)
            else:
                print("No differences found!")

        if self.compare_matches is True:
            print("\nMatches:")
            if matches:
                self.compatibility_matrix.jsonToTable(matches)
            else:
                print("No matches found!")

    def getJsonComparisons(self, json1, json2):
        """
        Recursively compares two JSON objects and returns two lists:
        1. Differences (keys/values that differ).
        2. Matches (keys/values that are identical).
        """
        differences = []
        matches = []
        self.compareDicts(json1, json2, differences, matches)
        return differences, matches

    def compareDicts(self, dict1, dict2, differences, matches, parentKey=""):
        """
        Recursively compares two dictionaries and appends differences and matches.
        Handles nested dictionaries and lists.
        """
        allKeys = set(dict1.keys()).union(set(dict2.keys()))
        for key in allKeys:
            fullKey = f"{parentKey}.{key}" if parentKey else key
            value1 = dict1.get(key)
            value2 = dict2.get(key)

            if isinstance(value1, dict) and isinstance(value2, dict):
                self.compareDicts(value1, value2, differences, matches, fullKey)
            elif isinstance(value1, list) and isinstance(value2, list):
                self.compareLists(value1, value2, differences, matches, fullKey)
            elif value1 != value2:
                differences.append({
                    "Section": parentKey,
                    "Setting": fullKey,
                    "Value in JSON1": value1,
                    "Value in JSON2": value2
                })
            else:
                matches.append({
                    "Section": parentKey,
                    "Setting": fullKey,
                    "Value in JSON1": value1,
                    "Value in JSON2": value2
                })

    def compareLists(self, list1, list2, differences, matches, parentKey=""):
        """
        Compares two lists and appends differences and matches.
        Handles lists of dictionaries by comparing them recursively.
        """
        maxLength = max(len(list1), len(list2))
        for i in range(maxLength):
            value1 = list1[i] if i < len(list1) else None
            value2 = list2[i] if i < len(list2) else None
            fullKey = f"{parentKey}[{i}]"

            if isinstance(value1, dict) and isinstance(value2, dict):
                self.compareDicts(value1, value2, differences, matches, fullKey)
            elif value1 != value2:
                differences.append({
                    "Section": parentKey,
                    "Setting": fullKey,
                    "Value in JSON1": value1,
                    "Value in JSON2": value2
                })
            else:
                matches.append({
                    "Section": parentKey,
                    "Setting": fullKey,
                    "Value": value1
                })

    def compareVideoJsonMetadata(
        self, source, dest, column_width=50, json_indent=4
    ):
        if isinstance(source, str):
            source = self.getFfprobeJsonFromFile(source)
        if isinstance(dest, str):
            dest = self.getFfprobeJsonFromFile(dest)

        if not isinstance(source, dict) or not isinstance(dest, dict):
            print("Could not get file metadata")
            return {}

        self.compareJsonBlobs(source, dest)

    def configureCliArguments(self):
        """
        Parse command line arguments
        """
        parser = argparse.ArgumentParser(
            description=f"FF Prober"
        )
        parser.add_argument(
            'probe_file', metavar='<ProbeFile>', nargs='?',
            help="File path of file to inspect (positional argument)"
        )
        parser.add_argument(
            '--probe-file', metavar='<ProbeFile>', help="File path of file to inspect"
        )
        parser.add_argument(
            '--input-file', metavar='<InputFile>', help="File path of file to convert"
        )
        parser.add_argument(
            '--output-file', metavar='<OutputFile>', help="File path of file to output"
        )
        parser.add_argument(
            '--run-command', action='store_true',
            help='Start transcoding using ffmpeg'
        )
        compare_group = parser.add_argument_group(
            'Compare video files',
            'Compare detailed metadata from two files'
        )
        compare_group.add_argument(
            '--compare', action='store_true',
            help='Compare detailed metadata from two files'
        )
        compare_group.add_argument(
            '--source', metavar='<SourceFile>',
            help='Path of source file'
        )
        compare_group.add_argument(
            '--dest', metavar='<DestFile>',
            help='Path of dest file'
        )
        compare_group.add_argument(
            '--diff', action='store_true',
            help='Display differences between metadata'
        )
        compare_group.add_argument(
            '--matches', action='store_true',
            help='Display matches between metadata'
        )

        args = parser.parse_args()
        if args.probe_file is None and not args.compare:
            parser.error("Require a probe file")

        if args.compare and not (args.source and args.dest):
            parser.error("--compare requires --source & --dest file paths")

        return args

    def main(self):
        args = self.configureCliArguments()

        input_file = None
        output_file = None
        run_command = False

        if args.input_file:
            input_file = args.input_file

        if args.output_file:
            output_file = args.output_file

        if args.run_command:
            run_command = True

        if args.probe_file:
            if os.path.exists(args.probe_file):
                self.getTranscodeSettingsFromFile(
                    args.probe_file,
                    input_file=input_file,
                    output_file=output_file,
                    run_command=run_command
                )
            else:
                print(f"\nFile does not exists: {args.probe_file}\n")
                sys.exit(1)

        if args.diff:
            self.compare_diff = True
        if args.matches:
            self.compare_matches = True

        if args.compare and (args.source or args.dest):
            self.compareVideoJsonMetadata(args.source, args.dest)

if __name__ == "__main__":
    video_probe = VideoProbe()
    video_probe.main()
