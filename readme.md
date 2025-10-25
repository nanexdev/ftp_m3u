# Undertál — MP3 merge & optional FTP upload

Short and simple: this tool merges MP3 files by album into single MP3s, creates .m3u playlists, and can upload the results to an FTP server.

Quick start

 - Run "run_main.bat"

Run the main python script:

 - run "python main.py" in powershell or cmd

What the script does
- Check and counts for MP3s in `music/` and warns if missing/empty.
- Asks for ftp credidentials (skippable)
- Merges the files to a .m3u file
- Attempts to upload the .m3u and the merged .mp3 file (if ftp credidentials are correct)
    If the attempt fails, all of the files will be in "/ready" folder
- Asks to keep or delete ftp credidentials for futher use