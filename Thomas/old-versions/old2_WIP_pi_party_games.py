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
    4. Pacman Chase         (highest score after a 45-second run wins)

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
        # Fallback: ANSI clear
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
HOST_NAME = "[Host] You"
CHOICE_TIMEOUT_SEC = 120  # how long to wait for a player's choice (covers Pacman)
SOCKET_POLL_TIMEOUT = 0.5  # for accept loops, so we can shut down cleanly


def get_local_ip() -> str:
    """Best-effort local IP detection."""
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
    """Send a newline-delimited JSON message. Returns True on success."""
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
    A naive recv-and-split-on-newline drops everything after the first '\\n',
    which causes silent data loss on fast LANs. This class fixes that.
    """

    def __init__(self, sock: socket.socket):
        self.sock = sock
        self._buf = b""
        self._closed = False

    def read(self) -> Optional[dict]:
        """Return the next message, or None if the socket closed/errored."""
        while True:
            if b"\n" in self._buf:
                line, self._buf = self._buf.split(b"\n", 1)
                if not line:
                    continue
                try:
                    return json.loads(line.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    # Skip malformed frame and keep going
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
#
# Each game implements:
#   NAME           -- string identifier
#   prompt_choice() -> Any        run by each player; returns their move/result
#   resolve(choices) -> dict       run by server; returns {"winners": [...], ...}
#   format_result(result, my_name) -> str
#
# IMPORTANT: every game in this build resolves each player INDEPENDENTLY against
# something random (a coin flip, a CPU move, a target number, a Pacman run).
# Players are not pitted against each other -- they're all competing in parallel.


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
    """
    Each player picks rock/paper/scissors. The COMPUTER picks one move at random.
    Every player whose pick beats the computer wins; ties and losses do not.
    Players are not pitted against each other.
    """
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
        lines = [
            f"\n  🤖  Computer played: {C.BOLD}{C.YELLOW}{cpu_emoji} {cpu}{C.RESET}\n"
        ]
        # Sort: winners first, then ties, then losses
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
            valid = False
            num = 0
            try:
                num = int(raw)
                valid = NumberGuess.TARGET_MIN <= num <= NumberGuess.TARGET_MAX
            except ValueError:
                valid = False
            if valid:
                return num
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


# ── Pacman Chase ───────────────────────────────────────────────────────────────
#
# Single-player curses game. Each player runs it locally; scores are compared.
# - Walls drawn as solid block (█) so the maze is clearly visible.
# - 3 lives; getting caught costs a life and respawns; running out ends the game.
# - Ghosts move at half the speed of Pacman so the game is playable.
# - Hardcoded LAYOUT grid (1=wall, 0=open) constrains movement to corridors.

class PacmanChase:
    NAME = "Pacman Chase"
    GRID_WIDTH = 21
    GRID_HEIGHT = 13
    TICK_RATE = 0.15
    MAX_LIVES = 3
    GAME_DURATION = 45  # seconds
    PELLET_COUNT = 14

    # 1 = wall, 0 = corridor. Must be GRID_HEIGHT rows of GRID_WIDTH ints.
    # Symmetric Pacman-style maze, fully connected.
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
        # Build the key map lazily, after curses is initialized.
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
        """Place Pacman near the center, ghosts far from Pacman."""
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
        """
        Return the next cell along the shortest path from start to target,
        or None if target is unreachable. Uses BFS so the ghost doesn't get
        stuck oscillating against walls (which a greedy heuristic does).
        """
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
        # Walk back from target to find the cell adjacent to start
        cur = target
        while came_from[cur] != start:
            cur = came_from[cur]
        return cur

    @staticmethod
    def _move_ghost(
        ghost: Tuple[int, int],
        target: Tuple[int, int],
    ) -> Tuple[int, int]:
        """
        Use BFS to chase the player. Adds a small chance to pick a random
        neighbor instead so two ghosts don't always end up on the same cell.
        """
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
        """Run the game in curses. Returns final score."""
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
                f"Time: {time_left:>2}s   [WASD/Arrows]  [Q to quit]"
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

        # Main game loop
        while True:
            if quit_pressed:
                break
            if lives <= 0:
                break
            if time.time() - start_t >= PacmanChase.GAME_DURATION:
                break

            # Brief freeze after losing a life so the player can see what happened
            if respawning and time.time() < respawn_until:
                render("  💀 You were caught! Respawning...")
                drain_key = stdscr.getch()
                while drain_key != -1:
                    drain_key = stdscr.getch()
                continue
            if respawning and time.time() >= respawn_until:
                respawning = False

            # ── Input ──
            key = stdscr.getch()
            if key in (ord("q"), ord("Q")):
                quit_pressed = True
                continue
            if key in PacmanChase.DIRECTION_KEYS:
                queued = PacmanChase.DIRECTION_KEYS[key]

            # Try queued direction first (allows pre-turning at corners)
            if queued != (0, 0):
                tx, ty = pacman_x + queued[0], pacman_y + queued[1]
                if not PacmanChase._is_wall(tx, ty):
                    direction = queued
                    queued = (0, 0)

            # ── Move Pacman ──
            if direction != (0, 0):
                nx = pacman_x + direction[0]
                ny = pacman_y + direction[1]
                if not PacmanChase._is_wall(nx, ny):
                    pacman_x, pacman_y = nx, ny

            # ── Eat pellet ──
            if (pacman_x, pacman_y) in pellets:
                pellets.discard((pacman_x, pacman_y))
                score += 10
                forbidden = {(pacman_x, pacman_y)} | set(ghosts) | pellets
                empty = [c for c in open_cells if c not in forbidden]
                if empty:
                    pellets.add(random.choice(empty))

            # ── Move ghosts (half speed) ──
            ghost_tick += 1
            if ghost_tick % 2 == 0:
                new_ghosts: List[Tuple[int, int]] = []
                for g in ghosts:
                    new_ghosts.append(PacmanChase._move_ghost(g, (pacman_x, pacman_y)))
                ghosts = new_ghosts

            # ── Collision check ──
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

        # Final frame
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
        cprint("  Use WASD or arrow keys.  Eat · pellets, avoid M ghosts.", C.WHITE)
        cprint("  You have 3 lives and 45 seconds.  Highest score wins!", C.WHITE)
        time.sleep(1.2)

        if not HAS_CURSES or not sys.stdin.isatty() or not sys.stdout.isatty():
            cprint(
                "  ⚠  Interactive terminal not available here. Scoring 0 for this round.",
                C.YELLOW,
            )
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
            if player in winners:
                mark = f"{C.GREEN}🏆"
            else:
                mark = f"{C.YELLOW}👾"
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


# Game registry
GAMES = {
    "1": HeadsOrTails,
    "2": RockPaperScissors,
    "3": NumberGuess,
    "4": PacmanChase,
}


# ── Server ─────────────────────────────────────────────────────────────────────

class _ClientState:
    """Per-client state held by the server."""
    def __init__(self, sock: socket.socket, addr: Tuple[str, int], name: str):
        self.sock = sock
        self.addr = addr
        self.name = name
        self.reader = MessageReader(sock)
        # Per-round expected token; only choices matching this token are accepted
        self.round_token: Optional[str] = None
        self.choice: Any = None
        self.choice_received = threading.Event()


class Server:
    def __init__(self, host_plays: bool = True):
        self.host_plays = host_plays
        self.clients: Dict[str, _ClientState] = {}
        self.client_lock = threading.Lock()
        self.running = True
        self.accept_thread: Optional[threading.Thread] = None
        self.server_sock: Optional[socket.socket] = None

    # ── helpers ────────────────────────────────────────────────────────────────

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
        if base == HOST_NAME:
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

    # ── per-client message loop ────────────────────────────────────────────────

    def _client_loop(self, cs: _ClientState) -> None:
        """
        One thread per client. Continuously reads messages and routes them.
        Choices are only accepted if they carry the round_token currently set
        on this client's state -- this prevents stale messages from a prior
        round being misattributed to the next round.
        """
        while self.running:
            msg = cs.reader.read()
            if msg is None:
                break
            mtype = msg.get("type")
            if mtype == "choice":
                token = msg.get("token")
                # Accept if the token matches what we're expecting for this round
                if cs.round_token is not None and token == cs.round_token:
                    cs.choice = msg.get("choice")
                    cs.choice_received.set()
                # else: stale or wrong-round; discard silently
            # Ignore other message types from clients
        self._drop_client(cs.name)

    # ── join handshake ─────────────────────────────────────────────────────────

    def _accept_one(self, conn: socket.socket, addr: Tuple[str, int]) -> None:
        # Use a temporary reader for the handshake; reuse it once we accept
        reader = MessageReader(conn)
        try:
            conn.settimeout(15.0)
        except (socket.error, OSError):
            pass
        msg = reader.read()
        try:
            conn.settimeout(None)
        except (socket.error, OSError):
            pass

        if not msg or msg.get("type") != "join":
            try:
                conn.close()
            except (socket.error, OSError):
                pass
            return

        name = self._unique_name(str(msg.get("name", "")), addr[0])
        cs = _ClientState(conn, addr, name)
        cs.reader = reader  # carry over any buffered bytes from the handshake

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

    # ── round logic ────────────────────────────────────────────────────────────

    def collect_choices(self, game_class, host_choice: Any = None) -> Dict[str, Any]:
        """
        Issue a unique round token, prompt every client, wait for matching responses.
        Returns {player_name: choice}.
        """
        round_token = f"r{int(time.time() * 1000)}_{random.randint(0, 99999)}"

        # Reset every client's per-round state and assign the new token.
        # Doing this BEFORE sending the prompt closes the race where a client
        # could reply faster than the host's main thread can update state.
        clients = self._snapshot_clients()
        for cs in clients:
            cs.choice = None
            cs.choice_received.clear()
            cs.round_token = round_token

        # Send prompt with the token
        prompt_msg = {"type": "prompt", "game": game_class.NAME, "token": round_token}
        dead: List[str] = []
        for cs in clients:
            if not send_msg(cs.sock, prompt_msg):
                dead.append(cs.name)
        for name in dead:
            self._drop_client(name)

        # Wait for each client (up to CHOICE_TIMEOUT_SEC total)
        deadline = time.time() + CHOICE_TIMEOUT_SEC
        clients = self._snapshot_clients()  # refresh after potential drops
        for cs in clients:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            cs.choice_received.wait(timeout=remaining)

        # Collect results
        choices: Dict[str, Any] = {}
        for cs in self._snapshot_clients():
            if cs.choice_received.is_set() and cs.choice is not None:
                choices[cs.name] = cs.choice
            # Clear token so any straggler from this round is ignored next round
            cs.round_token = None

        if host_choice is not None:
            choices[HOST_NAME] = host_choice

        return choices

    def _print_scoreboard(self, scores: Dict[str, int]) -> None:
        cprint(f"\n  {C.BOLD}── Scoreboard ──{C.RESET}", C.CYAN)
        if not scores:
            cprint("  (no players)", C.DIM)
            return
        for name, s in sorted(scores.items(), key=lambda kv: -kv[1]):
            bar = "█" * s
            you = " ← you" if name == HOST_NAME else ""
            cprint(
                f"  {name}: {C.YELLOW}{bar}{C.RESET} {s}{C.DIM}{you}{C.RESET}",
                C.WHITE,
            )

    # ── main run ───────────────────────────────────────────────────────────────

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

        ip = get_local_ip()
        cprint(f"\n  Your IP address: {C.BOLD}{C.YELLOW}{ip}{C.RESET}")
        cprint(f"  Port:            {C.BOLD}{PORT}{C.RESET}")
        cprint(f"\n  Other players run:", C.DIM)
        cprint(
            f"  {C.CYAN}python3 pi_party_games.py --join{C.RESET}"
            f"  then enter  {C.BOLD}{ip}{C.RESET}\n"
        )

        # Bind the server socket
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
            cprint(
                f"\n  ⚠  Need at least 2 players to start (have {total}). Exiting.",
                C.YELLOW,
            )
            self._shutdown()
            return

        cprint(f"\n  🎮  Starting with {total} player(s)!\n", C.GREEN + C.BOLD)
        self.broadcast({"type": "start"})

        scores: Dict[str, int] = {}
        with self.client_lock:
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
                cprint("    [Q]  Quit / End session", C.DIM)

                pick = ""
                while True:
                    pick = input(f"\n  {C.BOLD}> {C.RESET}").strip().lower()
                    if pick == "q" or pick in GAMES:
                        break
                    cprint("  ⚠  Invalid choice.", C.YELLOW)

                if pick == "q":
                    self.broadcast(
                        {"type": "end", "msg": "Host ended the session. Thanks for playing!"}
                    )
                    cprint("\n  Session ended. Final scores:", C.CYAN + C.BOLD)
                    self._print_scoreboard(scores)
                    break

                game_class = GAMES[pick]
                self.broadcast({"type": "game_selected", "game": game_class.NAME})

                # Sync scores dict with currently connected clients
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

                # Show host their result locally, then broadcast to clients
                if self.host_plays and HOST_NAME in choices:
                    print(game_class.format_result(result, HOST_NAME))

                for winner in result.get("winners", []):
                    scores[winner] = scores.get(winner, 0) + 1

                self.broadcast(
                    {"type": "result", "game": game_class.NAME, "result": result}
                )
                self._print_scoreboard(scores)

                again = input(
                    f"\n  {C.BOLD}Next round? [Enter to continue / Q to quit]{C.RESET} "
                ).strip().lower()
                if again == "q":
                    self.broadcast(
                        {"type": "end", "msg": "Host ended the session. Thanks for playing!"}
                    )
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
        cprint(
            f"\n  {C.GREEN}✔  Connected! You joined as: {C.BOLD}{confirmed}{C.RESET}",
            C.GREEN,
        )
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
                    cprint(
                        f"\n  {C.GREEN}{C.BOLD}🎮  Game is starting!{C.RESET}\n",
                        C.GREEN,
                    )

                elif mtype == "game_selected":
                    game_name = msg.get("game", "")
                    cprint(f"\n  {C.BOLD}[{game_name}]{C.RESET}", C.MAGENTA)

                elif mtype == "prompt":
                    game_name = msg.get("game", "")
                    token = msg.get("token")
                    game_class = game_map.get(game_name)
                    if game_class is None:
                        cprint(f"  ⚠  Unknown game from host: {game_name}", C.YELLOW)
                        send_msg(
                            self.sock,
                            {"type": "choice", "choice": None, "token": token},
                        )
                    else:
                        choice = game_class.prompt_choice()
                        send_msg(
                            self.sock,
                            {"type": "choice", "choice": choice, "token": token},
                        )
                        cprint(
                            f"  {C.DIM}Choice sent. Waiting for results...{C.RESET}",
                            C.DIM,
                        )

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
