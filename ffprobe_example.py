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
            search_extension = extension.replace('.', '').lower()
            data = {
                "index": stream.get('index', None),
                "extension": extension.replace('.', ''),
                "codec_name": stream.get('codec_name', None),
                "codec_type": stream.get('codec_type', None)
            }
            if stream.get('codec_type') == "audio":
                search_audio_codec = stream.get('codec_name', None)
                data.update({
                    "sample_rate": stream.get('sample_rate', None),
                    "channels": stream.get('channels', None),
                    "channel_layout": stream.get('channel_layout', None),
                    "bit_rate": stream.get('bit_rate', None)
                })
            if stream.get('codec_type') == "video":
                search_video_codec = stream.get('codec_name', None)
                data.update({
                    "width": stream.get('width', None),
                    "height": stream.get('height', None),
                    "pix_fmt": stream.get('pix_fmt', None),
                    "r_frame_rate": stream.get('r_frame_rate', None),
                    "bit_rate": stream.get('bit_rate', None)
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
