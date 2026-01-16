
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

__author__                      = "Perry Kundert"
__email__                       = "perry@dominionrnd.com"
__copyright__                   = "Copyright (c) 2022 Dominion Research & Development Corp."
__license__                     = "Dual License: GPLv3 (or later) and Commercial (see LICENSE)"

__all__				= [
    'Serializable', 'LicenseIncompatibility', 'License', 'LicenseSigned', 'Agent',
    'domainkey', 'domainkey_service', 'authoring',
    'issue', 'verify', 'load', 'load_keypairs', 'save', 'save_keypair',
    'check', 'check_nolog', 'license',  'registered', 'authorized', 'authorized_nolog',
    'machine_UUIDv4',
    'KeypairEncrypted', 'KeypairPlaintext',
    'KEYPATTERN', 'KEYEXTENSION', 'LICPATTERN', 'LICEXTENSION',
    'ENVPASSWORD', 'ENVUSERNAME',
]

from .defaults		import *
from .errors		import *
from .grants		import *
from .serializable	import *
from .verification	import *
# And a few conversion utilities from ..misc that used to be defined here
from ..misc		import (
    into_boolean, into_b64, into_text, into_hex, into_str,
)
