# -*- coding: utf-8 -*-

import json

from ..misc import urlopen, urlencode, Request
from . import doh

import requests


def test_doh_smoke():
    """For example:

        curl -H "accept: application/dns-json" "https://cloudflare-dns.com/dns-query?name=example.com&type=AAAA"
    """
    #url				= 'https://cloudflare-dns.com/dns-query'
    #url				= 'https://1.1.1.1/dns-query'
    #url				= 'https://dns.google/resolve'
    url				= 'https://8.8.8.8/resolve'
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
        'default._domainkey.justicewall.com', 'TXT' )
    print( json.dumps( recs ) )
    assert recs[0].get( 'data' ) \
        == "v=DKIM1; k=rsa; p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA0PMv4yXqvYlPWxCt7ZjdfR9Q4GzkGhxIEqxFTQEsPF0GxpZPr54GTiMsvmWxsrJWCb9OFo5qx48lPnHu1Y/KZcx6"\
        "xydZiNxYdGedcRZFtMAwQAKQgo2Iq28PamZf5D8BO1+rg9tlAo2vYKrp6Cf1zTxDqHzSVl85RA7PZj1Jb/7jpqujT1SRXngrerB4iYBtx" \
        "aPXTN/aI+cvS8kREW7tYkb4nt2fK3sb2RtCe5hxGTOdtIie/stZj/w/5ozsrtEZ6CiGQA38IaVOFsGwAvmhucy08UzbycmXKYsJiWPpSyXBXSX+O+5WaqgOYvcGT9CHBBWoFJG37Qf4KHoQqhS7IwIDAQAB;"
