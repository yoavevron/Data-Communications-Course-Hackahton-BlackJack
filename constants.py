MAGIC_COOKIE = 0xabcddcba

# message types
OFFER = 0x2
REQUEST = 0x3
PAYLOAD = 0x4

UDP_PORT = 13122

SERVER_NAME = "DorAndYoav"

SUITS = ["Heart", "Diamond", "Club", "Spade"]


def card_value(rank: int) -> int:
    # Rank encoding: 1=Ace, 11=J, 12=Q, 13=K
    if rank >= 10:
        return 10
    if rank == 1:
        return 11
    return rank


def get_card_name(rank):
    if rank == 1:
        return "A (11)"
    elif rank <= 10:
        return str(rank)
    elif rank == 11:
        return "J (10)"
    elif rank == 12:
        return "Q (10)"
    elif rank == 13:
        return "K (10)"


def get_suit_symbol(value):
    suits = {
        0: "♥",
        1: "♣",
        2: "♦",
        3: "♠",
    }
    return suits.get(value, "")

