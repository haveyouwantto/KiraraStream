from email.mime import image
import os
import hashlib
import sqlite3
from flask import Flask, jsonify, send_file
from tinytag import TinyTag
from datetime import datetime
from PIL import Image
import io

app = Flask(__name__)
db = sqlite3.connect('music_database.db')

# Initialize database schema
with db:
    db.execute('''
        CREATE TABLE IF NOT EXISTS songs (
            id TEXT PRIMARY KEY,
            disc INT,
            track INT,
            title TEXT,
            artist TEXT,
            artist_id TEXT,
            duration INT,
            album TEXT,
            album_id TEXT,
            path TEXT,
            modified_date DATETIME,
            cover_hash TEXT
        );
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS albums (
            id TEXT PRIMARY KEY,
            title TEXT,
            artist TEXT,
            artist_id TEXT,
            release_year INT,
            cover_hash TEXT
        );
    ''')

music_dir = '/mnt/sda1/media/Music'
cache_dir = './.cache/'

default_cover_image = os.path.join(cache_dir,'default.jpg')
if not os.path.exists(default_cover_image):

    # Load the image using PIL
    image = Image.open('../frontend/dist/default.png').convert('RGB')

    # Save the resized image to the cache path
    image.save(default_cover_image, format='JPEG')  # You can adjust the format as needed

@app.route('/api/songs')
def get_songs():
    db = sqlite3.connect('music_database.db')
    with db:
        cursor = db.cursor()
        cursor.execute('SELECT * FROM songs')
        rows = cursor.fetchall()

        songs = []
        for row in rows:
            song = {
                "id": row[0],
                "track":row[1],
                "title": row[2],
                "artist": row[3],
                "artist_id": row[4],
                "duration": row[5],
                "album": row[6],
                "album_id": row[7],
                "cover_hash": row[8]
            }
            songs.append(song)
        
        return jsonify(songs)

@app.route('/api/albums')
def get_albums():
    db = sqlite3.connect('music_database.db')
    with db:
        cursor = db.cursor()
        cursor.execute('SELECT * FROM albums')
        rows = cursor.fetchall()

        albums = []
        for row in rows:
            album = {
                "id": row[0],
                "title":row[1],
                "artist": row[2],
                "artist_id": row[3],
                "release_year": row[4],
                "cover_hash": row[5]
            }
            albums.append(album)
        
        return jsonify(albums)
    
@app.route('/api/songs/<album_id>')
def get_songs_by_album(album_id):
    db = sqlite3.connect('music_database.db')
    with db:
        cursor = db.cursor()

        # Get album information
        cursor.execute('SELECT title, artist, artist_id, release_year FROM albums WHERE id = ?', (album_id,))
        album_info = cursor.fetchone()

        if album_info:
            album_title, album_artist, artist_id, release_year = album_info
            cursor.execute('SELECT id, disc, track, title, artist, artist_id, duration, cover_hash FROM songs WHERE album_id = ? ORDER BY track', (album_id,))
            songs = cursor.fetchall()

            response = {
                "album_id": album_id,
                "album_title": album_title,
                "album_artist": album_artist,
                "artist_id":artist_id,
                "release_year": release_year,
                "songs": []
            }

            for song_id, disc, track, title, artist, artist_id, duration, cover_hash in songs:
                song = {
                    "id": song_id,
                    "disc":disc,
                    "track": track,
                    "title": title,
                    "artist": artist,
                    "artist_id":artist_id,
                    "duration": duration,
                    "cover_hash": cover_hash
                }
                response["songs"].append(song)

            return jsonify(response)
        else:
            return "Album not found", 404

@app.route('/api/cover/<hash>')
def get_cover(hash):
    cover_path = os.path.join('.cache', hash[:2], hash)
    if os.path.exists(cover_path):
        return send_file(cover_path, mimetype='image')  # Change mimetype as needed
    return send_file(default_cover_image, mimetype='image')  # Fallback cover image


@app.route('/api/play/<song_id>')
def play_song(song_id):
    db = sqlite3.connect('music_database.db')
    with db:
        cursor = db.cursor()

        # Get the path of the song based on song_id
        cursor.execute('SELECT path FROM songs WHERE id = ?', (song_id,))
        song_path = cursor.fetchone()

        if song_path:
            song_path = song_path[0]
            return send_file(song_path, mimetype='audio')
        else:
            return "Song not found", 404
        
@app.route('/')
def index():
    return send_file('../frontend/dist/index.html')

@app.route('/<file>')
def staticfile(file):
    path = '../frontend/dist/'+file
    if os.path.exists(path):
        return send_file(path)
    else:
        return "404", 404
    

def scan_music_directory(directory):
    with db:
        for root, dirs, files in os.walk(directory):
            for file in files:
                if file.lower().endswith(('.mp3', '.flac', '.wav')):
                    file_path = os.path.join(root, file)
                    # Calculate hash for ID
                    file_hash = hashlib.sha1(file_path.encode()).hexdigest()

                    try:

                        # Get the file's modification date
                        modified_date = datetime.fromtimestamp(os.path.getmtime(file_path))

                        # Check if this file has already been processed
                        cursor = db.cursor()
                        cursor.execute('SELECT id FROM songs WHERE path = ?', (file_path,))
                        existing_song = cursor.fetchone()

                        if existing_song:
                            continue

                        tags = TinyTag.get(file_path, image=True)
                        # Parse file and populate database
                        # You would need to use a library like mutagen to extract metadata
                        # For simplicity, I'm assuming you have functions to parse the metadata
                        song_id = file_hash
                        disc = tags.disc
                        title = tags.title  # Extract from metadata
                        title = title if title else file
                        track = tags.track
                        artist = tags.artist  # Extract from metadata
                        artist_id = hashlib.sha1(artist.encode() if artist else b'').hexdigest()
                        duration = tags.duration  # Example duration in seconds
                        album_title = tags.album.strip()  # Extract from metadata
                        album_id = hashlib.sha1(album_title.encode() if album_title else b'').hexdigest()
                        cover = tags.get_image()    # image data in bytes
                        cover_id = 'default'
                        if cover:
                            cover_id = hashlib.sha1(cover).hexdigest()
                            cover_path = os.path.join(cache_dir, cover_id[:2], cover_id)
                            os.makedirs(os.path.dirname(cover_path), exist_ok=True)

                            # Load the image using PIL
                            image = Image.open(io.BytesIO(cover)).convert('RGB')

                            # Limit the image dimensions to 512x512
                            max_width = 768
                            max_height = 768
                            image.thumbnail((max_width, max_height), Image.ANTIALIAS)

                            # Save the resized image to the cache path
                            image.save(cover_path, format='JPEG')  # You can adjust the format as needed

                        # Check if the album is already in the database
                        cursor = db.cursor()
                        cursor.execute('SELECT * FROM albums WHERE id = ?', (album_id,))
                        album_row = cursor.fetchone()

                        if not album_row:
                            # If album is not present, insert it
                            db.execute('INSERT OR REPLACE INTO albums VALUES (?, ?, ?, ?, ?, ?)',
                                    (album_id, album_title, artist, artist_id, tags.year, cover_id))

                        db.execute('INSERT OR REPLACE INTO songs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                                (song_id, disc, track, title, artist, artist_id, duration, album_title, album_id, file_path, modified_date, cover_id))
                        # You would need to copy/move the cover image to the cache path

                    except Exception as e:
                        print(f'Failed to process {file_path}')
                        print(e)

if __name__ == '__main__':
    scan_music_directory(music_dir)
    app.run(host='0.0.0.0')
