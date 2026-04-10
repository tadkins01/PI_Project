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
    os.system("clear" if os.name != "nt" else "cls")
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
                line, _ = buf.split(b"\n", 1)
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


class SnakeGame:
    NAME = "Strategic Snake"
    GRID_WIDTH = 24
    GRID_HEIGHT = 14
    TICK_RATE = 0.12
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

    @staticmethod
    def _spawn_food(snake: list[tuple[int, int]]) -> tuple[int, int]:
        while True:
            food = (
                random.randint(1, SnakeGame.GRID_WIDTH - 2),
                random.randint(1, SnakeGame.GRID_HEIGHT - 2),
            )
            if food not in snake:
                return food

    @staticmethod
    def _draw_board(stdscr, snake: list[tuple[int, int]], food: tuple[int, int], score: int):
        stdscr.clear()
        stdscr.addstr(0, 0, "Snake: use WASD or arrow keys. Press Q to quit.")
        stdscr.addstr(1, 0, f"Score: {score}")

        for y in range(SnakeGame.GRID_HEIGHT):
            row = []
            for x in range(SnakeGame.GRID_WIDTH):
                pos = (x, y)
                if x == 0 or y == 0 or x == SnakeGame.GRID_WIDTH - 1 or y == SnakeGame.GRID_HEIGHT - 1:
                    row.append("##")
                elif pos == snake[0]:
                    row.append("[]")
                elif pos in snake[1:]:
                    row.append("[]")
                elif pos == food:
                    row.append("()")
                else:
                    row.append("  ")
            stdscr.addstr(y + 3, 0, "".join(row))
        stdscr.refresh()

    @staticmethod
    def _run_curses_snake(stdscr) -> dict:
        curses.curs_set(0)
        stdscr.nodelay(True)
        stdscr.keypad(True)
        stdscr.timeout(int(SnakeGame.TICK_RATE * 1000))

        snake = [(SnakeGame.GRID_WIDTH // 2, SnakeGame.GRID_HEIGHT // 2)]
        snake.extend([
            (snake[0][0] - 1, snake[0][1]),
            (snake[0][0] - 2, snake[0][1]),
        ])
        direction = (1, 0)
        food = SnakeGame._spawn_food(snake)
        score = 0
        alive = True

        while alive:
            SnakeGame._draw_board(stdscr, snake, food, score)
            key = stdscr.getch()

            if key in (ord("q"), ord("Q")):
                alive = False
                break

            new_direction = SnakeGame.DIRECTION_KEYS.get(key)
            if new_direction and new_direction != (-direction[0], -direction[1]):
                direction = new_direction

            next_head = (snake[0][0] + direction[0], snake[0][1] + direction[1])
            hit_wall = (
                next_head[0] <= 0
                or next_head[0] >= SnakeGame.GRID_WIDTH - 1
                or next_head[1] <= 0
                or next_head[1] >= SnakeGame.GRID_HEIGHT - 1
            )
            hit_self = next_head in snake
            if hit_wall or hit_self:
                alive = False
                break

            snake.insert(0, next_head)
            if next_head == food:
                score += 1
                food = SnakeGame._spawn_food(snake)
            else:
                snake.pop()

        SnakeGame._draw_board(stdscr, snake, food, score)
        stdscr.addstr(SnakeGame.GRID_HEIGHT + 4, 0, f"Game over. Final score: {score}. Press any key to continue.")
        stdscr.nodelay(False)
        stdscr.getch()
        return {"score": score, "alive": alive}

    @staticmethod
    def prompt_choice() -> dict:
        cprint("\n  Launching snake...", C.CYAN)
        cprint("  Control it with WASD or the arrow keys.", C.WHITE)
        cprint("  The snake moves one block at a time. Avoid walls and yourself.", C.WHITE)
        time.sleep(1)

        if not sys.stdin.isatty() or not sys.stdout.isatty():
            cprint("  ⚠  Interactive terminal controls are not available here.", C.YELLOW)
            cprint("  Returning a score of 0 for this round.", C.YELLOW)
            return {"score": 0, "alive": False}

        try:
            return curses.wrapper(SnakeGame._run_curses_snake)
        except Exception:
            cprint("  ⚠  Snake couldn't start in curses mode on this terminal.", C.YELLOW)
            cprint("  Returning a score of 0 for this round.", C.YELLOW)
            return {"score": 0, "alive": False}

    @staticmethod
    def resolve(choices: dict) -> dict:
        """Players compete by score after each local snake run."""
        normalized = {}
        for player, result in choices.items():
            if isinstance(result, dict):
                normalized[player] = {
                    "score": int(result.get("score", 0)),
                    "alive": bool(result.get("alive", False)),
                }
            else:
                normalized[player] = {"score": 0, "alive": False}

        max_score = max((result["score"] for result in normalized.values()), default=0)
        winners = [player for player, result in normalized.items() if result["score"] == max_score and max_score > 0]
        return {"choices": normalized, "winners": winners, "high_score": max_score}

    @staticmethod
    def format_result(result: dict, my_name: str) -> str:
        choices = result["choices"]
        winners = result["winners"]
        lines = [f"\n  {C.BOLD}── Snake Results ──{C.RESET}\n"]

        ranked_players = sorted(choices.items(), key=lambda item: item[1]["score"], reverse=True)
        for player, stats in ranked_players:
            tag = " ← you" if player == my_name else ""
            if player in winners:
                mark = f"{C.GREEN}🏆"
                note = "winner"
            else:
                mark = f"{C.WHITE}🐍"
                note = "crashed" if not stats["alive"] else "finished"
            lines.append(
                f"  {mark}{C.RESET}  {player}: {C.BOLD}{stats['score']}{C.RESET} apples"
                f" {C.DIM}({note}){tag}{C.RESET}"
            )

        if not winners:
            lines.append(f"\n  {C.YELLOW}No one scored this round.{C.RESET}")
        elif my_name in winners:
            lines.append(f"\n  {C.GREEN}{C.BOLD}You won the snake round!{C.RESET}")
        else:
            winner_names = ", ".join(winners)
            lines.append(f"\n  {C.CYAN}Top score: {winner_names}.{C.RESET}")

        return "\n".join(lines)


class NumberGuess:
    NAME = "Number Guess"

    @staticmethod
    def prompt_choice() -> int:
        """Ask the player to guess a number between 1 and 15."""
        while True:
            cprint("\n  🔢  Guess the secret number!", C.CYAN)
            cprint("     Pick a number from 1 to 15:", C.WHITE)
            raw = input(f"\n  {C.BOLD}> {C.RESET}").strip()
            try:
                num = int(raw)
                if 1 <= num <= 15:
                    return num
                cprint("  ⚠  Please enter a number between 1 and 15.", C.YELLOW)
            except ValueError:
                cprint("  ⚠  That's not a valid number. Enter 1–15.", C.YELLOW)

    @staticmethod
    def resolve(choices: dict) -> dict:
        """Pick a random secret number; whoever is closest wins."""
        secret = random.randint(1, 15)
        distances = {}
        for player, guess in choices.items():
            g = int(guess) if not isinstance(guess, int) else guess
            distances[player] = abs(g - secret)

        min_dist = min(distances.values())
        winners = [p for p, d in distances.items() if d == min_dist]

        return {
            "secret": secret,
            "choices": {p: int(g) if not isinstance(g, int) else g for p, g in choices.items()},
            "distances": distances,
            "winners": winners,
            "exact": min_dist == 0,
        }

    @staticmethod
    def format_result(result: dict, my_name: str) -> str:
        secret = result["secret"]
        choices = result["choices"]
        distances = result["distances"]
        winners = result["winners"]
        exact = result["exact"]

        lines = [f"\n  🎯  The secret number was: {C.BOLD}{C.YELLOW}{secret}{C.RESET}\n"]

        # Sort players by distance (closest first)
        ranked = sorted(choices.items(), key=lambda item: distances[item[0]])
        for player, guess in ranked:
            tag = " ← you" if player == my_name else ""
            dist = distances[player]
            if dist == 0:
                mark = f"{C.GREEN}🎯"
                note = "exact!"
            elif player in winners:
                mark = f"{C.GREEN}✔"
                note = f"off by {dist}"
            else:
                mark = f"{C.RED}✘"
                note = f"off by {dist}"
            lines.append(
                f"  {mark}{C.RESET}  {player}: guessed {C.BOLD}{guess}{C.RESET}"
                f" {C.DIM}({note}){tag}{C.RESET}"
            )

        if my_name in winners:
            if exact:
                lines.append(f"\n  {C.GREEN}{C.BOLD}🎉 You nailed it!{C.RESET}")
            else:
                lines.append(f"\n  {C.GREEN}{C.BOLD}🏆 You were the closest!{C.RESET}")
        else:
            lines.append(f"\n  {C.RED}Not close enough this time!{C.RESET}")

        return "\n".join(lines)


GAMES = {
    "1": HeadsOrTails,
    "2": RockPaperScissors,
    "3": SnakeGame,
    "4": NumberGuess,
}


# ── Server ─────────────────────────────────────────────────────────────────────

class Server:
    def __init__(self, host_plays: bool = True):
        self.host_plays = host_plays
        self.clients = {}       # name -> socket
        self.lock = threading.Lock()
        self.game_class = None
        self.running = True

    def broadcast(self, data: dict, exclude=None):
        with self.lock:
            for name, sock in list(self.clients.items()):
                if name != exclude:
                    send_msg(sock, data)

    def handle_client(self, conn, addr):
        """Handle a single remote client connection."""
        msg = recv_msg(conn)
        if not msg or msg.get("type") != "join":
            conn.close()
            return
        name = msg["name"].strip()[:20] or f"Player_{addr[0]}"

        with self.lock:
            self.clients[name] = conn

        cprint(f"  ✔  {name} joined from {addr[0]}", C.GREEN)
        send_msg(conn, {"type": "welcome", "name": name})
        self.broadcast({"type": "chat", "msg": f"  📡  {name} connected."}, exclude=name)

        while self.running:
            time.sleep(0.5)

        conn.close()

    def collect_choices(self, game_class, host_choice=None) -> dict:
        """Send prompt to all clients, collect their choices. Return name->choice dict."""
        choices = {}
        responses = {}
        response_lock = threading.Lock()
        done_event = threading.Event()

        expected = list(self.clients.keys())
        expected_remote = [n for n in expected]

        def ask_client(name, sock):
            send_msg(sock, {"type": "prompt", "game": game_class.NAME})
            msg = recv_msg(sock)
            with response_lock:
                if msg and msg.get("type") == "choice":
                    responses[name] = msg["choice"]
                if len(responses) >= len(expected_remote):
                    done_event.set()

        threads = []
        with self.lock:
            for name, sock in self.clients.items():
                t = threading.Thread(target=ask_client, args=(name, sock), daemon=True)
                t.start()
                threads.append(t)

        done_event.wait(timeout=120)


        choices.update(responses)
        if host_choice is not None:
            choices["[Host] You"] = host_choice

        return choices

    def run(self):
        banner()
        cprint("  ══════════════════════════════════════", C.CYAN)
        cprint("   🖥   HOST MODE", C.CYAN + C.BOLD)
        cprint("  ══════════════════════════════════════", C.CYAN)

        ip = get_local_ip()
        cprint(f"\n  Your IP address: {C.BOLD}{C.YELLOW}{ip}{C.RESET}")
        cprint(f"  Port:            {C.BOLD}{PORT}{C.RESET}")
        cprint(f"\n  Share this with other players:", C.DIM)
        cprint(f"  {C.CYAN}python3 game.py --join{C.RESET}  then enter  {C.BOLD}{ip}{C.RESET}\n")

        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind(("", PORT))
        server_sock.listen(8)
        server_sock.settimeout(1.0)

        cprint("  Waiting for players to connect...", C.DIM)
        cprint("  Press {ENTER} when everyone is ready to start.\n", C.DIM)

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
        self.scores = {}

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
        except Exception as e:
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
                        self.scores[winner] = self.scores.get(winner, 0) + 1
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
        sys.exit(0)