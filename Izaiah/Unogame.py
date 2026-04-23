"""
UNO Pi Party Server
A real-time multiplayer UNO game server using sockets and threading.

Features:
- Multiplayer lobby system (2–4 players)
- Full UNO gameplay logic (cards, turns, rules)
- Wild cards, stacking, and special effects
- UNO call & challenge system
- Real-time JSON communication with clients
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

"""
UNO Pi Party Client
A terminal-based multiplayer UNO game client using sockets.

Features:
- Connects to UNO Pi Party server
- Real-time game state rendering in terminal
- Colored card display using ANSI escape codes
- Turn-based input system with validation
- UNO call, challenge, and chat support
- Wild card color selection interface
"""

import socket
import threading
import json
import sys
import os
import time

# ─────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────
DEFAULT_PORT = 5555
COLORS = ["Red", "Green", "Blue", "Yellow"]

COLOR_CODES = {
    "Red":    "\033[91m",
    "Green":  "\033[92m",
    "Yellow": "\033[93m",
    "Blue":   "\033[94m",
    "Wild":   "\033[95m",
    "Reset":  "\033[0m",
    "Bold":   "\033[1m",
    "Cyan":   "\033[96m",
    "White":  "\033[97m",
    "Gray":   "\033[90m",
}

def color(text, clr):
    return f"{COLOR_CODES.get(clr, '')}{text}{COLOR_CODES['Reset']}"

def bold(text):
    return f"{COLOR_CODES['Bold']}{text}{COLOR_CODES['Reset']}"


# ─────────────────────────────────────────────
#  DISPLAY HELPERS
# ─────────────────────────────────────────────
def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")

def print_banner():
    print(color("=" * 52, "Cyan"))
    print(color("   🃏  UNO  —  Pi Party Edition  🎉", "Bold"))
    print(color("=" * 52, "Cyan"))

def format_card(card):
    """Format a card for display with color."""
    c = card["color"]
    v = card["value"]
    if c == "Wild":
        return color(f"[{v}]", "Wild")
    return color(f"[{c} {v}]", c)

def print_hand(hand, highlight_playable=None, top_card=None, declared_color=None):
    """Print a numbered list of cards in the player's hand."""
    print(bold("\n📋 Your Hand:"))
    for i, card in enumerate(hand):
        playable = ""
        if highlight_playable and top_card:
            if can_play(card, top_card, declared_color):
                playable = color(" ✓", "Green")
            else:
                playable = color(" ✗", "Gray")
        print(f"  {i+1:2}. {format_card(card)}{playable}")

def print_top_card(top_card, declared_color=None):
    """Print the current top of discard pile."""
    card_str = format_card(top_card)
    dc = f"  (Declared: {color(declared_color, declared_color)})" if declared_color else ""
    print(f"\n🎴 Top Card: {card_str}{dc}")

def print_players(player_card_counts, current_player, my_name, player_order):
    """Print all players and their card counts."""
    print(bold("\n👥 Players:"))
    for name in player_order:
        count = player_card_counts.get(name, 0)
        marker = color(" ◄ THEIR TURN", "Yellow") if name == current_player else ""
        me = color(" (you)", "Cyan") if name == my_name else ""
        uno_alert = color(" 🚨 UNO!", "Red") if count == 1 else ""
        print(f"  {'→' if name == current_player else ' '} {name}{me}: {count} card(s){uno_alert}{marker}")

def can_play(card, top_card, declared_color=None):
    """Client-side check if a card can be played."""
    if card["value"] in ("Wild", "WildDraw4"):
        return True
    active_color = declared_color if top_card["value"] in ("Wild", "WildDraw4") else top_card["color"]
    if card["color"] == active_color:
        return True
    if card["value"] == top_card["value"]:
        return True
    return False

