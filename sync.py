import os
import json
import yt_dlp

# Configuration from Environment
MUSIC_DIR = os.environ.get("MUSIC_DIR", ".")
YOUTUBE_PLAYLIST_URL = os.environ.get("YOUTUBE_PLAYLIST_URL")
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY") # e.g. "owner/repo"

def main():
    if not YOUTUBE_PLAYLIST_URL or not GITHUB_REPOSITORY:
        print("Missing required environment variables (YOUTUBE_PLAYLIST_URL or GITHUB_REPOSITORY).")
        return

    # Create directories if they do not exist
    songs_dir = os.path.join(MUSIC_DIR, "songs")
    os.makedirs(songs_dir, exist_ok=True)

    # Load or initialize manifest.json
    manifest_path = os.path.join(MUSIC_DIR, "manifest.json")
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
        except Exception as e:
            print(f"Error loading manifest: {e}. Resetting manifest.")
            manifest = {"tracks": []}
    else:
        manifest = {"tracks": []}

    existing_tracks = {track['videoId']: track for track in manifest['tracks']}
    updated_tracks = []

    print(f"Fetching playlist from {YOUTUBE_PLAYLIST_URL}")
    cookie_file = "cookies.txt"
    if not os.path.exists(cookie_file) and os.path.exists("yt_cookies.txt"):
        cookie_file = "yt_cookies.txt"
    ydl_opts_flat = {'extract_flat': True, 'quiet': True, 'ignoreerrors': True}
    if os.path.exists(cookie_file):
        print(f"Using cookies from {cookie_file} for playlist fetching.")
        ydl_opts_flat['cookiefile'] = cookie_file
    playlist_info = None
    try:
        with yt_dlp.YoutubeDL(ydl_opts_flat) as ydl:
            playlist_info = ydl.extract_info(YOUTUBE_PLAYLIST_URL, download=False)
    except Exception as e_flat:
        if os.path.exists(cookie_file):
            print(f"Playlist fetch with cookies failed: {e_flat}. Retrying WITHOUT cookies...")
            ydl_opts_flat_nocookie = ydl_opts_flat.copy()
            ydl_opts_flat_nocookie.pop('cookiefile', None)
            try:
                with yt_dlp.YoutubeDL(ydl_opts_flat_nocookie) as ydl_nocookie:
                    playlist_info = ydl_nocookie.extract_info(YOUTUBE_PLAYLIST_URL, download=False)
            except Exception as e_nocookie:
                print(f"Playlist fetch without cookies also failed: {e_nocookie}")
                return
        else:
            print(f"Failed to fetch playlist info: {e_flat}")
            return

    if not playlist_info:
        # Fallback if returned empty but no exception
        if os.path.exists(cookie_file):
            print("Playlist fetch with cookies returned empty. Retrying WITHOUT cookies...")
            ydl_opts_flat_nocookie = ydl_opts_flat.copy()
            ydl_opts_flat_nocookie.pop('cookiefile', None)
            with yt_dlp.YoutubeDL(ydl_opts_flat_nocookie) as ydl_nocookie:
                playlist_info = ydl_nocookie.extract_info(YOUTUBE_PLAYLIST_URL, download=False)
        
        if not playlist_info:
            print("Failed to retrieve playlist info (returned empty).")
            return

    entries = playlist_info.get('entries', [])

    new_tracks_added = False

    for entry in entries:
        if not entry:
            continue
        video_id = entry.get('id')
        title = entry.get('title', 'Unknown Title')
        
        if not video_id:
            continue

        mp3_file_path = os.path.join(songs_dir, f"{video_id}.mp3")
        if video_id in existing_tracks and os.path.exists(mp3_file_path):
            # Keep existing track info in its current playlist position
            updated_tracks.append(existing_tracks[video_id])
            continue

        print(f"Downloading {title} ({video_id})...")
        try:
            url = f"https://www.youtube.com/watch?v={video_id}"
            out_template = os.path.join(songs_dir, f"{video_id}.%(ext)s")
            
            ydl_opts = {
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '128',
                }],
                'outtmpl': out_template,
                'quiet': False,
                'no_warnings': True
            }
            if os.path.exists(cookie_file):
                ydl_opts['cookiefile'] = cookie_file
            
            info = None
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl_download:
                    info = ydl_download.extract_info(url, download=True)
            except Exception as e_download:
                if os.path.exists(cookie_file):
                    print(f"Download with cookies failed: {e_download}. Retrying WITHOUT cookies...")
                    ydl_opts_nocookie = ydl_opts.copy()
                    ydl_opts_nocookie.pop('cookiefile', None)
                    with yt_dlp.YoutubeDL(ydl_opts_nocookie) as ydl_download_nocookie:
                        info = ydl_download_nocookie.extract_info(url, download=True)
                else:
                    raise e_download
            
            title = info.get('title', title)
            artist = info.get('uploader') or info.get('artist') or info.get('creator') or 'Unknown Artist'
            duration = info.get('duration', 0)
            
            track_info = {
                "videoId": video_id,
                "title": title,
                "author": artist,
                "duration": duration,
                "url": f"https://cdn.jsdelivr.net/gh/{GITHUB_REPOSITORY}/songs/{video_id}.mp3",
                "thumbnail": f"https://img.youtube.com/vi/{video_id}/default.jpg"
            }
            updated_tracks.append(track_info)
            new_tracks_added = True
            
        except Exception as e:
            print(f"Failed to process {video_id}: {e}")

    # Detect track order changes or track deletions
    old_video_ids = [t['videoId'] for t in manifest['tracks']]
    new_video_ids = [t['videoId'] for t in updated_tracks]
    if old_video_ids != new_video_ids:
        new_tracks_added = True

    # Clean up orphaned mp3 files (songs deleted from the playlist)
    active_video_ids = set(new_video_ids)
    if os.path.exists(songs_dir):
        for filename in os.listdir(songs_dir):
            if filename.endswith(".mp3"):
                v_id = filename[:-4]
                if v_id not in active_video_ids:
                    file_path = os.path.join(songs_dir, filename)
                    print(f"Removing orphaned song file: {filename}")
                    try:
                        os.remove(file_path)
                        new_tracks_added = True
                    except Exception as e:
                        print(f"Failed to remove {filename}: {e}")

    if new_tracks_added:
        manifest['tracks'] = updated_tracks
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2)
        print("Manifest updated successfully.")
    else:
        print("No new tracks or track order updates. Manifest unchanged.")

if __name__ == "__main__":
    main()
