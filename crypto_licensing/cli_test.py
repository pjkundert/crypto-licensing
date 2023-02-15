import json
import os

try:
    from pathlib	import Path
except ImportError:
    from pathlib2	import Path

import pytest  # noqa: F401

from click.testing	import CliRunner

from .cli	import cli

runner				= CliRunner()


def test_cli( tmp_path ):

    tmp				= Path( tmp_path )
    cwd				= tmp / "cwd"
    os.mkdir( str( cwd ))
    print( "Changing CWD to {}".format( cwd ))
    os.chdir( str( cwd ))

    response			= runner.invoke( cli, "--help" )
    print( "--help:\n{}\n\n".format( response.output ))
    assert response.exit_code == 0

    response			= runner.invoke( cli, [ "registered", "--help" ] )
    print( "registered --help:\n{}\n\n".format( response.output ))
    assert response.exit_code == 0

    # Lets make an Agent ID, w/ reverse_save ensuring it ends up in our 'extra' dir (not in the
    # CWD).  This proves that '.' is not included in the config_paths by default when writing.
    response			= runner.invoke( cli, [
        "--name", "something",  # to avoid collisions w/ ~/.crypto-licensing/crypto-licensing.crypto-key* Keypairs
        "--extra", str( tmp ),
        "--reverse-save",
        "registered",
        "--seed", "00" * 32,
        "--username", "a@b.c",
        "--password", "password",
    ] )
    print( "registered:\n{}\n\n".format( response.output ))
    assert response.exit_code == 0

    filename,vk			= json.loads( response.output )
    assert Path( filename ) == tmp / 'something.crypto-keypair'
    assert vk == "O2onvM62pC1io6jQKm8Nc2UyFXcd4kOmOsBIoYtZ2ik="

    response			= runner.invoke( cli, [
        "-v",
        "--name", "something",  # to avoid collisions w/ ~/.crypto-licensing/crypto-licensing.crypto-key* Keypairs
        "--extra", str( tmp ),
        "--private",
        "--reverse-save",
        "registered",
        "--username", "a@b.c",
        "--password", "password",
    ] )

    print( "registered (again):\n{}\n\n".format( response.output ))
    assert response.exit_code == 0
    filename,sk,keypair		= json.loads( response.output )
    assert Path( filename ) == tmp / 'something.crypto-keypair'
    assert sk == "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA7aie8zrakLWKjqNAqbw1zZTIVdx3iQ6Y6wEihi1naKQ=="

    # Now that we have an Agent ID, let's create a self-signed License for something.  This is just
    # to remember some fact for later, and assure ourself that we have provenance for this fact.
    response			= runner.invoke( cli, [
        "-v",
        "--name", "something",
        "--why", "License Something Awesome",
        "--extra", str( tmp ),
        "--reverse-save",
        "license",
        "--author", "End User (self-issued)",
        "--domain", "b.c",
        "--product", "Something",		# Also implies the Author's Keypair, something
        "--username", "a@b.c",
        "--password", "password",
        "--no-confirm",				# Don't confirm Author pubkey via DKIM
        "--grant", json.dumps( { "some": { "capability": 1 }} ),
        "--client", "End User",
        "--client-pubkey", vk,
    ] )
    print( "license (again):\n{}\n\n".format( response.output ))
    assert response.exit_code == 0
    filename,license		= json.loads( response.output )
    assert Path( filename ) == tmp / 'something.crypto-license'
    assert license == {
        "license":{
            "author":{
                "domain":"b.c",
                "name":"End User (self-issued)",
                "product":"Something",
                "pubkey":"O2onvM62pC1io6jQKm8Nc2UyFXcd4kOmOsBIoYtZ2ik="
            },
            "client":{
                "name":"End User",
                "pubkey":"O2onvM62pC1io6jQKm8Nc2UyFXcd4kOmOsBIoYtZ2ik="
            },
            "dependencies":[],
            "grant":{
                "some":{
                    "capability":1
                }
            },
        },
        "signature":"Q4PtEkyTQ2ufHKTrkP495tQ9wCkJwriVu0T84/Wwo49Bixpo7L7fEaItH8hVfKHhtWE9TNPU9oArRBnSYw14Bw==",
    }
