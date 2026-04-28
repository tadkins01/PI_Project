"""
================================================================================
  Pi Party Games — Multiplayer Terminal Games over LAN
  Compatible with Raspberry Pi OS & Ubuntu LTS
  Requires: Python 3.7+  |  No external packages needed
================================================================================

  Usage:
    python3 game.py              # Interactive menu
    python3 game.py --host       # Jump straight to hosting
    python3 game.py --join       # Jump straight to joining

  Games:
    1. Heads or Tails
    2. Rock Paper Scissors
    3. Strategic Snake
    4. Number Guess (1–15)
    5. Pacman Chase
================================================================================
"""

import socket
import threading
import random
import json
import time
import sys
import os
import argparse
import curses
import subprocess
from collections import defaultdict


# ── ANSI Colors ────────────────────────────────────────────────────────────────

class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    RED     = "\033[91m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    BLUE    = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN    = "\033[96m"
    WHITE   = "\033[97m"
    BG_BLUE = "\033[44m"
    BG_RED  = "\033[41m"

def cprint(text, color=C.WHITE):
    print(f"{color}{text}{C.RESET}")

def banner():
    subprocess.run("cls" if os.name == "nt" else "clear", shell=False, check=False)
    print(f"""
{C.CYAN}{C.BOLD}
 ██████╗ ██╗    ██████╗  █████╗ ██████╗ ████████╗██╗   ██╗
 ██╔══██╗██║    ██╔══██╗██╔══██╗██╔══██╗╚══██╔══╝╚██╗ ██╔╝
 ██████╔╝██║    ██████╔╝███████║██████╔╝   ██║    ╚████╔╝ 
 ██╔═══╝ ██║    ██╔═══╝ ██╔══██║██╔══██╗   ██║     ╚██╔╝  
 ██║     ██║    ██║     ██║  ██║██║  ██║   ██║      ██║   
 ╚═╝     ╚═╝    ╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝      ╚═╝   
{C.RESET}{C.YELLOW}            🎮  Pi Party Games  🎮{C.RESET}
{C.DIM}       Multiplayer LAN games for Raspberry Pi & Ubuntu{C.RESET}
""")


# ── Networking Helpers ─────────────────────────────────────────────────────────

PORT = 65432
BUFFER = 4096

def get_local_ip():
    """Best-effort local IP detection."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def send_msg(sock, data: dict):
    """Send a JSON message over a socket."""
    try:
        raw = json.dumps(data).encode()
        sock.sendall(raw + b"\n")
    except Exception:
        pass

def recv_msg(sock) -> dict | None:
    """Receive a newline-delimited JSON message."""
    try:
        buf = b""
        while True:
            chunk = sock.recv(BUFFER)
            if not chunk:
                return None
            buf += chunk
            if b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                return json.loads(line.decode())
    except Exception:
        return None


# ── Game Logic ─────────────────────────────────────────────────────────────────

class HeadsOrTails:
    NAME = "Heads or Tails"
    CHOICES = ["heads", "tails"]

    @staticmethod
    def prompt_choice() -> str:
        while True:
            cprint("\n  Your guess:", C.CYAN)
            cprint("    [H] Heads", C.WHITE)
            cprint("    [T] Tails", C.WHITE)
            raw = input(f"\n  {C.BOLD}> {C.RESET}").strip().lower()
            if raw in ("h", "heads"):
                return "heads"
            if raw in ("t", "tails"):
                return "tails"
            cprint("  ⚠  Please enter H or T.", C.YELLOW)

    @staticmethod
    def resolve(choices: dict) -> dict:
        """choices = {player_name: 'heads'|'tails'}"""
        flip = random.choice(HeadsOrTails.CHOICES)
        winners = [p for p, c in choices.items() if c == flip]
        return {"flip": flip, "winners": winners, "choices": choices}

    @staticmethod
    def format_result(result: dict, my_name: str) -> str:
        flip = result["flip"].upper()
        choices = result["choices"]
        winners = result["winners"]
        lines = [f"\n  🪙  The coin landed on: {C.BOLD}{C.YELLOW}{flip}{C.RESET}\n"]
        for player, choice in choices.items():
            tag = " ← you" if player == my_name else ""
            mark = f"{C.GREEN}✔" if player in winners else f"{C.RED}✘"
            lines.append(f"  {mark}{C.RESET}  {player}: {choice}{C.DIM}{tag}{C.RESET}")
        if my_name in winners:
            lines.append(f"\n  {C.GREEN}{C.BOLD}🎉 You guessed right!{C.RESET}")
        else:
            lines.append(f"\n  {C.RED}Better luck next time!{C.RESET}")
        return "\n".join(lines)


class RockPaperScissors:
    NAME = "Rock Paper Scissors"
    BEATS = {"rock": "scissors", "scissors": "paper", "paper": "rock"}
    EMOJI = {"rock": "🪨", "scissors": "✂️ ", "paper": "📄"}

    @staticmethod
    def prompt_choice() -> str:
        while True:
            cprint("\n  Your move:", C.CYAN)
            cprint("    [R] Rock", C.WHITE)
            cprint("    [P] Paper", C.WHITE)
            cprint("    [S] Scissors", C.WHITE)
            raw = input(f"\n  {C.BOLD}> {C.RESET}").strip().lower()
            if raw in ("r", "rock"):
                return "rock"
            if raw in ("p", "paper"):
                return "paper"
            if raw in ("s", "scissors"):
                return "scissors"
            cprint("  ⚠  Please enter R, P, or S.", C.YELLOW)

    @staticmethod
    def resolve(choices: dict) -> dict:
        """Works for 2+ players. Each player beats those they defeat."""
        players = list(choices.keys())
        scores = {p: 0 for p in players}
        for i, p1 in enumerate(players):
            for p2 in players[i+1:]:
                c1, c2 = choices[p1], choices[p2]
                if c1 == c2:
                    pass  # tie
                elif RockPaperScissors.BEATS[c1] == c2:
                    scores[p1] += 1
                else:
                    scores[p2] += 1
        max_score = max(scores.values())
        winners = [p for p, s in scores.items() if s == max_score]
        # True winner only if they beat everyone
        true_winners = winners if len(winners) < len(players) else []
        return {
            "choices": choices,
            "scores": scores,
            "winners": true_winners,
            "tie": len(true_winners) == 0
        }

    @staticmethod
    def format_result(result: dict, my_name: str) -> str:
        choices = result["choices"]
        winners = result["winners"]
        tie = result["tie"]
        emoji = RockPaperScissors.EMOJI
        lines = [f"\n  {C.BOLD}── Results ──{C.RESET}\n"]
        for player, choice in choices.items():
            tag = " ← you" if player == my_name else ""
            won = player in winners
            mark = f"{C.GREEN}✔" if won else f"{C.DIM} "
            lines.append(f"  {mark}{C.RESET}  {player}: {emoji.get(choice,'?')} {choice}{C.DIM}{tag}{C.RESET}")
        if tie:
            lines.append(f"\n  {C.YELLOW}{C.BOLD}🤝 It's a tie!{C.RESET}")
        elif my_name in winners:
            lines.append(f"\n  {C.GREEN}{C.BOLD}🏆 You win!{C.RESET}")
        else:
            lines.append(f"\n  {C.RED}You lost this round.{C.RESET}")
        return "\n".join(lines)


class NumberGuess:
    NAME = "Number Guess (1–15)"
    TARGET_MIN = 1
    TARGET_MAX = 15

    @staticmethod
    def prompt_choice() -> str:
        while True:
            cprint(f"\n  Guess a number ({NumberGuess.TARGET_MIN}–{NumberGuess.TARGET_MAX}):", C.CYAN)
            raw = input(f"  {C.BOLD}> {C.RESET}").strip()
            try:
                num = int(raw)
                if NumberGuess.TARGET_MIN <= num <= NumberGuess.TARGET_MAX:
                    return str(num)
            except ValueError:
                pass
            cprint(f"  ⚠  Please enter a valid number between {NumberGuess.TARGET_MIN} and {NumberGuess.TARGET_MAX}.", C.YELLOW)

    @staticmethod
    def resolve(choices: dict) -> dict:
        """choices = {player_name: '5'}"""
        target = random.randint(NumberGuess.TARGET_MIN, NumberGuess.TARGET_MAX)
        
        # Find closest guesses
        guesses = {p: int(c) for p, c in choices.items()}
        distances = {p: abs(guess - target) for p, guess in guesses.items()}
        min_dist = min(distances.values()) if distances else 999
        winners = [p for p, d in distances.items() if d == min_dist]
        
        return {
            "target": target,
            "guesses": guesses,
            "distances": distances,
            "winners": winners
        }

    @staticmethod
    def format_result(result: dict, my_name: str) -> str:
        target = result["target"]
        guesses = result["guesses"]
        distances = result["distances"]
        winners = result["winners"]
        
        lines = [f"\n  🎯  The target was: {C.BOLD}{C.YELLOW}{target}{C.RESET}\n"]
        for player, guess in sorted(guesses.items(), key=lambda x: distances[x[0]]):
            tag = " ← you" if player == my_name else ""
            dist = distances[player]
            mark = f"{C.GREEN}✔" if player in winners else f"{C.RED} "
            lines.append(f"  {mark}{C.RESET}  {player}: {guess} (off by {dist}){C.DIM}{tag}{C.RESET}")
        
        if my_name in winners:
            lines.append(f"\n  {C.GREEN}{C.BOLD}🎉 You were closest!{C.RESET}")
        else:
            lines.append(f"\n  {C.RED}Better luck next time!{C.RESET}")
        return "\n".join(lines)


class PacmanChase:
    """Pacman game with walls, 3 lives, and proper curses rendering."""
    NAME = "Pacman Chase"
    GRID_WIDTH = 22
    GRID_HEIGHT = 13
    TICK_RATE = 0.15
    MAX_LIVES = 3
    DIRECTION_KEYS = {
        ord("w"): (0, -1),
        ord("W"): (0, -1),
        curses.KEY_UP: (0, -1),
        ord("s"): (0, 1),
        ord("S"): (0, 1),
        curses.KEY_DOWN: (0, 1),
        ord("a"): (-1, 0),
        ord("A"): (-1, 0),
        curses.KEY_LEFT: (-1, 0),
        ord("d"): (1, 0),
        ord("D"): (1, 0),
        curses.KEY_RIGHT: (1, 0),
    }

    # 1 = wall, 0 = open. Must match GRID_HEIGHT x GRID_WIDTH.
    LAYOUT = [
        [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
        [1,0,0,0,0,0,0,0,0,0,0,1,0,0,0,0,0,0,0,0,0,1],
        [1,0,1,1,0,1,1,1,0,1,0,1,0,1,0,1,1,1,0,1,0,1],
        [1,0,1,0,0,0,0,0,0,1,0,0,0,1,0,0,0,0,0,0,0,1],
        [1,0,1,0,1,1,0,1,0,1,1,1,1,1,0,1,0,1,1,0,0,1],
        [1,0,0,0,1,0,0,0,0,0,0,0,0,0,0,0,0,1,0,0,0,1],
        [1,1,1,0,1,0,1,1,0,1,1,0,1,1,0,1,0,1,0,1,1,1],
        [1,0,0,0,1,0,0,0,0,0,0,0,0,0,0,0,0,1,0,0,0,1],
        [1,0,1,0,1,1,0,1,0,1,1,1,1,1,0,1,0,1,1,0,0,1],
        [1,0,1,0,0,0,0,0,0,1,0,0,0,1,0,0,0,0,0,0,0,1],
        [1,0,1,1,0,1,1,1,0,1,0,1,0,1,0,1,1,1,0,1,0,1],
        [1,0,0,0,0,0,0,0,0,0,0,1,0,0,0,0,0,0,0,0,0,1],
        [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
    ]
    WALL_CHAR  = "█"
    EMPTY_CHAR = " "
    PELLET_CHAR = "·"
    PACMAN_CHAR = "C"
    GHOST_CHAR  = "G"

    @staticmethod
    def _open_cells():
        """Return all non-wall cell coordinates."""
        return [
            (x, y)
            for y, row in enumerate(PacmanChase.LAYOUT)
            for x, cell in enumerate(row)
            if cell == 0
        ]

    @staticmethod
    def _is_wall(x, y) -> bool:
        gw, gh = PacmanChase.GRID_WIDTH, PacmanChase.GRID_HEIGHT
        if not (0 <= x < gw and 0 <= y < gh):
            return True
        return PacmanChase.LAYOUT[y][x] == 1

    @staticmethod
    def _reset_positions(open_cells):
        """Pick a random starting cell for Pacman away from edges."""
        interior = [(x, y) for x, y in open_cells if 2 <= x <= PacmanChase.GRID_WIDTH - 3
                    and 2 <= y <= PacmanChase.GRID_HEIGHT - 3]
        px, py = random.choice(interior if interior else open_cells)
        ghosts = []
        for _ in range(2):
            candidates = [(x, y) for x, y in open_cells
                          if abs(x - px) + abs(y - py) > 5]
            ghosts.append(random.choice(candidates if candidates else open_cells))
        return px, py, ghosts

    @staticmethod
    def prompt_choice() -> str:
        """Run a Pacman game with 3 lives and return final score."""
        score = 0

        def _run_game(stdscr):
            nonlocal score
            curses.curs_set(0)
            stdscr.nodelay(True)
            stdscr.timeout(50)

            open_cells = PacmanChase._open_cells()
            direction = (0, 0)
            lives = PacmanChase.MAX_LIVES
            game_time = 45
            start_t = time.time()

            # Seed pellets on open cells
            pellets = set(random.sample(open_cells, min(12, len(open_cells))))

            pacman_x, pacman_y, ghosts = PacmanChase._reset_positions(open_cells)

            def render():
                stdscr.clear()
                for y, row in enumerate(PacmanChase.LAYOUT):
                    line = ""
                    for x, cell in enumerate(row):
                        if cell == 1:
                            line += PacmanChase.WALL_CHAR
                        elif x == pacman_x and y == pacman_y:
                            line += PacmanChase.PACMAN_CHAR
                        elif (x, y) in [(gx, gy) for gx, gy in ghosts]:
                            line += PacmanChase.GHOST_CHAR
                        elif (x, y) in pellets:
                            line += PacmanChase.PELLET_CHAR
                        else:
                            line += PacmanChase.EMPTY_CHAR
                    try:
                        stdscr.addstr(y, 0, line)
                    except curses.error:
                        pass
                time_left = max(0, int(game_time - (time.time() - start_t)))
                hearts = "♥ " * lives
                try:
                    stdscr.addstr(
                        PacmanChase.GRID_HEIGHT, 0,
                        f" Score: {score:<5}  Lives: {hearts}  Time: {time_left:>2}s  [WASD/arrows] [Q quit]"
                    )
                except curses.error:
                    pass
                stdscr.refresh()

            ghost_tick = 0  # ghosts move every other game tick (slower than pacman)

            while time.time() - start_t < game_time and lives > 0:
                # --- Input ---
                key = stdscr.getch()
                if key in PacmanChase.DIRECTION_KEYS:
                    direction = PacmanChase.DIRECTION_KEYS[key]
                elif key == ord("q"):
                    break

                # --- Move Pacman ---
                nx = pacman_x + direction[0]
                ny = pacman_y + direction[1]
                if not PacmanChase._is_wall(nx, ny):
                    pacman_x, pacman_y = nx, ny

                # --- Pellet ---
                if (pacman_x, pacman_y) in pellets:
                    pellets.discard((pacman_x, pacman_y))
                    score += 10
                    # Respawn pellet elsewhere
                    empty = [c for c in open_cells if c not in pellets
                             and c != (pacman_x, pacman_y)]
                    if empty:
                        pellets.add(random.choice(empty))

                # --- Move Ghosts (half speed) ---
                ghost_tick += 1
                if ghost_tick % 2 == 0:
                    new_ghosts = []
                    for gx, gy in ghosts:
                        dx = 1 if pacman_x > gx else (-1 if pacman_x < gx else 0)
                        dy = 1 if pacman_y > gy else (-1 if pacman_y < gy else 0)
                        # Try primary direction; fall back to alternatives
                        moved = False
                        for attempt in [(dx, dy), (dx, 0), (0, dy),
                                        (random.choice([-1, 1]), 0), (0, random.choice([-1, 1]))]:
                            ax, ay = attempt
                            if ax == 0 and ay == 0:
                                continue
                            cx, cy = (gx + ax) % PacmanChase.GRID_WIDTH, (gy + ay) % PacmanChase.GRID_HEIGHT
                            if not PacmanChase._is_wall(cx, cy):
                                new_ghosts.append((cx, cy))
                                moved = True
                                break
                        if not moved:
                            new_ghosts.append((gx, gy))
                    ghosts = new_ghosts

                # --- Ghost collision ---
                caught = any(gx == pacman_x and gy == pacman_y for gx, gy in ghosts)
                if caught:
                    lives -= 1
                    render()
                    time.sleep(0.6)
                    if lives > 0:
                        # Respawn Pacman away from ghosts; ghosts also reset
                        pacman_x, pacman_y, ghosts = PacmanChase._reset_positions(open_cells)
                        direction = (0, 0)

                render()
                time.sleep(PacmanChase.TICK_RATE)

        try:
            curses.wrapper(_run_game)
        except Exception:
            pass

        return str(score)

    @staticmethod
    def resolve(choices: dict) -> dict:
        """choices = {player_name: 'score'}"""
        scores = {p: int(c) for p, c in choices.items()}
        max_score = max(scores.values()) if scores else 0
        winners = [p for p, s in scores.items() if s == max_score]
        return {
            "scores": scores,
            "winners": winners
        }

    @staticmethod
    def format_result(result: dict, my_name: str) -> str:
        scores = result["scores"]
        winners = result["winners"]
        lines = [f"\n  👾  Pacman Chase Results:\n"]
        for player, score in sorted(scores.items(), key=lambda x: -x[1]):
            tag = " ← you" if player == my_name else ""
            mark = f"{C.GREEN}✔" if player in winners else f"{C.DIM} "
            lines.append(f"  {mark}{C.RESET}  {player}: {C.YELLOW}{score}{C.RESET} pts{C.DIM}{tag}{C.RESET}")
        
        if my_name in winners:
            lines.append(f"\n  {C.GREEN}{C.BOLD}🏆 You had the highest score!{C.RESET}")
        else:
            lines.append(f"\n  {C.RED}Better luck next time!{C.RESET}")
        return "\n".join(lines)


# Game registry
GAMES = {
    "1": HeadsOrTails,
    "2": RockPaperScissors,
    "3": NumberGuess,
    "4": PacmanChase,
}


# ── Server ─────────────────────────────────────────────────────────────────────

class Server:
    def __init__(self, host_plays=False):
        self.clients = {}
        self.host_plays = host_plays
        self.running = True
        self.client_lock = threading.Lock()
        self.pending_choices: dict = {}   # written by handle_client, read by collect_choices
        self.choices_lock = threading.Lock()

    def broadcast(self, data: dict):
        """Send message to all connected clients."""
        dead_clients = []
        with self.client_lock:
            for name, sock in self.clients.items():
                if not send_msg(sock, data):
                    dead_clients.append(name)
        
        for name in dead_clients:
            with self.client_lock:
                self.clients.pop(name, None)

    def collect_choices(self, game_class, host_choice=None):
        """Collect choices from all clients, waiting up to 60 s."""
        # Clear any stale choices from a previous round
        with self.choices_lock:
            self.pending_choices.clear()
            if host_choice is not None:
                self.pending_choices["[Host] You"] = host_choice

        self.broadcast({"type": "prompt", "game": game_class.NAME})

        expected = len(self.clients) + (1 if self.host_plays else 0)
        deadline = time.time() + 60  # give players up to 60 s (e.g. Pacman game length)
        while time.time() < deadline:
            with self.choices_lock:
                if len(self.pending_choices) >= expected:
                    break
            time.sleep(0.1)

        with self.choices_lock:
            return dict(self.pending_choices)

    def handle_client(self, conn, addr):
        """Handle individual client connection."""
        name = None
        try:
            msg = recv_msg(conn)
            if not msg or msg.get("type") != "join":
                conn.close()
                return

            name = msg.get("name", "Unknown").strip()[:20]
            
            # Ensure unique name
            with self.client_lock:
                counter = 1
                original_name = name
                while any(n == name for n in self.clients.keys()):
                    name = f"{original_name}_{counter}"
                    counter += 1
                self.clients[name] = conn

            send_msg(conn, {"type": "welcome", "name": name})

            while self.running:
                msg = recv_msg(conn)
                if not msg:
                    break

                mtype = msg.get("type")
                if mtype == "choice":
                    choice = msg.get("choice", "")
                    with self.choices_lock:
                        self.pending_choices[name] = choice

        except Exception:
            pass
        finally:
            with self.client_lock:
                if name and name in self.clients:
                    self.clients.pop(name, None)
            conn.close()

    def run(self):
        """Main server loop."""
        banner()
        cprint("  ══════════════════════════════════════", C.MAGENTA)
        cprint("   🖥   HOST MODE", C.MAGENTA + C.BOLD)
        cprint("  ══════════════════════════════════════", C.MAGENTA)

        local_ip = get_local_ip()
        cprint(f"\n  📡  Server IP: {C.BOLD}{C.YELLOW}{local_ip}:{PORT}{C.RESET}", C.GREEN)
        cprint("  Players can connect by entering this IP address.", C.DIM)
        cprint(f"\n  {C.DIM}Press [Enter] when ready to start...{C.RESET}")

        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind(("0.0.0.0", PORT))
        server_sock.listen(5)
        server_sock.settimeout(0.5)

        def accept_loop():
            while self.running:
                try:
                    conn, addr = server_sock.accept()
                    t = threading.Thread(target=self.handle_client, args=(conn, addr), daemon=True)
                    t.start()
                except socket.timeout:
                    continue
                except Exception:
                    break

        accept_thread = threading.Thread(target=accept_loop, daemon=True)
        accept_thread.start()

        input()

        if not self.clients and not self.host_plays:
            cprint("\n  ⚠  No players connected. Exiting.", C.YELLOW)
            self.running = False
            return

        total_players = len(self.clients) + (1 if self.host_plays else 0)
        cprint(f"\n  🎮  Starting with {total_players} player(s)!\n", C.GREEN + C.BOLD)

        self.broadcast({"type": "start"})

        scores = {name: 0 for name in self.clients}
        if self.host_plays:
            scores["[Host] You"] = 0

        round_num = 0

        while True:
            round_num += 1
            cprint(f"\n  ══ Round {round_num} ══", C.CYAN + C.BOLD)

            cprint("\n  Select a game:", C.WHITE + C.BOLD)
            for key, g in GAMES.items():
                cprint(f"    [{key}] {g.NAME}", C.WHITE)
            cprint(f"    [Q] Quit / End session", C.DIM)

            while True:
                pick = input(f"\n  {C.BOLD}> {C.RESET}").strip().lower()
                if pick == "q":
                    break
                if pick in GAMES:
                    break
                cprint("  ⚠  Invalid choice.", C.YELLOW)

            if pick == "q":
                self.broadcast({"type": "end", "msg": "Host ended the session. Thanks for playing!"})
                cprint("\n  Session ended. Final scores:", C.CYAN + C.BOLD)
                for name, s in sorted(scores.items(), key=lambda x: -x[1]):
                    cprint(f"    {name}: {s} pts", C.WHITE)
                break

            game_class = GAMES[pick]

            self.broadcast({"type": "game_selected", "game": game_class.NAME})

            host_choice = None
            if self.host_plays:
                cprint(f"\n  {C.BOLD}[{game_class.NAME}]{C.RESET}", C.MAGENTA)
                host_choice = game_class.prompt_choice()
                cprint(f"\n  {C.DIM}Waiting for other players...{C.RESET}", C.DIM)

            choices = self.collect_choices(game_class, host_choice=host_choice)

            if not choices:
                cprint("  ⚠  No choices received.", C.YELLOW)
                continue

            result = game_class.resolve(choices)

            if self.host_plays:
                print(game_class.format_result(result, "[Host] You"))

            for winner in result.get("winners", []):
                if winner in scores:
                    scores[winner] += 1

            self.broadcast({
                "type": "result",
                "game": game_class.NAME,
                "result": result
            })

            cprint(f"\n  {C.BOLD}── Scoreboard ──{C.RESET}", C.CYAN)
            for name, s in sorted(scores.items(), key=lambda x: -x[1]):
                bar = "█" * s
                you = " ← you" if name == "[Host] You" else ""
                cprint(f"  {name}: {C.YELLOW}{bar}{C.RESET} {s}{C.DIM}{you}{C.RESET}", C.WHITE)

            again = input(f"\n  {C.BOLD}Next round? [Enter to continue / Q to quit]{C.RESET} ").strip().lower()
            if again == "q":
                self.broadcast({"type": "end", "msg": "Host ended the session. Thanks for playing!"})
                cprint("\n  Thanks for playing!", C.GREEN + C.BOLD)
                break

        self.running = False
        server_sock.close()


# ── Client ─────────────────────────────────────────────────────────────────────

class Client:
    def __init__(self):
        self.name = ""
        self.sock = None
        self.scores = defaultdict(int)

    def run(self):
        banner()
        cprint("  ══════════════════════════════════════", C.MAGENTA)
        cprint("   📡   JOIN MODE", C.MAGENTA + C.BOLD)
        cprint("  ══════════════════════════════════════", C.MAGENTA)

        cprint("\n  Enter the host's IP address:", C.WHITE)
        cprint(f"  {C.DIM}(shown on the host's screen when they start){C.RESET}", C.DIM)
        server_ip = input(f"\n  {C.BOLD}IP > {C.RESET}").strip()
        if not server_ip:
            cprint("  ⚠  No IP entered. Exiting.", C.YELLOW)
            return

        cprint("\n  Enter your player name:", C.WHITE)
        self.name = input(f"  {C.BOLD}Name > {C.RESET}").strip()[:20]
        if not self.name:
            self.name = f"Player_{random.randint(100,999)}"

        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((server_ip, PORT))
        except Exception:
            cprint(f"\n  ✘  Could not connect to {server_ip}:{PORT}", C.RED)
            return

        send_msg(self.sock, {"type": "join", "name": self.name})
        msg = recv_msg(self.sock)
        if not msg or msg.get("type") != "welcome":
            cprint("  ✘  Unexpected response from server.", C.RED)
            return

        confirmed_name = msg.get("name", self.name)
        cprint(f"\n  {C.GREEN}✔  Connected! You joined as: {C.BOLD}{confirmed_name}{C.RESET}", C.GREEN)
        cprint(f"  {C.DIM}Waiting for the host to start...{C.RESET}\n", C.DIM)

        game_map = {g.NAME: g for g in GAMES.values()}

        while True:
            msg = recv_msg(self.sock)
            if msg is None:
                cprint("\n  ✘  Disconnected from server.", C.RED)
                break

            mtype = msg.get("type")

            if mtype == "chat":
                cprint(msg.get("msg", ""), C.DIM)
            elif mtype == "start":
                cprint(f"\n  {C.GREEN}{C.BOLD}🎮  Game is starting!{C.RESET}\n", C.GREEN)
            elif mtype == "game_selected":
                game_name = msg.get("game", "")
                cprint(f"\n  {C.BOLD}[{game_name}]{C.RESET}", C.MAGENTA)
            elif mtype == "prompt":
                game_name = msg.get("game", "")
                game_class = game_map.get(game_name)
                if game_class:
                    choice = game_class.prompt_choice()
                    send_msg(self.sock, {"type": "choice", "choice": choice})
                    cprint(f"  {C.DIM}Choice sent. Waiting for results...{C.RESET}", C.DIM)
            elif mtype == "result":
                game_name = msg.get("game", "")
                result = msg.get("result", {})
                game_class = game_map.get(game_name)
                if game_class:
                    print(game_class.format_result(result, confirmed_name))
                    for winner in result.get("winners", []):
                        self.scores[winner] += 1
                    cprint(f"\n  {C.DIM}Waiting for next round...{C.RESET}", C.DIM)
            elif mtype == "end":
                cprint(f"\n  {C.CYAN}{C.BOLD}🏁  {msg.get('msg', 'Session ended.')}{C.RESET}", C.CYAN)
                break

        self.sock.close()


# ── Main Menu ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Pi Party Games — Multiplayer LAN games")
    parser.add_argument("--host", action="store_true", help="Start as host/server")
    parser.add_argument("--join", action="store_true", help="Join an existing game")
    args = parser.parse_args()

    if args.host:
        Server(host_plays=True).run()
        return
    if args.join:
        Client().run()
        return

    banner()
    cprint("  ══════════════════════════════════════", C.CYAN)
    cprint("   What would you like to do?", C.WHITE + C.BOLD)
    cprint("  ══════════════════════════════════════\n", C.CYAN)
    cprint("    [1]  🖥   Host a game  (you are the server)", C.WHITE)
    cprint("    [2]  📡   Join a game  (connect to a host)", C.WHITE)
    cprint("    [Q]       Quit\n", C.DIM)

    while True:
        choice = input(f"  {C.BOLD}> {C.RESET}").strip().lower()
        if choice in ("1", "host"):
            Server(host_plays=True).run()
            break
        elif choice in ("2", "join"):
            Client().run()
            break
        elif choice in ("q", "quit"):
            break

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        cprint("\n\n  👋 Thanks for playing!", C.CYAN)
        sys.exit(0)