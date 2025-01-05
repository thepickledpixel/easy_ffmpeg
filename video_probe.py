import os
import sys
import json
import argparse
import subprocess
import textwrap

from tabulate import tabulate
from deepdiff import DeepDiff
from compatibility_matrix import CompatibilityMatrix

class VideoProbe:
    def __init__(self):
        self.compatibility_matrix = CompatibilityMatrix()
        self.compare_diff = False
        self.compare_matches = False
        self.video_map = {
            "video_codec":           ("-c:v", None),
            "video_pix_fmt":         ("-pix_fmt", None),
            "video_color_space":     ("-colorspace", None),
            "video_color_transfer":  ("-color_trc", None),
            "video_color_range":     ("-color_range", None),
            "video_color_primaries": ("-color_primaries", None),
            "video_profile":         ("-profile:v", None),
            "video_frame_rate":      ("-r", None),
            "video_bit_rate":        ("-b:v", None),
            "video_chroma_location": ("-chroma_sample_location", None),
            "video_has_b_frames":    ("-bf", None),
            "video_time_base":       ("-time_base", None),
            "video_level":           ("-level:v", None),
            "video_field_order":     ("-field_order", None),
        }
        self.audio_map = {
            "audio_codec":           ("-c:a", None),
            "audio_sample_rate":     ("-ar", None),
            "audio_channels":        ("-ac", str),
            "audio_channel_layout":  ("-channel_layout", None),
            "audio_bit_rate":        ("-b:a", None),
        }

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
            return {}
        return json.loads(result.stdout)

    def runFfmpeg(self, command):
        with subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        ) as process:

            for line in process.stderr:
                line = line.rstrip()
                if line:
                    print(line)

            process.wait()

        return process

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
            result = self.runFfmpeg(ffmpeg_command)

    def checkInputFileInterlacing(self, input_file):
        input_file_interlaced = False
        input_file_ffprobe_json = None
        if input_file:
            input_file_ffprobe_json = self.getFfprobeJsonFromFile(input_file)
            if input_file_ffprobe_json:
                for stream in input_file_ffprobe_json.get("streams", []):
                    if stream.get("codec_type") == "video":
                        # If field_order == progressive, set input_file_interlaced = True
                        if stream.get("field_order", "").lower() == "progressive":
                            input_file_interlaced = True
        return input_file_interlaced

    def generateFfmpegTranscodeCommand(self, json_data, input_file=None, output_file=None):
        """
        Converts a JSON dictionary into an FFmpeg command line.
        """
        # Create the base command
        command = ["ffmpeg", "-y"]

        # Replace input/output files with placeholders if none specified
        if not input_file:
            input_file = "[input_file]"
        if not output_file:
            output_file = f"[output_file.{json_data.get('extension', 'mp4')}]"

        command += ["-i", input_file]

        input_file_interlaced = self.checkInputFileInterlacing(input_file)
        video_filter_parts = []

        # Handle scale if video_width/height exist
        width = json_data.get("video_width")
        height = json_data.get("video_height")
        if width and height:
            video_filter_parts.append(f"scale={width}:{height}")

        # # Iterate through the video mapping
        for json_key, (flag, cast_func) in self.video_map.items():
            value = json_data.get(json_key)
            if value is not None:
                value_str = cast_func(value) if cast_func else str(value)
                if value_str.strip():
                    command += [flag, value_str]

        # If input_file_interlaced == False, but the desired field_order is progressive:
        # apply the yadif filter to deinterlace
        video_field_order = json_data.get("video_field_order")
        if input_file_interlaced is False:
            if video_field_order == "progressive":
                print("Input file is Interlaced, and needs de-interlacing")
                video_filter_parts.append("yadif=mode=1")

        # If input_file_interlaced == True, but field_order != progressive
        # we need to re-interlace the file using +ildct+ilme flags
        if input_file_interlaced is True:
            if video_field_order != "progressive":
                print("Input file is Progressive, and needs interlacing")
                command += ["-flags", "+ildct+ilme"]

        # If we have any video filters join them here
        if video_filter_parts:
            command += ["-vf", ",".join(video_filter_parts)]

        # Iterate through audio mapping
        for json_key, (flag, cast_func) in self.audio_map.items():
            value = json_data.get(json_key)
            if value is not None:
                value_str = cast_func(value) if cast_func else str(value)
                if value_str.strip():
                    command += [flag, value_str]

        # Add the metadata tags here
        tags = json_data.get("tags", {})
        for key, value in tags.items():
            command += ["-metadata", f"{key}={value}"]

        # Add the output file
        command += [output_file]

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
                    "Value in JSON1": value1,
                    "Value in JSON2": value2
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
