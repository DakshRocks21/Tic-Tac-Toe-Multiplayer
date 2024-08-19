from flask import Flask, render_template, request
from flask_socketio import SocketIO, join_room, leave_room, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app)

rooms = {}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/room/<room_id>')
def room(room_id):
    if room_id not in rooms:
        rooms[room_id] = {
            'players': [],
            'turn': 1  # Player 1 starts
        }
    return render_template('room.html', room_id=room_id)

@socketio.on('join')
def handle_join(data):
    room_id = data['room_id']
    join_room(room_id)

    if len(rooms[room_id]['players']) < 2:
        player_number = len(rooms[room_id]['players']) + 1
        rooms[room_id]['players'].append({'sid': request.sid, 'player_number': player_number})
        emit('set_player', player_number)
        emit('room_joined', {'room_id': room_id, 'player_number': player_number}, room=room_id)
    else:
        emit('room_full')

@socketio.on('make_move')
def handle_make_move(data):
    room_id = data['room_id']
    move = data['move']
    player = next((player for player in rooms[room_id]['players'] if player['sid'] == request.sid), None)

    if player and rooms[room_id]['turn'] == player['player_number']:
        emit('move_made', {'move': move, 'player': player['player_number']}, room=room_id)
        rooms[room_id]['turn'] = 2 if player['player_number'] == 1 else 1  # Toggle turn

@socketio.on('disconnect')
def handle_disconnect():
    for room_id, room in rooms.items():
        room['players'] = [p for p in room['players'] if p['sid'] != request.sid]
        if not room['players']:
            del rooms[room_id]
        break

if __name__ == '__main__':
    socketio.run(app, debug=True)
