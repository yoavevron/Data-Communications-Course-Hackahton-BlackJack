import socket
import struct
import threading
import random
import time
from constants import *

# Server chooses a random TCP port each run (as required by assignment).
TCP_PORT = random.randint(20000, 40000)


def create_deck():
    deck = [(rank, suit) for rank in range(1, 14) for suit in range(4)]
    random.shuffle(deck)
    return deck


def send_offers():
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
    # [Server -> Client] payload
    msg = struct.pack("!IbBHB", MAGIC_COOKIE, PAYLOAD, result, rank, suit)
    conn.sendall(msg)


def recv_client_decision(conn: socket.socket):
    data = recv_exact(conn, 10)
    if not data:
        return None

    cookie, mtype, decision = struct.unpack("!Ib5s", data)
    if cookie != MAGIC_COOKIE or mtype != PAYLOAD:
        return None

    return decision.decode("ascii").strip().lower()


def handle_client(conn: socket.socket, addr):
    print(f"Client connected: {addr}")

    #region client connected
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

        # player and dealer get two cards (each deck.pop generate one card - number and suit)
        player = [deck.pop(), deck.pop()]
        dealer = [deck.pop(), deck.pop()]

        player_sum = sum(card_value(c_val) for c_val, suit in player)

        # send to client the initial deal
        for r, s in player:
            send_payload(conn, 0, r, s)
        send_payload(conn, 0, dealer[0][0], dealer[0][1])

        # print('player sum: ', player_sum)
        # Player turn
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
            # print('CARD: ', card[0])
            player_sum += cv
            if player_sum <= 21:
                send_payload(conn, 0, card[0], card[1])
            else:
                break

        if player_sum > 21:
            send_payload(conn, 2, card[0], card[1])  # player loss
            continue

        # Dealer turn
        dealer_sum = sum(card_value(r) for r, _ in dealer)
        send_payload(conn, 0, dealer[1][0], dealer[1][1])  # reveal hidden

        while dealer_sum < 17:
            card = deck.pop()
            dealer.append(card)
            dealer_sum += card_value(card[0])
            send_payload(conn, 0, card[0], card[1])

        # Result
        if dealer_sum > 21 or player_sum > dealer_sum:
            wins += 1
            result = 3
        elif dealer_sum > player_sum:
            result = 2
        else:
            result = 1

        send_payload(conn, result, 0, 0)

    print(f"CLIENT FINISHED. WIN RATE: {wins}/{rounds}")
    try:
        conn.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    conn.close()


#region shit
def tcp_server():
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
    threading.Thread(target=send_offers, daemon=True).start()
    tcp_server()
#endregion