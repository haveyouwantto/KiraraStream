from email.mime import image
import os
import hashlib
import sqlite3
from flask import Flask, jsonify, send_file
from tinytag import TinyTag
from datetime import datetime
from PIL import Image
import io
import sys
import json

from lrcparser import LrcParser
import traceback

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
        cover_hash TEXT,
        format TEXT,
        bit_depth INT,
        bitrate INT,
        sample_rate INT,
        has_lyrics BOOLEAN
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

cache_dir = './.cache/'

default_cover_image = os.path.join(cache_dir,'default.jpg')
if not os.path.exists(default_cover_image):

    # Load the image using PIL
    image = Image.open('../frontend/resources/assets/default.png').convert('RGB')

    # Save the resized image to the cache path
    image.save(default_cover_image, format='JPEG')  # You can adjust the format as needed

def first_non_null(*args):
    for arg in args:
        if arg is not None:
            return arg
    return None  # Return None if all arguments are None
    
def generate_song_dict(row):
    return {
        "id": row[0],
        "disc": row[1],
        "track": row[2],
        "title": row[3],
        "artist": row[4],
        "artist_id": row[5],
        "duration": row[6],
        "album": row[7],
        "album_id": row[8],
        "cover_hash": row[11],
        "format": row[12],
        "bit_depth": row[13],
        "bitrate": row[14],
        "sample_rate": row[15],
        "has_lyrics": row[16] == 1
    }

def generate_album_dict(row):
    return {
        "id": row[0],
        "title": row[1],
        "artist": row[2],
        "artist_id": row[3],
        "release_year": row[4],
        "cover_hash": row[5]
    }

@app.route('/api/songs')
def get_songs():
    db = sqlite3.connect('music_database.db')
    with db:
        cursor = db.cursor()
        cursor.execute('SELECT * FROM songs')
        rows = cursor.fetchall()

        songs = [generate_song_dict(row) for row in rows]
        return jsonify(songs)

@app.route('/api/albums')
def get_albums():
    db = sqlite3.connect('music_database.db')
    with db:
        cursor = db.cursor()
        cursor.execute('SELECT * FROM albums')
        rows = cursor.fetchall()

        albums = [generate_album_dict(row) for row in rows]
        return jsonify(albums)
    
@app.route('/api/songs/<album_id>')
def get_songs_by_album(album_id):
    db = sqlite3.connect('music_database.db')
    with db:
        cursor = db.cursor()

        # Get album information
        cursor.execute('SELECT * FROM albums WHERE id = ?', (album_id,))
        album_info = cursor.fetchone()

        if album_info:
            cursor.execute('SELECT * FROM songs WHERE album_id = ? ORDER BY track', (album_id,))
            songs_rows = cursor.fetchall()

            response = generate_album_dict(album_info)
            response['songs'] = [generate_song_dict(row) for row in songs_rows]

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
        
@app.route('/api/lyrics/<song_id>')
def get_lyrics(song_id):
    db = sqlite3.connect('music_database.db')
    with db:
        cursor = db.cursor()
        cursor.execute('SELECT path FROM songs WHERE id = ?', (song_id,))
        song_path = cursor.fetchone()

    if song_path:
        lrc_file_path = get_lyrics_path(song_path[0])  # Assuming you have the get_lyrics_path function

        if os.path.exists(lrc_file_path):
            lyrics_parser = LrcParser(lrc_file_path)
            lyrics = lyrics_parser.parse()
            return jsonify(lyrics)
        else:
            return "Lyrics not found", 404
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
    
import os
import hashlib
from datetime import datetime
from PIL import Image
import io
from tinytag import TinyTag

def process_tags(file_path):
    tags = TinyTag.get(file_path, image=True)
    album_title = first_non_null(tags.album, f"[{os.path.basename(os.path.dirname(file_path))}]").strip()
    return {
        "disc": tags.disc,
        "track": tags.track,
        "title": tags.title or os.path.basename(file_path),
        "artist": tags.artist,
        "artist_id": hashlib.sha1(first_non_null(tags.artist,'').encode()).hexdigest(),
        "duration": tags.duration,
        "album_artist":first_non_null(tags.albumartist,tags.artist,''),
        "album_title": album_title,
        "album_id": hashlib.sha1(album_title.encode()).hexdigest(),
        "formats": os.path.splitext(file_path)[-1][1:].upper(),
        "bit_depth": tags.bitdepth,
        "bitrate": tags.bitrate,
        "sample_rate": tags.samplerate,
        "year":tags.year
    }

