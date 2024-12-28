import ctypes

# Load FFmpeg libraries
libavformat = ctypes.cdll.LoadLibrary("/usr/local/lib/libavformat.dylib")

# Define the return type and argument types for av_guess_codec
libavformat.av_guess_codec.restype = ctypes.c_int  # Returns an AVCodecID (integer)
libavformat.av_guess_codec.argtypes = [
    ctypes.POINTER(ctypes.c_void_p),  # const AVOutputFormat *
    ctypes.c_char_p,                  # const char *short_name
    ctypes.c_char_p,                  # const char *filename
    ctypes.c_char_p,                  # const char *mime_type
    ctypes.c_int                      # enum AVMediaType
]

# Define AVMediaType enum
AVMEDIA_TYPE_VIDEO = 0
AVMEDIA_TYPE_AUDIO = 1

# Find an output format
libavformat.av_guess_format.restype = ctypes.POINTER(ctypes.c_void_p)
libavformat.av_guess_format.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p]
output_format = libavformat.av_guess_format(b"mp4", None, None)

# Call av_guess_codec
codec_id = libavformat.av_guess_codec(
    output_format,  # AVOutputFormat
    None,           # short_name
    None,           # filename
    None,           # mime_type
    AVMEDIA_TYPE_VIDEO  # media type
)

# Print the result
if codec_id == -1:  # AV_CODEC_ID_NONE
    print("No suitable codec found.")
else:
    print(f"Codec ID: {codec_id}")
