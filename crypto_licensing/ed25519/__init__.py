#
# Crypto-licensing -- Cryptographically signed licensing, w/ Cryptocurrency payments
#
# Copyright (c) 2022, Dominion Research & Development Corp.
#
# Crypto-licensing is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version.  It is also available under alternative (eg. Commercial)
# licenses, at your option.  See the LICENSE file at the top of the source tree.
#
# It is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE.  See the GNU General Public License for more details.
#

import warnings

from ..misc		import (
    into_b64, into_bytes
)

# We require that at least the basic dholth/ed25519ll API must be available
__all__ = [
    'crypto_sign', 'crypto_sign_open', 'crypto_sign_keypair', 'Keypair',
    'PUBLICKEYBYTES', 'SECRETKEYBYTES', 'SIGNATUREBYTES'
]

# Get Ed25519 support. Try a globally installed ed25519ll possibly with a CTypes binding
try:
    from ed25519ll import *
except Exception: # If not installed/built correctly, may have various errors...
    # Otherwise, try our local Python-only ed25519ll derivation
    try:
        from ..ed25519ll_pyonly import *
    except ImportError:
        # Fall back to the very slow D.J.Bernstein Python reference implementation
        from ..ed25519_djb import *


def into_keys( keypair, verify=False ):
    """Return whatever Ed25519 (public, signing) keys are available in the provided unencrypted Keypair
    (something w/ vk and sk attributes) or 32/64-byte key material.  This destructuring ordering is
    consistent with the namedtuple('Keypair', ('vk', 'sk')).

    Supports deserialization of keys from hex or base-64 encode public (32-byte) or secret/signing
    (64-byte) data.  To avoid nondeterminism, we will assume that all Ed25519 key material is encoded in
    base64 (never hex).

    """
    try:
        # May be a Keypair namedtuple
        if verify:
            keypair_verify	= crypto_sign_keypair( seed=keypair.sk )
            assert keypair_verify.vk == keypair.vk, \
                "Invalid Ed25519 Keypair; public key: {} doesn't match derived: {}".format(
                    into_b64( keypair.vk ),
                    into_b64( keypair_verify.vk ),
                )
        return keypair.vk, keypair.sk
    except AttributeError:
        pass
    # Not a Keypair.  First, see if it's a serialized public/private key.
    deserialized		= into_bytes( keypair, ('base64',), ignore_invalid=True )
    if deserialized:
        keypair			= deserialized
    # Finally, see if we've recovered a signing or public key
    if isinstance( keypair, bytes ):
        if len( keypair ) == 64:
            # Must be a 64-byte signing key, which also contains the public key.  Can verify.
            if verify:
                keypair_verify	= crypto_sign_keypair( seed=keypair[0:32] )
                assert keypair_verify.vk == keypair[32:64], \
                    "Invalid Ed25519 Keypair; public key: {} doesn't match derived: {}".format(
                        into_b64( keypair[32:64] ),
                        into_b64( keypair_verify.vk ),
                )
            return keypair[32:64], keypair[0:64]
        elif len( keypair ) == 32:
            # Can only contain a 32-byte public key.  No way to confirm.
            return keypair[:32], None
    # Unknown key material.
    return None, None


# Disable warnings about seed source; we expect to provide cryptographically secure randomness
warnings.filterwarnings( action="ignore", category=RuntimeWarning, module=__name__ )
