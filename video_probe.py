import subprocess
import os
import json
import argparse
from tabulate import tabulate
import textwrap

from deepdiff import DeepDiff
from compatibility_matrix import CompatibilityMatrix

class VideoProbe:
    def __init__(self):
        self.no_value = None

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
            print(e)
            return None
        return json.loads(result.stdout)


    def getTranscodeSettingsFromFile(self, file_path):
        """
        Uses ffprobe to extract codec and encoder information for the given media file.
        """
        ffprobe_json = self.getFfprobeJsonFromFile(file_path)

        data = {}

        formatted_data = json.dumps(ffprobe_json, indent=4)
        # print(formatted_data)
        # quit()

        _, extension = os.path.splitext(file_path)

        search_extension = None
        search_audio_codec = None
        search_video_codec = None

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
                "extension": search_extension
            }

        })

        formatted_data = json.dumps(data, indent=4)

        compatible_encoders = compatibility_matrix.searchExtensionsAttributesJson(
            video_codec=search_video_codec,
            audio_codec=search_audio_codec,
            extension=search_extension
        )

        transcode_data = {}

        if len(compatible_encoders) > 0:
            compatibility_matrix.displayEncoderAttributes(
                compatible_encoders
            )

            transcode_data.update({
                "encoder": compatible_encoders[0],
                "extension": data['container']['extension']
            })

            for channel, attributes in data.items():

                if attributes.get('codec_type') == "video":
                    transcode_data.update({
                        "video_codec": attributes.get('codec_name', None),
                        "video_width": attributes.get('width', None),
                        "video_height": attributes.get('height', None),
                        "video_pix_fmt": attributes.get('pix_fmt', None),
                        "video_color_space": attributes.get('color_space', None),
                        "video_color_transfer": attributes.get('color_transfer', None),
                        "video_color_range": attributes.get('color_range', None),
                        "video_profile": attributes.get('profile', "").lower().replace(" ", ""),
                        "video_color_primaries": attributes.get('color_primaries', None),
                        "video_frame_rate": attributes.get('r_frame_rate', None),
                        "video_bit_rate": attributes.get('bit_rate', None),
                        "video_time_base": attributes.get('time_base', None),
                        "video_chroma_location": attributes.get('chroma_location', None),
                        "video_has_b_frames": str(attributes.get('has_b_frames', None)),
                        "video_level": str(attributes.get('level', None)),
                        "video_field_order": attributes.get('field_order', None)
                    })
                if attributes.get('codec_type') == "audio":
                    transcode_data.update({
                        "audio_codec": attributes.get('codec_name', None),
                        "audio_sample_rate": attributes.get('sample_rate', None),
                        "audio_channels": attributes.get('channels', None),
                        "audio_channel_layout": attributes.get('channel_layout', None),
                        "audio_bit_rate": attributes.get('bit_rate', None)
                    })

            print("\nTranscode Settings:")
            for item, value in transcode_data.items():
                print(f"\t{item}: {value}")

            ffmpeg_command = self.generateFfmpegTranscodeCommand(transcode_data)

            print("\nffmpeg command line:")
            print(f"\t{ffmpeg_command}\n")

        else:
            print("\nUnable to replicate transcode settings\n")

    def generateFfmpegTranscodeCommand(self, json_data):
        """
        Converts a JSON dictionary into an FFmpeg command line.
        """
        # Base command
        command = ["ffmpeg", "-y"]

        # Input file (example, replace as needed)
        input_file = "input_file.mp4"
        output_file = f"output_file.{json_data.get('extension', 'mp4')}"

        command += ["-i", input_file]

        # Video settings
        if json_data.get("video_codec"):
            command += ["-c:v", json_data.get("video_codec")]
        if json_data.get("video_width") and json_data.get("video_height"):
            command += ["-vf", f"scale={json_data.get('video_width')}:{json_data.get('video_height')}"]
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

        # Input and output files
        command.append(output_file)

        # Return as a command string
        return " ".join(command)

    def formatJson(self, value, indent=4):
        """
        Formats a JSON-like object with proper indentation.
        """
        if isinstance(value, (dict, list)):
            return json.dumps(value, indent=indent)
        return str(value)

    def generateTabulatedDiff(self, diff, column_width=50, json_indent=4):
        """
        Generates a clean, tabulated representation of JSON differences with formatted JSON.
        """
        table_data = []

        # Process values_changed
        if "values_changed" in diff:
            for key, change in diff["values_changed"].items():
                table_data.append([
                    key,  # Path
                    self.formatJson(change["old_value"], indent=json_indent),
                    self.formatJson(change["new_value"], indent=json_indent)
                ])

        # Process iterable_item_removed
        if "iterable_item_removed" in diff:
            for key, removed in diff["iterable_item_removed"].items():
                table_data.append([
                    key,
                    self.formatJson(removed, indent=json_indent),
                    "Removed"
                ])

        # Process iterable_item_added
        if "iterable_item_added" in diff:
            for key, added in diff["iterable_item_added"].items():
                table_data.append([
                    key,
                    "Added",
                    self.formatJson(added, indent=json_indent)
                ])

        # Generate a tabulated table
        table = tabulate(
            table_data,
            headers=["Path", "Old Value", "New Value"],
            tablefmt="fancy_grid",
            numalign="left",
            stralign="left",
        )
        return table

    def compareVideoJsonMetadata(self, source, dest, column_width=50, json_indent=4):
        # Load JSON if paths are provided
        if isinstance(source, str):
            source = self.getFfprobeJsonFromFile(source)
        if isinstance(dest, str):
            dest = self.getFfprobeJsonFromFile(dest)

        # Ensure valid JSON objects
        if not isinstance(source, dict) or not isinstance(dest, dict):
            print("Could not get file metadata")
            return {}

        # Compare using DeepDiff
        diff = DeepDiff(source, dest, ignore_order=True)

        # Generate tabulated output with JSON formatting
        diff_table = self.generateTabulatedDiff(diff, column_width=column_width, json_indent=json_indent)
        print(diff_table)

    def configureCliArguments(self):
        """
        Parse command line arguments
        """
        parser = argparse.ArgumentParser(
            description=f"FF Prober"
        )
        parser.add_argument(
            '--file', metavar='<File>', help="File path of file to inspect"
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

        args = parser.parse_args()

        if args.compare and not (args.source and args.dest):
            parser.error("--compare requires --source & --dest file paths")

        return args


if __name__ == "__main__":
    compatibility_matrix = CompatibilityMatrix()
    video_probe = VideoProbe()

    args = video_probe.configureCliArguments()

    if args.file:
        video_probe.getTranscodeSettingsFromFile(args.file)

    if args.compare and (args.source or args.dest):
        video_probe.compareVideoJsonMetadata(args.source, args.dest)
