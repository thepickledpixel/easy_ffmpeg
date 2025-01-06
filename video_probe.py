import os
import sys
import json
import shlex
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
        self.video_transcode_settings = {
            "codec_name":       "video_codec",
            "width":            "video_width",
            "height":           "video_height",
            "pix_fmt":          "video_pix_fmt",
            "color_space":      "video_color_space",
            "color_transfer":   "video_color_transfer",
            "color_range":      "video_color_range",
            "color_primaries":  "video_color_primaries",
            "chroma_location":  "video_chroma_location",
            "level":            "video_level",
            "has_b_frames":     "video_has_b_frames",
            "profile":          "video_profile",
            "bit_rate":         "video_bit_rate",
            "time_base":        "video_time_base",
            "r_frame_rate":     "video_frame_rate",
            "field_order":      "video_field_order"
        }
        self.audio_transcode_settings = {
            "codec_name":       "audio_codec",
            "sample_rate":      "audio_sample_rate",
            "channels":         "audio_channels",
            "channel_layout":   "audio_channel_layout",
            "bit_rate":         "audio_bit_rate"
        }
        self.valid_dnx_bitrates = [
            36, 42, 45, 60, 63, 75, 80, 84, 90, 100, 110, 115,
            120, 145, 175, 180, 185, 220, 240, 290, 350, 365,
            390, 440, 730, 880
        ]
        self.prores_profile_map = {
            "Apple ProRes 422 Proxy": "0",
            "Apple ProRes 422 LT":    "1",
            "Apple ProRes 422":       "2",
            "Apple ProRes 422 HQ":    "3",
            "Apple ProRes 4444":      "4",
            "Apple ProRes 4444 XQ":   "5"
        }

    def ffprobeJsonFromFile(self, file_path):
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

    def ffmpegRun(self, command):
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

    def checkOutputFileExtension(self, container_ext, output_file):
        if output_file:
            output_file_no_ext, output_file_ext = os.path.splitext(output_file)
            if output_file_ext.lstrip(".").lower() != container_ext:
                print(
                    f"\nSpecified file extension {output_file_ext}"
                    f" does not match container format of {container_ext}."
                    f" Switching extension to {container_ext}"
                )
                output_file = f"{output_file_no_ext}.{container_ext}"
        return output_file

    def getVideoTranscoder(self, stream):
        encoder = None
        tags = stream.get('tags', None)
        if tags:
            print(tags)
            encoder = tags.get('encoder', None)
        return encoder

    def getTranscodeSettingsFromFile(
        self, file_path, input_file, output_file, run_command=False
    ):
        """
        Uses ffprobe to extract codec/encoder info for the given media file,
        then generates a dictionary of transcode settings and prints a command line.
        """
        ffprobe_json = self.ffprobeJsonFromFile(file_path)
        if not ffprobe_json:
            print(f"\nUnable to get metadata for {file_path}\n")
            return

        _, extension = os.path.splitext(file_path)
        format_info  = ffprobe_json.get("format", {})
        format_tags  = format_info.get("tags", {})
        format_brate = format_info.get("bit_rate")
        container_ext = extension.lstrip(".").lower()
        output_file = self.checkOutputFileExtension(container_ext, output_file)

        transcode_data = {
            "extension": container_ext,
            "tags":      format_tags
        }

        detected_video = None
        detected_audio = None

        for stream in ffprobe_json.get("streams", []):
            codec_type = stream.get("codec_type")

            if codec_type == "video":
                video_codec_name = stream.get("codec_name")
                encoder = self.getVideoTranscoder(stream)
                detected_video   = self.compatibility_matrix.getCodecAttributes(
                    video_codec_name
                )
                if detected_video:
                    self.mergeVideoStreamIntoTranscodeData(
                        stream, transcode_data, format_brate, encoder
                    )

            elif codec_type == "audio":
                audio_codec_name = stream.get("codec_name")
                detected_audio   = self.compatibility_matrix.getCodecAttributes(
                    audio_codec_name
                )
                if detected_audio:
                    self.mergeAudioStreamIntoTranscodeData(
                        stream, transcode_data
                    )

        if not detected_video and not detected_audio:
            print("Could not detect any video or audio settings")
            return

        # Show detected codecs and the final transcode data
        print("\nDetected Codecs:")
        self.compatibility_matrix.jsonToTable(
            [detected_video, detected_audio]
        )

        print("\nTranscode Settings:")
        self.compatibility_matrix.jsonToTable(
            self.reformatJsonForTable(transcode_data)
        )

        # Generate the FFmpeg command and (optionally) run it
        ffmpeg_command = self.ffmpegGenerateTranscodeCommand(
            transcode_data, input_file, output_file
        )
        cmd_string = " ".join(shlex.quote(arg) for arg in ffmpeg_command)

        print("\nffmpeg command line:\n")
        print(cmd_string, "\n")

        if run_command:
            self.ffmpegRun(ffmpeg_command)

    def checkDnxBitrate(self, transcode_data):
        if transcode_data.get("video_codec") == "dnxhd":
            original_rate = transcode_data.get("video_bit_rate", 0)
            new_rate = self.snapDnxBitrate(original_rate)
            transcode_data["video_bit_rate"] = new_rate
            print(f"Snapped DNxHD bitrate from {original_rate} to {new_rate}")
        return transcode_data

    def checkProResProfile(self, transcode_data, encoder):
        if transcode_data.get("video_codec") == "prores":
            profile_code = self.prores_profile_map.get(encoder)
            if profile_code:
                transcode_data["video_profile"] = profile_code
        return transcode_data

    def checkAS11Profile(self, transcode_data):
        if transcode_data.get("video_codec") == "mpeg2video":
            transcode_data["video_profile"] = None
            transcode_data["video_level"] = None
            transcode_data["video_color_transfer"] = None
        return transcode_data

    def snapDnxBitrate(self, input_bitrate):
        """
        Given an input_bitrate (in Mbps), return the closest valid DNxHD bitrate.
        """
        input_bitrate = float(input_bitrate) / 1_000_000.0
        closest_bitrate = min(
            self.valid_dnx_bitrates,
            key=lambda x: abs(x - input_bitrate)
        )
        return f"{closest_bitrate}M"

    def mergeVideoStreamIntoTranscodeData(self, stream, transcode_data, format_brate, encoder):
        """
        Extracts fields from a video stream via self.video_transcode_settings
        and merges them into transcode_data.
        """
        for probe_key, transcode_key in self.video_transcode_settings.items():
            value = stream.get(probe_key, None)
            # Convert has_b_frames to string, if present
            if probe_key == "has_b_frames" and value is not None:
                value = str(value)
            transcode_data[transcode_key] = value

        # If there's no dedicated video_bit_rate, fallback to container bit_rate
        if not transcode_data.get("video_bit_rate"):
            transcode_data["video_bit_rate"] = format_brate

        if transcode_data.get("video_profile"):
            profile_str = transcode_data["video_profile"] or ""
            transcode_data["video_profile"] = profile_str.lower().replace(" ", "")

        transcode_data = self.checkDnxBitrate(transcode_data)
        transcode_data = self.checkProResProfile(transcode_data, encoder)
        transcode_data = self.checkAS11Profile(transcode_data)

    def mergeAudioStreamIntoTranscodeData(self, stream, transcode_data):
        """
        Extracts fields from an audio stream via self.audio_transcode_settings
        and merges them into transcode_data.
        """
        for probe_key, transcode_key in self.audio_transcode_settings.items():
            value = stream.get(probe_key, None)
            transcode_data[transcode_key] = value

    def checkInputFileInterlacing(self, input_file):
        input_file_interlaced = False
        input_file_ffprobe_json = None
        if input_file:
            input_file_ffprobe_json = self.ffprobeJsonFromFile(input_file)
            if input_file_ffprobe_json:
                for stream in input_file_ffprobe_json.get("streams", []):
                    if stream.get("codec_type") == "video":
                        # If field_order == progressive, set input_file_interlaced = True
                        if stream.get("field_order", "").lower() == "progressive":
                            input_file_interlaced = True
        return input_file_interlaced

    def ffmpegGenerateTranscodeCommand(self, json_data, input_file=None, output_file=None):
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

    def compareJsonBlobs(self, json1, json2):
        """
        Compares two JSON objects and displays two tables:
        1. Differences between the objects
        2. Matches (keys/values that are identical)
        """
        differences, matches = self.getJsonComparisons(json1, json2)

        if self.compare_diff:
            print("\nDifferences:")
            if differences:
                self.compatibility_matrix.jsonToTable(differences)
            else:
                print("No differences found!")

        if self.compare_matches:
            print("\nMatches:")
            if matches:
                self.compatibility_matrix.jsonToTable(matches)
            else:
                print("No matches found!")

    def getJsonComparisons(self, json1, json2):
        """
        Recursively compares two JSON objects and returns two lists:
        1. differences (keys/values that differ)
        2. matches (keys/values that match)
        """
        differences = []
        matches = []
        self.compareItems(json1, json2, differences, matches, parentKey="")
        return differences, matches

    def compareItems(self, value1, value2, differences, matches, parentKey=""):
        """
        Main comparison method that checks whether values are dict, list, or scalars.
        Delegates to compareDicts / compareLists if needed, otherwise compares directly.
        """
        if isinstance(value1, dict) and isinstance(value2, dict):
            self.compareDicts(value1, value2, differences, matches, parentKey)
        elif isinstance(value1, list) and isinstance(value2, list):
            self.compareLists(value1, value2, differences, matches, parentKey)
        else:
            # Direct scalar comparison
            if value1 != value2:
                differences.append({
                    "Section": parentKey.rsplit('.', 1)[0] if '.' in parentKey else "",
                    "Setting": parentKey,
                    "Value in JSON1": value1,
                    "Value in JSON2": value2
                })
            else:
                matches.append({
                    "Section": parentKey.rsplit('.', 1)[0] if '.' in parentKey else "",
                    "Setting": parentKey,
                    "Value in JSON1": value1,
                    "Value in JSON2": value2
                })

    def compareDicts(self, dict1, dict2, differences, matches, parentKey=""):
        """
        Compares two dictionaries, iterating through their keys.
        Delegates the actual item comparison to compareItems.
        """
        allKeys = set(dict1.keys()) | set(dict2.keys())
        for key in allKeys:
            fullKey = f"{parentKey}.{key}" if parentKey else key
            val1 = dict1.get(key)
            val2 = dict2.get(key)
            # Compare the items under this key
            self.compareItems(val1, val2, differences, matches, parentKey=fullKey)

    def compareLists(self, list1, list2, differences, matches, parentKey=""):
        """
        Compares two lists by index.
        Delegates the actual item comparison to compareItems.
        """
        maxLen = max(len(list1), len(list2))
        for i in range(maxLen):
            val1 = list1[i] if i < len(list1) else None
            val2 = list2[i] if i < len(list2) else None
            fullKey = f"{parentKey}[{i}]"
            # Compare the items at this index
            self.compareItems(val1, val2, differences, matches, parentKey=fullKey)

    def compareVideoJsonMetadata(
        self, source, dest, column_width=50, json_indent=4
    ):
        if isinstance(source, str):
            source = self.ffprobeJsonFromFile(source)
        if isinstance(dest, str):
            dest = self.ffprobeJsonFromFile(dest)

        if not isinstance(source, dict) or not isinstance(dest, dict):
            print("Could not get file metadata")
            return {}

        self.compareJsonBlobs(source, dest)

    def configureCliArguments(self):
        """
        Parse command line arguments
        """
        parser = argparse.ArgumentParser(
            description=f"Video Probe"
        )
        parser.add_argument(
            'probe_file', metavar='<ProbeFile>', nargs='?',
            help="File path of file to inspect"
        )
        parser.add_argument(
            '--input-file', metavar='<InputFile>', help="File path of file to convert"
        )
        parser.add_argument(
            '--output-file', metavar='<OutputFile>', help="File path of file to output"
        )
        parser.add_argument(
            '--run', action='store_true',
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
        if not self.compatibility_matrix.ffmpegCheckInstalled():
            print("ffmpeg is not installed correctly")
            sys.exit(1)

        args = self.configureCliArguments()

        input_file = None
        output_file = None
        run_command = False

        if args.input_file:
            input_file = args.input_file

        if args.output_file:
            output_file = args.output_file

        if args.run:
            run_command = True

        if args.probe_file:
            if os.path.exists(args.probe_file):
                self.getTranscodeSettingsFromFile(
                    args.probe_file,
                    input_file,
                    output_file,
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
