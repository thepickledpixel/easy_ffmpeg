import subprocess
import os
import json
import argparse

from compatibility_matrix import CompatibilityMatrix

def get_codec_and_encoder(file_path):
    """
    Uses ffprobe to extract codec and encoder information for the given media file.
    """
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
        return

    ffprobe_json = json.loads(result.stdout)
    data = {}

    formatted_data = json.dumps(ffprobe_json, indent=4)
    # print(formatted_data)

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
                    "r_frame_rate": stream.get('r_frame_rate', None),
                    "bit_rate": stream.get('bit_rate', None)
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
                    "video_frame_rate": attributes.get('r_frame_rate', None),
                    "video_bit_rate": attributes.get('bit_rate', None)
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

        ffmpeg_command = generate_ffmpeg_command(transcode_data)

        print("\nffmpeg command line:")
        print(f"\t{ffmpeg_command}\n")

    else:
        print("\nUnable to replicate transcode settings\n")

def generate_ffmpeg_command(json_data):
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
    if json_data.get("video_frame_rate"):
        command += ["-r", json_data.get("video_frame_rate")]
    if json_data.get("video_bit_rate"):
        command += ["-b:v", json_data.get("video_bit_rate")]

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

def configureCliArguments():
    """
    Parse command line arguments
    """
    parser = argparse.ArgumentParser(
        description=f"FF Prober"
    )
    parser.add_argument(
        '--file', metavar='<File>', help="File path of file to inspect"
    )

    return parser.parse_args()


if __name__ == "__main__":
    compatibility_matrix = CompatibilityMatrix()
    args = configureCliArguments()

    if args.file:
        codec_and_encoder = get_codec_and_encoder(args.file)
