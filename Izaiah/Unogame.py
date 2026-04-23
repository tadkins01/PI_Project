import random
import os
import time

# =============================
# COLORS
# =============================
class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"
    DIM = "\033[2m"

def clear():
    os.system("cls" if os.name == "nt" else "clear")

# =============================
# BANNER + MENU
# =============================
def banner():
    clear()
    print(f"""{C.CYAN}{C.BOLD}
========================================
           🎮 PI PARTY 🎮
========================================
             UNO SYSTEM
========================================
{C.RESET}""")

def main_menu():
    while True:
        banner()
        print("1. Local Multiplayer (3–4 players)")
        print("2. Play vs AI Bots")
        print("3. Online Mode (Simulated Lobby)")
        print("Q. Quit\n")

        choice = input("> ").lower()

        if choice == "1":
            start_game(mode="local")
        elif choice == "2":
            start_game(mode="ai")
        elif choice == "3":
            start_game(mode="online")
        elif choice == "q":
            break

# =============================
# UNO CORE
# =============================
COLORS = ["Red", "Blue", "Green", "Yellow"]
VALUES = [str(i) for i in range(10)] + ["Skip", "Reverse", "Draw2"]

def create_deck():
    deck = []
    for c in COLORS:
        for v in VALUES:
            deck += [{"color": c, "value": v}] * 2
    for _ in range(4):
        deck.append({"color": "Any", "value": "Wild"})
    random.shuffle(deck)
    return deck

def draw(deck):
    return deck.pop() if deck else None

def show(card):
    return f"{card['color']} {card['value']}"

def valid(card, top):
    return (
        card["color"] == top["color"]
        or card["value"] == top["value"]
        or card["color"] == "Any"
    )

def choose_color():
    return random.choice(COLORS)

# =============================
# UNO CALL OUT SYSTEM
# =============================
def uno_callout(players, current, deck):
    print(f"\n⚠ {current['name']} has 1 card!")

    caller = input("Type 'call' to challenge UNO: ").lower()

    if caller == "call":
        print(f"💥 {current['name']} got caught!")
        for _ in range(2):
            current["hand"].append(draw(deck))
    else:
        print("No challenge.")

# =============================
# AI BOTS
# =============================
def ai_move(player, deck, top):
    time.sleep(0.8)

    for i, card in enumerate(player["hand"]):
        if valid(card, top):
            player["hand"].pop(i)
            print(f"🤖 {player['name']} played {show(card)}")
            return card, card["value"]

    card = draw(deck)
    if card:
        player["hand"].append(card)
        print(f"🤖 {player['name']} drew a card")
    return top, None

# =============================
# PLAYER MOVE
# =============================
def player_move(player, deck, top, players):
    print(f"\n🎯 {player['name']}'s turn")
    print("Top:", show(top))

    for i, c in enumerate(player["hand"]):
        print(f"{i}: {show(c)}")

    while True:
        move = input("> (index / draw / uno): ").lower()

        if move == "uno":
            if len(player["hand"]) == 2:
                player["uno"] = True
                print("UNO called!")
            else:
                print("Too early for UNO")

        elif move == "draw":
            card = draw(deck)
            if card:
                player["hand"].append(card)
            return top, None

        else:
            try:
                i = int(move)
                card = player["hand"][i]

                if valid(card, top):
                    player["hand"].pop(i)

                    if len(player["hand"]) == 1 and not player["uno"]:
                        uno_callout(players, player, deck)

                    player["uno"] = False
                    return card, card["value"]

                print("Invalid move")
            except:
                print("Try again")

# =============================
# GAME ENGINE
# =============================
def start_game(mode="local"):
    banner()

    # players setup
    players = []

    if mode == "local":
        n = int(input("Players (3–4): "))
        for i in range(n):
            name = input(f"Player {i+1}: ")
            players.append({"name": name, "hand": [], "uno": False, "ai": False})

    elif mode == "ai":
        name = input("Your name: ")
        players.append({"name": name, "hand": [], "uno": False, "ai": False})

        for i in range(2):
            players.append({"name": f"Bot {i+1}", "hand": [], "uno": False, "ai": True})

    elif mode == "online":
        print("\n🌐 ONLINE MODE (SIMULATED LOBBY)")
        print("Pretending players joined network...\n")
        time.sleep(1)

        players = [
            {"name": "You", "hand": [], "uno": False, "ai": False},
            {"name": "Online_Player_1", "hand": [], "uno": False, "ai": True},
            {"name": "Online_Player_2", "hand": [], "uno": False, "ai": True},
        ]

    scores = {p["name"]: 0 for p in players}
    round_num = 1

    # =============================
    # GAME LOOP
    # =============================
    while True:
        deck = create_deck()
        top = draw(deck)
        turn = 0

        for p in players:
            p["hand"] = []
            p["uno"] = False

        for _ in range(7):
            for p in players:
                p["hand"].append(draw(deck))

        print(f"\n===== ROUND {round_num} =====")

        while True:
            current = players[turn]

            if current["ai"]:
                top, effect = ai_move(current, deck, top)
            else:
                top, effect = player_move(current, deck, top, players)

            # win
            if len(current["hand"]) == 0:
                print(f"\n🏆 {current['name']} wins round!")
                scores[current["name"]] += 1
                break

            # effects
            if effect == "Skip":
                turn += 1
            elif effect == "Reverse":
                players.reverse()
            elif effect == "Draw2":
                nxt = players[(turn + 1) % len(players)]
                for _ in range(2):
                    nxt["hand"].append(draw(deck))

            turn = (turn + 1) % len(players)

        # scoreboard
        print("\n📊 SCOREBOARD")
        for k, v in sorted(scores.items(), key=lambda x: -x[1]):
            print(k, ":", v)

        again = input("\nNext round? (y/n): ").lower()
        if again != "y":
            break

        round_num += 1

# =============================
# RUN
# =============================
if __name__ == "__main__":
    main_menu()
