"""
================================================
  UNO GAME SERVER - Pi Party Edition
  Hosts the game so classmates can connect!
  Run this on YOUR computer first, then share
  your IP address with classmates.
================================================
"""

import socket
import threading
import json
import random
import time
import sys

# ─────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────
HOST = "0.0.0.0"       # Listen on all interfaces
PORT = 5555            # Port classmates connect to
MAX_PLAYERS = 4
MIN_PLAYERS = 2

COLORS = ["Red", "Green", "Blue", "Yellow"]
SPECIAL_CARDS = ["Skip", "Reverse", "Draw2"]
WILD_CARDS = ["Wild", "WildDraw4"]
NUMBER_CARDS = [str(n) for n in range(0, 10)]

# ─────────────────────────────────────────────
#  CARD CLASS
# ─────────────────────────────────────────────
class Card:
    def __init__(self, color, value):
        self.color = color   # "Red", "Green", "Blue", "Yellow", "Wild"
        self.value = value   # "0"-"9", "Skip", "Reverse", "Draw2", "Wild", "WildDraw4"

    def to_dict(self):
        return {"color": self.color, "value": self.value}

    def __str__(self):
        return f"{self.color} {self.value}"

    def can_play_on(self, top_card, declared_color=None):
        """Check if this card can be played on top of the top card."""
        # Wilds can always be played
        if self.value in WILD_CARDS:
            return True
        # Match color (use declared_color if top is wild)
        active_color = declared_color if top_card.value in WILD_CARDS else top_card.color
        if self.color == active_color:
            return True
        # Match value
        if self.value == top_card.value:
            return True
        return False


# ─────────────────────────────────────────────
#  DECK CLASS
# ─────────────────────────────────────────────
class Deck:
    def __init__(self):
        self.cards = []
        self.discard_pile = []
        self._build()
        self.shuffle()

    def _build(self):
        """Build a standard 108-card UNO deck."""
        for color in COLORS:
            # One 0 per color
            self.cards.append(Card(color, "0"))
            # Two of each 1-9 and specials
            for value in NUMBER_CARDS[1:] + SPECIAL_CARDS:
                self.cards.append(Card(color, value))
                self.cards.append(Card(color, value))
        # 4 Wilds and 4 Wild Draw 4s
        for _ in range(4):
            self.cards.append(Card("Wild", "Wild"))
            self.cards.append(Card("Wild", "WildDraw4"))

    def shuffle(self):
        random.shuffle(self.cards)

    def draw(self):
        """Draw a card, reshuffling discard if needed."""
        if not self.cards:
            if len(self.discard_pile) <= 1:
                return None  # Deck exhausted (very rare)
            # Keep top discard, reshuffle rest
            top = self.discard_pile.pop()
            self.cards = self.discard_pile
            self.discard_pile = [top]
            random.shuffle(self.cards)
        return self.cards.pop()

    def draw_many(self, count):
        return [self.draw() for _ in range(count)]

    def discard(self, card):
        self.discard_pile.append(card)

    @property
    def top_card(self):
        return self.discard_pile[-1] if self.discard_pile else None


# ─────────────────────────────────────────────
#  PLAYER CLASS
# ─────────────────────────────────────────────
class Player:
    def __init__(self, name, conn, addr):
        self.name = name
        self.conn = conn
        self.addr = addr
        self.hand = []
        self.has_said_uno = False

    def hand_to_list(self):
        return [c.to_dict() for c in self.hand]

    def remove_card(self, color, value):
        for i, card in enumerate(self.hand):
            if card.color == color and card.value == value:
                return self.hand.pop(i)
        return None

    def has_playable_card(self, top_card, declared_color=None):
        return any(c.can_play_on(top_card, declared_color) for c in self.hand)


