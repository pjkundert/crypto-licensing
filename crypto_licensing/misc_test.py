import datetime

import pytz

from .misc	import (
    parse_datetime, parse_seconds, Timestamp, Duration
)


def test_Duration():
    d_str		= Duration( "1m33s123ms" )
    assert str( d_str ) == "1m33.123s"


def test_Timestamp( monkeypatch ):
    monkeypatch.setattr( Timestamp, 'LOC', pytz.timezone( "Canada/Mountain" ))

    dt			= parse_datetime( "2021-01-01 00:00:00.1 Canada/Pacific" )
    assert isinstance( dt, datetime.datetime )

    ts_dt		= Timestamp( dt )
    assert isinstance( ts_dt, Timestamp )
    assert isinstance( ts_dt, datetime.datetime )
    assert ts_dt.timestamp() == 1609488000.1

    ts_int		= Timestamp( 0 )
    assert isinstance( ts_int, Timestamp )
    assert isinstance( ts_int, datetime.datetime )
    assert ts_int.timestamp() == 0

    assert float( ts_dt ) == float( Timestamp( datetime.datetime(
        year=2021, month=1, day=1, hour=8, minute=0, second=0, microsecond=100000, tzinfo=pytz.UTC
    )))

    assert str( ts_dt ) == "2021-01-01 01:00:00.100 Canada/Mountain"

    assert str( ts_dt + "1m1.33s" ) == "2021-01-01 01:01:01.430 Canada/Mountain"
    assert str( ts_dt - "1m1s330ms" ) == "2021-01-01 00:58:58.770 Canada/Mountain"

    assert str( ts_dt +  61.33 ) == "2021-01-01 01:01:01.430 Canada/Mountain"
    assert str( ts_dt -  61.33 ) == "2021-01-01 00:58:58.770 Canada/Mountain"

    assert parse_seconds(      "01.33" ) ==  1.33       # as a simple float
    # [HHH]:MM[:SS[.sss]] time specs default to MM, then H:MM, and only with sufficient segments, then to H:MM:SS
    assert parse_seconds(     ":01" ) == 60.0
    assert parse_seconds(    "0:01" ) == 60.0
    assert parse_seconds(   "01:01" ) == 3660.0		# as a HH:MM time tuple
    assert parse_seconds( "0:01:01.33" ) == 61.33
    assert str( ts_dt + parse_seconds( "0:01:01.33" )) == "2021-01-01 01:01:01.430 Canada/Mountain"
    assert str( ts_dt - parse_seconds( "61.33" )) == "2021-01-01 00:58:58.770 Canada/Mountain"
    assert str( ts_dt - parse_seconds( "1m1s330000us" )) == "2021-01-01 00:58:58.770 Canada/Mountain"

    assert ts_dt.timestamp() == 1609488000.1
    assert ( ts_dt + "1ms" ).timestamp() == 1609488000.101
    assert ( ts_dt - "1ms" ).timestamp() == 1609488000.099
    assert str( ts_dt + "1ms" ) == "2021-01-01 01:00:00.101 Canada/Mountain"
    assert str( ts_dt - "1ms" ) == "2021-01-01 01:00:00.099 Canada/Mountain"

    assert ( ts_dt + "1us" ).timestamp() == 1609488000.100001
    assert ( ts_dt - "1us" ).timestamp() == 1609488000.099999

    # Solidly beyond _precision (comparisons are +/- (10 ** _precision) / 2)
    ts_dt_p1ms		= ts_dt + "1ms"
    ts_dt_m1ms		= ts_dt - "1ms"

    # Round to w/in _precision
    ts_dt_p499us	= ts_dt + "499us"
    ts_dt_m499us	= ts_dt - "499us"

    # Rounds beyond _precision
    ts_dt_p501us	= ts_dt + "501us"
    ts_dt_m501us	= ts_dt - "501us"

    assert( ts_dt_p1ms    >    ts_dt )
    assert( ts_dt_p1ms    >       dt )
    assert( ts_dt_p1ms    !=   ts_dt )
    assert( ts_dt_p1ms    !=      dt )
    assert( ts_dt_p1ms    >=   ts_dt )
    assert( ts_dt_p1ms    >=      dt )
    assert( ts_dt_m1ms    <    ts_dt )
    assert( ts_dt_m1ms    <       dt )
    assert( ts_dt_m1ms    <=   ts_dt )
    assert( ts_dt_m1ms    <=      dt )
    assert( ts_dt_p499us  ==   ts_dt )
    assert( ts_dt_p499us  ==      dt )
    assert( ts_dt_p501us  !=   ts_dt )
    assert( ts_dt_p501us  !=      dt )
    assert( ts_dt_p499us  >=   ts_dt )
    assert( ts_dt_p499us  >=      dt )
    assert( ts_dt_m499us  ==   ts_dt )
    assert( ts_dt_m499us  ==      dt )
    assert( ts_dt_m501us  !=   ts_dt )
    assert( ts_dt_m501us  !=      dt )
    assert( ts_dt_m499us  <=   ts_dt )
    assert( ts_dt_m499us  <=      dt )
    assert( ts_dt         <    ts_dt_p1ms )
    assert( ts_dt         <=   ts_dt_p1ms )
    assert( ts_dt         >    ts_dt_m1ms )
    assert( ts_dt         >=   ts_dt_m1ms )
    assert( ts_dt         ==   ts_dt_p499us )
    assert( ts_dt         >=   ts_dt_p499us )
    assert( ts_dt         <=   ts_dt_p499us )
    assert( ts_dt         ==   ts_dt_m499us )
    assert( ts_dt         >=   ts_dt_m499us )
    assert( ts_dt         <=   ts_dt_m499us )