def print_game_state(state, my_name, pending_draw=0):
    """Render the full game board."""
    clear_screen()
    print_banner()

    top_card = state.get("top_card")
    declared_color = state.get("declared_color")
    current_player = state.get("current_player")
    hand = state.get("your_hand", [])
    player_order = state.get("player_order", [])
    player_card_counts = state.get("player_card_counts", {})
    direction_val = state.get("direction", 1)
    turn = state.get("turn_count", 0)
    pending = state.get("pending_draw", 0)

    direction_str = color("↻ Clockwise", "Green") if direction_val == 1 else color("↺ Counter-CW", "Yellow")
    print(f"\n  Turn #{turn}  |  Direction: {direction_str}")

    if top_card:
        print_top_card(top_card, declared_color)

    if pending > 0:
        print(color(f"\n⚠️  Pending Draw: {pending} cards (draw or stack!)", "Red"))

    print_players(player_card_counts, current_player, my_name, player_order)

    if hand:
        print_hand(hand, highlight_playable=True, top_card=top_card, declared_color=declared_color)

    is_my_turn = current_player == my_name
    print()
    if is_my_turn:
        print(color("  ★  IT'S YOUR TURN!", "Yellow"))
    else:
        print(color(f"  Waiting for {current_player}...", "Gray"))

    print(color("\n─" * 52, "Gray"))


# ─────────────────────────────────────────────
#  INPUT HELPERS
# ─────────────────────────────────────────────
def get_input(prompt, valid_options=None, allow_empty=False):
    """Get validated input from the user."""
    while True:
        try:
            val = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[Disconnected]")
            sys.exit(0)
        if allow_empty and val == "":
            return val
        if valid_options and val.lower() not in [v.lower() for v in valid_options]:
            print(color(f"  Invalid input. Choose: {', '.join(valid_options)}", "Red"))
            continue
        return val

def choose_card_to_play(hand, top_card, declared_color, pending_draw):
    """Let the player pick a card or draw."""
    playable = [i for i, c in enumerate(hand) if can_play(c, top_card, declared_color)]

    if pending_draw > 0:
        print(color(f"\n⚠️  You must draw {pending_draw} cards — unless you can stack a matching draw card!", "Red"))

    if not playable and pending_draw == 0:
        print(color("\n  No playable cards. You must draw.", "Gray"))
        input("  Press Enter to draw a card...")
        return "draw", None

    print(color(f"\n  Options:", "Cyan"))
    print(f"    Enter a card number (1–{len(hand)}) to play")
    print(f"    Type 'd' to draw a card")
    print(f"    Type 'u' to say UNO (when you have 2 cards!)")
    print(f"    Type 'c' to challenge UNO")
    print(f"    Type 'chat' to send a message")
    print(f"    Type 'q' to quit")

    while True:
        raw = input(color("\n  Your move: ", "Bold")).strip()
        if raw.lower() == "d":
            return "draw", None
        if raw.lower() == "u":
            return "uno", None
        if raw.lower() == "c":
            return "challenge", None
        if raw.lower() == "chat":
            msg = input("  Message: ").strip()
            return "chat", msg
        if raw.lower() == "q":
            print("  Thanks for playing!")
            sys.exit(0)
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(hand):
                card = hand[idx]
                if can_play(card, top_card, declared_color):
                    return "play", idx
                else:
                    print(color("  That card can't be played right now.", "Red"))
            else:
                print(color(f"  Please enter a number between 1 and {len(hand)}.", "Red"))
        else:
            print(color("  Invalid input.", "Red"))

