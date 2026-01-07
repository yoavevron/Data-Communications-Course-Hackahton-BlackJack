import socket
import struct
from constants import *

TEAM_NAME = "client 1"


def recv_exact(sock: socket.socket, n: int):
    """Read exactly n bytes from a TCP socket (or return None on disconnect)."""
    data = b""
    try:
        while len(data) < n:
            chunk = sock.recv(n - len(data))
            if not chunk:
                return None
            data += chunk
        return data
    except (ConnectionResetError, ConnectionAbortedError, OSError):
        return None


def send_decision(sock: socket.socket, decision: str):
    """Send the player's decision ("hittt" / "Stand") as a fixed-size payload."""
    decision = decision.ljust(5)[:5]  # must be exactly 5 bytes
    msg = struct.pack(
        "!Ib5s",
        MAGIC_COOKIE,
        PAYLOAD,
        decision.encode("ascii")
    )
    sock.sendall(msg)


def listen_for_offer():
    """Listen on UDP for server offers and return (server_ip, tcp_port)."""
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    udp.bind(('', UDP_PORT))

    while True:
        data, addr = udp.recvfrom(1024)
        if len(data) < 39:
            continue
        cookie, mtype, port, server_name = struct.unpack("!IbH32s", data[:39])
        if cookie == MAGIC_COOKIE and mtype == OFFER:
            print(f"Received offer from {addr[0]}")
            return addr[0], port


def play():
    #region ask how many rounds
    while True:
        try:
            rounds = int(input("How many rounds? ").strip())
            if 1 <= rounds <= 255:
                break
            print("Please enter a number between 1 and 255.")
        except ValueError:
            print("Please enter a valid integer.")
    #endregion

    print("Client started, listening for offer requests...")

    # Discover server via UDP broadcast (offer), then connect over TCP
    ip, port = listen_for_offer()

    #region Connect to server (request) and send number of rounds
    tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp.connect((ip, port))

    req = struct.pack(
        "!IbB32s",
        MAGIC_COOKIE,
        REQUEST,
        rounds,
        TEAM_NAME.encode("ascii", errors="ignore").ljust(32, b'\x00')  # fixed 32B team name
    )
    tcp.sendall(req)
    #endregion

    #region initialize game
    wins, ties, played = 0, 0, 0

    phase = "init"  # init -> player -> dealer
    init_cards_seen = 0
    player_cards = []
    dealer_cards = []

    def reset_round_state():
        """Reset per-round state while keeping overall statistics."""
        nonlocal phase, init_cards_seen, player_cards, dealer_cards
        phase = "init"
        init_cards_seen = 0
        player_cards = []
        dealer_cards = []

    reset_round_state()
    #endregion

    print(f'\n===ROUND ({played+1}/{rounds}) STARTED!===')
    # Main loop: receive cards/results from server and respond with decisions
    while True:
        data = recv_exact(tcp, 9)
        if not data:
            break

        cookie, mtype, result, rank, suit = struct.unpack("!IbBHB", data)
        card_text = f"{get_card_name(rank)} {get_suit_symbol(suit)}"
        if cookie != MAGIC_COOKIE or mtype != PAYLOAD:
            continue

        # round NOT over
        if result == 0:
            if phase == "init":
                init_cards_seen += 1
                # First 2 cards are the player's initial hand, rest are dealer's
                if init_cards_seen <= 2:
                    player_cards.append((rank, suit))
                    total_player = sum(card_value(c[0]) for c in player_cards)
                    total_dealer = sum(card_value(c[0]) for c in dealer_cards)
                    print(f"\tYou: {card_text}\t\tPlayer:{total_player}, Dealer:{total_dealer}")
                else:
                    dealer_cards.append((rank, suit))
                    total_player = sum(card_value(c[0]) for c in player_cards)
                    total_dealer = sum(card_value(c[0]) for c in dealer_cards)
                    print(f"\tDealer: {card_text}\t\tPlayer:{total_player}, Dealer:{total_dealer}")
                    phase = "player"

            elif phase == "player":
                player_cards.append((rank, suit))
                total_player = sum(card_value(c[0]) for c in player_cards)
                total_dealer = sum(card_value(c[0]) for c in dealer_cards)
                print(f"\tYou: {card_text}\t\tPlayer:{total_player}, Dealer:{total_dealer}")

            else:  # phase=dealer
                dealer_cards.append((rank, suit))
                total_player = sum(card_value(c[0]) for c in player_cards)
                total_dealer = sum(card_value(c[0]) for c in dealer_cards)
                print(f"\tDealer: {card_text}\t\tPlayer:{total_player}, Dealer:{total_dealer}")

            if phase == "player":
                decision_in = input("CHOOSE Hit or Stand (h/s): ").strip().lower()
                if decision_in in ("stand", "s"):
                    send_decision(tcp, "Stand")
                    phase = "dealer"
                elif decision_in in ("hit", "h"):
                    send_decision(tcp, "hittt")
                else:
                    # Default behavior on invalid input: Stand
                    print("Invalid input is -> STAND!")
                    send_decision(tcp, "stand")
                    phase = "dealer"

            continue

        # round IS over
        else:
            played += 1
            remaining = rounds - played

            if result == 3:
                print(f"YOU WIN!")
                wins += 1
            elif result == 2:
                # If the last message includes a player card at end-of-round, print it
                if phase == 'player':
                    player_cards.append((rank, suit))
                    total_player = sum(card_value(c[0]) for c in player_cards)
                    total_dealer = sum(card_value(c[0]) for c in dealer_cards)
                    print(f"\tYou: {card_text}\t\tPlayer:{total_player}, Dealer:{total_dealer}")
                print(f"YOU LOSS!")
            elif result == 1:
                print(f"ITS A TIE!")
                ties += 1

            reset_round_state()
            if played + 1 <= rounds:
                print(f'\n===ROUND ({played + 1}/{rounds}) STARTED!===')

        if played >= rounds:
            break

    win_rate = (wins / played) if played else 0.0

    # summarize results
    print(f'\n==================================')
    print(f'\n========{rounds} ROUNDS FINISHED!========')
    print(f'\n==================================')
    print('USER STATISTICS')
    print(f'WINS: {wins}')
    print(f'TIES: {ties}')
    print(f'LOSSES: {rounds-wins-ties}')
    print(f"WIN RATE: {round(win_rate*100,1)}%")
    print(f'\n==================================')

    try:
        tcp.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    tcp.close()


if __name__ == "__main__":
    play()
