from setuptools import setup

import os
import sys
import glob
import fnmatch

HERE				= os.path.dirname( os.path.abspath( __file__ ))

# Must work if setup.py is run in the source distribution context, or from
# within the packaged distribution directory.
__version__			= None
try:
    exec( open( 'crypto_licensing/version.py', 'r' ).read() )
except FileNotFoundError:
    exec( open( 'version.py', 'r' ).read() )

console_scripts			= [
    'crypto-licensing		= crypto_licensing.licensing.main:main',
]

entry_points			= {
    'console_scripts': 		console_scripts,
}

install_requires		= open( os.path.join( HERE, "requirements.txt" )).readlines()

tests_require			= open( os.path.join( HERE, "requirements-tests.txt" )).readlines()
extras_require			= {
    option: open( os.path.join( HERE, "requirements-{}.txt".format( option ))).readlines()
    for option in [
        'dev',		# crypto_licensing[dev]:    All modules to support development
    ]
}

package_dir			= {
    "crypto_licensing":			"./crypto_licensing",
    "crypto_licensing/ed25519":		"./crypto_licensing/ed25519",
    "crypto_licensing/ed25519ll_pyonly":"./crypto_licensing/ed25519ll_pyonly",
    "crypto_licensing/licensing":	"./crypto_licensing/licensing",
    "crypto_licensing/licensing/doh":	"./crypto_licensing/licensing/doh",
}


long_description_content_type	= 'text/plain'
long_description		= """\
Licensing software and getting paid for it has become extremely difficult, due to government
regulatory and banking interference.

Using crypto-licensing allows you automatically and securely issue licenses, and get paid in various
cryptocurrencies.
"""

classifiers			= [
    "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
    "License :: Other/Proprietary License",
    "Programming Language :: Python :: 2",
    "Programming Language :: Python :: 3",
    "Development Status :: 5 - Production/Stable",
    "Intended Audience :: Developers",
    "Intended Audience :: Financial and Insurance Industry",
    "Environment :: Console",
    "Topic :: Security :: Cryptography",
    "Topic :: Office/Business :: Financial",
]
project_urls			= {
    "Bug Tracker": "https://github.com/pjkundert/crypto-licensing/issues",
}
setup(
    name			= "crypto_licensing",
    version			= __version__,
    tests_require		= tests_require,
    extras_require		= extras_require,
    install_requires		= install_requires,
    packages			= package_dir.keys(),
    package_dir			= package_dir,
    include_package_data	= True,
    entry_points		= entry_points,
    author			= "Perry Kundert",
    author_email		= "perry@dominionrnd.com",
    project_urls		= project_urls,
    description			= "The crypto-licensing module implements Ed25519-signed license checking and automatic issuance after cryptocurrency payment",
    long_description		= long_description,
    long_description_content_type = long_description_content_type,
    license			= "Dual License; GPLv3 and Proprietary",
    keywords			= "licensing Bitcoin Ethereum cryptocurrency payments Ed25519 signatures",
    url				= "https://github.com/pjkundert/crypto-licensing",
    classifiers			= classifiers,
)
