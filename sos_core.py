from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils import keccak, to_checksum_address

CONTRACT_NAME = "69069"
CONTRACT_VERSION = "1"

# --- your deployed contract ---
CONTRACT_ADDRESS = "0x7373DBC24Dcd785896E8Ac3d5372c6ced9B75a8A"


def build_typed_data(chain_id: int, contract_address: str,
                      signer: str, intended_to: str,
                      payload_hash: str, metadata: str) -> dict:
    """
    Must mirror the Solidity struct EXACTLY:
    Record(address signer,address intendedTo,bytes32 payloadHash,bytes32 metadataHash)
    """
    domain = {
        "name": CONTRACT_NAME,
        "version": CONTRACT_VERSION,
        "chainId": chain_id,
        "verifyingContract": to_checksum_address(contract_address),
    }

    types = {
        "Record": [
            {"name": "signer", "type": "address"},
            {"name": "intendedTo", "type": "address"},
            {"name": "payloadHash", "type": "bytes32"},
            {"name": "metadataHash", "type": "bytes32"},
        ]
    }

    message = {
        "signer": to_checksum_address(signer),
        "intendedTo": to_checksum_address(intended_to),
        "payloadHash": payload_hash,            # 0x... 32 bytes hex
        "metadataHash": keccak(text=metadata),  # keccak256(bytes(metadata))
    }

    return {
        "types": types,
        "primaryType": "Record",
        "domain": domain,
        "message": message,
    }


def sign_record(private_key: str, chain_id: int, intended_to: str,
                 payload_hash: str, metadata: str, contract_address: str = CONTRACT_ADDRESS):
    acct = Account.from_key(private_key)
    signer = acct.address

    typed_data = build_typed_data(
        chain_id, contract_address, signer, intended_to, payload_hash, metadata
    )

    signable = encode_typed_data(full_message=typed_data)
    signed = Account.sign_message(signable, private_key=private_key)

    sig_bytes = signed.signature  # r||s||v, 65 bytes — matches contract's layout

    return {
        "signer": signer,
        "intendedTo": intended_to,
        "payloadHash": payload_hash,
        "metadata": metadata,
        "signature": "0x" + sig_bytes.hex(),
    }
