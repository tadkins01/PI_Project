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
    5. Pac-Man (4 players, local terminal)
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
from typing import Optional


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

# Per-socket receive buffers (fixes dropped messages when two arrive in one TCP chunk)
_recv_buffers: dict = {}

def recv_msg(sock) -> Optional[dict]:
    """Receive a newline-delimited JSON message with per-socket buffering."""
    fd = sock.fileno()
    _recv_buffers.setdefault(fd, b"")
    try:
        while b"\n" not in _recv_buffers[fd]:
            chunk = sock.recv(BUFFER)
            if not chunk:
                return None
            _recv_buffers[fd] += chunk
        line, _recv_buffers[fd] = _recv_buffers[fd].split(b"\n", 1)
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
    def _spawn_food(snake: list) -> tuple:
        while True:
            food = (
                random.randint(1, SnakeGame.GRID_WIDTH - 2),
                random.randint(1, SnakeGame.GRID_HEIGHT - 2),
            )
            if food not in snake:
                return food

    @staticmethod
    def _draw_board(stdscr, snake: list, food: tuple, score: int):
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

        ranked = sorted(choices.items(), key=lambda item: distances[item[0]])
        for player, guess in ranked:
            tag = " ← you" if player == my_name else ""
            d = distances[player]
            if d == 0:
                mark = f"{C.GREEN}🎯"
                note = "exact!"
            elif player in winners:
                mark = f"{C.GREEN}✔"
                note = f"off by {d}"
            else:
                mark = f"{C.RED}✘"
                note = f"off by {d}"
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


