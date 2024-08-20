from flask import Flask, render_template, request, redirect, url_for
from flask_socketio import SocketIO, join_room, leave_room, emit
import gevent.monkey

gevent.monkey.patch_all()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, async_mode='gevent')
rooms = {}

def check_winner(board, size):
    for i in range(size):
        if all(board[i*size + j] == board[i*size] and board[i*size] != '' for j in range(size)):
            return True
        if all(board[j*size + i] == board[i] and board[i] != '' for j in range(size)):
            return True
    if all(board[i*size + i] == board[0] and board[0] != '' for i in range(size)):
        return True
    if all(board[i*size + (size-i-1)] == board[size-1] and board[size-1] != '' for i in range(size)):
        return True
    return False

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/room/<room_id>/<int:size>')
def create_room(room_id, size):
    password = request.args.get('password')
    if room_id not in rooms:
        rooms[room_id] = {
            'players': [],
            'board': [''] * (size * size),
            'size': size,
            'turn': 1,  # Player 1 starts
            'scores': {1: 0, 2: 0},
            'password': password
        }
    else:
        return "Room already exists!", 400
    return render_template('room.html', room_id=room_id, size=size)

@app.route('/join/<room_id>')
def join_room_view(room_id):
    password = request.args.get('password')
    if room_id in rooms:
        if rooms[room_id]['password'] == password:
            return render_template('room.html', room_id=room_id, size=rooms[room_id]['size'])
        else:
            return "Incorrect password!", 403
    return "Room not found!", 404

@socketio.on('join')
def handle_join(data):
    room_id = data['room_id']
    size = data['size']
    join_room(room_id)

    if len(rooms[room_id]['players']) < 2:
        player_number = len(rooms[room_id]['players']) + 1
        rooms[room_id]['players'].append({'sid': request.sid, 'player_number': player_number})
        emit('set_player', player_number)
    else:
        emit('spectator', {'size': rooms[room_id]['size']})

    emit('room_joined', {'room_id': room_id, 'board': rooms[room_id]['board'], 'size': size}, room=room_id)

@socketio.on('make_move')
def handle_make_move(data):
    room_id = data['room_id']
    move = int(data['move'])
    size = rooms[room_id]['size']
    player = next((player for player in rooms[room_id]['players'] if player['sid'] == request.sid), None)

    if player and rooms[room_id]['turn'] == player['player_number']:
        if rooms[room_id]['board'][move] == '':
            rooms[room_id]['board'][move] = 'X' if player['player_number'] == 1 else 'O'
            if check_winner(rooms[room_id]['board'], size):
                rooms[room_id]['scores'][player['player_number']] += 1
                emit('move_made', {'move': move, 'player': player['player_number']}, room=room_id)
                emit('game_over', {'winner': player['player_number']}, room=room_id)
            elif all(cell != '' for cell in rooms[room_id]['board']):
                emit('move_made', {'move': move, 'player': player['player_number']}, room=room_id)
                emit('game_over', {'winner': 0}, room=room_id)
            else:
                rooms[room_id]['turn'] = 2 if player['player_number'] == 1 else 1
                emit('move_made', {'move': move, 'player': player['player_number']}, room=room_id)

@socketio.on('rematch')
def handle_rematch(data):
    room_id = data['room_id']
    size = rooms[room_id]['size']
    rooms[room_id]['board'] = [''] * (size * size)
    rooms[room_id]['turn'] = 1  # Player 1 starts
    emit('start_rematch', {'size': size}, room=room_id)

@socketio.on('chat_message')
def handle_chat_message(data):
    room_id = data['room_id']
    player = next((player for player in rooms[room_id]['players'] if player['sid'] == request.sid), None)
    if player:
        emit('receive_message', {'player': player['player_number'], 'message': data['message']}, room=room_id)

@socketio.on('disconnect')
def handle_disconnect():
    for room_id, room in rooms.items():
        room['players'] = [p for p in room['players'] if p['sid'] != request.sid]
        if not room['players']:
            del rooms[room_id]
        break

if __name__ == '__main__':
    socketio.run(app, debug=True)
