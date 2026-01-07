import socket
import struct
import threading
import random
import time
from constants import *

# Server chooses a random TCP port each run (as required by assignment).
TCP_PORT = random.randint(20000, 40000)


def create_deck():
    """Create and shuffle a standard 52-card deck represented as (rank, suit) tuples."""
    deck = [(rank, suit) for rank in range(1, 14) for suit in range(4)]
    random.shuffle(deck)
    return deck


def send_offers():
    """Broadcast UDP 'offer' messages so clients can discover this server."""
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    msg = struct.pack(
        "!IbH32s",
        MAGIC_COOKIE,
        OFFER,
        TCP_PORT,
        SERVER_NAME.encode().ljust(32, b'\x00')
    )

    while True:
        try:
            udp.sendto(msg, ('<broadcast>', UDP_PORT))
        except OSError:
            pass
        time.sleep(1)


def recv_exact(conn: socket.socket, n: int):
    """Read exactly n bytes from a TCP socket
    (or return None on disconnect)."""
    data = b""
    try:
        while len(data) < n:
            chunk = conn.recv(n - len(data))
            if not chunk:
                return None
            data += chunk
        return data
    except (ConnectionResetError, ConnectionAbortedError, OSError):
        return None


def send_payload(conn: socket.socket, result, rank, suit):
    """Send a single [Server -> Client] payload message with game state."""
    msg = struct.pack("!IbBHB", MAGIC_COOKIE, PAYLOAD, result, rank, suit)
    conn.sendall(msg)


def recv_client_decision(conn: socket.socket):
    """Receive a decision payload from the client and return normalized decision text."""
    data = recv_exact(conn, 10)
    if not data:
        return None

    cookie, mtype, decision = struct.unpack("!Ib5s", data)
    if cookie != MAGIC_COOKIE or mtype != PAYLOAD:
        return None

    return decision.decode("ascii").strip().lower()


def handle_client(conn: socket.socket, addr):
    """Handle a single client session: handshake, then play N rounds of Blackjack."""
    print(f"Client connected: {addr}")

    #region client connected
    # Initial request contains cookie, type, number of rounds, and team name (fixed 32 bytes)
    req = recv_exact(conn, 38)
    if not req:
        conn.close()
        return

    cookie, mtype, rounds, team_name = struct.unpack("!IbB32s", req)
    if cookie != MAGIC_COOKIE or mtype != REQUEST:
        conn.close()
        return

    team_str = team_name.decode("ascii", errors="ignore").rstrip("\x00").strip()
    if team_str:
        print(f"Team: {team_str}")
    #endregion

    wins = 0

    for round_idx in range(rounds):
        print(f"=====ROUND: {round_idx+1}/{rounds} STARTED=====")
        deck = create_deck()

        # Deal 2 cards to player and 2 to dealer (one dealer card is hidden initially)
        player = [deck.pop(), deck.pop()]
        dealer = [deck.pop(), deck.pop()]

        player_sum = sum(card_value(c_val) for c_val, suit in player)

        # Send initial deal to client (player cards + dealer up-card)
        for r, s in player:
            send_payload(conn, 0, r, s)
        send_payload(conn, 0, dealer[0][0], dealer[0][1])

        # Player turn: keep hitting until stand or bust
        while player_sum <= 21:
            decision = recv_client_decision(conn)
            if decision is None:
                conn.close()
                return

            print('user decision: ', decision)
            if decision == "stand":
                break

            card = deck.pop()
            player.append(card)
            cv = card_value(card[0])
            player_sum += cv
            if player_sum <= 21:
                send_payload(conn, 0, card[0], card[1])
            else:
                break

        # If player busts, send loss result (2) and move to next round
        if player_sum > 21:
            send_payload(conn, 2, card[0], card[1])  # player loss
            continue

        # Dealer turn: reveal hidden card then draw until reaching 17+
        dealer_sum = sum(card_value(r) for r, _ in dealer)
        send_payload(conn, 0, dealer[1][0], dealer[1][1])  # reveal hidden

        while dealer_sum < 17:
            card = deck.pop()
            dealer.append(card)
            dealer_sum += card_value(card[0])
            send_payload(conn, 0, card[0], card[1])

        # Determine round outcome: 3=win, 2=loss, 1=tie
        if dealer_sum > 21 or player_sum > dealer_sum:
            wins += 1
            result = 3
        elif dealer_sum > player_sum:
            result = 2
        else:
            result = 1

        # Final round result message (rank/suit are unused here)
        send_payload(conn, result, 0, 0)

    print(f"CLIENT FINISHED. WIN RATE: {wins}/{rounds}")
    try:
        conn.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    conn.close()


#region shit
def tcp_server():
    """Start the TCP server loop and spawn a thread per connected client."""
    # Create a TCP socket (IPv4)
    tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    # Bind the socket to all network interfaces on the given TCP port
    tcp.bind(('', TCP_PORT))

    # Put the socket into listening mode (ready to accept connections)
    tcp.listen()

    # Get the local IP address
    ip = socket.gethostbyname(socket.gethostname())
    print(f"Server started, listening on IP address {ip}")

    # Main server loop – continuously accept new clients
    while True:
        # Block until a new client connects (no CPU used here)
        conn, addr = tcp.accept()

        # Handle each client in a separate thread
        threading.Thread(
            target=handle_client,
            args=(conn, addr),
            daemon=True
        ).start()


if __name__ == "__main__":
    # Run UDP offer broadcaster in the background, then start TCP server
    threading.Thread(target=send_offers, daemon=True).start()
    tcp_server()
#endregion
