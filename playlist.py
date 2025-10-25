import os
import shutil
import logging
import argparse
from datetime import datetime
from ftplib import FTP, error_perm
from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3


# === Load FTP config ===
def load_ftp_config(config_path):
    config = {}
    with open(config_path, "r", encoding="utf-8") as f:
        for line in f:
            if "=" in line:
                key, value = line.strip().split("=", 1)
                config[key.strip()] = value.strip()
    return config

# === Paths ===
ROOT = os.path.dirname(os.path.abspath(__file__))
MERGED_DIR = os.path.join(ROOT, "merged")
READY_DIR = os.path.join(ROOT, "ready")
MUSIC_DIR = os.path.join(ROOT, "music")
CONFIG_PATH = os.path.join(ROOT, "ftp_upload.txt")
os.makedirs(MERGED_DIR, exist_ok=True)
os.makedirs(READY_DIR, exist_ok=True)
os.makedirs(MUSIC_DIR, exist_ok=True)

# === Logging setup ===
LOGS_DIR = os.path.join(ROOT, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)
_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
_log_file = os.path.join(LOGS_DIR, f"upload_{_timestamp}.log")

logger = logging.getLogger(__name__)
if not logging.root.handlers:
    # configure basic logging to file + console
    file_handler = logging.FileHandler(_log_file, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    file_handler.setFormatter(fmt)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(fmt)

    logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler])
else:
    # If logging already configured by external code, just get logger
    logger = logging.getLogger(__name__)


# === Metadata and Upload ===
def get_album(filepath):
    try:
        audio = MP3(filepath, ID3=EasyID3)
        return audio.get("album", [None])[0]
    except Exception:
        logger.exception("Failed to read album metadata for %s", filepath)
        return None

def move_to_ready(filepath, filename):
    target_path = os.path.join(READY_DIR, filename)
    # ensure destination directory exists (defensive)
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    shutil.copy2(filepath, target_path)
    logger.info("Created music file: %s", filename)
    return target_path

def try_ftp_upload(ftp, filepath, filename):
    try:
        with open(filepath, "rb") as f:
            ftp.storbinary(f"STOR " + filename, f)
        logger.info("Uploaded: %s", filename)
        return True
    except Exception as e:
        logger.exception("FTP upload failed for %s: %s", filename, e)
        return False

def create_m3u(filename, playlist_name, use_web_url, web_base_url):
    playlist_path = os.path.join(READY_DIR, playlist_name)
    # ensure ready directory exists before writing playlist
    os.makedirs(os.path.dirname(playlist_path), exist_ok=True)
    with open(playlist_path, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        if use_web_url:
            f.write(f"{web_base_url}/{filename}\n")
        else:
            f.write(f"{filename}\n")
    logger.info("Created playlist: %s", playlist_name)
    return playlist_path

# === Main ===
def main():
    parser = argparse.ArgumentParser(description="Create playlists and optionally upload via FTP")
    parser.add_argument("--skip-ftp", action="store_true", help="Skip FTP upload")
    parser.add_argument("-d", "--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    # adjust logging if debug requested
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        for h in logging.getLogger().handlers:
            h.setLevel(logging.DEBUG)
        logger.debug("Debug logging enabled")

    ftp = None
    config = None
    if args.skip_ftp:
        logger.info("Skipping FTP as requested (--skip-ftp)")
    else:
        if os.path.exists(CONFIG_PATH):
            try:
                config = load_ftp_config(CONFIG_PATH)
                ftp = FTP(config.get("host", ""))
                ftp.login(config.get("user", ""), config.get("pass", ""))
                ftp.cwd(config.get("dir", ""))
            except Exception as e:
                logger.exception("FTP connection failed: %s", e)
                ftp = None
        else:
            logger.info("FTP config not found at %s, skipping FTP", CONFIG_PATH)

    for filename in os.listdir(MERGED_DIR):
        if filename.lower().endswith(".mp3"):
            filepath = os.path.join(MERGED_DIR, filename)
            album = get_album(filepath)
            sanitized_name = os.path.splitext(filename)[0]
            playlist_name = f"{sanitized_name}.m3u"

            # Move MP3 to /ready
            ready_path = move_to_ready(filepath, filename)

            # Try FTP upload
            uploaded = False
            if ftp:
                uploaded = try_ftp_upload(ftp, ready_path, filename)

            # Create playlist
            playlist_path = create_m3u(
                filename,
                playlist_name,
                use_web_url=uploaded,
                web_base_url=(config.get("url", "") if config else "")
            )

            # Upload playlist if FTP is working
            if ftp and uploaded:
                try_ftp_upload(ftp, playlist_path, playlist_name)

    if ftp:
        ftp.quit()
        logger.info("FTP session closed.")

if __name__ == "__main__":
    main()
