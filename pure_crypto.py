# Pure-Python Keccak-256 (original Keccak, padding 0x01 — NOT NIST SHA3's 0x06)
# and pure-Python secp256k1 ECDSA signing. Zero C-extension dependencies,
# so this cross-compiles cleanly under python-for-android.

# ---------------- Keccak-256 ----------------

_RC = [
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
    0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
    0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
    0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
    0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
]
_ROT = [
    [0, 36, 3, 41, 18], [1, 44, 10, 45, 2], [62, 6, 43, 15, 61],
    [28, 55, 25, 21, 56], [27, 20, 39, 8, 14],
]

def _rol(x, n):
    n %= 64
    return ((x << n) | (x >> (64 - n))) & 0xFFFFFFFFFFFFFFFF

def _keccak_f(state):
    for rnd in range(24):
        # theta
        C = [state[x][0] ^ state[x][1] ^ state[x][2] ^ state[x][3] ^ state[x][4] for x in range(5)]
        D = [C[(x - 1) % 5] ^ _rol(C[(x + 1) % 5], 1) for x in range(5)]
        for x in range(5):
            for y in range(5):
                state[x][y] ^= D[x]
        # rho + pi
        B = [[0] * 5 for _ in range(5)]
        for x in range(5):
            for y in range(5):
                B[y % 5][(2 * x + 3 * y) % 5] = _rol(state[x][y], _ROT[x][y])
        # chi
        for x in range(5):
            for y in range(5):
                state[x][y] = B[x][y] ^ ((~B[(x + 1) % 5][y]) & B[(x + 2) % 5][y])
        # iota
        state[0][0] ^= _RC[rnd]
    return state

def keccak256(data: bytes) -> bytes:
    rate = 136  # 1088 bits
    state = [[0] * 5 for _ in range(5)]

    # padding: original Keccak uses 0x01 (NOT SHA3's 0x06)
    padded = bytearray(data)
    padded.append(0x01)
    while len(padded) % rate != 0:
        padded.append(0x00)
    padded[-1] |= 0x80

    for offset in range(0, len(padded), rate):
        block = padded[offset:offset + rate]
        for i in range(rate // 8):
            lane = int.from_bytes(block[i * 8:i * 8 + 8], "little")
            x, y = (i % 5), (i // 5)
            state[x][y] ^= lane
        _keccak_f(state)

    out = bytearray()
    while len(out) < 32:
        for i in range(rate // 8):
            x, y = (i % 5), (i // 5)
            out += state[x][y].to_bytes(8, "little")
            if len(out) >= 32:
                break
        if len(out) < 32:
            _keccak_f(state)
    return bytes(out[:32])


# ---------------- secp256k1 ----------------

P = 2**256 - 2**32 - 977
A = 0
B = 7
Gx = 55066263022277343669578718895168534326250603453777594175500187360389116729240
Gy = 32670510020758816978083085130507043184471273380659243275938904335757337482424
N = 115792089237316195423570985008687907852837564279074904382605163141518161494337
G = (Gx, Gy)

def _inv(x, m):
    return pow(x, m - 2, m)

def _point_add(p1, p2):
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2 and (y1 + y2) % P == 0:
        return None
    if p1 == p2:
        lam = (3 * x1 * x1) * _inv(2 * y1, P) % P
    else:
        lam = (y2 - y1) * _inv((x2 - x1) % P, P) % P
    x3 = (lam * lam - x1 - x2) % P
    y3 = (lam * (x1 - x3) - y1) % P
    return (x3, y3)

def _scalar_mult(k, point):
    result = None
    addend = point
    while k:
        if k & 1:
            result = _point_add(result, addend)
        addend = _point_add(addend, addend)
        k >>= 1
    return result

def privkey_to_pubkey(privkey_int):
    return _scalar_mult(privkey_int, G)

def pubkey_to_address(pubkey_point) -> str:
    x, y = pubkey_point
    pubkey_bytes = x.to_bytes(32, "big") + y.to_bytes(32, "big")
    h = keccak256(pubkey_bytes)
    return "0x" + h[-20:].hex()

def _hmac_sha256(key, msg):
    import hmac, hashlib
    return hmac.new(key, msg, hashlib.sha256).digest()

def _rfc6979_k(privkey_int, msg_hash: bytes):
    # RFC 6979 deterministic nonce generation
    qlen_bytes = 32
    x = privkey_int.to_bytes(qlen_bytes, "big")
    h1 = msg_hash
    v = b"\x01" * 32
    k = b"\x00" * 32
    k = _hmac_sha256(k, v + b"\x00" + x + h1)
    v = _hmac_sha256(k, v)
    k = _hmac_sha256(k, v + b"\x01" + x + h1)
    v = _hmac_sha256(k, v)
    while True:
        v = _hmac_sha256(k, v)
        candidate = int.from_bytes(v, "big")
        if 1 <= candidate < N:
            return candidate
        k = _hmac_sha256(k, v + b"\x00")
        v = _hmac_sha256(k, v)

def sign(privkey_int, msg_hash: bytes):
    """Sign a 32-byte digest. Returns (r, s, v) with v in {27,28},
    low-s enforced (EIP-2)."""
    z = int.from_bytes(msg_hash, "big")
    k = _rfc6979_k(privkey_int, msg_hash)
    R = _scalar_mult(k, G)
    r = R[0] % N
    k_inv = _inv(k, N)
    s = (k_inv * (z + r * privkey_int)) % N

    recovery_id = R[1] & 1  # parity of R.y before any s flip

    if s > N // 2:
        s = N - s
        recovery_id ^= 1  # flipping s flips the recovery parity

    v = 27 + recovery_id
    return r, s, v

def sign_to_65_bytes(privkey_int, msg_hash: bytes) -> bytes:
    r, s, v = sign(privkey_int, msg_hash)
    return r.to_bytes(32, "big") + s.to_bytes(32, "big") + bytes([v])
