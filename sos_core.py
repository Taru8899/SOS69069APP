from pure_crypto import keccak256, privkey_to_pubkey, pubkey_to_address, sign_to_65_bytes

CONTRACT_NAME = "69069"
CONTRACT_VERSION = "1"

# --- your deployed contract ---
CONTRACT_ADDRESS = "0x7373DBC24Dcd785896E8Ac3d5372c6ced9B75a8A"

EIP712_DOMAIN_TYPEHASH = keccak256(
    b"EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"
)
RECORD_TYPEHASH = keccak256(
    b"Record(address signer,address intendedTo,bytes32 payloadHash,bytes32 metadataHash)"
)


def _addr_to_bytes32(addr_hex: str) -> bytes:
    addr_hex = addr_hex.lower().replace("0x", "")
    return bytes(12) + bytes.fromhex(addr_hex)


def _uint256_to_bytes32(n: int) -> bytes:
    return n.to_bytes(32, "big")


def _hex_to_bytes32(h: str) -> bytes:
    h = h.replace("0x", "")
    h = h.zfill(64)
    return bytes.fromhex(h)


def compute_domain_separator(chain_id: int, contract_address: str) -> bytes:
    """Mirrors the Solidity constructor's DOMAIN_SEPARATOR exactly:
    keccak256(abi.encode(EIP712_DOMAIN_TYPEHASH, keccak256("69069"),
                          keccak256("1"), chain_id, address(this)))
    abi.encode of (bytes32, bytes32, bytes32, uint256, address) is just
    5 concatenated 32-byte words (address left-padded).
    """
    encoded = (
        EIP712_DOMAIN_TYPEHASH
        + keccak256(CONTRACT_NAME.encode())
        + keccak256(CONTRACT_VERSION.encode())
        + _uint256_to_bytes32(chain_id)
        + _addr_to_bytes32(contract_address)
    )
    return keccak256(encoded)


def compute_record_struct_hash(signer: str, intended_to: str,
                                payload_hash: str, metadata: str) -> bytes:
    """Mirrors recordStructHash() in the contract exactly:
    keccak256(abi.encode(RECORD_TYPEHASH, signer, intendedTo,
                          payloadHash, keccak256(bytes(metadata))))
    """
    encoded = (
        RECORD_TYPEHASH
        + _addr_to_bytes32(signer)
        + _addr_to_bytes32(intended_to)
        + _hex_to_bytes32(payload_hash)
        + keccak256(metadata.encode())
    )
    return keccak256(encoded)


def address_from_private_key(private_key_hex: str) -> str:
    privkey_int = int(private_key_hex.replace("0x", ""), 16)
    pub = privkey_to_pubkey(privkey_int)
    return pubkey_to_address(pub)


def sign_record(private_key_hex: str, chain_id: int, intended_to: str,
                 payload_hash: str, metadata: str,
                 contract_address: str = CONTRACT_ADDRESS) -> dict:
    """Produces the exact EIP-712 signature the SOS69069 contract's
    _verifySignature() expects, using only pure-Python crypto
    (no eth_account / eth_utils / pycryptodome required)."""
    privkey_int = int(private_key_hex.replace("0x", ""), 16)
    signer = address_from_private_key(private_key_hex)

    domain_separator = compute_domain_separator(chain_id, contract_address)
    struct_hash = compute_record_struct_hash(signer, intended_to, payload_hash, metadata)

    # EIP-191/712 digest: keccak256("\x19\x01" || domainSeparator || structHash)
    digest = keccak256(b"\x19\x01" + domain_separator + struct_hash)

    sig_bytes = sign_to_65_bytes(privkey_int, digest)

    return {
        "signer": signer,
        "intendedTo": intended_to,
        "payloadHash": payload_hash,
        "metadata": metadata,
        "signature": "0x" + sig_bytes.hex(),
    }
