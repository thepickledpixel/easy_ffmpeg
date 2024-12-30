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
            "-v", "error",  # Suppress unnecessary output
            "-show_format",  # Show format-level metadata
            "-show_streams",  # Show stream-level metadata for all streams
            "-of", "json",  # Output in JSON format
            file_path
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)

        formatted_data = json.dumps(data, indent=4)

        _, extension = os.path.splitext(file_path)

        search_extension = None
        search_audio_codec = None
        search_video_codec = None

        for stream in data['streams']:
            search_extension = extension.replace('.', '')
            data = {
                "index": stream['index'],
                "extension": extension.replace('.', ''),
                "codec_name": stream['codec_name'],
                "codec_type": stream['codec_type']
            }
            if stream['codec_type'] == "audio":
                search_audio_codec = stream['codec_name']
                data.update({
                    "sample_rate": stream['sample_rate'],
                    "channels": stream['channels'],
                    "channel_layout": stream['channel_layout'],
                    "bit_rate": stream['bit_rate']
                })
            if stream['codec_type'] == "video":
                search_video_codec = stream['codec_name']
                data.update({
                    "width": stream['width'],
                    "height": stream['height'],
                    "pix_fmt": stream['pix_fmt'],
                    "r_frame_rate": stream['r_frame_rate'],
                    "bit_rate": stream['bit_rate']
                })

            formatted_data = json.dumps(data, indent=4)

            print(formatted_data)

        compatible_encoders = compatibility_matrix.searchExtensionsAttributesJson(
            video_codec=search_video_codec,
            audio_codec=search_audio_codec,
            extension=search_extension
        )

        if len(compatible_encoders) > 0:
            compatibility_matrix.displayEncoderAttributes(
                compatible_encoders
            )

    except subprocess.CalledProcessError as e:
        print(f"Error running ffprobe: {e.stderr}")
        return None
    except json.JSONDecodeError:
        print("Error decoding ffprobe output")
        return None

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

    args = parser.parse_args()

    return parser.parse_args()


if __name__ == "__main__":
    compatibility_matrix = CompatibilityMatrix()
    args = configureCliArguments()

    if args.file:
        codec_and_encoder = get_codec_and_encoder(args.file)
