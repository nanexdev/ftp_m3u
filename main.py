import os
import sys
import logging
import argparse
import subprocess
from datetime import datetime


ROOT = os.path.dirname(os.path.abspath(__file__))
MUSIC_DIR = os.path.join(ROOT, "music")
MERGED_DIR = os.path.join(ROOT, "merged")
READY_DIR = os.path.join(ROOT, "ready")
LOGS_DIR = os.path.join(ROOT, "logs")
CONFIG_PATH = os.path.join(ROOT, "ftp_upload.txt")


def setup_logging(debug: bool = False):
    os.makedirs(LOGS_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(LOGS_DIR, f"main_{timestamp}.log")

    root = logging.getLogger()
    if not root.handlers:
        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(fmt)
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        level = logging.DEBUG if debug else logging.INFO
        fh.setLevel(level)
        ch.setLevel(level)
        logging.basicConfig(level=level, handlers=[fh, ch])
    else:
        # adjust levels if handlers already exist
        level = logging.DEBUG if debug else logging.INFO
        root.setLevel(level)
        for h in root.handlers:
            h.setLevel(level)

    logger = logging.getLogger(__name__)
    logger.debug("Logging initialized (debug=%s)", debug)
    return logger


def count_mp3s():
    if not os.path.isdir(MUSIC_DIR):
        return None, 0
    files = [f for f in os.listdir(MUSIC_DIR) if f.lower().endswith('.mp3')]
    return True, len(files)


def prompt_ftp_and_save(logger):
    use_ftp = input("Do you want to configure FTP upload? (y/n): ").strip().lower() == 'y'
    if not use_ftp:
        logger.info("User chose not to configure FTP.")
        return False

    host = input("FTP host: ").strip()
    user = input("FTP user: ").strip()
    passwd = input("FTP pass: ").strip()
    directory = input("FTP remote dir: ").strip()
    url = input("Web base URL (optional, used in playlists): ").strip()

    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            f.write(f"host={host}\n")
            f.write(f"user={user}\n")
            f.write(f"pass={passwd}\n")
            f.write(f"dir={directory}\n")
            if url:
                f.write(f"url={url}\n")
        logger.info("Saved FTP configuration to %s", CONFIG_PATH)
        return True
    except Exception:
        logger.exception("Failed to save FTP configuration to %s", CONFIG_PATH)
        return False


def read_ftp_config():
    """Read ftp_upload.txt and return (config_dict, is_valid)

    is_valid is True when host,user,pass,dir are present and non-empty.
    """
    config = {}
    if not os.path.exists(CONFIG_PATH):
        return config, False
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    config[k.strip()] = v.strip()
        required = (config.get('host'), config.get('user'), config.get('pass'), config.get('dir'))
        is_valid = all(required) and all(s.strip() for s in required)
        return config, bool(is_valid)
    except Exception:
        return config, False
    


def run_subprocess(script_path, logger, extra_args=None):
    """Run another Python script as a subprocess and capture output."""
    cmd = [sys.executable, script_path]
    if extra_args:
        cmd.extend(extra_args)
    logger.info("Running: %s", ' '.join(cmd))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        stdout = proc.stdout or ''
        stderr = proc.stderr or ''
        if proc.returncode != 0:
            logger.error("Script %s exited with code %s", script_path, proc.returncode)
            logger.error("--- STDOUT ---\n%s", stdout)
            logger.error("--- STDERR ---\n%s", stderr)
            return False, stdout, stderr, proc.returncode
        else:
            logger.info("Script %s completed successfully", script_path)
            logger.debug("--- STDOUT ---\n%s", stdout)
            logger.debug("--- STDERR ---\n%s", stderr)
            return True, stdout, stderr, proc.returncode
    except Exception:
        logger.exception("Failed to run subprocess %s", script_path)
        return False, '', 'exception', -1


def ensure_dirs(logger):
    for name, path in (("music", MUSIC_DIR), ("merged", MERGED_DIR), ("ready", READY_DIR), ("logs", LOGS_DIR)):
        if os.path.isdir(path):
            logger.debug("Directory exists: %s -> %s", name, path)
        else:
            try:
                os.makedirs(path, exist_ok=True)
                logger.info("Created directory: %s -> %s", name, path)
            except Exception:
                logger.exception("Failed to create directory %s -> %s", name, path)


def main():
    parser = argparse.ArgumentParser(description="Runner: count mp3s, optionally configure FTP, run merge and playlist scripts")
    parser.add_argument("-d", "--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--reconfigure", action="store_true", help="Force reconfigure FTP even if ftp_upload.txt exists and looks valid")
    args = parser.parse_args()

    logger = setup_logging(debug=args.debug)

    # Ensure directories exist (creates if missing)
    ensure_dirs(logger)

    exists, count = count_mp3s()
    if exists is None:
        logger.warning("Music directory does not exist: %s", MUSIC_DIR)
        print(f"Warning: music directory missing: {MUSIC_DIR}")
    else:
        print(f"Found {count} mp3 file(s) in {MUSIC_DIR}")
        if count == 0:
            logger.warning("No mp3 files found in %s", MUSIC_DIR)
            print("Warning: no mp3 files found.")

    # Read existing FTP config (if any) and decide whether to prompt
    try:
        config, valid = read_ftp_config()
    except Exception:
        logger.exception("Failed to read existing FTP config")
        config, valid = {}, False

    if valid and not args.reconfigure:
        logger.info("Found valid FTP config in %s — skipping interactive prompt.", CONFIG_PATH)
        configured = True
    else:
        try:
            configured = prompt_ftp_and_save(logger)
            # refresh config after saving
            config, valid = read_ftp_config()
        except Exception:
            logger.exception("Error during FTP prompt")
            configured = False

    # Run merge.py
    merge_script = os.path.join(ROOT, 'merge.py')
    merge_args = []
    if args.debug:
        merge_args.append('--debug')
    ok, mout, merr, mcode = run_subprocess(merge_script, logger, extra_args=merge_args)
    if not ok:
        print(f"merge.py failed (code {mcode}). Check logs for details.")
        return
    else:
        print("merge.py completed successfully.")

    # Run playlist.py
    playlist_script = os.path.join(ROOT, 'playlist.py')
    playlist_args = []
    if args.debug:
        playlist_args.append('--debug')
    # if user didn't configure FTP, tell playlist to skip FTP
    if not configured:
        playlist_args.append('--skip-ftp')
    ok2, pout, perr, pcode = run_subprocess(playlist_script, logger, extra_args=playlist_args)
    if not ok2:
        print(f"playlist.py failed (code {pcode}). Check logs for details.")
        return
    else:
        print("playlist.py completed successfully.")

    # Summarize outputs
    logger.info("merge.py stdout:\n%s", mout)
    logger.info("merge.py stderr:\n%s", merr)
    logger.info("playlist.py stdout:\n%s", pout)
    logger.info("playlist.py stderr:\n%s", perr)

    # Optionally offer to delete stored FTP credentials
    try:
        if os.path.exists(CONFIG_PATH):
            resp = input("Do you want to delete saved FTP config (ftp_upload.txt)? (y/n): ").strip().lower()
            if resp == 'y':
                try:
                    os.remove(CONFIG_PATH)
                    logger.info("Deleted %s", CONFIG_PATH)
                    print("Deleted ftp_upload.txt")
                except Exception:
                    logger.exception("Failed to delete %s", CONFIG_PATH)
    except Exception:
        logger.exception("Error while asking to delete ftp config")

    try:
        input("\nPress Enter to exit...")
    except Exception:
        pass


if __name__ == '__main__':
    main()
