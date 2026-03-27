"""WebSocket handlers for real-time messaging features"""
from flask_socketio import emit, join_room, leave_room, rooms
from flask import session
import json

# Track active users typing in conversations
typing_status = {}  # {conversation_id: {user_email: True/False}}
active_users = {}   # {conversation_id: [user_emails]}

def init_websocket(socketio):
    """Initialize WebSocket event handlers"""
    
    @socketio.on('connect')
    def handle_connect():
        """Handle user connection"""
        print(f"User connected: {session.get('user_email', 'Unknown')}")
        emit('connection_response', {'data': 'Connected to MediLink'})
    
    @socketio.on('disconnect')
    def handle_disconnect():
        """Handle user disconnection"""
        user_email = session.get('user_email')
        print(f"User disconnected: {user_email}")
        
        # Remove from all conversations
        for conv_id in list(active_users.keys()):
            if user_email in active_users[conv_id]:
                active_users[conv_id].remove(user_email)
    
    @socketio.on('join_conversation')
    def on_join_conversation(data):
        """User joins a conversation"""
        user_email = session.get('user_email')
        conversation_id = data.get('conversation_id')
        
        if not user_email or not conversation_id:
            return emit('error', {'message': 'Missing user_email or conversation_id'})
        
        room = f"conv_{conversation_id}"
        join_room(room)
        session['current_conversation'] = conversation_id
        
        # Track active users
        if conversation_id not in active_users:
            active_users[conversation_id] = []
        if user_email not in active_users[conversation_id]:
            active_users[conversation_id].append(user_email)
        
        # Broadcast that user joined
        emit('user_joined', {
            'user_email': user_email,
            'conversation_id': conversation_id,
            'active_users': active_users.get(conversation_id, [])
        }, room=room)
        
        print(f"{user_email} joined conversation {conversation_id}")
    
    @socketio.on('leave_conversation')
    def on_leave_conversation(data):
        """User leaves a conversation"""
        user_email = session.get('user_email')
        conversation_id = data.get('conversation_id')
        
        room = f"conv_{conversation_id}"
        leave_room(room)
        
        # Stop typing indicator
        if conversation_id in typing_status and user_email in typing_status[conversation_id]:
            del typing_status[conversation_id][user_email]
        
        # Remove from active users
        if conversation_id in active_users and user_email in active_users[conversation_id]:
            active_users[conversation_id].remove(user_email)
        
        # Broadcast user left
        emit('user_left', {
            'user_email': user_email,
            'conversation_id': conversation_id,
            'active_users': active_users.get(conversation_id, [])
        }, room=room)
    
    @socketio.on('typing')
    def on_typing(data):
        """Handle typing indicator"""
        user_email = session.get('user_email')
        conversation_id = data.get('conversation_id')
        is_typing = data.get('is_typing', True)
        
        if not conversation_id:
            return
        
        room = f"conv_{conversation_id}"
        
        # Track typing status
        if conversation_id not in typing_status:
            typing_status[conversation_id] = {}
        
        if is_typing:
            typing_status[conversation_id][user_email] = True
        else:
            typing_status[conversation_id].pop(user_email, None)
        
        # Broadcast typing indicator
        typing_users = list(typing_status[conversation_id].keys())
        emit('typing_indicator', {
            'typing_users': typing_users,
            'conversation_id': conversation_id,
            'user_email': user_email,
            'is_typing': is_typing
        }, room=room, skip_sid=True)
    
    @socketio.on('message_read')
    def on_message_read(data):
        """Notify when message is read"""
        user_email = session.get('user_email')
        conversation_id = data.get('conversation_id')
        message_id = data.get('message_id')
        
        room = f"conv_{conversation_id}"
        emit('message_read_receipt', {
            'message_id': message_id,
            'read_by': user_email,
            'conversation_id': conversation_id
        }, room=room)
    
    @socketio.on('message_reaction')
    def on_message_reaction(data):
        """Broadcast message reaction"""
        user_email = session.get('user_email')
        conversation_id = data.get('conversation_id')
        message_id = data.get('message_id')
        emoji = data.get('emoji')
        action = data.get('action', 'add')  # add or remove
        
        room = f"conv_{conversation_id}"
        emit('reaction_added', {
            'message_id': message_id,
            'emoji': emoji,
            'user_email': user_email,
            'action': action,
            'conversation_id': conversation_id
        }, room=room)
    
    @socketio.on('message_pinned')
    def on_message_pinned(data):
        """Broadcast message pin/unpin"""
        user_email = session.get('user_email')
        conversation_id = data.get('conversation_id')
        message_id = data.get('message_id')
        is_pinned = data.get('is_pinned', True)
        
        room = f"conv_{conversation_id}"
        emit('message_pin_status', {
            'message_id': message_id,
            'is_pinned': is_pinned,
            'pinned_by': user_email,
            'conversation_id': conversation_id
        }, room=room)
    
    @socketio.on('get_active_users')
    def on_get_active_users(data):
        """Get active users in a conversation"""
        conversation_id = data.get('conversation_id')
        emit('active_users_list', {
            'conversation_id': conversation_id,
            'active_users': active_users.get(conversation_id, [])
        })
    
    @socketio.on('get_typing_users')
    def on_get_typing_users(data):
        """Get users currently typing"""
        conversation_id = data.get('conversation_id')
        typing_users = list(typing_status.get(conversation_id, {}).keys())
        emit('typing_users_list', {
            'conversation_id': conversation_id,
            'typing_users': typing_users
        })
