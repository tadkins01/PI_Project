#!/usr/bin/env python3
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


GAMES = {
    "1": HeadsOrTails,
    "2": RockPaperScissors,
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
        # Step 1: get their name
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

        # Connection stays open; we drive rounds from the main loop
        # Just keep the socket alive until server closes it
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
        if host_choice is not None:
            expected_remote = [n for n in expected]
        else:
            expected_remote = list(expected)

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

        # Wait up to 120 seconds for all players
        done_event.wait(timeout=120)

        choices.update(responses)
        if host_choice is not None:
            # Find the host's own name
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

        # Start listening
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

        input()  # Host presses Enter to start

        if not self.clients and not self.host_plays:
            cprint("\n  ⚠  No players connected. Exiting.", C.YELLOW)
            self.running = False
            return

        total_players = len(self.clients) + (1 if self.host_plays else 0)
        cprint(f"\n  🎮  Starting with {total_players} player(s)!\n", C.GREEN + C.BOLD)

        # Notify clients game is starting
        self.broadcast({"type": "start"})

        # ── Game Loop ──────────────────────────────────────────────
        scores = {name: 0 for name in self.clients}
        if self.host_plays:
            scores["[Host] You"] = 0

        round_num = 0

        while True:
            round_num += 1
            cprint(f"\n  ══ Round {round_num} ══", C.CYAN + C.BOLD)

            # Choose game
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

            # Tell clients which game
            self.broadcast({"type": "game_selected", "game": game_class.NAME})

            # Host makes their own choice if playing
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

            # Show result to host
            if self.host_plays:
                print(game_class.format_result(result, "[Host] You"))

            # Update scores
            for winner in result.get("winners", []):
                if winner in scores:
                    scores[winner] += 1

            # Send result to clients
            self.broadcast({
                "type": "result",
                "game": game_class.NAME,
                "result": result
            })

            # Show scoreboard
            cprint(f"\n  {C.BOLD}── Scoreboard ──{C.RESET}", C.CYAN)
            for name, s in sorted(scores.items(), key=lambda x: -x[1]):
                bar = "█" * s
                you = " ← you" if name == "[Host] You" else ""
                cprint(f"  {name}: {C.YELLOW}{bar}{C.RESET} {s}{C.DIM}{you}{C.RESET}", C.WHITE)

            # Play again?
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

        # Get server IP
        cprint("\n  Enter the host's IP address:", C.WHITE)
        cprint(f"  {C.DIM}(shown on the host's screen when they start){C.RESET}", C.DIM)
        server_ip = input(f"\n  {C.BOLD}IP > {C.RESET}").strip()
        if not server_ip:
            cprint("  ⚠  No IP entered. Exiting.", C.YELLOW)
            return

        # Get player name
        cprint("\n  Enter your player name:", C.WHITE)
        self.name = input(f"  {C.BOLD}Name > {C.RESET}").strip()[:20]
        if not self.name:
            self.name = f"Player_{random.randint(100,999)}"

        # Connect
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((server_ip, PORT))
        except Exception as e:
            cprint(f"\n  ✘  Could not connect to {server_ip}:{PORT}", C.RED)
            cprint(f"  {C.DIM}{e}{C.RESET}", C.DIM)
            cprint("\n  Make sure:", C.YELLOW)
            cprint("  • The host has started the game", C.WHITE)
            cprint("  • You're on the same network", C.WHITE)
            cprint("  • The IP address is correct", C.WHITE)
            return

        # Handshake
        send_msg(self.sock, {"type": "join", "name": self.name})
        msg = recv_msg(self.sock)
        if not msg or msg.get("type") != "welcome":
            cprint("  ✘  Unexpected response from server.", C.RED)
            return

        confirmed_name = msg.get("name", self.name)
        cprint(f"\n  {C.GREEN}✔  Connected! You joined as: {C.BOLD}{confirmed_name}{C.RESET}", C.GREEN)
        cprint(f"  {C.DIM}Waiting for the host to start...{C.RESET}\n", C.DIM)

        self.scores = {}

        # ── Message Loop ───────────────────────────────────────────
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
                else:
                    cprint(f"  ⚠  Unknown game: {game_name}", C.YELLOW)
                    send_msg(self.sock, {"type": "choice", "choice": "unknown"})

            elif mtype == "result":
                game_name = msg.get("game", "")
                result = msg.get("result", {})
                game_class = game_map.get(game_name)
                if game_class:
                    print(game_class.format_result(result, confirmed_name))
                    # Update local score view
                    for winner in result.get("winners", []):
                        self.scores[winner] = self.scores.get(winner, 0) + 1
                    self.scores[confirmed_name] = self.scores.get(confirmed_name, 0)
                    cprint(f"\n  {C.DIM}Waiting for next round...{C.RESET}", C.DIM)

            elif mtype == "end":
                cprint(f"\n  {C.CYAN}{C.BOLD}🏁  {msg.get('msg', 'Session ended.')}{C.RESET}", C.CYAN)
                break

        self.sock.close()
        cprint("\n  Goodbye! 👋\n", C.GREEN)


# ── Main Menu ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Pi Party Games — Multiplayer LAN games")
    parser.add_argument("--host", action="store_true", help="Start as host/server")
    parser.add_argument("--join", action="store_true", help="Join an existing game")
    args = parser.parse_args()

    if args.host:
        server = Server(host_plays=True)
        server.run()
        return

    if args.join:
        client = Client()
        client.run()
        return

    # Interactive menu
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
            server = Server(host_plays=True)
            server.run()
            break
        elif choice in ("2", "join"):
            client = Client()
            client.run()
            break
        elif choice in ("q", "quit", "exit"):
            cprint("\n  Goodbye! 👋\n", C.GREEN)
            break
        else:
            cprint("  ⚠  Please enter 1, 2, or Q.", C.YELLOW)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{C.DIM}  Interrupted. Goodbye! 👋{C.RESET}\n")
        sys.exit(0)
