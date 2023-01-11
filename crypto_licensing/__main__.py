
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

from __future__ import absolute_import, print_function, division

import click
import codecs
import json
import logging
import os
import sys

from .misc	import log_cfg, log_level
from .		import licensing


__author__                      = "Perry Kundert"
__email__                       = "perry@dominionrnd.com"
__copyright__                   = "Copyright (c) 2022, Dominion Research & Development Corp."
__license__                     = "Dual License: GPLv3 (or later) and Commercial (see LICENSE)"


log				= logging.getLogger( __package__ )


#
# Generate Agent Keypairs and Licenses
#
# --filename	The name of the Keypair or License, eg. Some Name ==> some-name.crypto-key
#
@click.group()
@click.option('-v', '--verbose', count=True)
@click.option('-q', '--quiet', count=True)
@click.option('-p', '--private/--no-private', default=False, help="Disclose Private Key material")
@click.option('-l', '--log-file', help="Log file name")
@click.option('-w', '--why', help="What is being done (for logging details)")
def cli( verbose, quiet, private, log_file, why ):
    cli.verbosity		= verbose - quiet
    log_cfg['level']		= log_level( cli.verbosity )
    if log_file:
        log_cfg['filename']	= log_file
    logging.basicConfig( **log_cfg )
    if verbose or quiet:
        logging.getLogger().setLevel( log_cfg['level'] )
    if private:
        cli.private	= True
    if why:
        cli.why		= why
cli.private		= False  # noqa: E305
cli.verbosity		= 0
cli.why			= None


@click.command()
@click.option( "--name", help="Defines the file name Keypair is saved under" )
@click.option( "--username", help="The email address (if encrypted Keypair desired))" )
@click.option( "--password", help="The password" )
def check( name, username, password ):
    """Check for Agent ID Ed25519 Key, and any associated License(s).  If neither Keypair nor
    License(s) are found, an Exception is raised.

    If not -q, outputs JSON { <key>: [ <lic>, ...], }

    """
    username		= username or os.getenv( licensing.ENVUSERNAME )
    password		= password or os.getenv( licensing.ENVPASSWORD )
    log.info( "Checking {why} w/ {username}: {password!r}".format(
        why		= cli.why or name,
        username	= username,
        password	= '*' * len( password ) if password else password,
    ))

    i			= None
    licenses		= {}
    for i,(keypair_raw,lic) in enumerate( licensing.check(
        basename	= name,
        username	= username,
        password	= password,
        package		= __package__,
    )):
        if not keypair_raw:
            log.warning( "No Agent ID Keypair {name}".format( name=name or ''))
        else:
            key		= licensing.into_hex( keypair_raw.sk ) if cli.private else licensing.into_b64( keypair_raw.vk )
            licenses.setdefault( key, [] )
            if lic:
                licenses[key].append( lic )
    if cli.verbosity >= 0 and licenses:
        click.echo( licensing.into_JSON( licenses, indent=4, prefix=' ' * 4 ))
    assert licenses, \
        "Failed to find any Agent ID Keypairs or Licenses for {}".format( name )


@click.command()
@click.option( "--name", help="Defines the file name Keypair is saved under" )
@click.option( "--username", help="The email address (if encrypted Keypair desired))" )
@click.option( "--password", help="The password" )
@click.option( "--registering/--no-registering", default=True, help="If no Keypair found, create and register a new one" )
@click.option( "--seed", help="A 32-byte (256-bit) Seed, in Hex (default: random)" )
def registered( name, username, password, registering, seed ):
    """Determine if the specified name and credentials are registerd.  Locate (or create and save,
    by default) an Agent ID Ed25519 Keypair.

    If not -q, outputs JSON "<Pubkey>" (or "<Privkey>" if --private)

    """
    username		= username or os.getenv( licensing.ENVUSERNAME )
    password		= password or os.getenv( licensing.ENVPASSWORD )
    log.info( "Registering {why} w/ {username}: {password!r}".format(
        why		= cli.why or name,
        username	= username,
        password	= '*' * len( password ) if password else password,
    ))

    keypair			= licensing.registered(
        seed		= codecs.decode( seed, 'hex_codec' ) if seed else None,
        why		= cli.why or username,
        username	= username,
        password	= password,
        filename	= name,
        package		= __package__,
        registering	= registering,
    )
    keypair_raw		= keypair.into_keypair(
        username	= username,
        password	= password,
    )
    key			= licensing.into_hex( keypair_raw.sk ) if cli.private else licensing.into_b64( keypair_raw.vk )
    if cli.verbosity >= 0:
        click.echo( licensing.into_JSON( key, indent=4 ))


