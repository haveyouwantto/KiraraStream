from email.mime import image
import os
import hashlib
import sqlite3
from flask import Flask, jsonify, send_file
from tinytag import TinyTag
from datetime import datetime
from PIL import Image
import io

from lrcparser import LrcParser

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

music_dir = 'music'
cache_dir = './.cache/'

default_cover_image = os.path.join(cache_dir,'default.jpg')
if not os.path.exists(default_cover_image):

    # Load the image using PIL
    image = Image.open('../frontend/dist/default.png').convert('RGB')

    # Save the resized image to the cache path
    image.save(default_cover_image, format='JPEG')  # You can adjust the format as needed
    
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
    

def process_song_file(file_path, db, cache_dir):
    file_hash = hashlib.sha1(file_path.encode()).hexdigest()

    try:
        modified_date = datetime.fromtimestamp(os.path.getmtime(file_path))

        cursor = db.cursor()
        cursor.execute('SELECT id FROM songs WHERE path = ?', (file_path,))
        existing_song = cursor.fetchone()

        if existing_song:
            return

        tags = TinyTag.get(file_path, image=True)
        song_id = file_hash
        disc = tags.disc
        title = tags.title or os.path.basename(file_path)
        track = tags.track
        artist = tags.artist
        artist_id = hashlib.sha1(artist.encode() if artist else b'').hexdigest()
        duration = tags.duration
        album_title = tags.album.strip() if tags.album else None
        album_id = hashlib.sha1(album_title.encode() if album_title else b'').hexdigest()
        cover = tags.get_image()
        cover_id = 'default'
        formats = os.path.splitext(file_path)[-1][1:].upper()
        bit_depth = tags.bitdepth
        bitrate = tags.bitrate
        sample_rate = tags.samplerate
        has_lyrics = detect_lyrics(file_path)  # Implement the lyrics detection function

        if cover:
            cover_id = hashlib.sha1(cover).hexdigest()
            cover_path = os.path.join(cache_dir, cover_id[:2], cover_id)
            os.makedirs(os.path.dirname(cover_path), exist_ok=True)

            image = Image.open(io.BytesIO(cover)).convert('RGB')
            max_width = 768
            max_height = 768
            image.thumbnail((max_width, max_height), Image.ANTIALIAS)
            image.save(cover_path, format='JPEG')

        cursor = db.cursor()
        cursor.execute('SELECT * FROM albums WHERE id = ?', (album_id,))
        album_row = cursor.fetchone()

        if not album_row:
            db.execute('INSERT OR REPLACE INTO albums VALUES (?, ?, ?, ?, ?, ?)',
                       (album_id, album_title, artist, artist_id, tags.year, cover_id))

        db.execute('INSERT OR REPLACE INTO songs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                   (song_id, disc, track, title, artist, artist_id, duration, album_title, album_id,
                    file_path, modified_date, cover_id, formats, bit_depth, bitrate, sample_rate, has_lyrics))

    except Exception as e:
        print(f'Failed to process {file_path}')
        print(e)

def get_lyrics_path(file_path):
    # Get the directory and filename components of the file path
    directory, filename = os.path.split(file_path)

    # Generate the expected LRC file name by removing the last extension component and adding ".lrc"
    lrc_filename = ".".join(filename.split('.')[:-1]) + ".lrc"

    # Check if the expected LRC file exists in the same directory
    return os.path.join(directory, lrc_filename)

def detect_lyrics(file_path):
    return os.path.exists(get_lyrics_path(file_path))

def scan_music_directory(directory):
    with db:
        for root, dirs, files in os.walk(directory):
            for file in files:
                if file.lower().endswith(('.mp3', '.flac', '.wav','.ogg','.opus','.m4a')):
                    file_path = os.path.join(root, file)
                    process_song_file(file_path,db,cache_dir)

if __name__ == '__main__':
    scan_music_directory(music_dir)
    app.run(host='0.0.0.0')
