"""
================================================================================
  Pi Party Games — Multiplayer Terminal Games over LAN
  Compatible with Raspberry Pi OS, Ubuntu LTS, and macOS
  Requires: Python 3.8+  |  No external packages needed
================================================================================

  Usage:
    python3 pi_party_games.py              # Interactive menu
    python3 pi_party_games.py --host       # Jump straight to hosting
    python3 pi_party_games.py --join       # Jump straight to joining

  Games:
    1. Heads or Tails       (guess a random coin flip)
    2. Rock Paper Scissors  (play against a random computer move)
    3. Number Guess (1-100) (closest to a random target wins)
    4. Snake                (eat apples, avoid walls — highest score wins)
    5. Pacman Chase         (highest score after a 45-second run wins)
    6. Pac-Man              (4 players take turns on the same maze — WASD only)

  Players: 2-4 recommended.
================================================================================
"""

from __future__ import annotations

import argparse
import json
import os
import random
import socket
import subprocess
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    import curses
    HAS_CURSES = True
except ImportError:
    HAS_CURSES = False


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


def cprint(text: str, color: str = C.WHITE) -> None:
    print(f"{color}{text}{C.RESET}")


def clear_screen() -> None:
    """Clear the terminal without using os.system / shell=True."""
    cmd = "cls" if os.name == "nt" else "clear"
    try:
        subprocess.run([cmd], check=False)
    except (FileNotFoundError, OSError):
        print("\033[2J\033[H", end="")


def banner() -> None:
    clear_screen()
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


# ── Networking ─────────────────────────────────────────────────────────────────

PORT = 65432
BUFFER = 4096
HOST_NAME_DEFAULT = "Host"
CHOICE_TIMEOUT_SEC = 120
SOCKET_POLL_TIMEOUT = 0.5


def get_local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.settimeout(1.0)
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except (socket.error, OSError):
        return "127.0.0.1"
    finally:
        s.close()


def send_msg(sock: socket.socket, data: dict) -> bool:
    try:
        raw = json.dumps(data).encode("utf-8")
        sock.sendall(raw + b"\n")
        return True
    except (socket.error, OSError, BrokenPipeError):
        return False


