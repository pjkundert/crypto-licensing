# -*- coding: utf-8 -*-

import ast
import json

from ..misc import urlopen, urlencode, Request
from . import doh

import requests

import dns.resolver


def test_doh_smoke():
    """For example:

        curl -H "accept: application/dns-json" "https://cloudflare-dns.com/dns-query?name=example.com&type=AAAA"
    """
    #url				= 'https://cloudflare-dns.com/dns-query'
    #url				= 'https://1.1.1.1/dns-query'
    #url				= 'https://8.8.8.8/resolve'
    url				= 'https://dns.google/resolve'
    headers			= {
        #'Content-Type':  'application/dns-json',  	# cloudflare
        'Content-Type':  'application/x-javascript',    # google
    }

    payload			= dict(
        name	= 'crypto-licensing.crypto-licensing._domainkey.dominionrnd.com',
        type	= 'TXT',
        #name	= 'example.com',
        #type	= 'AAAA',
        ct	= headers['Content-Type'],
        do	= 'true',			# Include DNSSEC
    )
    query 			= urlencode( sorted( payload.items() ))
    print( query )
    request			= Request( url, data=query.encode( 'UTF-8' ), headers=headers )
    print( repr( request.data ))
    print( repr( request.header_items() ))

    # Will fail, due to not having access to CA certificates.  Crazily, this prevents it from
    # working, unless you actually patch the system SSL with a symbolic link to the certifi certs.
    try:
        response		= urlopen( request ).read()
        print( repr( response ))
        print( repr( response.full_url ))
        reply			= json.loads( response.decode( 'UTF-8' ))
        print( reply )
    except Exception as exc:
        print( str( exc ))
        pass

    # Now use requests.  Verifies SSL connections correctly, in Python 2 and 3 using certifi certs.
    response			= requests.get( url, params=payload, headers=headers, verify=True )
    print( response )
    print( response.url )
    print( response.status_code )
    print( repr( response.headers ))
    print( response.encoding )
    print( repr( response.text ))
    if response.text:
        print( repr( response.json() ))
        print( json.dumps( response.json(), indent=4 ))


def test_doh_api():
    recs			= doh.query(
        'crypto-licensing.crypto-licensing._domainkey.dominionrnd.com', 'TXT' )
    print( json.dumps( recs ) )

    assert len( recs ) == 1
    assert recs[0].get( 'data' ) \
        == 'v=DKIM1; k=ed25519; p=5cijeUNWyR1mvbIJpqNmUJ6V4Od7vPEgVWOEjxiim8w='

    # Now ensure multi-record (long) TXT entries are properly handled.
    recs			= doh.query(
        "fm1.kundert.ca.dkim.fmhosted.com", 'TXT' )
    recs_expected		="v=DKIM1; k=rsa; p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAvjD7ONPgakX9FURb/B+TzWczm9+VCrZs5YCrGAlUdtw76lHaXVOXBk+f+ptDHg4DhaECZ5anE590QthodDXVNXeVdWh6EGpm1rvy75nj3R5scB31TZ1zYhHWMxWd9m6RsJRAYI/ANcwxAGTtgDQAYW0rBdY61F7TpXPvwr0M/AFx6jTpKP8uXiF5/twcOTRqs" "q/dlshX6/x+jjqF3TkgOjmfB9cXmzqgD9OQkmI82ukGHFAJxwMG8nTwG92x5MjRG4xjhpXlSZFjaeatvw25/67AOk7bMR5EghSvBY7K5LPwxot+nNqb43XvMk1t7sLyoO5bBOU3r4oLLWOnPE9iTQIDAQAB"  # noqa E501
    print( json.dumps( recs, indent=4 ))
    assert recs[0].get( 'data' ) == recs_expected

    # Via Cloudflare, too?
    recs			= doh.query(
        "fm1.kundert.ca.dkim.fmhosted.com", 'TXT', provider=doh.DoH_Provider.CLOUDFLARE )
    print( json.dumps( recs, indent=4 ))
    assert recs[0].get( 'data' ) == recs_expected

    # Standard DNS resolver splits long records
    recs			= dns.resolver.query(
        "fm1.kundert.ca.dkim.fmhosted.com", 'TXT' )
    recs_str			= list( map( str, recs ))
    print( json.dumps( recs_str, indent=4 ))
    assert recs_str \
        == [
            '"v=DKIM1; k=rsa; p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAvjD7ONPgakX9FURb/B+TzWczm9+VCrZs5YCrGAlUdtw76lHaXVOXBk+f+ptDHg4DhaECZ5anE590QthodDXVNXeVdWh6EGpm1rvy75nj3R5scB31TZ1zYhHWMxWd9m6RsJRAYI/ANcwxAGTtgDQAYW0rBdY61F7TpXPvwr0M/AFx6jTpKP8uXiF5/twcOTRqs" "q/dlshX6/x+jjqF3TkgOjmfB9cXmzqgD9OQkmI82ukGHFAJxwMG8nTwG92x5MjRG4xjhpXlSZFjaeatvw25/67AOk7bMR5EghSvBY7K5LPwxot+nNqb43XvMk1t7sLyoO5bBOU3r4oLLWOnPE9iTQIDAQAB"'  # noqa E501
        ]
    assert ast.literal_eval( *recs_str ) == recs_expected
