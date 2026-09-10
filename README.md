# SOS 69069 APP
SOS 69069 originates from verified Activity and Signatures.

Whatever you do. SOS records. Whatever you do. Continue ...

What is the cost of your action right now?

Coffee me 0x1c10e6574ee696f54b21a611a21313e4714628ad

69069 — it’s a Ledger of Presence with no Assets to hold and no Wallet to drain. Presence written Permanently into the block History, carried Forward by activity, and made Provable through its x2 Legacy Continuity System. An Identityless Record Field. 0x7373DBC24Dcd785896E8Ac3d5372c6ced9B75a8A

SOS 69069 APP v 1.6.9.0.6.9,all files ZIP
https://github.com/Taru8899/SOS69069APP/blob/2861eb9cd963bc3ffe7082b8e39fc517e6504634/1.6.9.0.6.9-SOS69069APP.zip

SOS 69069 APP v 1.6.9.0.6.9, light version arm64-v8a
https://github.com/Taru8899/SOS69069APP/blob/41fd3ef7b5ce527ce75082e37a23203888609aef/1.6.9.0.6.9-sos69069-1.6.9-arm64-v8a-debug.apk

## Overview

69069 is a pure on-chain event ledger. It holds no assets, executes nothing on behalf of users, and has no admin, owner, or upgrade path. It only records signed data as permanent events.


## Core Mechanic

Every successful call writes one atomic record containing:

- the signer  
- the intended address  
- a payload hash  
- the raw signature  
- free-form metadata  

Writing a record increments two independent counters:

- `pushOf[signer]`  
- `trustOf[intendedTo]`  

A global counter, `phaseTotal`, also increments on every record.

The effective value for any address is defined as:

```
effective = trustOf − pushOf
```

This signed integer is exposed directly through `effectiveOf()` and `statsOf()`. For wallet-style display it is cast to a non-negative `uint256` via `balanceOf()`, which returns `max(0, effective)`.

All counters are cyclic `uint256` values. When a counter reaches `type(uint256).max` it wraps to zero and a separate, permanent overflow counter is incremented. An event is emitted on every wrap.

## Comparison to ERC-20 Tokens

From the outside, 69069 deliberately presents the familiar surface of an ERC-20 token:

- `name()` → `"69069"`  
- `symbol()` → `"SOS"`  
- `decimals()` → `0`  
- `balanceOf(address)` → non-negative Effective value  
- `totalSupply()` → total number of records ever written  
- `Transfer` events emitted on every record  

In a normal ERC-20, a Transfer moves tokens from one balance to another. In 69069 the same event is emitted, but the underlying meaning is different:

- The “from” address is the **signer** (Push).  
- The “to” address is the **intended** recipient (Trust).  
- The value is always 1.  

Consequently:

- When a signature is recorded with you as the intended address, your Effective rises by +1 (exactly as if you received 1 SOS).  
- When you are the signer, your Effective falls by −1 (exactly as if you sent 1 SOS).  

Wallets and explorers therefore display balances and transfer histories exactly as they would for any ordinary ERC-20. The user experience feels familiar. Internally, however, nothing is transferred, nothing can be spent, and no asset ever exists.

## Recording Functions

There are some ways to create a record.

**recordSignature**  
Accepts the same five fields but verifies the signature on-chain. It recovers the signing address from the signature and the payload hash using `ecrecover` and reverts unless the recovered address matches the declared signer exactly. The payload hash is used as-is, without any message prefix.

**recordSignatureOne**  
Accepts one signer, one intended address, and equal-length arrays of payload hashes, signatures, and metadata. Each entry is verified independently and written as its own record. A call with N entries increases both the signer’s Push and the intended address’s Trust by N, and emits one permanent event per entry. This is the only remaining batch-style function.

## Recording Path

All functions route through the same internal step, which:

1. Updates the Push and Trust counters (and the global phaseTotal).  
2. Emits a display-only `Transfer` event (signer → intendedTo, value = 1).  
3. Emits the permanent `SignatureRecorded` event containing the full packed unit: signer, intendedTo, payloadHash, signature, submitter, timestamp, and metadata.

## Signing and Submission

The signer only ever produces a signature off-chain. Any address can later submit that signature on-chain. The submitting address pays the gas and is recorded as the submitter. The signer and the submitter may be the same address or different ones.

## Wallet Display Surface

Because the contract exposes the standard ERC-20 view functions and emits Transfer events, ordinary wallets and block explorers treat 69069 as a normal token. Users see balances, transfer histories, and a familiar ticker. There is, however, no `transfer`, no `approve`, and no way to move anything. The familiar surface is purely presentational.

## HTML Bridge Layer

An HTML front-end can serve as a seamless bridge between the ordinary ERC-20 mental model and the ledger’s true behaviour.  

On the outside the page can present the classic actions users already understand:

- “Send 1 SOS to address X”  
- “Receive signatures intended for me”  
- Balance display that matches any wallet  

Under the hood the page constructs the correct payload, obtains an off-chain signature, and calls the appropriate record function (`recordSignature`, `recordSignatureOne`, etc.). The user therefore interacts exactly as they would with a normal ERC-20 token, while the contract itself remains a pure, non-transferable event ledger. The HTML layer absorbs the cognitive difference; the on-chain logic stays minimal and immutable.

## Safety Properties

- Rejects all direct ETH transfers.  
- Checks that both addresses are non-zero on every record.  
- Contains no self-destruct mechanism.  
- Contains no proxy.  
- Contains no privileged account of any kind.

69069 therefore gives users the familiar experience of an ERC-20 token while remaining, at its core, nothing more than an append-only, identityless record of presence.