@click.command()
@click.option( "--name", help="Defines the file name author Keypair read from, License is saved under" )
@click.option( "--username", help="The email address (if encrypted Keypair))" )
@click.option( "--password", help="The password" )
@click.option( "--registering/--no-registering", default=True, help="If no Keypair found, create and register a new one" )
@click.option( "--author", help="The author's name (eg. 'Awesome, Inc.'" )
@click.option( "--domain", help="The company's DNS domain (eg. 'awesome.com'" )
@click.option( "--product", help="The product name, (eg. 'Awesome Product')" )
@click.option( "--service", help="The DKIM/License Grant key, (default is derived from product, eg. 'awesome-product')" )
@click.option( "--grant", help="The License's Grants (as JSON)" )
@click.option( "--dependency", multiple=True, help="Sub-license the specified License (by filename) as one of this License's dependencies" )
@click.option( "--confirm/--no-confirm", default=True, help="Confirm the signatures via DKIM (default: True)" )
@click.option( "--client", help="The client's name (eg. 'Example, Inc.'" )
@click.option( "--client-domain", help="The client's DNS domain (eg. 'example.com'" )
@click.option( "--client-pubkey", help="The client's Ed25519 Agent ID" )
def license( name, username, password, registering, author, domain, product, service, grant, dependency, confirm, client, client_domain, client_pubkey ):
    """Load/create an Author ID, create/save a LicenseSigned for the specified product.

    Won't overwrite existing keypair or license files.

    Appends any specified dependencies without confirming signatures.
    """
    username		= username or os.getenv( licensing.ENVUSERNAME )
    password		= password or os.getenv( licensing.ENVPASSWORD )
    log.info( "Licensing {why} w/ {username}: {password!r}".format(
        why		= cli.why or name,
        username	= username,
        password	= '*' * len( password ) if password else password,
    ))

    dependencies		= []
    for f in ( open( dep, 'r' ) for dep in dependency ):
        with f:
            prov_ser		= f.read()
            prov_dict		= json.loads( prov_ser )
            prov		= licensing.LicenseSigned( confirm=confirm, _from=f.name, **prov_dict )
            log.detail( "Dependency: {prov!r}".format( prov=prov ))
        dependencies.append( prov )

    # Locate the Agent ID Keypair to use to author the License.  Default to create if not found.
    keypair			= licensing.registered(
        why		= cli.why or product,
        basename	= name,
        username	= username,
        password	= password,
        registering	= registering,
    )
    keypair_raw			= keypair.into_keypair(
        username	= username,
        password	= password,
    )
    key				= licensing.into_hex( keypair_raw.sk ) if cli.private else licensing.into_b64( keypair_raw.vk )
    log.detail( "Authoring Agent ID {what}: {key}, from {path}".format(
        what	= "Keypair" if cli.private else "Pubkey",
        key	= key,
        path	= keypair._from,
    ))
    lic				= licensing.license(
        author		= licensing.Agent(
            name	= author,
            domain	= domain,
            product	= product,
            service	= service or None,
            keypair	= keypair_raw,
        ),
        client		= None if not ( client or client_domain or client_pubkey ) else licensing.Agent(
            name	= client or "End-User",
            domain	= client_domain,
            pubkey	= client_pubkey
        ),
        dependencies	= dependencies,
        grant		= grant,
        why		= cli.why or product,
        basename	= name,
        confirm		= confirm,
    )
    log.normal( "Created License {!r} in {}".format( lic, lic._from ))
    if cli.verbosity >= 0:
        click.echo( licensing.into_JSON( lic, indent=4 ))


cli.add_command( registered )
cli.add_command( license )
cli.add_command( check )

try:
    cli()
except Exception as exc:
    log.warning( "Failed: {exc}".format( exc=exc ))
    sys.exit( 1 )
else:
    sys.exit( 0 )