class MessageReader:
    """
    Persistent per-socket buffer that correctly handles:
      - multiple JSON messages arriving in one TCP chunk
      - one message split across multiple chunks
    """

    def __init__(self, sock: socket.socket):
        self.sock = sock
        self._buf = b""
        self._closed = False

    def read(self) -> Optional[dict]:
        while True:
            if b"\n" in self._buf:
                line, self._buf = self._buf.split(b"\n", 1)
                if not line:
                    continue
                try:
                    return json.loads(line.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue

            if self._closed:
                return None

            try:
                chunk = self.sock.recv(BUFFER)
            except socket.timeout:
                continue
            except (socket.error, OSError):
                self._closed = True
                return None

            if not chunk:
                self._closed = True
                return None
            self._buf += chunk


# ── Game Interface ─────────────────────────────────────────────────────────────

class HeadsOrTails:
    NAME = "Heads or Tails"

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
    def resolve(choices: Dict[str, str]) -> dict:
        flip = random.choice(["heads", "tails"])
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
    """Each player picks rock/paper/scissors vs. the computer (random)."""
    NAME = "Rock Paper Scissors"
    BEATS = {"rock": "scissors", "scissors": "paper", "paper": "rock"}
    EMOJI = {"rock": "🪨", "scissors": "✂️ ", "paper": "📄"}

    @staticmethod
    def prompt_choice() -> str:
        while True:
            cprint("\n  Your move (vs the computer):", C.CYAN)
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
    def resolve(choices: Dict[str, str]) -> dict:
        cpu = random.choice(["rock", "paper", "scissors"])
        outcomes: Dict[str, str] = {}
        winners: List[str] = []
        for player, choice in choices.items():
            if choice == cpu:
                outcomes[player] = "tie"
            elif RockPaperScissors.BEATS[choice] == cpu:
                outcomes[player] = "win"
                winners.append(player)
            else:
                outcomes[player] = "lose"
        return {"cpu": cpu, "choices": choices, "outcomes": outcomes, "winners": winners}

    @staticmethod
    def format_result(result: dict, my_name: str) -> str:
        cpu = result["cpu"]
        choices = result["choices"]
        outcomes = result["outcomes"]
        emoji = RockPaperScissors.EMOJI
        cpu_emoji = emoji.get(cpu, "?")
        lines = [f"\n  🤖  Computer played: {C.BOLD}{C.YELLOW}{cpu_emoji} {cpu}{C.RESET}\n"]
        order = {"win": 0, "tie": 1, "lose": 2}
        for player, choice in sorted(
            choices.items(),
            key=lambda kv: order.get(outcomes.get(kv[0], "lose"), 3),
        ):
            tag = " ← you" if player == my_name else ""
            outcome = outcomes.get(player, "lose")
            if outcome == "win":
                mark, label = f"{C.GREEN}✔", "win"
            elif outcome == "tie":
                mark, label = f"{C.YELLOW}=", "tie"
            else:
                mark, label = f"{C.RED}✘", "lose"
            lines.append(
                f"  {mark}{C.RESET}  {player}: {emoji.get(choice, '?')} {choice}"
                f" {C.DIM}({label}){tag}{C.RESET}"
            )
        my_outcome = outcomes.get(my_name)
        if my_outcome == "win":
            lines.append(f"\n  {C.GREEN}{C.BOLD}🏆 You beat the computer!{C.RESET}")
        elif my_outcome == "tie":
            lines.append(f"\n  {C.YELLOW}{C.BOLD}🤝 Tied with the computer.{C.RESET}")
        elif my_outcome == "lose":
            lines.append(f"\n  {C.RED}The computer beat you this round.{C.RESET}")
        return "\n".join(lines)


class NumberGuess:
    NAME = "Number Guess (1-100)"
    TARGET_MIN = 1
    TARGET_MAX = 100

    @staticmethod
    def prompt_choice() -> int:
        while True:
            cprint(
                f"\n  🔢  Guess a number between "
                f"{NumberGuess.TARGET_MIN} and {NumberGuess.TARGET_MAX}:",
                C.CYAN,
            )
            raw = input(f"  {C.BOLD}> {C.RESET}").strip()
            try:
                num = int(raw)
                if NumberGuess.TARGET_MIN <= num <= NumberGuess.TARGET_MAX:
                    return num
            except ValueError:
                pass
            cprint(
                f"  ⚠  Please enter an integer between "
                f"{NumberGuess.TARGET_MIN} and {NumberGuess.TARGET_MAX}.",
                C.YELLOW,
            )

    @staticmethod
    def resolve(choices: Dict[str, int]) -> dict:
        target = random.randint(NumberGuess.TARGET_MIN, NumberGuess.TARGET_MAX)
        guesses: Dict[str, int] = {}
        for p, c in choices.items():
            try:
                guesses[p] = int(c)
            except (TypeError, ValueError):
                guesses[p] = NumberGuess.TARGET_MIN
        distances = {p: abs(g - target) for p, g in guesses.items()}
        if distances:
            min_dist = min(distances.values())
            winners = [p for p, d in distances.items() if d == min_dist]
        else:
            min_dist = 0
            winners = []
        return {
            "target": target,
            "guesses": guesses,
            "distances": distances,
            "winners": winners,
            "exact": min_dist == 0,
        }

    @staticmethod
    def format_result(result: dict, my_name: str) -> str:
        target = result["target"]
        guesses = result["guesses"]
        distances = result["distances"]
        winners = result["winners"]
        exact = result.get("exact", False)
        lines = [f"\n  🎯  The target number was: {C.BOLD}{C.YELLOW}{target}{C.RESET}\n"]
        for player, guess in sorted(
            guesses.items(), key=lambda kv: distances.get(kv[0], 999)
        ):
            tag = " ← you" if player == my_name else ""
            dist = distances.get(player, 0)
            if dist == 0:
                mark, note = f"{C.GREEN}🎯", "exact!"
            elif player in winners:
                mark, note = f"{C.GREEN}✔", f"off by {dist}"
            else:
                mark, note = f"{C.RED}✘", f"off by {dist}"
            lines.append(
                f"  {mark}{C.RESET}  {player}: {C.BOLD}{guess}{C.RESET}"
                f" {C.DIM}({note}){tag}{C.RESET}"
            )
        if my_name in winners:
            if exact:
                lines.append(f"\n  {C.GREEN}{C.BOLD}🎉 You nailed it exactly!{C.RESET}")
            else:
                lines.append(f"\n  {C.GREEN}{C.BOLD}🏆 You were closest!{C.RESET}")
        else:
            lines.append(f"\n  {C.RED}Not close enough this time!{C.RESET}")
        return "\n".join(lines)


class SnakeGame:
    """Classic Snake — WASD or arrow keys. 30-second timer, highest score wins."""
    NAME = "Snake"
    GRID_WIDTH = 28
    GRID_HEIGHT = 14
    TICK_RATE = 0.12
    GAME_DURATION = 30
    APPLE_POINTS = 10
    WALL_CHAR = "█"
    HEAD_CHAR = "@"
    BODY_CHAR = "o"
    APPLE_CHAR = "●"
    EMPTY_CHAR = " "

    DIRECTION_KEYS_INIT = False
    DIRECTION_KEYS: Dict[int, Tuple[int, int]] = {}

    @classmethod
    def _init_direction_keys(cls) -> None:
        if cls.DIRECTION_KEYS_INIT:
            return
        cls.DIRECTION_KEYS = {
            ord("w"): (0, -1), ord("W"): (0, -1), curses.KEY_UP: (0, -1),
            ord("s"): (0, 1),  ord("S"): (0, 1),  curses.KEY_DOWN: (0, 1),
            ord("a"): (-1, 0), ord("A"): (-1, 0), curses.KEY_LEFT: (-1, 0),
            ord("d"): (1, 0),  ord("D"): (1, 0),  curses.KEY_RIGHT: (1, 0),
        }
        cls.DIRECTION_KEYS_INIT = True

    @staticmethod
    def _is_wall(x: int, y: int) -> bool:
        return (
            x <= 0
            or x >= SnakeGame.GRID_WIDTH - 1
            or y <= 0
            or y >= SnakeGame.GRID_HEIGHT - 1
        )

    @staticmethod
    def _spawn_apple(snake: List[Tuple[int, int]]) -> Optional[Tuple[int, int]]:
        snake_set = set(snake)
        candidates = [
            (x, y)
            for y in range(1, SnakeGame.GRID_HEIGHT - 1)
            for x in range(1, SnakeGame.GRID_WIDTH - 1)
            if (x, y) not in snake_set
        ]
        if not candidates:
            return None
        return random.choice(candidates)

    @staticmethod
    def _run(stdscr) -> int:
        SnakeGame._init_direction_keys()
        curses.curs_set(0)
        stdscr.nodelay(True)
        stdscr.keypad(True)
        stdscr.timeout(int(SnakeGame.TICK_RATE * 1000))

        cx = SnakeGame.GRID_WIDTH // 2
        cy = SnakeGame.GRID_HEIGHT // 2
        snake: List[Tuple[int, int]] = [(cx, cy), (cx - 1, cy), (cx - 2, cy)]
        direction: Tuple[int, int] = (1, 0)
        queued: Tuple[int, int] = (1, 0)
        apple: Optional[Tuple[int, int]] = SnakeGame._spawn_apple(snake)
        score = 0

        start_t = time.time()
        quit_pressed = False
        crashed_wall = False
        crashed_self = False

        def render(final_msg: str = "") -> None:
            stdscr.erase()
            head = snake[0]
            body_set = set(snake[1:])
            for y in range(SnakeGame.GRID_HEIGHT):
                line_chars: List[str] = []
                for x in range(SnakeGame.GRID_WIDTH):
                    if SnakeGame._is_wall(x, y):
                        line_chars.append(SnakeGame.WALL_CHAR)
                    elif (x, y) == head:
                        line_chars.append(SnakeGame.HEAD_CHAR)
                    elif (x, y) in body_set:
                        line_chars.append(SnakeGame.BODY_CHAR)
                    elif apple is not None and (x, y) == apple:
                        line_chars.append(SnakeGame.APPLE_CHAR)
                    else:
                        line_chars.append(SnakeGame.EMPTY_CHAR)
                try:
                    stdscr.addstr(y, 0, "".join(line_chars))
                except curses.error:
                    pass
            time_left = max(0, int(SnakeGame.GAME_DURATION - (time.time() - start_t)))
            hud = (
                f" Score: {score:<5}  Length: {len(snake):<3}  "
                f"Time: {time_left:>2}s   [W=Up  S=Down  A=Left  D=Right]  [Q to quit]"
            )
            try:
                stdscr.addstr(SnakeGame.GRID_HEIGHT, 0, hud)
            except curses.error:
                pass
            if final_msg:
                try:
                    stdscr.addstr(SnakeGame.GRID_HEIGHT + 1, 0, final_msg)
                except curses.error:
                    pass
            stdscr.refresh()

        while True:
            if quit_pressed or crashed_wall or crashed_self:
                break
            if time.time() - start_t >= SnakeGame.GAME_DURATION:
                break

            key = stdscr.getch()
            if key in (ord("q"), ord("Q")):
                quit_pressed = True
                continue
            if key in SnakeGame.DIRECTION_KEYS:
                new_dir = SnakeGame.DIRECTION_KEYS[key]
                if (new_dir[0], new_dir[1]) != (-direction[0], -direction[1]):
                    queued = new_dir

            direction = queued

            head_x, head_y = snake[0]
            new_head = (head_x + direction[0], head_y + direction[1])

            if SnakeGame._is_wall(*new_head):
                crashed_wall = True
                continue

            will_eat = apple is not None and new_head == apple
            body_to_check = set(snake) if will_eat else set(snake[:-1])
            if new_head in body_to_check:
                crashed_self = True
                continue

            snake.insert(0, new_head)

            if will_eat:
                score += SnakeGame.APPLE_POINTS
                apple = SnakeGame._spawn_apple(snake)
            else:
                snake.pop()

            render()

        if crashed_wall:
            final_msg = f"  💥  You hit a wall!  Final score: {score}.  Press any key."
        elif crashed_self:
            final_msg = f"  🐍  You ran into yourself!  Final score: {score}.  Press any key."
        elif quit_pressed:
            final_msg = f"  Quit. Final score: {score}.  Press any key."
        else:
            final_msg = f"  ⏱  Time's up!  Final score: {score}.  Press any key."
        render(final_msg)
        stdscr.nodelay(False)
        stdscr.timeout(-1)
        stdscr.getch()
        return score

    @staticmethod
    def prompt_choice() -> int:
        cprint("\n  Launching Snake...", C.CYAN)
        cprint("  Use WASD or arrow keys.  Eat ● apples to grow and score.", C.WHITE)
        cprint("  Hitting a wall or yourself ends the game.  30 seconds total.", C.WHITE)
        time.sleep(1.2)

        if not HAS_CURSES or not sys.stdin.isatty() or not sys.stdout.isatty():
            cprint("  ⚠  Interactive terminal not available here. Scoring 0 for this round.", C.YELLOW)
            return 0

        try:
            score = curses.wrapper(SnakeGame._run)
            return int(score)
        except curses.error as e:
            cprint(f"  ⚠  Curses error: {e}. Scoring 0 for this round.", C.YELLOW)
            return 0
        except (RuntimeError, OSError) as e:
            cprint(f"  ⚠  Snake couldn't run ({e}). Scoring 0 for this round.", C.YELLOW)
            return 0

    @staticmethod
    def resolve(choices: Dict[str, int]) -> dict:
        scores: Dict[str, int] = {}
        for p, c in choices.items():
            try:
                scores[p] = int(c)
            except (TypeError, ValueError):
                scores[p] = 0
        if scores:
            max_score = max(scores.values())
            winners = [p for p, s in scores.items() if s == max_score and max_score > 0]
        else:
            winners = []
        return {"scores": scores, "winners": winners}

    @staticmethod
    def format_result(result: dict, my_name: str) -> str:
        scores = result["scores"]
        winners = result["winners"]
        lines = [f"\n  🐍  {C.BOLD}── Snake Results ──{C.RESET}\n"]
        for player, sc in sorted(scores.items(), key=lambda kv: -kv[1]):
            tag = " ← you" if player == my_name else ""
            mark = f"{C.GREEN}🏆" if player in winners else f"{C.YELLOW}🐍"
            lines.append(
                f"  {mark}{C.RESET}  {player}: {C.BOLD}{sc}{C.RESET} pts"
                f"{C.DIM}{tag}{C.RESET}"
            )
        if not winners:
            lines.append(f"\n  {C.YELLOW}No one scored this round!{C.RESET}")
        elif my_name in winners:
            lines.append(f"\n  {C.GREEN}{C.BOLD}🏆 You had the highest score!{C.RESET}")
        else:
            lines.append(f"\n  {C.RED}Better luck next time!{C.RESET}")
        return "\n".join(lines)


# ── Pacman Chase (single-player timed run) ─────────────────────────────────────

class PacmanChase:
    """
    Single-player curses game. Each player runs it locally; scores are compared.
    3 lives, 45-second timer. WASD / arrow keys.
    """
    NAME = "Pacman Chase"
    GRID_WIDTH = 21
    GRID_HEIGHT = 13
    TICK_RATE = 0.15
    MAX_LIVES = 3
    GAME_DURATION = 45
    PELLET_COUNT = 14

    LAYOUT = [
        [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
        [1,0,0,0,0,0,0,0,0,0,1,0,0,0,0,0,0,0,0,0,1],
        [1,0,1,1,0,1,1,1,0,0,0,0,0,1,1,1,0,1,1,0,1],
        [1,0,1,0,0,0,0,1,0,1,1,1,0,1,0,0,0,0,1,0,1],
        [1,0,1,0,1,1,0,1,0,0,0,0,0,1,0,1,1,0,1,0,1],
        [1,0,0,0,1,0,0,0,0,1,0,1,0,0,0,0,1,0,0,0,1],
        [1,1,1,0,1,0,1,1,0,0,0,0,0,1,1,0,1,0,1,1,1],
        [1,0,0,0,1,0,0,0,0,1,0,1,0,0,0,0,1,0,0,0,1],
        [1,0,1,0,1,1,0,1,0,0,0,0,0,1,0,1,1,0,1,0,1],
        [1,0,1,0,0,0,0,1,0,1,1,1,0,1,0,0,0,0,1,0,1],
        [1,0,1,1,0,1,1,1,0,0,0,0,0,1,1,1,0,1,1,0,1],
        [1,0,0,0,0,0,0,0,0,0,1,0,0,0,0,0,0,0,0,0,1],
        [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
    ]

    DIRECTION_KEYS_INIT = False
    DIRECTION_KEYS: Dict[int, Tuple[int, int]] = {}

    @classmethod
    def _init_direction_keys(cls) -> None:
        if cls.DIRECTION_KEYS_INIT:
            return
        cls.DIRECTION_KEYS = {
            ord("w"): (0, -1), ord("W"): (0, -1), curses.KEY_UP: (0, -1),
            ord("s"): (0, 1),  ord("S"): (0, 1),  curses.KEY_DOWN: (0, 1),
            ord("a"): (-1, 0), ord("A"): (-1, 0), curses.KEY_LEFT: (-1, 0),
            ord("d"): (1, 0),  ord("D"): (1, 0),  curses.KEY_RIGHT: (1, 0),
        }
        cls.DIRECTION_KEYS_INIT = True

    @staticmethod
    def _open_cells() -> List[Tuple[int, int]]:
        return [
            (x, y)
            for y, row in enumerate(PacmanChase.LAYOUT)
            for x, cell in enumerate(row)
            if cell == 0
        ]

    @staticmethod
    def _is_wall(x: int, y: int) -> bool:
        if not (0 <= x < PacmanChase.GRID_WIDTH and 0 <= y < PacmanChase.GRID_HEIGHT):
            return True
        return PacmanChase.LAYOUT[y][x] == 1

    @staticmethod
    def _spawn_positions(
        open_cells: List[Tuple[int, int]],
    ) -> Tuple[int, int, List[Tuple[int, int]]]:
        cx, cy = PacmanChase.GRID_WIDTH // 2, PacmanChase.GRID_HEIGHT // 2
        open_sorted = sorted(open_cells, key=lambda c: abs(c[0] - cx) + abs(c[1] - cy))
        px, py = open_sorted[0]
        far_cells = sorted(
            open_cells,
            key=lambda c: abs(c[0] - px) + abs(c[1] - py),
            reverse=True,
        )
        ghosts: List[Tuple[int, int]] = []
        used = {(px, py)}
        for cell in far_cells:
            if cell in used:
                continue
            ghosts.append(cell)
            used.add(cell)
            if len(ghosts) == 2:
                break
        while len(ghosts) < 2:
            ghosts.append(open_cells[0])
        return px, py, ghosts

    @staticmethod
    def _bfs_next_step(
        start: Tuple[int, int],
        target: Tuple[int, int],
    ) -> Optional[Tuple[int, int]]:
        if start == target:
            return None
        from collections import deque
        came_from: Dict[Tuple[int, int], Tuple[int, int]] = {start: start}
        q: "deque[Tuple[int, int]]" = deque([start])
        found = False
        while q:
            cur = q.popleft()
            if cur == target:
                found = True
                break
            for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
                nxt = (cur[0] + dx, cur[1] + dy)
                if nxt in came_from:
                    continue
                if PacmanChase._is_wall(*nxt):
                    continue
                came_from[nxt] = cur
                q.append(nxt)
        if not found:
            return None
        cur = target
        while came_from[cur] != start:
            cur = came_from[cur]
        return cur

    @staticmethod
    def _move_ghost(
        ghost: Tuple[int, int],
        target: Tuple[int, int],
    ) -> Tuple[int, int]:
        if random.random() < 0.15:
            options = []
            for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
                cand = (ghost[0] + dx, ghost[1] + dy)
                if not PacmanChase._is_wall(*cand):
                    options.append(cand)
            if options:
                return random.choice(options)
        nxt = PacmanChase._bfs_next_step(ghost, target)
        return nxt if nxt is not None else ghost

    @staticmethod
    def _run(stdscr) -> int:
        PacmanChase._init_direction_keys()
        curses.curs_set(0)
        stdscr.nodelay(True)
        stdscr.keypad(True)
        stdscr.timeout(int(PacmanChase.TICK_RATE * 1000))

        open_cells = PacmanChase._open_cells()
        pacman_x, pacman_y, ghosts = PacmanChase._spawn_positions(open_cells)
        direction = (0, 0)
        queued = (0, 0)
        score = 0
        lives = PacmanChase.MAX_LIVES

        occupied = {(pacman_x, pacman_y)} | set(ghosts)
        pellet_choices = [c for c in open_cells if c not in occupied]
        random.shuffle(pellet_choices)
        pellets = set(pellet_choices[:PacmanChase.PELLET_COUNT])

        start_t = time.time()
        ghost_tick = 0
        quit_pressed = False
        respawning = False
        respawn_until = 0.0

        def render(msg: str = "") -> None:
            stdscr.erase()
            for y, row in enumerate(PacmanChase.LAYOUT):
                line_chars: List[str] = []
                for x, cell in enumerate(row):
                    if cell == 1:
                        line_chars.append("█")
                    elif (x, y) == (pacman_x, pacman_y):
                        line_chars.append("C")
                    elif (x, y) in ghosts:
                        line_chars.append("M")
                    elif (x, y) in pellets:
                        line_chars.append("·")
                    else:
                        line_chars.append(" ")
                try:
                    stdscr.addstr(y, 0, "".join(line_chars))
                except curses.error:
                    pass
            time_left = max(0, int(PacmanChase.GAME_DURATION - (time.time() - start_t)))
            hearts = "♥ " * lives + "  " * (PacmanChase.MAX_LIVES - lives)
            hud = (
                f" Score: {score:<5}  Lives: {hearts.strip()}  "
                f"Time: {time_left:>2}s   [W=Up  S=Down  A=Left  D=Right]  [Q to quit]"
            )
            try:
                stdscr.addstr(PacmanChase.GRID_HEIGHT, 0, hud)
            except curses.error:
                pass
            if msg:
                try:
                    stdscr.addstr(PacmanChase.GRID_HEIGHT + 1, 0, msg)
                except curses.error:
                    pass
            stdscr.refresh()

        while True:
            if quit_pressed:
                break
            if lives <= 0:
                break
            if time.time() - start_t >= PacmanChase.GAME_DURATION:
                break

            if respawning and time.time() < respawn_until:
                render("  💀 You were caught! Respawning...")
                drain_key = stdscr.getch()
                while drain_key != -1:
                    drain_key = stdscr.getch()
                continue
            if respawning and time.time() >= respawn_until:
                respawning = False

            key = stdscr.getch()
            if key in (ord("q"), ord("Q")):
                quit_pressed = True
                continue
            if key in PacmanChase.DIRECTION_KEYS:
                queued = PacmanChase.DIRECTION_KEYS[key]

            if queued != (0, 0):
                tx, ty = pacman_x + queued[0], pacman_y + queued[1]
                if not PacmanChase._is_wall(tx, ty):
                    direction = queued
                    queued = (0, 0)

            if direction != (0, 0):
                nx = pacman_x + direction[0]
                ny = pacman_y + direction[1]
                if not PacmanChase._is_wall(nx, ny):
                    pacman_x, pacman_y = nx, ny

            if (pacman_x, pacman_y) in pellets:
                pellets.discard((pacman_x, pacman_y))
                score += 10
                forbidden = {(pacman_x, pacman_y)} | set(ghosts) | pellets
                empty = [c for c in open_cells if c not in forbidden]
                if empty:
                    pellets.add(random.choice(empty))

            ghost_tick += 1
            if ghost_tick % 2 == 0:
                new_ghosts: List[Tuple[int, int]] = []
                for g in ghosts:
                    new_ghosts.append(PacmanChase._move_ghost(g, (pacman_x, pacman_y)))
                ghosts = new_ghosts

            if (pacman_x, pacman_y) in set(ghosts):
                lives -= 1
                if lives > 0:
                    pacman_x, pacman_y, ghosts = PacmanChase._spawn_positions(open_cells)
                    direction = (0, 0)
                    queued = (0, 0)
                    respawning = True
                    respawn_until = time.time() + 1.0
                    render("  💀 You were caught! Respawning...")
                    continue

            render()

        if lives <= 0:
            final_msg = f"  Game over! Final score: {score}.  Press any key."
        elif quit_pressed:
            final_msg = f"  Quit. Final score: {score}.  Press any key."
        else:
            final_msg = f"  Time's up! Final score: {score}.  Press any key."
        render(final_msg)
        stdscr.nodelay(False)
        stdscr.timeout(-1)
        stdscr.getch()
        return score

    @staticmethod
    def prompt_choice() -> int:
        cprint("\n  Launching Pacman Chase...", C.CYAN)
        cprint("  Controls: W=Up  S=Down  A=Left  D=Right", C.WHITE)
        cprint("  Eat · pellets, avoid M ghosts.  3 lives, 45 seconds.  Highest score wins!", C.WHITE)
        time.sleep(1.2)

        if not HAS_CURSES or not sys.stdin.isatty() or not sys.stdout.isatty():
            cprint("  ⚠  Interactive terminal not available here. Scoring 0 for this round.", C.YELLOW)
            return 0

        try:
            score = curses.wrapper(PacmanChase._run)
            return int(score)
        except curses.error as e:
            cprint(f"  ⚠  Curses error: {e}. Scoring 0 for this round.", C.YELLOW)
            return 0
        except (RuntimeError, OSError) as e:
            cprint(f"  ⚠  Pacman couldn't run ({e}). Scoring 0 for this round.", C.YELLOW)
            return 0

    @staticmethod
    def resolve(choices: Dict[str, int]) -> dict:
        scores: Dict[str, int] = {}
        for p, c in choices.items():
            try:
                scores[p] = int(c)
            except (TypeError, ValueError):
                scores[p] = 0
        if scores:
            max_score = max(scores.values())
            winners = [p for p, s in scores.items() if s == max_score and max_score > 0]
        else:
            winners = []
        return {"scores": scores, "winners": winners}

    @staticmethod
    def format_result(result: dict, my_name: str) -> str:
        scores = result["scores"]
        winners = result["winners"]
        lines = [f"\n  👾  {C.BOLD}Pacman Chase Results{C.RESET}\n"]
        for player, sc in sorted(scores.items(), key=lambda kv: -kv[1]):
            tag = " ← you" if player == my_name else ""
            mark = f"{C.GREEN}🏆" if player in winners else f"{C.YELLOW}👾"
            lines.append(
                f"  {mark}{C.RESET}  {player}: {C.BOLD}{sc}{C.RESET} pts"
                f"{C.DIM}{tag}{C.RESET}"
            )
        if not winners:
            lines.append(f"\n  {C.YELLOW}No one scored this round!{C.RESET}")
        elif my_name in winners:
            lines.append(f"\n  {C.GREEN}{C.BOLD}🏆 You had the highest score!{C.RESET}")
        else:
            lines.append(f"\n  {C.RED}Better luck next time!{C.RESET}")
        return "\n".join(lines)


# ── Pac-Man (4-player turn-based, WASD only) ───────────────────────────────────
#
#  Up to 4 players take turns playing the SAME maze one at a time.
#  Controls: WASD only (W=up, A=left, S=down, D=right).
#  The WASD controls are always shown at the bottom of the screen during play.
#  After all players have had their turn, scores are compared and the winner
#  is whoever got the most points.
#
#  Scoring:
#    Pellet         10 pts
#    Power pellet   50 pts
#    Ghost eat     200 pts
#    Level clear   500 pts bonus

class PacManGame:
    NAME = "Pac-Man (4-Player Turns)"

    # Map template (20 × 20) — 1=wall  2=pellet  3=power  0=empty  4=ghost house
    _MAP_TEMPLATE = [
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
    CELL = 2      # chars wide per cell
    TICK = 0.13   # seconds per frame

    GHOST_PAIRS = [3, 4, 5, 6]  # colour pair indices for ghosts

    # Player start position (row, col) — all players start from the same spot
    PLAYER_START = (16, 9)

    PLAYER_COLORS = [7, 8, 9, 10]
    PLAYER_LABELS = ["P1", "P2", "P3", "P4"]

    # WASD only — no arrow keys, no IJKL, no numpad
    WASD_KEYS = {
        ord("w"): (-1, 0), ord("W"): (-1, 0),   # up
        ord("s"): (1, 0),  ord("S"): (1, 0),    # down
        ord("a"): (0, -1), ord("A"): (0, -1),   # left
        ord("d"): (0, 1),  ord("D"): (0, 1),    # right
    }

    # ── Ghost AI ─────────────────────────────────────────────────────────────

    class Ghost:
        def __init__(self, row, col, scatter_target, color_pair, home_row=9, home_col=9):
            self.row = row
            self.col = col
            self.dr = 0
            self.dc = 0
            self.scatter_target = scatter_target
            self.color_pair = color_pair
            self.home_row = home_row
            self.home_col = home_col
            self.scared = False
            self.dead = False
            self.move_counter = 0

        def reset(self):
            self.scared = False
            self.dead = False
            self.dr = 0
            self.dc = 0

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _make_map():
        return [row[:] for row in PacManGame._MAP_TEMPLATE]

    @staticmethod
    def _init_colors():
        curses.start_color()
        curses.use_default_colors()
        pairs = [
            (1,  curses.COLOR_BLUE,    -1),  # wall
            (2,  curses.COLOR_WHITE,   -1),  # pellet
            (3,  curses.COLOR_RED,     -1),  # Blinky
            (4,  curses.COLOR_MAGENTA, -1),  # Pinky
            (5,  curses.COLOR_CYAN,    -1),  # Inky
            (6,  curses.COLOR_YELLOW,  -1),  # Clyde
            (7,  curses.COLOR_YELLOW,  -1),  # P1
            (8,  curses.COLOR_CYAN,    -1),  # P2
            (9,  curses.COLOR_GREEN,   -1),  # P3
            (10, curses.COLOR_MAGENTA, -1),  # P4
            (11, curses.COLOR_BLUE,    -1),  # scared ghost
        ]
        for idx, fg, bg in pairs:
            try:
                curses.init_pair(idx, fg, bg)
            except Exception:
                pass

    @staticmethod
    def _can_move(grid, r, c, dr, dc):
        nr, nc = r + dr, c + dc
        if nr < 0 or nr >= PacManGame.ROWS or nc < 0 or nc >= PacManGame.COLS:
            return False
        return grid[nr][nc] != 1

    @staticmethod
    def _manhattan(r1, c1, r2, c2):
        return abs(r1 - r2) + abs(c1 - c2)

    @staticmethod
    def _ghost_move(ghost, grid, target_row, target_col):
        speed_every = 2 if ghost.dead else (3 if ghost.scared else 1)
        ghost.move_counter = (ghost.move_counter + 1) % speed_every
        if ghost.move_counter != 0:
            return

        r, c = ghost.row, ghost.col
        dirs = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        no_reverse = [(dr, dc) for dr, dc in dirs if not (dr == -ghost.dr and dc == -ghost.dc)]
        options = [d for d in no_reverse if PacManGame._can_move(grid, r, c, *d)] or \
                  [d for d in dirs if PacManGame._can_move(grid, r, c, *d)]
        if not options:
            return

        if ghost.dead:
            best = min(options, key=lambda d: PacManGame._manhattan(r+d[0], c+d[1], ghost.home_row, ghost.home_col))
            if r == ghost.home_row and c == ghost.home_col:
                ghost.dead = False
                ghost.scared = False
        elif ghost.scared:
            best = random.choice(options)
        else:
            best = min(options, key=lambda d: PacManGame._manhattan(r+d[0], c+d[1], target_row, target_col))

        ghost.dr, ghost.dc = best
        ghost.row += best[0]
        ghost.col += best[1]

        # Tunnel wrap
        if ghost.col < 0:
            ghost.col = PacManGame.COLS - 1
        elif ghost.col >= PacManGame.COLS:
            ghost.col = 0

    # ── Drawing ───────────────────────────────────────────────────────────────

    @staticmethod
    def _draw(stdscr, grid, player, ghosts, score, lives, level, frigh_timer,
              player_idx, player_label, height, width):
        stdscr.erase()
        C2 = PacManGame.CELL

        # HUD
        hud = f" {player_label} | Level:{level}  Lives:{lives}  Score:{score}"
        if frigh_timer > 0:
            hud += f"  *** POWER {frigh_timer} ***"
        try:
            stdscr.addstr(0, 0, hud[:width-1])
        except curses.error:
            pass

        # Grid
        for r in range(PacManGame.ROWS):
            for c in range(PacManGame.COLS):
                cell = grid[r][c]
                draw_row = r + 1
                draw_col = c * C2
                if draw_row >= height or draw_col + C2 >= width:
                    continue
                if cell == 1:
                    try:
                        stdscr.addstr(draw_row, draw_col, "██", curses.color_pair(1))
                    except curses.error:
                        pass
                elif cell == 2:
                    try:
                        stdscr.addstr(draw_row, draw_col, " ·", curses.color_pair(2))
                    except curses.error:
                        pass
                elif cell == 3:
                    try:
                        stdscr.addstr(draw_row, draw_col, " ●", curses.color_pair(2) | curses.A_BOLD)
                    except curses.error:
                        pass
                else:
                    try:
                        stdscr.addstr(draw_row, draw_col, "  ")
                    except curses.error:
                        pass

        # Ghosts
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
                stdscr.addstr(dr, dc, glyph, curses.color_pair(pair) | curses.A_BOLD)
            except curses.error:
                pass

        # Player
        if player["alive"]:
            dr = player["row"] + 1
            dc = player["col"] * C2
            if dr < height and dc + C2 < width:
                label = f">{player_idx+1}"
                try:
                    stdscr.addstr(dr, dc, label,
                                  curses.color_pair(PacManGame.PLAYER_COLORS[player_idx]) | curses.A_BOLD)
                except curses.error:
                    pass

        # Footer — always show WASD controls
        footer_row = PacManGame.ROWS + 1
        if footer_row < height:
            ctrl = "Controls: W=Up  S=Down  A=Left  D=Right  |  Q=Quit"
            try:
                stdscr.addstr(footer_row, 0, ctrl[:width-1], curses.A_BOLD)
            except curses.error:
                pass

        stdscr.refresh()

    # ── Single-player turn on the shared maze ─────────────────────────────────

    @classmethod
    def _run_one_turn(cls, stdscr, player_idx: int, player_label: str) -> int:
        """Run one player's turn. Returns the score they achieved."""
        cls._init_colors()
        curses.curs_set(0)
        stdscr.nodelay(True)
        stdscr.keypad(True)

        height, width = stdscr.getmaxyx()
        grid = cls._make_map()

        total_pellets = sum(1 for r in range(cls.ROWS) for c in range(cls.COLS) if grid[r][c] in (2, 3))

        sr, sc = cls.PLAYER_START
        player = {
            "row": sr, "col": sc,
            "dr": 0, "dc": 0,
            "next_dr": 0, "next_dc": 1,
            "alive": True,
        }

        score = 0

        ghosts = [
            cls.Ghost(9,  9,  (0,  cls.COLS-1), 3, home_row=9,  home_col=9),
            cls.Ghost(9,  10, (0,  0),           4, home_row=9,  home_col=10),
            cls.Ghost(10, 9,  (cls.ROWS-1, cls.COLS-1), 5, home_row=10, home_col=9),
            cls.Ghost(10, 10, (cls.ROWS-1, 0),   6, home_row=10, home_col=10),
        ]

        lives = 3
        level = 1
        frigh_timer = 0
        pellets_eaten = 0
        running = True
        game_over = False
        win = False
        last_tick = time.monotonic()

        while running:
            # ── Input ─────────────────────────────────────────────────────────
            key = stdscr.getch()
            if key in (ord("q"), ord("Q")):
                running = False
                break

            if key in cls.WASD_KEYS:
                dr, dc = cls.WASD_KEYS[key]
                player["next_dr"] = dr
                player["next_dc"] = dc

            now = time.monotonic()
            if now - last_tick < cls.TICK:
                time.sleep(0.01)
                continue
            last_tick = now

            # ── Move player ───────────────────────────────────────────────────
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

            # ── Move ghosts ───────────────────────────────────────────────────
            if player["alive"]:
                tr, tc = player["row"], player["col"]
            else:
                tr, tc = cls.PLAYER_START
            for g in ghosts:
                cls._ghost_move(g, grid, tr, tc)

            if frigh_timer > 0:
                frigh_timer -= 1
                if frigh_timer == 0:
                    for g in ghosts:
                        g.scared = False

            # ── Collisions ────────────────────────────────────────────────────
            if player["alive"]:
                for g in ghosts:
                    if g.row == player["row"] and g.col == player["col"]:
                        if g.scared and not g.dead:
                            g.dead = True
                            g.scared = False
                            score += 200
                        elif not g.dead:
                            player["alive"] = False
                            lives -= 1

            # Respawn if lives remain
            if not player["alive"] and lives > 0:
                sr2, sc2 = cls.PLAYER_START
                player.update({
                    "row": sr2, "col": sc2,
                    "dr": 0, "dc": 0,
                    "next_dr": 0, "next_dc": 1,
                    "alive": True,
                })
                for g in ghosts:
                    g.reset()
                    g.row, g.col = g.home_row, g.home_col

            # Win / lose
            if pellets_eaten >= total_pellets:
                win = True
                score += 500
                running = False

            if lives <= 0 or not player["alive"]:
                game_over = True
                running = False

            # ── Draw ──────────────────────────────────────────────────────────
            height, width = stdscr.getmaxyx()
            cls._draw(stdscr, grid, player, ghosts, score, lives, level,
                      frigh_timer, player_idx, player_label, height, width)

        # End screen
        stdscr.nodelay(False)
        stdscr.erase()
        msg = f"{player_label}: YOU WIN! 🎉  Score: {score}" if win else f"{player_label}: GAME OVER  Score: {score}"
        try:
            stdscr.addstr(2, 2, msg, curses.A_BOLD)
            stdscr.addstr(4, 2, "Press any key to continue to the next player.")
            # Still show WASD reminder even on end screen
            stdscr.addstr(6, 2, "Controls: W=Up  S=Down  A=Left  D=Right", curses.A_DIM)
        except curses.error:
            pass
        stdscr.refresh()
        stdscr.getch()
        return score

    # ── Public interface ──────────────────────────────────────────────────────

    @classmethod
    def prompt_choice(cls) -> dict:
        """
        Each player takes a turn one at a time on the same Pac-Man maze.
        Returns a dict with all individual scores.
        """
        cprint("\n  🎮  Pac-Man — Turn-Based (up to 4 players)", C.YELLOW + C.BOLD)
        cprint("  Players take turns one at a time on the same maze.", C.DIM)
        cprint("  Controls: W=Up  S=Down  A=Left  D=Right  (WASD only)", C.WHITE)

        while True:
            cprint("\n  How many players? [1 / 2 / 3 / 4]", C.CYAN)
            raw = input(f"  {C.BOLD}> {C.RESET}").strip()
            if raw in ("1", "2", "3", "4"):
                num_players = int(raw)
                break
            cprint("  ⚠  Enter 1, 2, 3, or 4.", C.YELLOW)

        # Collect player names
        player_names: List[str] = []
        for i in range(num_players):
            cprint(f"\n  Enter name for Player {i+1}:", C.WHITE)
            name = input(f"  {C.BOLD}> {C.RESET}").strip()[:20]
            if not name:
                name = f"P{i+1}"
            player_names.append(name)

        if not sys.stdin.isatty() or not sys.stdout.isatty():
            cprint("  ⚠  No interactive terminal. Returning zero scores.", C.YELLOW)
            return {name: 0 for name in player_names}

        all_scores: Dict[str, int] = {}

        for i, name in enumerate(player_names):
            cprint(f"\n  ──────────────────────────────────────", C.CYAN)
            cprint(f"  🎮  {name}'s turn!  (Player {i+1} of {num_players})", C.CYAN + C.BOLD)
            cprint(f"  Controls: W=Up  S=Down  A=Left  D=Right", C.WHITE)
            cprint(f"  Press Q in-game to end your turn early.", C.DIM)
            cprint(f"\n  Press ENTER when {name} is ready...", C.YELLOW)
            try:
                input()
            except EOFError:
                pass

            try:
                score = curses.wrapper(cls._run_one_turn, i, name)
            except Exception as e:
                cprint(f"  ⚠  Pac-Man couldn't launch for {name}: {e}", C.YELLOW)
                score = 0

            all_scores[name] = score
            cprint(f"\n  ✔  {name} finished with {score} pts!", C.GREEN + C.BOLD)

            if i < num_players - 1:
                cprint(f"  Passing to the next player...", C.DIM)
                time.sleep(1.5)

        return all_scores

    @staticmethod
    def resolve(choices: dict) -> dict:
        """choices = {player_name: score_int}. Highest score wins."""
        player_scores: Dict[str, int] = {}
        for player, result in choices.items():
            try:
                player_scores[player] = int(result)
            except (TypeError, ValueError):
                player_scores[player] = 0

        max_score = max(player_scores.values(), default=0)
        winners = [p for p, s in player_scores.items() if s == max_score and max_score > 0]
        return {
            "player_scores": player_scores,
            "winners": winners,
            "high_score": max_score,
        }

    @staticmethod
    def format_result(result: dict, my_name: str) -> str:
        player_scores = result["player_scores"]
        winners = result["winners"]
        lines = [f"\n  {C.BOLD}── Pac-Man Results ──{C.RESET}\n"]
        for player, score in sorted(player_scores.items(), key=lambda x: -x[1]):
            tag = " ← you" if player == my_name else ""
            mark = f"{C.YELLOW}🏆" if player in winners else f"{C.WHITE}👾"
            lines.append(f"  {mark}{C.RESET}  {player}: {C.BOLD}{score}{C.RESET} pts{C.DIM}{tag}{C.RESET}")
        if my_name in winners:
            lines.append(f"\n  {C.GREEN}{C.BOLD}🎉 You had the highest Pac-Man score!{C.RESET}")
        else:
            lines.append(f"\n  {C.RED}Better luck next maze!{C.RESET}")
        return "\n".join(lines)


# ── Game Registry ──────────────────────────────────────────────────────────────

GAMES = {
    "1": HeadsOrTails,
    "2": RockPaperScissors,
    "3": NumberGuess,
    "4": SnakeGame,
    "5": PacmanChase,
    "6": PacManGame,
}


# ── Server ─────────────────────────────────────────────────────────────────────

class _ClientState:
    """Per-client state held by the server."""
    def __init__(self, sock: socket.socket, addr: Tuple[str, int], name: str):
        self.sock = sock
        self.addr = addr
        self.name = name
        self.reader = MessageReader(sock)
        self.round_token: Optional[str] = None
        self.choice: Any = None
        self.choice_received = threading.Event()


class Server:
    def __init__(self, host_plays: bool = True):
        self.host_plays = host_plays
        self.host_name = HOST_NAME_DEFAULT
        self.clients: Dict[str, _ClientState] = {}
        self.client_lock = threading.Lock()
        self.running = True
        self.accept_thread: Optional[threading.Thread] = None
        self.server_sock: Optional[socket.socket] = None

    def _snapshot_clients(self) -> List[_ClientState]:
        with self.client_lock:
            return list(self.clients.values())

    def _drop_client(self, name: str) -> None:
        cs: Optional[_ClientState] = None
        with self.client_lock:
            cs = self.clients.pop(name, None)
        if cs is not None:
            try:
                cs.sock.close()
            except (socket.error, OSError):
                pass
            cprint(f"  ✘  {name} disconnected.", C.YELLOW)

    def _unique_name(self, requested: str, ip: str) -> str:
        base = (requested or "").strip()[:20]
        if not base:
            base = f"Player_{ip.replace('.', '_')}"
        if self.host_plays and base == self.host_name:
            base = base + "_2"
        with self.client_lock:
            if base not in self.clients:
                return base
            i = 2
            while f"{base}_{i}" in self.clients:
                i += 1
            return f"{base}_{i}"

    def broadcast(self, data: dict, exclude: Optional[str] = None) -> None:
        dead: List[str] = []
        for cs in self._snapshot_clients():
            if cs.name == exclude:
                continue
            if not send_msg(cs.sock, data):
                dead.append(cs.name)
        for name in dead:
            self._drop_client(name)

    def _client_loop(self, cs: _ClientState) -> None:
        while self.running:
            msg = cs.reader.read()
            if msg is None:
                break
            mtype = msg.get("type")
            if mtype == "choice":
                token = msg.get("token")
                if cs.round_token is not None and token == cs.round_token:
                    cs.choice = msg.get("choice")
                    cs.choice_received.set()
        self._drop_client(cs.name)

    def _accept_one(self, conn: socket.socket, addr: Tuple[str, int]) -> None:
        reader = MessageReader(conn)
        try:
            conn.settimeout(15.0)
        except (socket.error, OSError):
            pass

        msg = reader.read()
        if not msg or msg.get("type") != "join":
            try:
                conn.close()
            except (socket.error, OSError):
                pass
            return

        name = self._unique_name(msg.get("name", ""), addr[0])

        try:
            conn.settimeout(None)
        except (socket.error, OSError):
            pass

        cs = _ClientState(conn, addr, name)
        cs.reader = reader  # reuse the reader with its buffer

        with self.client_lock:
            self.clients[name] = cs

        if not send_msg(conn, {"type": "welcome", "name": name}):
            self._drop_client(name)
            return

        cprint(f"  ✔  {name} joined from {addr[0]}", C.GREEN)
        self.broadcast({"type": "chat", "msg": f"  📡  {name} connected."}, exclude=name)

        t = threading.Thread(target=self._client_loop, args=(cs,), daemon=True)
        t.start()

    def _accept_loop(self) -> None:
        assert self.server_sock is not None
        while self.running:
            try:
                conn, addr = self.server_sock.accept()
            except socket.timeout:
                continue
            except (socket.error, OSError):
                break
            t = threading.Thread(target=self._accept_one, args=(conn, addr), daemon=True)
            t.start()

    def collect_choices(self, game_class, host_choice: Any = None) -> Dict[str, Any]:
        round_token = f"r{int(time.time() * 1000)}_{random.randint(0, 99999)}"

        clients = self._snapshot_clients()
        for cs in clients:
            cs.choice = None
            cs.choice_received.clear()
            cs.round_token = round_token

        prompt_msg = {"type": "prompt", "game": game_class.NAME, "token": round_token}
        dead: List[str] = []
        for cs in clients:
            if not send_msg(cs.sock, prompt_msg):
                dead.append(cs.name)
        for name in dead:
            self._drop_client(name)

        deadline = time.time() + CHOICE_TIMEOUT_SEC
        clients = self._snapshot_clients()
        for cs in clients:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            cs.choice_received.wait(timeout=remaining)

        choices: Dict[str, Any] = {}
        for cs in self._snapshot_clients():
            if cs.choice_received.is_set() and cs.choice is not None:
                choices[cs.name] = cs.choice
            cs.round_token = None

        if host_choice is not None:
            choices[self.host_name] = host_choice

        return choices

    def _print_scoreboard(self, scores: Dict[str, int]) -> None:
        cprint(f"\n  {C.BOLD}── Scoreboard ──{C.RESET}", C.CYAN)
        if not scores:
            cprint("  (no players)", C.DIM)
            return
        for name, s in sorted(scores.items(), key=lambda kv: -kv[1]):
            bar = "█" * s
            you = " ← you" if name == self.host_name else ""
            cprint(f"  {name}: {C.YELLOW}{bar}{C.RESET} {s}{C.DIM}{you}{C.RESET}", C.WHITE)

    def _shutdown(self) -> None:
        self.running = False
        for cs in self._snapshot_clients():
            try:
                cs.sock.close()
            except (socket.error, OSError):
                pass
        with self.client_lock:
            self.clients.clear()
        if self.server_sock is not None:
            try:
                self.server_sock.close()
            except (socket.error, OSError):
                pass

    def run(self) -> None:
        banner()
        cprint("  ══════════════════════════════════════", C.CYAN)
        cprint("   🖥   HOST MODE", C.CYAN + C.BOLD)
        cprint("  ══════════════════════════════════════", C.CYAN)

        if self.host_plays:
            cprint("\n  Enter your player name:", C.WHITE)
            cprint(f"  {C.DIM}(this is what other players will see in scoreboards){C.RESET}", C.DIM)
            try:
                entered = input(f"  {C.BOLD}Name > {C.RESET}").strip()[:20]
            except EOFError:
                entered = ""
            self.host_name = entered or HOST_NAME_DEFAULT

        ip = get_local_ip()
        cprint(f"\n  Your IP address: {C.BOLD}{C.YELLOW}{ip}{C.RESET}")
        cprint(f"  Port:            {C.BOLD}{PORT}{C.RESET}")
        if self.host_plays:
            cprint(f"  Hosting as:      {C.BOLD}{C.GREEN}{self.host_name}{C.RESET}")
        cprint(f"\n  Other players run:", C.DIM)
        cprint(
            f"  {C.CYAN}python3 pi_party_games.py --join{C.RESET}"
            f"  then enter  {C.BOLD}{ip}{C.RESET}\n"
        )

        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.server_sock.bind(("0.0.0.0", PORT))
        except OSError as e:
            cprint(f"  ✘  Could not bind to port {PORT}: {e}", C.RED)
            cprint("  Is another instance already running?", C.DIM)
            return
        self.server_sock.listen(8)
        self.server_sock.settimeout(SOCKET_POLL_TIMEOUT)

        cprint("  Waiting for players to connect...", C.DIM)
        cprint("  Press [ENTER] when everyone is ready to start.\n", C.DIM)

        self.accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self.accept_thread.start()

        try:
            input()
        except EOFError:
            pass

        with self.client_lock:
            client_count = len(self.clients)
        total = client_count + (1 if self.host_plays else 0)

        if total < 2:
            cprint(f"\n  ⚠  Need at least 2 players to start (have {total}). Exiting.", C.YELLOW)
            self._shutdown()
            return

        cprint(f"\n  🎮  Starting with {total} player(s)!\n", C.GREEN + C.BOLD)
        self.broadcast({"type": "start"})

        scores: Dict[str, int] = {}
        with self.client_lock:
            for name in self.clients:
                scores[name] = 0
        if self.host_plays:
            scores[self.host_name] = 0

        round_num = 0
        try:
            while True:
                round_num += 1
                cprint(f"\n  ══ Round {round_num} ══", C.CYAN + C.BOLD)
                cprint("\n  Select a game:", C.WHITE + C.BOLD)
                for key, g in GAMES.items():
                    cprint(f"    [{key}] {g.NAME}", C.WHITE)
                cprint("    [Q]  Quit / End session", C.DIM)

                pick = ""
                while True:
                    pick = input(f"\n  {C.BOLD}> {C.RESET}").strip().lower()
                    if pick == "q" or pick in GAMES:
                        break
                    cprint("  ⚠  Invalid choice.", C.YELLOW)

                if pick == "q":
                    self.broadcast({"type": "end", "msg": "Host ended the session. Thanks for playing!"})
                    cprint("\n  Session ended. Final scores:", C.CYAN + C.BOLD)
                    self._print_scoreboard(scores)
                    break

                game_class = GAMES[pick]
                self.broadcast({"type": "game_selected", "game": game_class.NAME})

                with self.client_lock:
                    for name in self.clients:
                        if name not in scores:
                            scores[name] = 0

                host_choice = None
                if self.host_plays:
                    cprint(f"\n  {C.BOLD}[{game_class.NAME}]{C.RESET}", C.MAGENTA)
                    host_choice = game_class.prompt_choice()
                    cprint(f"\n  {C.DIM}Waiting for other players...{C.RESET}", C.DIM)

                choices = self.collect_choices(game_class, host_choice=host_choice)

                if not choices:
                    cprint("  ⚠  No choices received. Skipping round.", C.YELLOW)
                    continue

                result = game_class.resolve(choices)

                if self.host_plays and self.host_name in choices:
                    print(game_class.format_result(result, self.host_name))

                for winner in result.get("winners", []):
                    scores[winner] = scores.get(winner, 0) + 1

                self.broadcast({"type": "result", "game": game_class.NAME, "result": result})
                self._print_scoreboard(scores)

                again = input(
                    f"\n  {C.BOLD}Next round? [Enter to continue / Q to quit]{C.RESET} "
                ).strip().lower()
                if again == "q":
                    self.broadcast({"type": "end", "msg": "Host ended the session. Thanks for playing!"})
                    cprint("\n  Thanks for playing!", C.GREEN + C.BOLD)
                    self._print_scoreboard(scores)
                    break
        except KeyboardInterrupt:
            cprint("\n  Interrupted.", C.YELLOW)
            self.broadcast({"type": "end", "msg": "Host disconnected."})
        finally:
            self._shutdown()


# ── Client ─────────────────────────────────────────────────────────────────────

class Client:
    def __init__(self):
        self.name = ""
        self.sock: Optional[socket.socket] = None
        self.reader: Optional[MessageReader] = None

    def run(self) -> None:
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
            self.name = f"Player_{random.randint(100, 999)}"

        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(10.0)
            self.sock.connect((server_ip, PORT))
            self.sock.settimeout(None)
        except (socket.error, OSError) as e:
            cprint(f"\n  ✘  Could not connect to {server_ip}:{PORT} ({e})", C.RED)
            return

        self.reader = MessageReader(self.sock)

        if not send_msg(self.sock, {"type": "join", "name": self.name}):
            cprint("  ✘  Failed to send join message.", C.RED)
            return

        msg = self.reader.read()
        if not msg or msg.get("type") != "welcome":
            cprint("  ✘  Unexpected response from server.", C.RED)
            return

        confirmed = msg.get("name", self.name)
        cprint(f"\n  {C.GREEN}✔  Connected! You joined as: {C.BOLD}{confirmed}{C.RESET}", C.GREEN)
        cprint(f"  {C.DIM}Waiting for the host to start...{C.RESET}\n", C.DIM)

        game_map = {g.NAME: g for g in GAMES.values()}

        try:
            while True:
                msg = self.reader.read()
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
                    token = msg.get("token")
                    game_class = game_map.get(game_name)
                    if game_class is None:
                        cprint(f"  ⚠  Unknown game from host: {game_name}", C.YELLOW)
                        send_msg(self.sock, {"type": "choice", "choice": None, "token": token})
                    else:
                        choice = game_class.prompt_choice()
                        send_msg(self.sock, {"type": "choice", "choice": choice, "token": token})
                        cprint(f"  {C.DIM}Choice sent. Waiting for results...{C.RESET}", C.DIM)

                elif mtype == "result":
                    game_name = msg.get("game", "")
                    result = msg.get("result", {})
                    game_class = game_map.get(game_name)
                    if game_class:
                        print(game_class.format_result(result, confirmed))
                    cprint(f"\n  {C.DIM}Waiting for next round...{C.RESET}", C.DIM)

                elif mtype == "end":
                    cprint(
                        f"\n  {C.CYAN}{C.BOLD}🏁  {msg.get('msg', 'Session ended.')}{C.RESET}",
                        C.CYAN,
                    )
                    break
        except KeyboardInterrupt:
            cprint("\n  Interrupted.", C.YELLOW)
        finally:
            if self.sock is not None:
                try:
                    self.sock.close()
                except (socket.error, OSError):
                    pass


# ── Main Menu ──────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Pi Party Games — Multiplayer LAN games")
    parser.add_argument("--host", action="store_true", help="Start as host/server")
    parser.add_argument("--join", action="store_true", help="Join an existing game")
    parser.add_argument(
        "--no-play",
        action="store_true",
        help="(host only) Run the server without playing yourself",
    )
    args = parser.parse_args()

    if args.host:
        Server(host_plays=not args.no_play).run()
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
        try:
            choice = input(f"  {C.BOLD}> {C.RESET}").strip().lower()
        except EOFError:
            return
        if choice in ("1", "host"):
            Server(host_plays=True).run()
            return
        if choice in ("2", "join"):
            Client().run()
            return
        if choice in ("q", "quit"):
            return
        cprint("  ⚠  Please choose 1, 2, or Q.", C.YELLOW)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        cprint("\n\n  👋 Thanks for playing!", C.CYAN)
        sys.exit(0)
