"""
================================================================================
  Pi Party Games — Multiplayer Terminal Games over LAN
  Compatible with Raspberry Pi OS, Ubuntu LTS, macOS
  Requires: Python 3.8+  |  No external packages needed
================================================================================

  Usage:
    python3 pi_party_games.py              # Interactive menu
    python3 pi_party_games.py --host       # Jump straight to hosting
    python3 pi_party_games.py --join       # Jump straight to joining

  Games:
    1. Heads or Tails
    2. Rock Paper Scissors
    3. Number Guess (1–15)
    4. Strategic Snake   (local run, scores compared)
    5. Pac-Man           (local run, scores compared)

  Players: 2–4 recommended (supports more, but screen space matters)
================================================================================
"""

from __future__ import annotations

import argparse
import json
import os
import random
import socket
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


def banner() -> None:
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


# ── Networking ─────────────────────────────────────────────────────────────────

PORT = 65432
BUFFER = 4096
HOST_NAME = "[Host] You"
CHOICE_TIMEOUT = 300  # seconds to wait for a player to submit
SOCKET_TIMEOUT = 1.0  # for accept loops and graceful shutdown


def get_local_ip() -> str:
    """Best-effort local IP detection."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1.0)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def send_msg(sock: socket.socket, data: dict) -> bool:
    """Send a newline-delimited JSON message. Returns True on success."""
    try:
        raw = json.dumps(data).encode("utf-8")
        sock.sendall(raw + b"\n")
        return True
    except Exception:
        return False


class MessageReader:
    """
    Persistent per-socket buffer that correctly handles:
      - multiple messages arriving in one TCP chunk
      - one message split across multiple chunks
    Previous recv_msg() discarded everything after the first newline. This fixes that.
    """

    def __init__(self, sock: socket.socket):
        self.sock = sock
        self._buf = b""

    def read(self) -> Optional[dict]:
        """Return the next message, or None if the socket closed/errored."""
        while True:
            if b"\n" in self._buf:
                line, self._buf = self._buf.split(b"\n", 1)
                if not line:
                    continue
                try:
                    return json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    # Corrupted frame — skip and keep reading
                    continue
            try:
                chunk = self.sock.recv(BUFFER)
            except socket.timeout:
                continue
            except Exception:
                return None
            if not chunk:
                return None
            self._buf += chunk


# ── Game Interface ─────────────────────────────────────────────────────────────
#
# Every game implements three static methods:
#   prompt_choice() -> Any        run by each player locally; returns their move/result
#   resolve(choices) -> dict      run by server; choices is {name: move}; returns result dict
#   format_result(result, my_name) -> str   printable summary from a player's POV
#
# The result dict must have a "winners" key (list of player names) for scoring.


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
    def resolve(choices: Dict[str, str]) -> dict:
        """Each player scores a point for every other player they beat."""
        players = list(choices.keys())
        scores = {p: 0 for p in players}
        for i, p1 in enumerate(players):
            for p2 in players[i + 1:]:
                c1, c2 = choices[p1], choices[p2]
                if c1 == c2:
                    continue
                if RockPaperScissors.BEATS[c1] == c2:
                    scores[p1] += 1
                else:
                    scores[p2] += 1

        if not scores:
            return {"choices": choices, "scores": {}, "winners": [], "tie": True}

        max_score = max(scores.values())
        # Winners: players with top score, but only if they didn't all tie
        top = [p for p, s in scores.items() if s == max_score]
        winners = top if len(top) < len(players) else []
        return {
            "choices": choices,
            "scores": scores,
            "winners": winners,
            "tie": len(winners) == 0,
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
            lines.append(
                f"  {mark}{C.RESET}  {player}: {emoji.get(choice, '?')} {choice}"
                f"{C.DIM}{tag}{C.RESET}"
            )
        if tie:
            lines.append(f"\n  {C.YELLOW}{C.BOLD}🤝 It's a tie!{C.RESET}")
        elif my_name in winners:
            lines.append(f"\n  {C.GREEN}{C.BOLD}🏆 You win!{C.RESET}")
        else:
            lines.append(f"\n  {C.RED}You lost this round.{C.RESET}")
        return "\n".join(lines)


class NumberGuess:
    NAME = "Number Guess"
    MIN, MAX = 1, 15

    @staticmethod
    def prompt_choice() -> int:
        while True:
            cprint(f"\n  🔢  Guess the secret number ({NumberGuess.MIN}–{NumberGuess.MAX}):", C.CYAN)
            raw = input(f"\n  {C.BOLD}> {C.RESET}").strip()
            try:
                num = int(raw)
                if NumberGuess.MIN <= num <= NumberGuess.MAX:
                    return num
                cprint(f"  ⚠  Enter a number between {NumberGuess.MIN} and {NumberGuess.MAX}.", C.YELLOW)
            except ValueError:
                cprint("  ⚠  That's not a valid number.", C.YELLOW)

    @staticmethod
    def resolve(choices: Dict[str, int]) -> dict:
        secret = random.randint(NumberGuess.MIN, NumberGuess.MAX)
        normalized = {p: int(g) for p, g in choices.items()}
        distances = {p: abs(g - secret) for p, g in normalized.items()}
        if not distances:
            return {"secret": secret, "choices": {}, "distances": {}, "winners": [], "exact": False}
        min_dist = min(distances.values())
        winners = [p for p, d in distances.items() if d == min_dist]
        return {
            "secret": secret,
            "choices": normalized,
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
            dist = distances[player]
            if dist == 0:
                mark, note = f"{C.GREEN}🎯", "exact!"
            elif player in winners:
                mark, note = f"{C.GREEN}✔", f"off by {dist}"
            else:
                mark, note = f"{C.RED}✘", f"off by {dist}"
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


# ── Curses helpers (shared by Snake + Pac-Man) ─────────────────────────────────

def _curses_available() -> bool:
    return HAS_CURSES and sys.stdin.isatty() and sys.stdout.isatty()


def _run_in_curses(fn: Callable[[Any], dict], fallback: dict, intro_lines: List[Tuple[str, str]]) -> dict:
    """
    Shared launcher for curses games. Prints an intro, then runs fn via curses.wrapper.
    Returns `fallback` if curses isn't available or the game crashes.
    """
    for text, color in intro_lines:
        cprint(text, color)
    time.sleep(1)

    if not _curses_available():
        cprint("  ⚠  Interactive terminal not available here. Scoring 0 for this round.", C.YELLOW)
        return fallback

    try:
        return curses.wrapper(fn)
    except Exception as e:
        cprint(f"  ⚠  Couldn't run in curses mode ({e}). Scoring 0 for this round.", C.YELLOW)
        return fallback


# ── Snake ──────────────────────────────────────────────────────────────────────

class SnakeGame:
    NAME = "Strategic Snake"
    GRID_W = 24
    GRID_H = 14
    TICK = 0.12

    _DIRS = {
        "up":    (0, -1),
        "down":  (0, 1),
        "left":  (-1, 0),
        "right": (1, 0),
    }

    @staticmethod
    def _dir_from_key(key: int) -> Optional[Tuple[int, int]]:
        if key in (ord("w"), ord("W"), curses.KEY_UP):    return SnakeGame._DIRS["up"]
        if key in (ord("s"), ord("S"), curses.KEY_DOWN):  return SnakeGame._DIRS["down"]
        if key in (ord("a"), ord("A"), curses.KEY_LEFT):  return SnakeGame._DIRS["left"]
        if key in (ord("d"), ord("D"), curses.KEY_RIGHT): return SnakeGame._DIRS["right"]
        return None

    @staticmethod
    def _spawn_food(snake: List[Tuple[int, int]]) -> Tuple[int, int]:
        while True:
            food = (
                random.randint(1, SnakeGame.GRID_W - 2),
                random.randint(1, SnakeGame.GRID_H - 2),
            )
            if food not in snake:
                return food

    @staticmethod
    def _draw(stdscr, snake, food, score):
        stdscr.erase()
        try:
            stdscr.addstr(0, 0, "Snake: WASD or arrows to move. Q to quit.")
            stdscr.addstr(1, 0, f"Score: {score}")
        except curses.error:
            pass

        for y in range(SnakeGame.GRID_H):
            row_parts = []
            for x in range(SnakeGame.GRID_W):
                pos = (x, y)
                if x == 0 or y == 0 or x == SnakeGame.GRID_W - 1 or y == SnakeGame.GRID_H - 1:
                    row_parts.append("##")
                elif pos == snake[0]:
                    row_parts.append("@@")
                elif pos in snake:
                    row_parts.append("[]")
                elif pos == food:
                    row_parts.append("()")
                else:
                    row_parts.append("  ")
            try:
                stdscr.addstr(y + 3, 0, "".join(row_parts))
            except curses.error:
                pass
        stdscr.refresh()

    @staticmethod
    def _play(stdscr) -> dict:
        curses.curs_set(0)
        stdscr.nodelay(True)
        stdscr.keypad(True)
        stdscr.timeout(int(SnakeGame.TICK * 1000))

        cx, cy = SnakeGame.GRID_W // 2, SnakeGame.GRID_H // 2
        snake = [(cx, cy), (cx - 1, cy), (cx - 2, cy)]
        direction = (1, 0)
        food = SnakeGame._spawn_food(snake)
        score = 0
        alive = True

        while True:
            SnakeGame._draw(stdscr, snake, food, score)
            key = stdscr.getch()

            if key in (ord("q"), ord("Q")):
                alive = False
                break

            new_dir = SnakeGame._dir_from_key(key)
            if new_dir and new_dir != (-direction[0], -direction[1]):
                direction = new_dir

            new_head = (snake[0][0] + direction[0], snake[0][1] + direction[1])
            hit_wall = (
                new_head[0] <= 0 or new_head[0] >= SnakeGame.GRID_W - 1
                or new_head[1] <= 0 or new_head[1] >= SnakeGame.GRID_H - 1
            )
            if hit_wall or new_head in snake:
                alive = False
                break

            snake.insert(0, new_head)
            if new_head == food:
                score += 1
                food = SnakeGame._spawn_food(snake)
            else:
                snake.pop()

        SnakeGame._draw(stdscr, snake, food, score)
        try:
            stdscr.addstr(SnakeGame.GRID_H + 4, 0, f"Game over. Score: {score}. Press any key.")
        except curses.error:
            pass
        stdscr.nodelay(False)
        stdscr.getch()
        return {"score": score, "alive": alive}

    @staticmethod
    def prompt_choice() -> dict:
        return _run_in_curses(
            SnakeGame._play,
            fallback={"score": 0, "alive": False},
            intro_lines=[
                ("\n  Launching Snake...", C.CYAN),
                ("  Use WASD or arrow keys. Avoid walls and yourself.", C.WHITE),
            ],
        )

    @staticmethod
    def resolve(choices: Dict[str, dict]) -> dict:
        normalized = {}
        for p, r in choices.items():
            if isinstance(r, dict):
                normalized[p] = {"score": int(r.get("score", 0)), "alive": bool(r.get("alive", False))}
            else:
                normalized[p] = {"score": 0, "alive": False}
        max_score = max((r["score"] for r in normalized.values()), default=0)
        winners = [p for p, r in normalized.items() if r["score"] == max_score and max_score > 0]
        return {"choices": normalized, "winners": winners, "high_score": max_score}

    @staticmethod
    def format_result(result: dict, my_name: str) -> str:
        choices = result["choices"]
        winners = result["winners"]
        lines = [f"\n  {C.BOLD}── Snake Results ──{C.RESET}\n"]
        ranked = sorted(choices.items(), key=lambda i: i[1]["score"], reverse=True)
        for p, stats in ranked:
            tag = " ← you" if p == my_name else ""
            if p in winners:
                mark, note = f"{C.GREEN}🏆", "winner"
            else:
                note = "crashed" if not stats["alive"] else "finished"
                mark = f"{C.WHITE}🐍"
            lines.append(
                f"  {mark}{C.RESET}  {p}: {C.BOLD}{stats['score']}{C.RESET} apples"
                f" {C.DIM}({note}){tag}{C.RESET}"
            )
        if not winners:
            lines.append(f"\n  {C.YELLOW}No one scored this round.{C.RESET}")
        elif my_name in winners:
            lines.append(f"\n  {C.GREEN}{C.BOLD}You won the snake round!{C.RESET}")
        else:
            lines.append(f"\n  {C.CYAN}Top score: {', '.join(winners)}.{C.RESET}")
        return "\n".join(lines)


# ── Pac-Man ────────────────────────────────────────────────────────────────────
#
# Simple single-player Pac-Man. Each player runs locally; scores compared after.
# Maze is a hand-authored ASCII grid. One ghost chases the player.
#
# Cell legend in MAZE:
#   '#' = wall
#   '.' = pellet  (1 pt)
#   'o' = power pellet (5 pts + makes ghost flee for a bit)
#   ' ' = empty
#   'P' = player start
#   'G' = ghost start
#
# Keeping it minimal & readable: one ghost, no tunnels, no fruit. Still feels like Pac-Man.

class PacMan:
    NAME = "Pac-Man"
    TICK = 0.15
    POWER_DURATION = 25  # in ticks
    GHOST_EATEN_BONUS = 10

    MAZE = [
        "#####################",
        "#o........#........o#",
        "#.##.####.#.####.##.#",
        "#.#.....#.#.#.....#.#",
        "#.#.###.#.#.#.###.#.#",
        "#...#.....G.....#...#",
        "###.#.#######.#.#.###",
        "#.....#..P..#.......#",
        "#.###.#.###.#.#.###.#",
        "#.#.....#.#.#.....#.#",
        "#.##.####.#.####.##.#",
        "#o........#........o#",
        "#####################",
    ]

    @staticmethod
    def _parse_maze() -> Tuple[List[List[str]], Tuple[int, int], Tuple[int, int], int]:
        """Return (grid, player_pos, ghost_pos, total_pellets). Grid has P/G replaced with ' '."""
        grid = [list(row) for row in PacMan.MAZE]
        player = (0, 0)
        ghost = (0, 0)
        pellets = 0
        for y, row in enumerate(grid):
            for x, ch in enumerate(row):
                if ch == "P":
                    player = (x, y)
                    grid[y][x] = " "
                elif ch == "G":
                    ghost = (x, y)
                    grid[y][x] = " "
                elif ch in (".", "o"):
                    pellets += 1
        return grid, player, ghost, pellets

    @staticmethod
    def _dir_from_key(key: int) -> Optional[Tuple[int, int]]:
        if key in (ord("w"), ord("W"), curses.KEY_UP):    return (0, -1)
        if key in (ord("s"), ord("S"), curses.KEY_DOWN):  return (0, 1)
        if key in (ord("a"), ord("A"), curses.KEY_LEFT):  return (-1, 0)
        if key in (ord("d"), ord("D"), curses.KEY_RIGHT): return (1, 0)
        return None

    @staticmethod
    def _passable(grid: List[List[str]], pos: Tuple[int, int]) -> bool:
        x, y = pos
        if y < 0 or y >= len(grid) or x < 0 or x >= len(grid[0]):
            return False
        return grid[y][x] != "#"

    @staticmethod
    def _bfs_next_step(
        grid: List[List[str]],
        start: Tuple[int, int],
        target: Tuple[int, int],
    ) -> Optional[Tuple[int, int]]:
        """Return the next position along the shortest path from start to target, or None."""
        if start == target:
            return None
        from collections import deque
        came_from: Dict[Tuple[int, int], Tuple[int, int]] = {start: start}
        q = deque([start])
        while q:
            cur = q.popleft()
            if cur == target:
                break
            for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
                nxt = (cur[0] + dx, cur[1] + dy)
                if nxt in came_from:
                    continue
                if not PacMan._passable(grid, nxt):
                    continue
                came_from[nxt] = cur
                q.append(nxt)
        if target not in came_from:
            return None
        # Walk back from target to find the first step away from start
        cur = target
        while came_from[cur] != start:
            cur = came_from[cur]
        return cur

    @staticmethod
    def _ghost_step(
        grid: List[List[str]],
        ghost: Tuple[int, int],
        last_dir: Tuple[int, int],
        target: Tuple[int, int],
        flee: bool,
    ) -> Tuple[Tuple[int, int], Tuple[int, int]]:
        """
        Pick a direction using BFS. Chases target (shortest path), or picks the
        neighbor maximizing BFS distance to target when fleeing. 10% jitter keeps
        it from feeling perfectly robotic.
        """
        # Flee mode: pick passable neighbor with maximum shortest-path distance to target
        if flee:
            best_pos = ghost
            best_dir = last_dir
            best_dist = -1
            for d in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
                cand = (ghost[0] + d[0], ghost[1] + d[1])
                if not PacMan._passable(grid, cand):
                    continue
                # Estimate distance by BFS from candidate to target
                dist = PacMan._bfs_distance(grid, cand, target)
                if dist > best_dist:
                    best_dist = dist
                    best_pos = cand
                    best_dir = d
            return best_pos, best_dir

        # Chase mode: BFS from ghost to target, take first step
        if random.random() < 0.10:
            # Occasional wander: pick any valid neighbor
            candidates = []
            for d in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
                cand = (ghost[0] + d[0], ghost[1] + d[1])
                if PacMan._passable(grid, cand):
                    candidates.append((cand, d))
            if candidates:
                pos, direction = random.choice(candidates)
                return pos, direction

        next_pos = PacMan._bfs_next_step(grid, ghost, target)
        if next_pos is None:
            return ghost, last_dir
        direction = (next_pos[0] - ghost[0], next_pos[1] - ghost[1])
        return next_pos, direction

    @staticmethod
    def _bfs_distance(grid: List[List[str]], start: Tuple[int, int], target: Tuple[int, int]) -> int:
        """Shortest-path distance from start to target (or a large number if unreachable)."""
        if start == target:
            return 0
        from collections import deque
        visited = {start}
        q = deque([(start, 0)])
        while q:
            pos, d = q.popleft()
            if pos == target:
                return d
            for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
                nxt = (pos[0] + dx, pos[1] + dy)
                if nxt in visited or not PacMan._passable(grid, nxt):
                    continue
                visited.add(nxt)
                q.append((nxt, d + 1))
        return 10_000

    @staticmethod
    def _draw(stdscr, grid, player, ghost, score, pellets_left, power_left, msg: str = ""):
        stdscr.erase()
        try:
            stdscr.addstr(0, 0, "Pac-Man: WASD or arrows. Q to quit.")
            status = f"Score: {score:4d}    Pellets: {pellets_left:3d}"
            if power_left > 0:
                status += f"    POWER: {power_left}"
            stdscr.addstr(1, 0, status)
        except curses.error:
            pass

        for y, row in enumerate(grid):
            for x, ch in enumerate(row):
                if (x, y) == player:
                    draw_ch = "C"
                elif (x, y) == ghost:
                    draw_ch = "M" if power_left > 0 else "G"
                elif ch == "#":
                    draw_ch = "#"
                elif ch == ".":
                    draw_ch = "."
                elif ch == "o":
                    draw_ch = "o"
                else:
                    draw_ch = " "
                try:
                    stdscr.addstr(y + 3, x, draw_ch)
                except curses.error:
                    pass

        if msg:
            try:
                stdscr.addstr(len(grid) + 4, 0, msg)
            except curses.error:
                pass
        stdscr.refresh()

    @staticmethod
    def _play(stdscr) -> dict:
        curses.curs_set(0)
        stdscr.nodelay(True)
        stdscr.keypad(True)
        stdscr.timeout(int(PacMan.TICK * 1000))

        grid, player, ghost, total_pellets = PacMan._parse_maze()
        pellets_left = total_pellets
        score = 0
        direction = (0, 0)      # stationary until player presses a key
        queued_dir = (0, 0)
        ghost_last_dir = (0, 0)
        power_left = 0
        alive = True
        won = False
        ghost_move_tick = False  # ghost moves every other tick (slower than player)

        while True:
            PacMan._draw(stdscr, grid, player, ghost, score, pellets_left, power_left)
            key = stdscr.getch()

            if key in (ord("q"), ord("Q")):
                alive = False
                break

            new_dir = PacMan._dir_from_key(key)
            if new_dir is not None:
                queued_dir = new_dir

            # Try queued direction first (allows pre-turning at corners)
            if queued_dir != (0, 0):
                test = (player[0] + queued_dir[0], player[1] + queued_dir[1])
                if PacMan._passable(grid, test):
                    direction = queued_dir
                    queued_dir = (0, 0)

            # Move player if current direction is passable
            if direction != (0, 0):
                test = (player[0] + direction[0], player[1] + direction[1])
                if PacMan._passable(grid, test):
                    player = test

            # Eat pellet under player
            cell = grid[player[1]][player[0]]
            if cell == ".":
                grid[player[1]][player[0]] = " "
                score += 1
                pellets_left -= 1
            elif cell == "o":
                grid[player[1]][player[0]] = " "
                score += 5
                pellets_left -= 1
                power_left = PacMan.POWER_DURATION

            # Win condition
            if pellets_left <= 0:
                won = True
                score += 50  # clear bonus
                break

            # Ghost moves every other tick
            if ghost_move_tick:
                ghost, ghost_last_dir = PacMan._ghost_step(
                    grid, ghost, ghost_last_dir, player, flee=(power_left > 0)
                )
            ghost_move_tick = not ghost_move_tick

            # Collision check
            if player == ghost:
                if power_left > 0:
                    score += PacMan.GHOST_EATEN_BONUS
                    # Respawn ghost at its starting area (find a non-wall cell near top-middle)
                    ghost = PacMan._respawn_ghost(grid)
                    ghost_last_dir = (0, 0)
                else:
                    alive = False
                    break

            if power_left > 0:
                power_left -= 1

        # Final frame
        if won:
            final_msg = f"You cleared the maze! Final score: {score}. Press any key."
        elif alive:
            final_msg = f"Quit. Final score: {score}. Press any key."
        else:
            final_msg = f"The ghost got you! Final score: {score}. Press any key."
        PacMan._draw(stdscr, grid, player, ghost, score, pellets_left, power_left, final_msg)
        stdscr.nodelay(False)
        stdscr.getch()
        return {"score": score, "alive": alive, "won": won}

    @staticmethod
    def _respawn_ghost(grid: List[List[str]]) -> Tuple[int, int]:
        """Find a reasonable respawn cell (first non-wall cell in the middle band)."""
        h = len(grid)
        w = len(grid[0])
        mid_y = h // 2
        for dy in range(0, 4):
            for y in (mid_y - dy, mid_y + dy):
                if 0 <= y < h:
                    for x in range(w // 2 - 3, w // 2 + 4):
                        if 0 <= x < w and grid[y][x] != "#":
                            return (x, y)
        # Fallback
        return (w // 2, h // 2)

    @staticmethod
    def prompt_choice() -> dict:
        return _run_in_curses(
            PacMan._play,
            fallback={"score": 0, "alive": False, "won": False},
            intro_lines=[
                ("\n  Launching Pac-Man...", C.CYAN),
                ("  Use WASD or arrow keys. Eat all pellets, avoid G (ghost).", C.WHITE),
                ("  Power pellets (o) let you eat the ghost for bonus points.", C.WHITE),
            ],
        )

    @staticmethod
    def resolve(choices: Dict[str, dict]) -> dict:
        normalized = {}
        for p, r in choices.items():
            if isinstance(r, dict):
                normalized[p] = {
                    "score": int(r.get("score", 0)),
                    "alive": bool(r.get("alive", False)),
                    "won": bool(r.get("won", False)),
                }
            else:
                normalized[p] = {"score": 0, "alive": False, "won": False}
        max_score = max((r["score"] for r in normalized.values()), default=0)
        winners = [p for p, r in normalized.items() if r["score"] == max_score and max_score > 0]
        return {"choices": normalized, "winners": winners, "high_score": max_score}

    @staticmethod
    def format_result(result: dict, my_name: str) -> str:
        choices = result["choices"]
        winners = result["winners"]
        lines = [f"\n  {C.BOLD}── Pac-Man Results ──{C.RESET}\n"]
        ranked = sorted(choices.items(), key=lambda i: i[1]["score"], reverse=True)
        for p, stats in ranked:
            tag = " ← you" if p == my_name else ""
            if p in winners:
                mark = f"{C.GREEN}🏆"
            else:
                mark = f"{C.YELLOW}🟡"
            if stats.get("won"):
                note = "cleared maze!"
            elif not stats["alive"]:
                note = "eaten"
            else:
                note = "quit"
            lines.append(
                f"  {mark}{C.RESET}  {p}: {C.BOLD}{stats['score']}{C.RESET} pts"
                f" {C.DIM}({note}){tag}{C.RESET}"
            )
        if not winners:
            lines.append(f"\n  {C.YELLOW}No one scored this round.{C.RESET}")
        elif my_name in winners:
            lines.append(f"\n  {C.GREEN}{C.BOLD}You won the Pac-Man round!{C.RESET}")
        else:
            lines.append(f"\n  {C.CYAN}Top score: {', '.join(winners)}.{C.RESET}")
        return "\n".join(lines)


# ── Game Registry ──────────────────────────────────────────────────────────────

GAMES = {
    "1": HeadsOrTails,
    "2": RockPaperScissors,
    "3": NumberGuess,
    "4": SnakeGame,
    "5": PacMan,
}


# ── Server ─────────────────────────────────────────────────────────────────────

class Server:
    def __init__(self, host_plays: bool = True):
        self.host_plays = host_plays
        self.clients: Dict[str, socket.socket] = {}   # name -> socket
        self.readers: Dict[str, MessageReader] = {}   # name -> reader
        self.lock = threading.Lock()
        self.running = True
        self.accept_thread: Optional[threading.Thread] = None
        self.server_sock: Optional[socket.socket] = None

    def _unique_name(self, requested: str, fallback_ip: str) -> str:
        """Ensure the player name doesn't collide with an existing one."""
        base = (requested or f"Player_{fallback_ip}").strip()[:20] or f"Player_{fallback_ip}"
        if base == HOST_NAME:
            base = base + "_2"
        with self.lock:
            if base not in self.clients:
                return base
            i = 2
            while f"{base}_{i}" in self.clients:
                i += 1
            return f"{base}_{i}"

    def broadcast(self, data: dict, exclude: Optional[str] = None) -> None:
        dead: List[str] = []
        with self.lock:
            for name, sock in list(self.clients.items()):
                if name == exclude:
                    continue
                if not send_msg(sock, data):
                    dead.append(name)
        for name in dead:
            self._drop_client(name)

    def _drop_client(self, name: str) -> None:
        with self.lock:
            sock = self.clients.pop(name, None)
            self.readers.pop(name, None)
        if sock:
            try:
                sock.close()
            except Exception:
                pass
        cprint(f"  ✘  {name} disconnected.", C.YELLOW)

    def _handle_join(self, conn: socket.socket, addr) -> Optional[str]:
        """Read join message, register the client, send welcome. Returns assigned name or None."""
        reader = MessageReader(conn)
        conn.settimeout(10.0)
        try:
            msg = reader.read()
        except Exception:
            msg = None
        finally:
            conn.settimeout(None)

        if not msg or msg.get("type") != "join":
            try:
                conn.close()
            except Exception:
                pass
            return None

        name = self._unique_name(str(msg.get("name", "")), addr[0])
        with self.lock:
            self.clients[name] = conn
            self.readers[name] = reader

        if not send_msg(conn, {"type": "welcome", "name": name}):
            self._drop_client(name)
            return None

        cprint(f"  ✔  {name} joined from {addr[0]}", C.GREEN)
        self.broadcast({"type": "chat", "msg": f"  📡  {name} connected."}, exclude=name)
        return name

    def _accept_loop(self) -> None:
        while self.running:
            try:
                assert self.server_sock is not None
                conn, addr = self.server_sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._handle_join, args=(conn, addr), daemon=True).start()

    def collect_choices(self, game_class, host_choice=None) -> Dict[str, Any]:
        """Prompt each client in parallel, gather their responses."""
        with self.lock:
            targets = list(self.clients.items())

        responses: Dict[str, Any] = {}
        responses_lock = threading.Lock()
        dead: List[str] = []

        def ask(name: str, sock: socket.socket):
            if not send_msg(sock, {"type": "prompt", "game": game_class.NAME}):
                dead.append(name)
                return
            with self.lock:
                reader = self.readers.get(name)
            if reader is None:
                return
            try:
                sock.settimeout(CHOICE_TIMEOUT)
            except Exception:
                pass
            try:
                msg = reader.read()
            except Exception:
                msg = None
            finally:
                try:
                    sock.settimeout(None)
                except Exception:
                    pass
            if msg is None:
                dead.append(name)
                return
            if msg.get("type") == "choice":
                with responses_lock:
                    responses[name] = msg.get("choice")

        threads = [threading.Thread(target=ask, args=(n, s), daemon=True) for n, s in targets]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for name in dead:
            self._drop_client(name)

        choices: Dict[str, Any] = dict(responses)
        if host_choice is not None:
            choices[HOST_NAME] = host_choice
        return choices

    def _print_scoreboard(self, scores: Dict[str, int]) -> None:
        cprint(f"\n  {C.BOLD}── Scoreboard ──{C.RESET}", C.CYAN)
        if not scores:
            cprint("  (no players)", C.DIM)
            return
        for name, s in sorted(scores.items(), key=lambda x: -x[1]):
            bar = "█" * s
            you = " ← you" if name == HOST_NAME else ""
            cprint(f"  {name}: {C.YELLOW}{bar}{C.RESET} {s}{C.DIM}{you}{C.RESET}", C.WHITE)

    def run(self) -> None:
        banner()
        cprint("  ══════════════════════════════════════", C.CYAN)
        cprint("   🖥   HOST MODE", C.CYAN + C.BOLD)
        cprint("  ══════════════════════════════════════", C.CYAN)

        ip = get_local_ip()
        cprint(f"\n  Your IP address: {C.BOLD}{C.YELLOW}{ip}{C.RESET}")
        cprint(f"  Port:            {C.BOLD}{PORT}{C.RESET}")
        cprint(f"\n  Tell other players to run:", C.DIM)
        cprint(f"  {C.CYAN}python3 pi_party_games.py --join{C.RESET}  then enter  {C.BOLD}{ip}{C.RESET}\n")

        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.server_sock.bind(("", PORT))
        except OSError as e:
            cprint(f"  ✘  Could not bind to port {PORT}: {e}", C.RED)
            return
        self.server_sock.listen(8)
        self.server_sock.settimeout(SOCKET_TIMEOUT)

        cprint("  Waiting for players to connect...", C.DIM)
        cprint("  Press [ENTER] when everyone is ready to start.\n", C.DIM)

        self.accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self.accept_thread.start()

        try:
            input()
        except EOFError:
            pass

        with self.lock:
            client_count = len(self.clients)
        total = client_count + (1 if self.host_plays else 0)

        if total < 1:
            cprint("\n  ⚠  No players connected. Exiting.", C.YELLOW)
            self._shutdown()
            return
        if total < 2:
            cprint(f"\n  ⚠  Only {total} player — games need at least 2. Exiting.", C.YELLOW)
            self._shutdown()
            return

        cprint(f"\n  🎮  Starting with {total} player(s)!\n", C.GREEN + C.BOLD)
        self.broadcast({"type": "start"})

        scores: Dict[str, int] = {}
        with self.lock:
            for name in self.clients:
                scores[name] = 0
        if self.host_plays:
            scores[HOST_NAME] = 0

        round_num = 0
        try:
            while True:
                round_num += 1
                cprint(f"\n  ══ Round {round_num} ══", C.CYAN + C.BOLD)

                cprint("\n  Select a game:", C.WHITE + C.BOLD)
                for key, g in GAMES.items():
                    cprint(f"    [{key}] {g.NAME}", C.WHITE)
                cprint(f"    [Q]  Quit / End session", C.DIM)

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

                # Sync any newly registered players into scores
                with self.lock:
                    for name in self.clients:
                        scores.setdefault(name, 0)

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

                if self.host_plays and HOST_NAME in choices:
                    print(game_class.format_result(result, HOST_NAME))

                for winner in result.get("winners", []):
                    if winner in scores:
                        scores[winner] += 1
                    else:
                        scores[winner] = 1

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

    def _shutdown(self) -> None:
        self.running = False
        with self.lock:
            sockets = list(self.clients.values())
            self.clients.clear()
            self.readers.clear()
        for s in sockets:
            try:
                s.close()
            except Exception:
                pass
        if self.server_sock:
            try:
                self.server_sock.close()
            except Exception:
                pass


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
        except Exception as e:
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
                    game_class = game_map.get(game_name)
                    if game_class is None:
                        cprint(f"  ⚠  Unknown game from host: {game_name}", C.YELLOW)
                        send_msg(self.sock, {"type": "choice", "choice": None})
                    else:
                        choice = game_class.prompt_choice()
                        send_msg(self.sock, {"type": "choice", "choice": choice})
                        cprint(f"  {C.DIM}Choice sent. Waiting for results...{C.RESET}", C.DIM)

                elif mtype == "result":
                    game_name = msg.get("game", "")
                    result = msg.get("result", {})
                    game_class = game_map.get(game_name)
                    if game_class:
                        print(game_class.format_result(result, confirmed))
                    cprint(f"\n  {C.DIM}Waiting for next round...{C.RESET}", C.DIM)

                elif mtype == "end":
                    cprint(f"\n  {C.CYAN}{C.BOLD}🏁  {msg.get('msg', 'Session ended.')}{C.RESET}", C.CYAN)
                    break
        except KeyboardInterrupt:
            cprint("\n  Interrupted.", C.YELLOW)
        finally:
            if self.sock:
                try:
                    self.sock.close()
                except Exception:
                    pass


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Pi Party Games — Multiplayer LAN games")
    parser.add_argument("--host", action="store_true", help="Start as host/server")
    parser.add_argument("--join", action="store_true", help="Join an existing game")
    parser.add_argument("--no-play", action="store_true", help="(host only) Don't play, just run the server")
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
        sys.exit(0)