# ─────────────────────────────────────────────
#  GAME CLASS
# ─────────────────────────────────────────────
class UnoGame:
    def __init__(self, players):
        self.players = players
        self.deck = Deck()
        self.current_player_index = 0
        self.direction = 1          # 1 = clockwise, -1 = counter-clockwise
        self.declared_color = None  # Used after a Wild is played
        self.pending_draw = 0       # Stacked Draw 2 / Wild Draw 4
        self.game_over = False
        self.winner = None
        self.turn_count = 0

        # Deal 7 cards to each player
        for player in self.players:
            player.hand = self.deck.draw_many(7)

        # Flip first card (skip Wilds as starting card)
        start_card = self.deck.draw()
        while start_card.value in WILD_CARDS:
            self.deck.cards.insert(0, start_card)
            start_card = self.deck.draw()
        self.deck.discard(start_card)

        # Apply starting card effect
        self._apply_start_card_effect(start_card)

    def _apply_start_card_effect(self, card):
        """Apply the effect of the first flipped card."""
        if card.value == "Skip":
            self.current_player_index = self._next_index(self.current_player_index)
        elif card.value == "Reverse":
            self.direction *= -1
            if len(self.players) == 2:
                self.current_player_index = self._next_index(self.current_player_index)
        elif card.value == "Draw2":
            self.pending_draw += 2

    def _next_index(self, index):
        return (index + self.direction) % len(self.players)

    @property
    def current_player(self):
        return self.players[self.current_player_index]

    def advance_turn(self):
        self.current_player_index = self._next_index(self.current_player_index)
        self.turn_count += 1

    def play_card(self, player, color, value):
        """
        Attempt to play a card. Returns (success, message, extra_data).
        extra_data may include {'new_color': ..., 'draw_count': ...}
        """
        if player != self.current_player:
            return False, "It's not your turn!", {}

        # Handle pending draw stack — player must draw unless they stack
        if self.pending_draw > 0:
            card_played = player.remove_card(color, value)
            if card_played is None:
                return False, "You don't have that card.", {}
            # Can only stack matching draw cards
            if card_played.value == "Draw2" and self.deck.top_card.value == "Draw2":
                self.pending_draw += 2
                self.deck.discard(card_played)
                self.advance_turn()
                return True, f"{player.name} stacked Draw2! Pending: {self.pending_draw}", {"stacked": self.pending_draw}
            elif card_played.value == "WildDraw4":
                self.pending_draw += 4
                player.hand.append(card_played)  # Return card, handle wild color below
                player.remove_card(color, value)
                self.deck.discard(card_played)
                self.advance_turn()
                return True, f"{player.name} stacked WildDraw4! Pending: {self.pending_draw}", {"needs_color": True, "stacked": self.pending_draw}
            else:
                # Can't stack, put card back
                player.hand.append(card_played)
                return False, f"You must draw {self.pending_draw} cards (or stack a matching draw card).", {"must_draw": self.pending_draw}

        card_played = player.remove_card(color, value)
        if card_played is None:
            return False, "You don't have that card.", {}

        top = self.deck.top_card
        if not card_played.can_play_on(top, self.declared_color):
            player.hand.append(card_played)  # Return card
            return False, "That card can't be played right now.", {}

        self.deck.discard(card_played)
        self.declared_color = None
        extra = {}

        # Apply card effects
        if card_played.value == "Skip":
            self.advance_turn()  # Skip next player
            self.advance_turn()
            extra["skipped"] = self.players[self._next_index(self.current_player_index)].name

        elif card_played.value == "Reverse":
            self.direction *= -1
            if len(self.players) == 2:
                self.advance_turn()  # In 2-player, Reverse acts like Skip
                self.advance_turn()
            else:
                self.advance_turn()

        elif card_played.value == "Draw2":
            self.pending_draw += 2
            self.advance_turn()
            # Next player will have to draw when it's their turn

        elif card_played.value in ("Wild", "WildDraw4"):
            extra["needs_color"] = True
            if card_played.value == "WildDraw4":
                self.pending_draw += 4
            self.advance_turn()

        else:
            # Normal number card
            self.advance_turn()

        # Check for UNO win
        if len(player.hand) == 0:
            self.game_over = True
            self.winner = player
            extra["winner"] = player.name

        # Check if player has one card (UNO alert)
        if len(player.hand) == 1:
            extra["uno"] = player.name

        return True, f"{player.name} played {card_played}", extra

    def draw_card(self, player):
        """Player draws a card (or draws pending cards)."""
        if player != self.current_player:
            return False, "It's not your turn!", []

        if self.pending_draw > 0:
            drawn = self.deck.draw_many(self.pending_draw)
            player.hand.extend(drawn)
            count = self.pending_draw
            self.pending_draw = 0
            self.advance_turn()
            return True, f"{player.name} drew {count} cards.", [c.to_dict() for c in drawn]

        card = self.deck.draw()
        if card:
            player.hand.append(card)
            self.advance_turn()
            return True, f"{player.name} drew a card.", [card.to_dict()]
        return False, "Deck is empty!", []

    def declare_color(self, player, color):
        """Called after playing a Wild card."""
        if color not in COLORS:
            return False, "Invalid color."
        self.declared_color = color
        return True, f"{player.name} declared {color}!"

    def get_state(self, for_player=None):
        """Build a game state dict to send to a player."""
        state = {
            "top_card": self.deck.top_card.to_dict() if self.deck.top_card else None,
            "declared_color": self.declared_color,
            "current_player": self.current_player.name,
            "direction": self.direction,
            "pending_draw": self.pending_draw,
            "turn_count": self.turn_count,
            "game_over": self.game_over,
            "winner": self.winner.name if self.winner else None,
            "player_card_counts": {p.name: len(p.hand) for p in self.players},
            "player_order": [p.name for p in self.players],
        }
        if for_player:
            state["your_hand"] = for_player.hand_to_list()
        return state


