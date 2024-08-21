from flask import Flask, render_template, request, redirect, url_for
from flask_socketio import SocketIO, join_room, leave_room, emit
from flask_sqlalchemy import SQLAlchemy
import gevent.monkey
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.exc import IntegrityError

gevent.monkey.patch_all()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tic_tac_toe.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, async_mode='gevent')

class Room(db.Model):
    id = db.Column(db.String(80), primary_key=True)
    size = db.Column(db.Integer, nullable=False)
    board = db.Column(db.Text, nullable=False)  # We'll store the board as a string
    turn = db.Column(db.Integer, default=1)  # 1 or 2
    player1_id = db.Column(db.String(80), db.ForeignKey('player.sid'), nullable=True)
    player2_id = db.Column(db.String(80), db.ForeignKey('player.sid'), nullable=True)
    player1_score = db.Column(db.Integer, default=0)
    player2_score = db.Column(db.Integer, default=0)
    password = db.Column(db.String(100), nullable=True)

class Player(db.Model):
    sid = db.Column(db.String(80), primary_key=True)
    room_id = db.Column(db.String(80), db.ForeignKey('room.id'), nullable=False)
    player_number = db.Column(db.Integer, nullable=False)

class Move(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.String(80), db.ForeignKey('room.id'), nullable=False)
    player_number = db.Column(db.Integer, nullable=False)
    move_index = db.Column(db.Integer, nullable=False)

class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.String(80), db.ForeignKey('room.id'), nullable=False)
    player_number = db.Column(db.Integer, nullable=False)
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())

with app.app_context():
    db.create_all()


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


@socketio.on('join')
def handle_join(data):
    room_id = data['room_id']
    size = data['size']
    join_room(room_id)

    room = db.session.get(Room, room_id)
    if room:
        try:
            player = db.session.query(Player).filter_by(sid=request.sid, room_id=room_id).one()
        except NoResultFound:
            player = None

        if not player:
            try:
                if not room.player1_id:
                    player_number = 1
                    room.player1_id = request.sid
                elif not room.player2_id:
                    player_number = 2
                    room.player2_id = request.sid
                else:
                    emit('spectator', {'size': room.size})
                    return

                new_player = Player(sid=request.sid, room_id=room_id, player_number=player_number)
                db.session.add(new_player)
                db.session.commit()
                emit('set_player', player_number)
            except IntegrityError:
                db.session.rollback()
                emit('error', {'message': 'Player could not be added due to an integrity error.'})
                return

        emit('room_joined', {'room_id': room_id, 'board': room.board, 'size': size}, room=room_id)
        
@app.route('/room/<room_id>/<int:size>')
def create_room(room_id, size):
    password = request.args.get('password')
    if not db.session.get(Room, room_id):
        new_room = Room(
            id=room_id,
            size=int(size),
            board=' ' * (size * size), 
            password=password
        )
        db.session.add(new_room)
        db.session.commit()
    else:
        return "Room already exists!", 400
    return render_template('room.html', room_id=room_id, size=size)

@app.route('/join/<room_id>')
def join_room_view(room_id):
    password = request.args.get('password')
    room = db.session.get(Room, room_id)
    if room:
        if room.password == password:
            return render_template('room.html', room_id=room_id, size=room.size)
        else:
            return "Incorrect password!", 403
    return "Room not found!", 404

@socketio.on('make_move')
def handle_make_move(data):
    print("hello world")
    room_id = data['room_id']
    move = int(data['move'])
    room = Room.query.get(room_id)
    player = Player.query.filter_by(sid=request.sid, room_id=room_id).first()

    if player and room.turn == player.player_number:
        board_list = list(room.board)
        if board_list[move] == ' ':
            board_list[move] = 'X' if player.player_number == 1 else 'O'
            room.board = ''.join(board_list)

            if check_winner(board_list, room.size):
                if player.player_number == 1:
                    room.player1_score += 1
                else:
                    room.player2_score += 1
                emit('move_made', {'move': move, 'player': player.player_number}, room=room_id)
                emit('game_over', {'winner': player.player_number}, room=room_id)
            elif all(cell != ' ' for cell in board_list):
                emit('move_made', {'move': move, 'player': player.player_number}, room=room_id)
                emit('game_over', {'winner': 0}, room=room_id)
            else:
                room.turn = 2 if player.player_number == 1 else 1
                emit('move_made', {'move': move, 'player': player.player_number}, room=room_id)

            db.session.commit()  # Save changes to the database

@socketio.on('rematch')
def handle_rematch(data):
    room_id = data['room_id']
    room = Room.query.get(room_id)
    room.board = ' ' * (room.size * room.size)
    room.turn = 1  # Player 1 starts
    db.session.commit()
    emit('start_rematch', {'size': room.size}, room=room_id)

@socketio.on('chat_message')
def handle_chat_message(data):
    room_id = data['room_id']
    player = Player.query.filter_by(sid=request.sid, room_id=room_id).first()
    
    if player:
        # Store the message in the database
        new_message = ChatMessage(
            room_id=room_id,
            player_number=player.player_number,
            message=data['message']
        )
        db.session.add(new_message)
        db.session.commit()
        
        # Emit the message to the room
        emit('receive_message', {
            'player': player.player_number,
            'message': data['message']
        }, room=room_id)


@socketio.on('reconnect')
def handle_reconnect(data):
    room_id = data['room_id']
    player = Player.query.filter_by(sid=request.sid, room_id=room_id).first()
    if player:
        room = Room.query.get(room_id)
        emit('room_joined', {'room_id': room_id, 'board': room.board, 'size': room.size}, room=request.sid)
        emit('set_player', player.player_number)


@socketio.on('disconnect')
def handle_disconnect():
    player = Player.query.filter_by(sid=request.sid).first()
    if player:
        room = Room.query.filter_by(id=player.room_id).first()
        if room:
            if player.player_number == 1:
                room.player1_id = None
            elif player.player_number == 2:
                room.player2_id = None
            
            db.session.delete(player)
            db.session.commit()
            
            if not room.player1_id and not room.player2_id:
                db.session.delete(room)
                db.session.commit()
            else:
                emit('player_disconnected', {'player_number': player.player_number}, room=room.id)


if __name__ == '__main__':
    socketio.run(app, debug=True)
