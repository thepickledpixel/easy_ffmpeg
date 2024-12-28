import subprocess
import json
import re

def get_formats():
    """Get a list of formats from FFmpeg."""
    result = subprocess.run(["ffmpeg", "-formats"], capture_output=True, text=True)
    formats = []
    lines = result.stdout.splitlines()

    # Process lines to extract formats
    for line in lines:
        match = re.match(r"^\s*([DE]+)\s+(\S+)\s+(.+)", line)
        if match:
            direction, name, description = match.groups()
            formats.append({
                "direction": direction,
                "name": name,
                "description": description
            })

    return formats

def get_muxers():
    """Get a list of muxers from FFmpeg."""
    result = subprocess.run(["ffmpeg", "-muxers"], capture_output=True, text=True)
    muxers = []
    lines = result.stdout.splitlines()

    # Process lines to extract muxers
    for line in lines:
        match = re.match(r"^\s*([DE]+)\s+(\S+)\s+(.+)", line)
        if match:
            flag, name, description = match.groups()
            muxers.append({
                "flag": flag,
                "name": name,
                "description": description
            })

    return muxers

def get_encoders():
    """Get a list of encoders from FFmpeg."""
    result = subprocess.run(["ffmpeg", "-encoders"], capture_output=True, text=True)
    encoders = []
    lines = result.stdout.splitlines()

    # Process lines to extract encoders
    for line in lines:
        match = re.match(r"^\s*([VAS]+)\s+(\S+)\s+(.+)", line)
        if match:
            flags, name, description = match.groups()
            encoders.append({
                "flags": flags,
                "name": name,
                "description": description
            })

    return encoders

def correlate_formats_muxers_encoders():
    """Correlate formats, muxers, and encoders."""
    formats = get_formats()
    muxers = get_muxers()
    encoders = get_encoders()

    # Infer relationships (basic example, adjust for your needs)
    relationships = []
    for fmt in formats:
        for mux in muxers:
            if fmt["name"] == mux["name"]:  # Match format name with muxer name
                compatible_encoders = [
                    enc for enc in encoders if mux["name"] in enc["description"]
                ]
                relationships.append({
                    "format": fmt,
                    "muxer": mux,
                    "encoders": compatible_encoders
                })

    return relationships

if __name__ == "__main__":
    relationships = correlate_formats_muxers_encoders()

    pretty_settings = json.dumps(relationships, indent=4)

    print(pretty_settings)
