from flask import Flask, request, redirect, render_template
from flask_socketio import SocketIO, emit
import threading
import subprocess
import time

app = Flask(__name__)
socketio = SocketIO(app)
queue = []
now_playing = None
skip_votes = set()

connected_users = 0

@socketio.on('connect')
def handle_connect():
    global connected_users
    connected_users += 1
    print(f"Connected: {connected_users} users")
    socketio.emit('user_count', {'count': connected_users})

@socketio.on('disconnect')
def handle_disconnect():
    global connected_users
    connected_users -= 1
    print(f"Disconnected: {connected_users} users")
    socketio.emit('user_count', {'count': connected_users})
    
@socketio.on('vote_skip')
def handle_vote_skip():
    global skip_votes

    user_id = request.sid

    if user_id not in skip_votes:
        skip_votes.add(user_id)

    needed_votes = (connected_users // 2) + 1
    current_votes = len(skip_votes)

    socketio.emit('skip_vote_update', {
        'current': current_votes,
        'needed': needed_votes
    })

    if current_votes >= needed_votes:
        print("\nMajority voted skip!")
        subprocess.run(["pkill", "mpv"])  # Omoară mpv-ul


def play_music():
    global now_playing
    while True:
        if queue:
            song = queue.pop(0)
            now_playing = song
            
            socketio.emit('queue_updated', {"queue": queue})

            print(f"Redau: {song['title']}")
            socketio.emit('now_playing', {
                'title': song['title'],
                'uploader': song['uploader'],
                'thumbnail': song['thumbnail']
            })

            subprocess.run(["mpv", "--no-video", song["audio_url"]])

            now_playing = None
            socketio.emit('now_playing', None)
            
            skip_votes.clear()
            socketio.emit('skip_reset')

        time.sleep(1)

def process_song(query):
    if query.startswith('http'):
        yt_query = query
    else:
        yt_query = f"ytsearch1:{query}"

    result = subprocess.run([
        'yt-dlp',
        '-f', 'bestaudio[ext=m4a]/bestaudio/best',
        '--print', '%(title)s\n%(uploader)s\n%(url)s\n%(thumbnail)s',
        yt_query
    ], capture_output=True, text=True)

    output = result.stdout.strip().split('\n')
    if len(output) < 4:
        print(f"Error processing song: {query}")
        return

    title, uploader, url, thumbnail = output
    song = {
        "title": title,
        "uploader": uploader,
        "audio_url": url,
        "thumbnail": thumbnail
    }

    queue.append(song)
    socketio.emit('queue_updated', {"queue": queue})

@app.route('/')
def index():
    return render_template('index.html', queue=queue, now_playing=now_playing)

@app.route('/add', methods=['POST'])
def add():
    query = request.form['link']
    if not query:
        return redirect('/')
    threading.Thread(target=process_song, args=(query,), daemon=True).start()
    return redirect('/')


@app.route('/queue')
def view_queue():
    return {"queue": queue}

@app.route('/nowplaying')
def view_nowplaying():
    return {"now_playing": now_playing}

if __name__ == "__main__":
    threading.Thread(target=play_music, daemon=True).start()
    socketio.run(app, host='0.0.0.0', port=5000)
