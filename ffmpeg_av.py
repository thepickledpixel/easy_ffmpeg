import av
import io
import json
import re
import csv
from io import StringIO
import subprocess

formats = av.formats_available
codecs = av.codecs_available

compatibility_matrix = []


def clean_and_split(text):
    # Remove unwanted characters and split by spaces or /
    return re.split(r'[ /]+', re.sub(r'[()]', '', text.lower()))

def ffmpegOutput(command):
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=True
    )
    return result

def getMuxers():
    """Get a list of available Muxers from the current FFmpeg installation."""
    result = ffmpegOutput(["ffmpeg", "-muxers"])
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

muxers = getMuxers()

# print(muxers)

for format_name in formats:
    try:
        fmt = av.format.ContainerFormat(format_name, mode='w')

        if not fmt.is_output:
            continue

        muxers_list = []

        file_extensions = list(fmt.extensions) if fmt.extensions else []
        file_extensions.sort()

        options = [option.name for option in fmt.options] if fmt.options else []
        options.sort()

        desc_options = [option.name for option in fmt.descriptor.options] if fmt.descriptor.options else []
        desc_options.sort()

        muxer = fmt.descriptor.name

        muxer_split = clean_and_split(muxer)

        for mux in muxers:
            for part in muxer_split:
                if mux['name'].lower() == part:
                    muxers_list.append(mux['name'])

        muxers_list.sort()

        data = {
            "format": format_name,
            "format_name": fmt.name,
            "format_long_name": fmt.long_name,
            "format_options": options,
            "extensions": file_extensions,
            "muxer": muxer,
            "available_muxers": muxers_list,
            "muxer_options": desc_options,
            "output_name": fmt.output.name
        }

        compatibility_matrix.append(data)

    except Exception as e:
        # print(e)
        pass

pretty_settings = json.dumps(compatibility_matrix, indent=4)
print(pretty_settings)
