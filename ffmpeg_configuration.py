import subprocess
import json
import re
import csv
from io import StringIO

class EncoderConfiguration:
    def ffmpegOutput(self, command):
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True
        )
        return result

    def getMuxersAndSettings(self):
        muxers = self.getMuxers()
        all_muxers = []

        for muxer in muxers:
            muxer_settings = encoder_config.getMuxerSettings(muxer['name'])
            all_muxers.append(muxer_settings)

        pretty_settings = json.dumps(all_muxers, indent=4)
        print(pretty_settings)

    def getEncodersAndSettings(self):
        encoders = self.getEncoders()
        all_encoders = []

        for encoder in encoders:
            encoder_settings = encoder_config.getEncoderSettings(encoder['name'])
            all_encoders.append(encoder_settings)

        pretty_settings = json.dumps(all_encoders, indent=4)
        print(pretty_settings)

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

    def getMuxerSettings(self, muxer_name):
        """Get a list of available flags/settings for a muxer"""
        result = self.ffmpegOutput(["ffmpeg", "-h", f"muxer={muxer_name}"])

        output = result.stdout
        metadata_regex = re.compile(r"^\s{4}(?P<key>[A-Za-z ]+):\s+(?P<value>.+)$")
        option_regex = re.compile(r"^\s{2}-(?P<name>\S+)\s+<(?P<type>\S+)>\s+(?P<flags>[A-Z.]+)\s+(?P<description>.+)$")
        value_regex = re.compile(r"^\s{5}(?P<value_name>\S+)\s+(?P<value>[\-\d]+)\s+(?P<value_flags>[A-Z.]+)\s+(?P<value_description>.+)$")

        metadata = {}
        options = []
        current_option = None
        for line in output.splitlines():
            metadata_match = metadata_regex.match(line)
            if metadata_match:
                metadata[metadata_match.group("key").strip()] = metadata_match.group("value").strip()

            option_match = option_regex.match(line)
            if option_match:
                if current_option:
                    options.append(current_option)

                current_option = {
                    "name": option_match.group("name"),
                    "type": option_match.group("type"),
                    "flags": option_match.group("flags"),
                    "description": option_match.group("description"),
                    "values": []
                }
            elif current_option:
                value_match = value_regex.match(line)
                if value_match:
                    current_option["values"].append({
                        "name": value_match.group("value_name"),
                        "value": int(value_match.group("value")),
                        "flags": value_match.group("value_flags"),
                        "description": value_match.group("value_description")
                    })

        if current_option:
            options.append(current_option)

        result = {
            "muxer_name": muxer_name,
            "metadata": metadata,
            "options": options
        }

        return result

    def getEncoders(self):
        """Get a list of available Encoders from the current FFmpeg installation"""
        result = self.ffmpegOutput(["ffmpeg", "-encoders"])
        output = result.stdout

        encoders = []

        lines = output.splitlines()
        start_index = next(i for i, line in enumerate(lines) if "------" in line) + 1
        encoder_lines = lines[start_index:]

        reader = csv.reader(encoder_lines, delimiter=' ', skipinitialspace=True)
        for row in reader:
            if len(row) < 3:
                continue

            flags = row[0]
            name = row[1]
            description = ' '.join(row[2:])
            encoders.append({
                "flags": flags,
                "name": name,
                "description": description.strip()
            })

        return encoders

    def getEncoderSettings(self, encoder_name):
        """Get a list of available flags/settings for an encoder"""
        result = self.ffmpegOutput(["ffmpeg", "-h", f"encoder={encoder_name}"])
        output = result.stdout

        # Regular expressions for parsing
        capabilities_regex = re.compile(r"^\s{4}(?P<key>[A-Za-z ]+):\s+(?P<value>.+)$")
        pixel_formats_regex = re.compile(r"^\s{4}Supported pixel formats:\s+(?P<formats>.+)$")
        option_regex = re.compile(r"^\s{2}-(?P<name>\S+)\s+<(?P<type>\S+)>\s+(?P<flags>[A-Z.]+)\s+(?P<description>.+)$")
        value_regex = re.compile(r"^\s{5}(?P<value_name>\S+)\s+(?P<value>[\-\d]+)\s+(?P<value_flags>[A-Z.]+)\s+(?P<value_description>.+)$")

        capabilities = {}
        pixel_formats = []
        options = []
        current_option = None

        for line in output.splitlines():
            # Parse capabilities
            capabilities_match = capabilities_regex.match(line)
            if capabilities_match:
                capabilities[capabilities_match.group("key").strip()] = capabilities_match.group("value").strip()

            # Parse supported pixel formats
            pixel_formats_match = pixel_formats_regex.match(line)
            if pixel_formats_match:
                pixel_formats = [fmt.strip() for fmt in pixel_formats_match.group("formats").split()]

            # Parse options and values
            option_match = option_regex.match(line)
            if option_match:
                if current_option:
                    options.append(current_option)

                current_option = {
                    "name": option_match.group("name"),
                    "type": option_match.group("type"),
                    "flags": option_match.group("flags"),
                    "description": option_match.group("description"),
                    "values": []
                }
            elif current_option:
                value_match = value_regex.match(line)
                if value_match:
                    current_option["values"].append({
                        "name": value_match.group("value_name"),
                        "value": int(value_match.group("value")),
                        "flags": value_match.group("value_flags"),
                        "description": value_match.group("value_description")
                    })

        # Append the last parsed option
        if current_option:
            options.append(current_option)

        # Combine results
        result = {
            "encoder": encoder_name,
            "capabilities": capabilities,
            "pixel_formats": pixel_formats,
            "options": options
        }

        return result

if __name__ == "__main__":

    encoder_config = EncoderConfiguration()
    # encoder_config.getMuxersAndSettings()

    encoder_config.getEncodersAndSettings()
