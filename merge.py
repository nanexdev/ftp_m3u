import os
import subprocess
import logging
import argparse
import shutil
import sys
from datetime import datetime
from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3

def find_ffmpeg():
    """Find ffmpeg executable.

    Order:
    1. If running from PyInstaller bundle, look under _MEIPASS/ffmpeg/ffmpeg.exe
    2. shutil.which('ffmpeg') on PATH
    Returns full path or None.
    """
    # 1) bundled with PyInstaller
    if getattr(sys, 'frozen', False):
        bundle_dir = getattr(sys, '_MEIPASS', None)
        if bundle_dir:
            candidate = os.path.join(bundle_dir, 'ffmpeg', 'ffmpeg.exe')
            if os.path.exists(candidate):
                return candidate
    # 2) system PATH
    path = shutil.which('ffmpeg')
    return path

ROOT = os.path.dirname(os.path.abspath(__file__))
MUSIC_DIR = os.path.join(ROOT, "music")
MERGED_DIR = os.path.join(ROOT, "merged")
CONFIG_PATH = os.path.join(ROOT, "ftp_upload.txt")

# --- Logging setup (create logs dir immediately so file handler can open) ---
LOGS_DIR = os.path.join(ROOT, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)
_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
_log_file = os.path.join(LOGS_DIR, f"merge_{_timestamp}.log")

logger = logging.getLogger(__name__)
if not logging.root.handlers:
    fh = logging.FileHandler(_log_file, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh.setFormatter(fmt)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logging.basicConfig(level=logging.INFO, handlers=[fh, ch])
else:
    logger = logging.getLogger(__name__)

def get_metadata(filepath):
    try:
        audio = MP3(filepath, ID3=EasyID3)
        artist = audio.get("artist", ["Unknown Artist"])[0]
        title = audio.get("title", ["Unknown Title"])[0]
        album = audio.get("album", [None])[0]
        return artist, title, album
    except Exception as e:
        logger.exception("Error reading metadata from %s: %s", filepath, e)
        return "Unknown Artist", "Unknown Title", None

def merge_album(album_name, filepaths, ffmpeg_path):
    list_path = os.path.join(MERGED_DIR, f"{album_name}_list.txt")
    with open(list_path, "w", encoding="utf-8") as f:
        for path in filepaths:
            f.write(f"file '{path.replace('\\', '/')}'\n")

    sanitized_name = album_name.replace(" ", "_") if album_name else "Unknown_Album"
    output_path = os.path.join(MERGED_DIR, f"{sanitized_name}.mp3")

    cmd = [ffmpeg_path, "-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy", output_path]
    subprocess.run(cmd)
    os.remove(list_path)

    # Apply metadata from first track
    artist, _, _ = get_metadata(filepaths[0])
    try:
        audio = MP3(output_path, ID3=EasyID3)
        audio["artist"] = artist
        audio["album"] = album_name
        audio.save()
        logger.info("Merged album: %s → %s", album_name, output_path)
    except Exception as e:
        logger.exception("Failed to tag %s: %s", output_path, e)

def main():
    parser = argparse.ArgumentParser(description="Merge music into albums")
    parser.add_argument("-d", "--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        for h in logging.getLogger().handlers:
            h.setLevel(logging.DEBUG)
        logger.debug("Debug logging enabled")

    # ensure expected directories exist
    for name, path in (("music", MUSIC_DIR), ("merged", MERGED_DIR), ("logs", LOGS_DIR)):
        if os.path.isdir(path):
            logger.debug("Directory exists: %s -> %s", name, path)
        else:
            try:
                os.makedirs(path, exist_ok=True)
                logger.info("Created directory: %s -> %s", name, path)
            except Exception as e:
                logger.exception("Failed to create directory %s (%s): %s", name, path, e)

    # Check ffmpeg is available (bundled or on PATH)
    ffmpeg_path = find_ffmpeg()
    if not ffmpeg_path:
        logger.error("ffmpeg not found (bundled or on PATH). Please install ffmpeg or include it in the build.")
        sys.exit(2)

    albums = {}
    no_album = []

    for filename in os.listdir(MUSIC_DIR):
        if filename.lower().endswith(".mp3"):
            filepath = os.path.join(MUSIC_DIR, filename)
            artist, title, album = get_metadata(filepath)
            if album:
                albums.setdefault(album, []).append(filepath)
            else:
                print(f"\n No album found for: {filename}")
                print(f"   Artist: {artist}, Title: {title}")
                include = input("   Include in 'Unknown Album'? (y/n): ").strip().lower()
                if include == "y":
                    no_album.append(filepath)

    for album, files in albums.items():
        merge_album(album, files, ffmpeg_path)

    if no_album:
        merge_album("Unknown Album", no_album, ffmpeg_path)

if __name__ == "__main__":
    main()