# ─────────────────────────────────────────────
#  LOBBY / SERVER
# ─────────────────────────────────────────────
class UnoServer:
    def __init__(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.players = []        # List of Player objects
        self.game = None
        self.lobby_open = True
        self.lock = threading.Lock()

    def start(self):
        self.server_socket.bind((HOST, PORT))
        self.server_socket.listen(MAX_PLAYERS)
        print("=" * 50)
        print("  🃏  UNO Pi Party Server Started!")
        print("=" * 50)
        print(f"  Listening on port {PORT}")
        print(f"  Waiting for {MIN_PLAYERS}–{MAX_PLAYERS} players...")
        print(f"  Share your IP address with classmates.")
        print("=" * 50)

        # Accept connections in main thread
        accept_thread = threading.Thread(target=self._accept_connections)
        accept_thread.daemon = True
        accept_thread.start()

        # Keep server alive
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[Server] Shutting down.")
            self.server_socket.close()

    def _accept_connections(self):
        while self.lobby_open:
            try:
                conn, addr = self.server_socket.accept()
                if not self.lobby_open:
                    self._send(conn, {"type": "error", "message": "Game already started!"})
                    conn.close()
                    continue
                if len(self.players) >= MAX_PLAYERS:
                    self._send(conn, {"type": "error", "message": "Lobby is full!"})
                    conn.close()
                    continue

                # Ask for player name
                self._send(conn, {"type": "name_request", "message": "Enter your name:"})
                data = self._recv(conn)
                name = data.get("name", f"Player{len(self.players)+1}") if data else f"Player{len(self.players)+1}"
                name = name.strip()[:16] or f"Player{len(self.players)+1}"

                player = Player(name, conn, addr)
                with self.lock:
                    self.players.append(player)

                print(f"[Lobby] {name} joined from {addr[0]} ({len(self.players)}/{MAX_PLAYERS})")

                self._send(conn, {
                    "type": "lobby_joined",
                    "message": f"Welcome to Pi Party UNO, {name}! Waiting for players...",
                    "players": [p.name for p in self.players],
                    "min_players": MIN_PLAYERS,
                    "max_players": MAX_PLAYERS
                })

                # Notify others
                self._broadcast({
                    "type": "player_joined",
                    "message": f"{name} joined the lobby!",
                    "players": [p.name for p in self.players]
                }, exclude=player)

                # Start game thread for this player
                t = threading.Thread(target=self._handle_player, args=(player,))
                t.daemon = True
                t.start()

                # Auto-start when max players reached
                if len(self.players) == MAX_PLAYERS:
                    self.lobby_open = False
                    time.sleep(0.5)
                    self._start_game()

            except Exception as e:
                print(f"[Accept Error] {e}")
                break

    def _handle_player(self, player):
        """Listen for messages from a connected player."""
        while True:
            data = self._recv(player.conn)
            if data is None:
                print(f"[Server] {player.name} disconnected.")
                self._broadcast({"type": "player_left", "message": f"{player.name} left the game."}, exclude=player)
                with self.lock:
                    if player in self.players:
                        self.players.remove(player)
                break

            msg_type = data.get("type")

            # ── Lobby: Host starts game manually ──
            if msg_type == "start_game":
                if len(self.players) >= MIN_PLAYERS and self.game is None:
                    self.lobby_open = False
                    self._start_game()
                else:
                    self._send(player.conn, {"type": "error", "message": f"Need at least {MIN_PLAYERS} players to start."})

            # ── In-game actions ──
            elif msg_type == "play_card" and self.game:
                color = data.get("color")
                value = data.get("value")
                with self.lock:
                    success, message, extra = self.game.play_card(player, color, value)
                if success:
                    self._broadcast_game_state(message, extra)
                    if extra.get("needs_color"):
                        self._send(player.conn, {"type": "choose_color", "message": "Choose a color: Red, Green, Blue, Yellow"})
                else:
                    self._send(player.conn, {"type": "error", "message": message})

            elif msg_type == "draw_card" and self.game:
                with self.lock:
                    success, message, drawn = self.game.draw_card(player)
                if success:
                    self._send(player.conn, {"type": "drew_cards", "message": message, "cards": drawn})
                    self._broadcast_game_state(message, {})
                else:
                    self._send(player.conn, {"type": "error", "message": message})

            elif msg_type == "declare_color" and self.game:
                color = data.get("color")
                with self.lock:
                    success, message = self.game.declare_color(player, color)
                if success:
                    self._broadcast_game_state(message, {"color_declared": color})
                else:
                    self._send(player.conn, {"type": "error", "message": message})

            elif msg_type == "say_uno" and self.game:
                player.has_said_uno = True
                self._broadcast({"type": "uno_called", "message": f"🚨 {player.name} says UNO!", "player": player.name})

            elif msg_type == "challenge_uno" and self.game:
                # Check if last player who should have said UNO did
                self._handle_uno_challenge(player)

            elif msg_type == "chat":
                msg = data.get("message", "")[:200]
                self._broadcast({"type": "chat", "from": player.name, "message": msg})

    def _start_game(self):
        """Initialize and start the UNO game."""
        with self.lock:
            self.game = UnoGame(list(self.players))

        print(f"[Server] Game started with {len(self.players)} players!")
        self._broadcast({"type": "game_starting", "message": "🃏 Game is starting! Cards are being dealt..."})
        time.sleep(1)
        self._broadcast_game_state("Game started! Good luck!", {"game_start": True})

    def _broadcast_game_state(self, message, extra):
        """Send updated game state to all players."""
        if not self.game:
            return
        for player in list(self.players):
            state = self.game.get_state(for_player=player)
            payload = {
                "type": "game_state",
                "message": message,
                "state": state,
                **extra
            }
            self._send(player.conn, payload)

        if self.game.game_over:
            winner = self.game.winner
            self._broadcast({
                "type": "game_over",
                "message": f"🏆 {winner.name} wins the game!",
                "winner": winner.name
            })

    def _handle_uno_challenge(self, challenger):
        """Handle a UNO challenge against the previous player."""
        if not self.game:
            return
        # Find the player who just played (previous turn)
        prev_index = (self.game.current_player_index - self.game.direction) % len(self.game.players)
        prev_player = self.game.players[prev_index]
        if len(prev_player.hand) == 1 and not prev_player.has_said_uno:
            # Caught! Draw 2 cards
            cards = self.game.deck.draw_many(2)
            prev_player.hand.extend(cards)
            self._broadcast({
                "type": "uno_challenge_success",
                "message": f"{challenger.name} caught {prev_player.name} not saying UNO! {prev_player.name} draws 2!",
                "caught": prev_player.name,
                "challenger": challenger.name
            })
            self._broadcast_game_state("UNO challenge!", {})
        else:
            # Failed challenge — challenger draws 2
            cards = self.game.deck.draw_many(2)
            challenger.hand.extend(cards)
            self._broadcast({
                "type": "uno_challenge_fail",
                "message": f"{challenger.name}'s challenge failed! They draw 2 cards.",
                "challenger": challenger.name
            })
            self._broadcast_game_state("Challenge failed!", {})

    def _broadcast(self, data, exclude=None):
        for player in list(self.players):
            if player != exclude:
                self._send(player.conn, data)

    def _send(self, conn, data):
        try:
            msg = json.dumps(data) + "\n"
            conn.sendall(msg.encode("utf-8"))
        except Exception:
            pass

    def _recv(self, conn):
        try:
            buffer = ""
            while True:
                chunk = conn.recv(4096).decode("utf-8")
                if not chunk:
                    return None
                buffer += chunk
                if "\n" in buffer:
                    line, _ = buffer.split("\n", 1)
                    return json.loads(line)
        except Exception:
            return None


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    server = UnoServer()
    server.start()
    