"""
╔══════════════════════════════════════════════════════════════════════════════╗
║           PAC-MAN  —  4-Player Turn-Based Tournament Edition                ║
║                                                                              ║
║  Each player takes a solo turn one at a time.                               ║
║  Everyone uses the same controls (Arrow keys) on their own turn.            ║
║  Highest score after all turns wins!                                        ║
║                                                                              ║
║  Controls (your turn only)                                                  ║
║  ─────────────────────────────────────────────────────────────────────────  ║
║  Arrow keys  — move                                                         ║
║  Q           — end your turn early                                          ║
║                                                                              ║
║  Scoring                                                                     ║
║  ─────────────────────────────────────────────────────────────────────────  ║
║  Pellet      10 pts     Power pellet   50 pts                               ║
║  Ghost eat  200 pts     Level clear   500 pts bonus                         ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import curses
import random
import sys
import time
from collections import deque
from typing import Any, Dict, List, Optional, Tuple


# ── Colour-print helpers ──────────────────────────────────────────────────────

class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    RED    = "\033[31m"
    GREEN  = "\033[32m"
    YELLOW = "\033[33m"
    CYAN   = "\033[36m"
    WHITE  = "\033[37m"

def cprint(msg: str, style: str = "") -> None:
    print(f"{style}{msg}{C.RESET}")


# ══════════════════════════════════════════════════════════════════════════════
#  Ghost  (BFS chase + scatter/frightened)
# ══════════════════════════════════════════════════════════════════════════════

class Ghost:
    DIRS = [(-1, 0), (1, 0), (0, -1), (0, 1)]

    def __init__(
        self,
        row: int, col: int,
        scatter_target: Tuple[int, int],
        color_pair: int,
        home_row: int, home_col: int,
    ) -> None:
        self.row = row
        self.col = col
        self.dr = 0
        self.dc = 0
        self.scatter_target = scatter_target
        self.color_pair = color_pair
        self.home_row = home_row
        self.home_col = home_col
        self.scared = False
        self.dead   = False
        self.move_counter = 0

    def reset(self) -> None:
        self.scared = False
        self.dead   = False
        self.dr = 0
        self.dc = 0

    @staticmethod
    def _bfs_next(
        grid: List[List[int]], rows: int, cols: int,
        start: Tuple[int, int], target: Tuple[int, int],
    ) -> Optional[Tuple[int, int]]:
        if start == target:
            return None
        came_from: Dict[Tuple[int, int], Tuple[int, int]] = {start: start}
        q: deque = deque([start])
        found = False
        while q:
            cur = q.popleft()
            if cur == target:
                found = True
                break
            r, c = cur
            for dr, dc in Ghost.DIRS:
                nr, nc = r + dr, c + dc
                if not (0 <= nr < rows and 0 <= nc < cols):
                    continue
                if grid[nr][nc] == 1:
                    continue
                nxt = (nr, nc)
                if nxt in came_from:
                    continue
                came_from[nxt] = cur
                q.append(nxt)
        if not found:
            return None
        cur = target
        while came_from[cur] != start:
            cur = came_from[cur]
        return cur

    def move(
        self,
        grid: List[List[int]], rows: int, cols: int,
        player_positions: List[Tuple[int, int]],
        scatter_mode: bool,
    ) -> None:
        speed_every = 2 if self.dead else (3 if self.scared else 1)
        self.move_counter = (self.move_counter + 1) % speed_every
        if self.move_counter != 0:
            return

        r, c = self.row, self.col

        if self.scared and not self.dead:
            no_rev = [
                (dr, dc) for dr, dc in Ghost.DIRS
                if not (dr == -self.dr and dc == -self.dc)
                and 0 <= r + dr < rows and 0 <= c + dc < cols
                and grid[r + dr][c + dc] != 1
            ]
            options = no_rev or [
                (dr, dc) for dr, dc in Ghost.DIRS
                if 0 <= r + dr < rows and 0 <= c + dc < cols
                and grid[r + dr][c + dc] != 1
            ]
            if options:
                self.dr, self.dc = random.choice(options)
            self.row += self.dr
            self.col += self.dc
            return

        if self.dead:
            bfs_target = (self.home_row, self.home_col)
        elif scatter_mode or not player_positions:
            bfs_target = self.scatter_target
        else:
            bfs_target = min(
                player_positions,
                key=lambda p: abs(p[0] - r) + abs(p[1] - c),
            )

        nxt = Ghost._bfs_next(grid, rows, cols, (r, c), bfs_target)
        if nxt is not None:
            self.dr = nxt[0] - r
            self.dc = nxt[1] - c
            self.row, self.col = nxt
        else:
            options = [
                (dr, dc) for dr, dc in Ghost.DIRS
                if 0 <= r + dr < rows and 0 <= c + dc < cols
                and grid[r + dr][c + dc] != 1
            ]
            if options:
                self.dr, self.dc = random.choice(options)
                self.row += self.dr
                self.col += self.dc

        if self.dead and self.row == self.home_row and self.col == self.home_col:
            self.dead   = False
            self.scared = False

        self.col %= cols


# ══════════════════════════════════════════════════════════════════════════════
#  Solo game (one player, arrow keys only)
# ══════════════════════════════════════════════════════════════════════════════

class _SoloGame:
    """Runs a single player's turn inside curses."""

    _MAP_TEMPLATE: List[List[int]] = [
        [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
        [1,2,2,2,2,2,2,2,2,1,1,2,2,2,2,2,2,2,2,1],
        [1,3,1,1,2,1,1,1,2,1,1,2,1,1,1,2,1,1,3,1],
        [1,2,1,1,2,1,1,1,2,1,1,2,1,1,1,2,1,1,2,1],
        [1,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,1],
        [1,2,1,1,2,1,2,1,1,1,1,1,1,2,1,2,1,1,2,1],
        [1,2,2,2,2,1,2,2,2,1,1,2,2,2,1,2,2,2,2,1],
        [1,1,1,1,2,1,1,1,0,0,0,0,1,1,1,2,1,1,1,1],
        [1,1,1,1,2,1,0,4,4,4,4,4,4,0,1,2,1,1,1,1],
        [1,1,1,1,2,0,0,4,4,4,4,4,4,0,0,2,1,1,1,1],
        [0,0,0,0,2,0,0,4,4,4,4,4,4,0,0,2,0,0,0,0],
        [1,1,1,1,2,0,0,4,4,4,4,4,4,0,0,2,1,1,1,1],
        [1,1,1,1,2,1,0,0,0,0,0,0,0,0,1,2,1,1,1,1],
        [1,1,1,1,2,1,0,1,1,1,1,1,1,0,1,2,1,1,1,1],
        [1,2,2,2,2,2,2,2,2,1,1,2,2,2,2,2,2,2,2,1],
        [1,2,1,1,2,1,1,1,2,1,1,2,1,1,1,2,1,1,2,1],
        [1,3,2,1,2,2,2,2,2,0,0,2,2,2,2,2,1,2,3,1],
        [1,1,2,1,2,1,2,1,1,1,1,1,1,2,1,2,1,2,1,1],
        [1,2,2,2,2,1,2,2,2,1,1,2,2,2,1,2,2,2,2,1],
        [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
    ]

    ROWS = 20
    COLS = 20
    CELL = 2
    TICK = 0.13

    _GHOST_DEFS = [
        (9,  9,  (0, COLS-1), 3),
        (9,  10, (0, 0),      4),
        (10, 9,  (ROWS-1, COLS-1), 5),
        (10, 10, (ROWS-1, 0), 6),
    ]

    _SCATTER_TICKS = 35
    _CHASE_TICKS   = 100

    PLAYER_START = (16, 9)   # single fixed start

    @staticmethod
    def _init_colors() -> None:
        curses.start_color()
        curses.use_default_colors()
        for idx, fg, bg in [
            (1, curses.COLOR_BLUE,    -1),
            (2, curses.COLOR_WHITE,   -1),
            (3, curses.COLOR_RED,     -1),
            (4, curses.COLOR_MAGENTA, -1),
            (5, curses.COLOR_CYAN,    -1),
            (6, curses.COLOR_YELLOW,  -1),
            (7, curses.COLOR_YELLOW,  -1),   # player colour
            (11,curses.COLOR_BLUE,    -1),
        ]:
            try:
                curses.init_pair(idx, fg, bg)
            except Exception:
                pass

    @staticmethod
    def _make_map():
        return [row[:] for row in _SoloGame._MAP_TEMPLATE]

    @staticmethod
    def _can_move(grid, r, c, dr, dc):
        nr, nc = r + dr, c + dc
        if not (0 <= nr < _SoloGame.ROWS and 0 <= nc < _SoloGame.COLS):
            return False
        return grid[nr][nc] != 1

    @staticmethod
    def _draw(stdscr, grid, player, ghosts, score, lives, frigh_timer,
              scatter_mode, player_name, height, width):
        stdscr.erase()
        C2 = _SoloGame.CELL

        mode_str = "[SCATTER]" if scatter_mode else "[CHASE]"
        hud = (f"  {player_name}  |  Score: {score}  |  Lives: {'♥ ' * lives}"
               f"|  {mode_str}")
        if frigh_timer > 0:
            hud += f"  *** POWER {frigh_timer} ***"
        try:
            stdscr.addstr(0, 0, hud[:width - 1])
        except curses.error:
            pass

        for r in range(_SoloGame.ROWS):
            for c in range(_SoloGame.COLS):
                cell     = grid[r][c]
                draw_row = r + 1
                draw_col = c * C2
                if draw_row >= height or draw_col + C2 >= width:
                    continue
                try:
                    if cell == 1:
                        stdscr.addstr(draw_row, draw_col, "██", curses.color_pair(1))
                    elif cell == 2:
                        stdscr.addstr(draw_row, draw_col, " ·", curses.color_pair(2))
                    elif cell == 3:
                        stdscr.addstr(draw_row, draw_col, " ●",
                                      curses.color_pair(2) | curses.A_BOLD)
                    else:
                        stdscr.addstr(draw_row, draw_col, "  ")
                except curses.error:
                    pass

        for ghost in ghosts:
            dr = ghost.row + 1
            dc = ghost.col * C2
            if dr >= height or dc + C2 >= width:
                continue
            if ghost.dead:
                glyph, pair = " X", 2
            elif ghost.scared:
                glyph, pair = " &", 11
            else:
                glyph, pair = " G", ghost.color_pair
            try:
                stdscr.addstr(dr, dc, glyph,
                               curses.color_pair(pair) | curses.A_BOLD)
            except curses.error:
                pass

        if player["alive"]:
            dr = player["row"] + 1
            dc = player["col"] * C2
            if dr < height and dc + C2 < width:
                try:
                    stdscr.addstr(dr, dc, " C",
                                   curses.color_pair(7) | curses.A_BOLD)
                except curses.error:
                    pass

        footer_row = _SoloGame.ROWS + 1
        if footer_row < height:
            try:
                stdscr.addstr(footer_row, 0,
                               "  Arrow keys: move   Q: end turn"[:width - 1],
                               curses.A_DIM)
            except curses.error:
                pass

        stdscr.refresh()

    @classmethod
    def run(cls, stdscr, player_name: str) -> int:
        """Play one solo turn. Returns the score."""
        cls._init_colors()
        curses.curs_set(0)
        stdscr.nodelay(True)
        stdscr.keypad(True)

        height, width = stdscr.getmaxyx()
        grid = cls._make_map()

        total_pellets = sum(
            1 for r in range(cls.ROWS) for c in range(cls.COLS)
            if grid[r][c] in (2, 3)
        )

        sr, sc = cls.PLAYER_START
        player = {"row": sr, "col": sc, "dr": 0, "dc": 0,
                  "next_dr": 0, "next_dc": 1, "alive": True}

        ghosts: List[Ghost] = []
        for row, col, scatter_t, cp in cls._GHOST_DEFS:
            ghosts.append(Ghost(row, col, scatter_t, cp, row, col))

        score         = 0
        lives         = 3
        frigh_timer   = 0
        pellets_eaten = 0
        scatter_timer = cls._SCATTER_TICKS
        scatter_mode  = True
        running       = True
        win           = False
        last_tick     = time.monotonic()

        while running:
            key = stdscr.getch()
            if key in (ord("q"), ord("Q")):
                break

            if key == curses.KEY_UP:
                player["next_dr"] = -1; player["next_dc"] = 0
            elif key == curses.KEY_DOWN:
                player["next_dr"] =  1; player["next_dc"] = 0
            elif key == curses.KEY_LEFT:
                player["next_dr"] =  0; player["next_dc"] = -1
            elif key == curses.KEY_RIGHT:
                player["next_dr"] =  0; player["next_dc"] =  1

            now = time.monotonic()
            if now - last_tick < cls.TICK:
                time.sleep(0.01)
                continue
            last_tick = now

            # Scatter/chase phase
            if frigh_timer == 0:
                scatter_timer -= 1
                if scatter_timer <= 0:
                    scatter_mode  = not scatter_mode
                    scatter_timer = cls._SCATTER_TICKS if scatter_mode else cls._CHASE_TICKS

            # Move player
            if player["alive"]:
                r, c = player["row"], player["col"]
                for dr, dc in [(player["next_dr"], player["next_dc"]),
                               (player["dr"],      player["dc"])]:
                    if dr == 0 and dc == 0:
                        continue
                    if cls._can_move(grid, r, c, dr, dc):
                        player["dr"], player["dc"] = dr, dc
                        break

                nr = (r + player["dr"]) % cls.ROWS
                nc = (c + player["dc"]) % cls.COLS
                if grid[nr][nc] != 1:
                    player["row"], player["col"] = nr, nc

                cell = grid[player["row"]][player["col"]]
                if cell == 2:
                    grid[player["row"]][player["col"]] = 0
                    score += 10
                    pellets_eaten += 1
                elif cell == 3:
                    grid[player["row"]][player["col"]] = 0
                    score += 50
                    pellets_eaten += 1
                    frigh_timer = 30
                    for g in ghosts:
                        if not g.dead:
                            g.scared = True

            # Move ghosts
            pos = [(player["row"], player["col"])] if player["alive"] else []
            for g in ghosts:
                g.move(grid, cls.ROWS, cls.COLS, pos, scatter_mode)

            if frigh_timer > 0:
                frigh_timer -= 1
                if frigh_timer == 0:
                    for g in ghosts:
                        g.scared = False

            # Collisions
            if player["alive"]:
                for g in ghosts:
                    if g.row == player["row"] and g.col == player["col"]:
                        if g.scared and not g.dead:
                            g.dead   = True
                            g.scared = False
                            score   += 200
                        elif not g.dead:
                            player["alive"] = False
                            lives -= 1

            # Respawn
            if not player["alive"] and lives > 0:
                sr, sc = cls.PLAYER_START
                player.update({"row": sr, "col": sc,
                                "dr": 0, "dc": 0,
                                "next_dr": 0, "next_dc": 1,
                                "alive": True})
                for g in ghosts:
                    g.reset()
                    g.row, g.col = g.home_row, g.home_col

            # Win / lose
            if pellets_eaten >= total_pellets:
                score += 500
                win    = True
                running = False
            if lives <= 0:
                running = False

            height, width = stdscr.getmaxyx()
            cls._draw(stdscr, grid, player, ghosts, score, lives,
                      frigh_timer, scatter_mode, player_name, height, width)

        # End screen for this turn
        stdscr.nodelay(False)
        stdscr.erase()
        end_msg = f"  {'🎉 BOARD CLEARED!' if win else 'Turn over!'}"
        try:
            stdscr.addstr(2, 2, end_msg, curses.A_BOLD)
            stdscr.addstr(4, 2, f"  {player_name}  —  {score} pts")
            stdscr.addstr(6, 2, "  Press any key to continue...")
        except curses.error:
            pass
        stdscr.refresh()
        stdscr.getch()
        return score


# ══════════════════════════════════════════════════════════════════════════════
#  PacManGame  — tournament wrapper (the public-facing class)
# ══════════════════════════════════════════════════════════════════════════════

class PacManGame:
    NAME = "Pac-Man Tournament"

    @classmethod
    def prompt_choice(cls) -> dict:
        """
        Ask for each player's name, then run each solo turn in order.
        Returns a results dict compatible with resolve() / format_result().
        """
        cprint("\n  🎮  Pac-Man Tournament  —  4 Players, Solo Turns", C.YELLOW + C.BOLD)
        cprint("  Each person plays alone, one after another.", C.DIM)
        cprint("  Arrow keys to move, Q to end your turn early.\n", C.WHITE)

        # Collect names
        names: List[str] = []
        for i in range(1, 5):
            while True:
                raw = input(f"  {C.BOLD}Enter name for Player {i}: {C.RESET}").strip()
                if raw:
                    names.append(raw)
                    break
                cprint("  ⚠  Name cannot be empty.", C.YELLOW)

        if not sys.stdin.isatty() or not sys.stdout.isatty():
            cprint("  ⚠  No interactive terminal — scoring 0 for all.", C.YELLOW)
            return {"scores": {n: 0 for n in names}, "win": False}

        scores: Dict[str, int] = {}

        for turn, name in enumerate(names, 1):
            cprint(f"\n  ─────────────────────────────────────────", C.DIM)
            cprint(f"  Turn {turn}/4  →  {name}", C.CYAN + C.BOLD)
            cprint(f"  Get ready! Press any key when you're at the keyboard...", C.WHITE)
            input(f"  {C.BOLD}[ENTER to start]{C.RESET} ")

            try:
                score = curses.wrapper(_SoloGame.run, name)
            except Exception as e:
                cprint(f"  ⚠  Game error: {e}. Scoring 0.", C.YELLOW)
                score = 0

            scores[name] = score
            cprint(f"\n  {name} finished with {C.BOLD}{score}{C.RESET} pts!", C.GREEN)

        return {"scores": scores, "win": False}

    @staticmethod
    def resolve(choices: Dict[str, Any]) -> dict:
        """
        choices = {player_name: result_dict}  where result_dict has 'scores'.
        Also accepts the direct output of prompt_choice() passed straight in.
        """
        # Support both calling styles
        flat: Dict[str, int] = {}
        for player, val in choices.items():
            if isinstance(val, dict):
                # Nested: came from a network/lobby wrapper
                sc = val.get("scores", {})
                if isinstance(sc, dict):
                    flat[player] = sc.get(player, 0)
                elif isinstance(sc, list):
                    flat[player] = max(sc) if sc else 0
                else:
                    flat[player] = int(sc)
            else:
                flat[player] = int(val) if val else 0

        max_score = max(flat.values(), default=0)
        winners   = [p for p, s in flat.items() if s == max_score and max_score > 0]
        return {
            "player_scores": flat,
            "winners":       winners,
            "high_score":    max_score,
        }

    @staticmethod
    def format_result(result: dict, my_name: str) -> str:
        player_scores = result["player_scores"]
        winners       = result["winners"]
        lines = [
            f"\n  {C.BOLD}╔══════════════════════════════╗{C.RESET}",
            f"  {C.BOLD}║   🕹  Pac-Man Leaderboard   ║{C.RESET}",
            f"  {C.BOLD}╚══════════════════════════════╝{C.RESET}\n",
        ]
        ranked = sorted(player_scores.items(), key=lambda x: -x[1])
        medals = ["🥇", "🥈", "🥉", "   "]
        for rank, (player, score) in enumerate(ranked):
            medal = medals[min(rank, 3)]
            tag   = f"  {C.DIM}← you{C.RESET}" if player == my_name else ""
            crown = f" {C.YELLOW}👑{C.RESET}" if player in winners else ""
            lines.append(
                f"  {medal}  {player}{crown}  —  "
                f"{C.BOLD}{score}{C.RESET} pts{tag}"
            )
        lines.append("")
        if my_name in winners:
            lines.append(f"  {C.GREEN}{C.BOLD}🎉 You topped the leaderboard!{C.RESET}")
        else:
            lines.append(f"  {C.RED}Better luck next maze!{C.RESET}")
        return "\n".join(lines)


# backwards-compat alias
PacmanChase = PacManGame


# ══════════════════════════════════════════════════════════════════════════════
#  Stand-alone entry point
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    result = PacManGame.prompt_choice()

    # Build a resolve-compatible dict from the direct output
    raw_scores = result.get("scores", {})
    resolved   = PacManGame.resolve(raw_scores)

    cprint("\n" + "─" * 44, C.DIM)
    cprint(PacManGame.format_result(resolved, ""), C.RESET)


# ── Game Registry ──────────────────────────────────────────────────────────────

GAMES = {
    "1": HeadsOrTails,
    "2": RockPaperScissors,
    "3": SnakeGame,
    "4": NumberGuess,
    "5": PacManGame,
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
        """Send prompt to all clients, collect their choices."""
        choices = {}
        responses = {}
        response_lock = threading.Lock()
        done_event = threading.Event()

        expected_remote = list(self.clients.keys())

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