def choose_color():
    """Prompt player to choose a color after playing a Wild."""
    print(color("\n🎨 Choose a color:", "Bold"))
    for i, c in enumerate(COLORS, 1):
        print(f"  {i}. {color(c, c)}")
    while True:
        raw = input("  Enter 1–4 or color name: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= 4:
            return COLORS[int(raw) - 1]
        for c in COLORS:
            if raw.lower() == c.lower():
                return c
        print(color("  Invalid. Choose Red, Green, Blue, or Yellow.", "Red"))


# ─────────────────────────────────────────────
#  UNO CLIENT
# ─────────────────────────────────────────────
class UnoClient:
    def __init__(self):
        self.sock = None
        self.my_name = ""
        self.current_state = None
        self.game_started = False
        self.game_over = False
        self.running = True
        self.lock = threading.Lock()
        self.my_turn_event = threading.Event()
        self.pending_messages = []   # Queued server messages to display
        self.choose_color_flag = False

    def connect(self, host, port):
        """Connect to the server."""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((host, port))

    def _send(self, data):
        try:
            msg = json.dumps(data) + "\n"
            self.sock.sendall(msg.encode("utf-8"))
        except Exception as e:
            print(color(f"\n[Error sending] {e}", "Red"))

    def _recv_loop(self):
        """Background thread: continuously receive messages from server."""
        buffer = ""
        while self.running:
            try:
                chunk = self.sock.recv(4096).decode("utf-8")
                if not chunk:
                    print(color("\n[Server disconnected]", "Red"))
                    self.running = False
                    break
                buffer += chunk
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if line:
                        try:
                            data = json.loads(line)
                            self._handle_server_message(data)
                        except json.JSONDecodeError:
                            pass
            except Exception:
                self.running = False
                break

    def _handle_server_message(self, data):
        """Process a message received from the server."""
        msg_type = data.get("type")

        if msg_type == "name_request":
            # Handled in main flow
            pass

        elif msg_type == "lobby_joined":
            print(color(f"\n✅ {data['message']}", "Green"))
            print(f"  Players in lobby: {', '.join(data['players'])}")
            print(color(f"\n  Waiting for {data['min_players']}–{data['max_players']} players...", "Gray"))
            print(color("  Type 'start' to start the game (if you're the host)\n", "Cyan"))

        elif msg_type == "player_joined":
            print(color(f"\n🎉 {data['message']}", "Green"))
            print(f"  Players: {', '.join(data['players'])}")

        elif msg_type == "player_left":
            print(color(f"\n👋 {data['message']}", "Yellow"))

        elif msg_type == "game_starting":
            print(color(f"\n🃏 {data['message']}", "Bold"))
            time.sleep(0.5)

        elif msg_type == "game_state":
            with self.lock:
                self.current_state = data.get("state")
                self.game_started = True
            message = data.get("message", "")
            if message:
                self.pending_messages.append(color(f"\n  📢 {message}", "Cyan"))

            # Trigger turn if it's ours
            if self.current_state and self.current_state.get("current_player") == self.my_name:
                if not self.current_state.get("game_over"):
                    self.my_turn_event.set()

        elif msg_type == "drew_cards":
            cards_str = ", ".join(format_card(c) for c in data.get("cards", []))
            self.pending_messages.append(color(f"\n  🎴 You drew: {cards_str}", "Yellow"))

        elif msg_type == "choose_color":
            self.choose_color_flag = True

        elif msg_type == "uno_called":
            self.pending_messages.append(color(f"\n  🚨 {data['message']}", "Red"))

        elif msg_type in ("uno_challenge_success", "uno_challenge_fail"):
            self.pending_messages.append(color(f"\n  ⚡ {data['message']}", "Yellow"))

        elif msg_type == "chat":
            self.pending_messages.append(color(f"\n  💬 [{data['from']}]: {data['message']}", "White"))

        elif msg_type == "game_over":
            self.game_over = True
            self.pending_messages.append(color(f"\n  🏆 {data['message']}", "Bold"))
            self.my_turn_event.set()  # Unblock input loop

        elif msg_type == "error":
            self.pending_messages.append(color(f"\n  ❌ {data['message']}", "Red"))

    def _flush_messages(self):
        """Print any pending messages."""
        with self.lock:
            msgs = self.pending_messages[:]
            self.pending_messages = []
        for m in msgs:
            print(m)

    def run(self):
        """Main client flow."""
        clear_screen()
        print_banner()

        # Get server IP
        host = input(color("\n  Enter host IP address: ", "Cyan")).strip()
        if not host:
            host = "127.0.0.1"

        port_str = input(color(f"  Enter port [{DEFAULT_PORT}]: ", "Cyan")).strip()
        port = int(port_str) if port_str.isdigit() else DEFAULT_PORT

        print(color(f"\n  Connecting to {host}:{port}...", "Gray"))
        try:
            self.connect(host, port)
        except Exception as e:
            print(color(f"\n  ❌ Could not connect: {e}", "Red"))
            print("  Make sure the server is running and the IP/port is correct.")
            sys.exit(1)

        # Start receiver thread
        recv_thread = threading.Thread(target=self._recv_loop)
        recv_thread.daemon = True
        recv_thread.start()

        # Wait for name request
        time.sleep(0.3)
        self.my_name = input(color("  Your name: ", "Cyan")).strip()[:16]
        if not self.my_name:
            self.my_name = "Player"
        self._send({"type": "name", "name": self.my_name})

        print(color(f"\n  Hello, {self.my_name}! Waiting in lobby...", "Green"))

        # Lobby loop — wait for game to start, allow manual start
        while not self.game_started and self.running:
            self._flush_messages()
            try:
                cmd = input("  > ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                break
            if cmd == "start":
                self._send({"type": "start_game"})
            elif cmd == "quit" or cmd == "q":
                sys.exit(0)
            elif cmd:
                self._send({"type": "chat", "message": cmd})
            time.sleep(0.1)

        # Main game loop
        while not self.game_over and self.running:
            # Wait for our turn
            self.my_turn_event.wait(timeout=0.5)

            with self.lock:
                state = self.current_state
                is_my_turn = state and state.get("current_player") == self.my_name if state else False
                game_over = state.get("game_over") if state else False

            if game_over or self.game_over:
                self._flush_messages()
                break

            if not is_my_turn:
                # Display state and flush messages while waiting
                if state:
                    print_game_state(state, self.my_name)
                    self._flush_messages()
                time.sleep(0.5)
                continue

            # It's our turn!
            self.my_turn_event.clear()

            with self.lock:
                state = self.current_state

            print_game_state(state, self.my_name)
            self._flush_messages()

            # Handle color choice if needed
            if self.choose_color_flag:
                chosen = choose_color()
                self._send({"type": "declare_color", "color": chosen})
                self.choose_color_flag = False
                continue

            top_card = state.get("top_card")
            declared_color = state.get("declared_color")
            hand = state.get("your_hand", [])
            pending = state.get("pending_draw", 0)

            action, data = choose_card_to_play(hand, top_card, declared_color, pending)

            if action == "play":
                card = hand[data]
                self._send({"type": "play_card", "color": card["color"], "value": card["value"]})

                # If it's a wild, wait briefly then ask for color
                if card["value"] in ("Wild", "WildDraw4"):
                    time.sleep(0.3)
                    chosen = choose_color()
                    self._send({"type": "declare_color", "color": chosen})

                # Auto say UNO if 2 cards (after playing = 1 left)
                if len(hand) == 2:
                    time.sleep(0.1)
                    self._send({"type": "say_uno"})
                    print(color("\n  🚨 UNO! (auto-called)", "Red"))

            elif action == "draw":
                self._send({"type": "draw_card"})

            elif action == "uno":
                self._send({"type": "say_uno"})
                print(color("  🚨 UNO called!", "Red"))

            elif action == "challenge":
                self._send({"type": "challenge_uno"})
                print(color("  ⚡ UNO challenge sent!", "Yellow"))

            elif action == "chat":
                self._send({"type": "chat", "message": data})

            time.sleep(0.2)

        # Game over
        print_banner()
        if self.current_state:
            winner = self.current_state.get("winner")
            if winner:
                if winner == self.my_name:
                    print(color("\n  🏆 YOU WIN! Congratulations! 🎉", "Bold"))
                else:
                    print(color(f"\n  {winner} wins the game. Better luck next time!", "Yellow"))
        self._flush_messages()
        print(color("\n  Thanks for playing Pi Party UNO!\n", "Cyan"))
        input("  Press Enter to exit...")


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    client = UnoClient()
    client.run()