def process_cover(file_path, cache_dir):
    tags = TinyTag.get(file_path, image=True)
    cover = tags.get_image()

    if cover:
        cover_id = hashlib.sha1(cover).hexdigest()
        cover_path = os.path.join(cache_dir, cover_id[:2], cover_id)
        if not os.path.exists(cover_path):
            os.makedirs(os.path.dirname(cover_path), exist_ok=True)

            image = Image.open(io.BytesIO(cover)).convert('RGB')
            max_width = 768
            max_height = 768
            image.thumbnail((max_width, max_height), Image.ANTIALIAS)
            image.save(cover_path, format='JPEG')

        return cover_id
    else:
        return 'default'

def process_song_file(file_path, db, cache_dir):
    file_hash = hashlib.sha1(file_path.encode()).hexdigest()

    try:
        modified_date = datetime.fromtimestamp(os.path.getmtime(file_path))

        cursor = db.cursor()
        cursor.execute('SELECT id FROM songs WHERE path = ?', (file_path,))
        existing_song = cursor.fetchone()

        if existing_song:
            return

        tags = process_tags(file_path)
        cover_id = process_cover(file_path,cache_dir)

        cursor = db.cursor()
        cursor.execute('SELECT * FROM albums WHERE id = ?', (tags["album_id"],))
        album_row = cursor.fetchone()

        if not album_row:
            db.execute('INSERT OR REPLACE INTO albums VALUES (?, ?, ?, ?, ?, ?)',
                       (tags["album_id"], tags["album_title"], tags["album_artist"], tags["artist_id"], tags["year"], cover_id))


        has_lyrics = detect_lyrics(file_path)

        db.execute('INSERT OR REPLACE INTO songs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                   (file_hash, tags["disc"], tags["track"], tags["title"], tags["artist"], tags["artist_id"], tags["duration"],
                    tags["album_title"], tags["album_id"], file_path, modified_date, cover_id, tags["formats"],
                    tags["bit_depth"], tags["bitrate"], tags["sample_rate"], has_lyrics))

        return True

    except Exception as e:
        print(f'Failed to process {file_path}')
        traceback.print_exc()


def get_lyrics_path(file_path):
    # Get the directory and filename components of the file path
    directory, filename = os.path.split(file_path)

    # Generate the expected LRC file name by removing the last extension component and adding ".lrc"
    lrc_filename = ".".join(filename.split('.')[:-1]) + ".lrc"

    # Check if the expected LRC file exists in the same directory
    return os.path.join(directory, lrc_filename)

def detect_lyrics(file_path):
    return os.path.exists(get_lyrics_path(file_path))

def scan_existing(db):
    with db:
        cursor = db.cursor()
        cursor.execute('SELECT id, path FROM songs')
        existing_songs = cursor.fetchall()

        for song_id, file_path in existing_songs:
            if not os.path.exists(file_path):
                cursor.execute('DELETE FROM songs WHERE id = ?', (song_id,))
                print(f'Removed song {song_id} (no longer exists)')
                sys.stdout.flush()
            else:
                modified_date = datetime.fromtimestamp(os.path.getmtime(file_path))
                cursor.execute('SELECT modified_date FROM songs WHERE id = ?', (song_id,))
                current_modified_date = cursor.fetchone()[0]

                if modified_date != current_modified_date:
                    process_song_file(file_path, db, cache_dir)
                    # db.execute('UPDATE songs SET modified_date = ? WHERE id = ?', (modified_date, song_id))
                    print(f'Updated song {song_id}')
                    # sys.stdout.flush()


                cursor.execute('SELECT has_lyrics FROM songs WHERE id = ?', (song_id,))
                current_has_lyrics = cursor.fetchone()[0]
                has_lyrics = detect_lyrics(file_path)

                if has_lyrics != current_has_lyrics:
                    db.execute('UPDATE songs SET has_lyrics = ? WHERE id = ?', (has_lyrics, song_id))
                    print(f'Updated lyrics status for song {song_id}')
                    sys.stdout.flush()



def scan_all_dirs():
    with open('config.json', 'r') as config_file:
        config = json.load(config_file)
        music_directories = config.get("music_directories", [])

        for music_dir in music_directories:
            scan_music_directory(music_dir)

def scan_music_directory(directory):
    new_songs = 0
    with db:
        for root, dirs, files in os.walk(directory):
            for file in files:
                if file.lower().endswith(('.mp3', '.flac', '.wav', '.ogg', '.opus', '.m4a')):
                    file_path = os.path.join(root, file)
                    if process_song_file(file_path, db, cache_dir):
                        new_songs += 1
                        print(f'Added {new_songs} new songs', end='\r')
                        sys.stdout.flush()

if __name__ == '__main__':
    scan_existing(db)
    scan_all_dirs()
    app.run(host='0.0.0.0')