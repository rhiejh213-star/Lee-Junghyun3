import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
import monitor

class MonitorTests(unittest.TestCase):
    def test_status_classification(self):
        self.assertEqual(monitor.status_of("출발","departure"),"completed")
        self.assertEqual(monitor.status_of("도착","arrival"),"completed")
        self.assertEqual(monitor.status_of("결항","departure"),"cancelled")
        self.assertEqual(monitor.status_of("지연","departure"),"delayed")
        self.assertEqual(monitor.status_of("정상","departure"),"pending")
        self.assertEqual(monitor.status_of("기타","departure"),"unknown")
    def test_time_parser(self):
        d=monitor.parse_dt("202611120805")
        self.assertEqual(d.strftime("%Y-%m-%d %H:%M"),"2026-11-12 08:05")
    def test_domestic_filter_and_codeshare(self):
        start=datetime(2026,11,12,8,tzinfo=ZoneInfo("Asia/Seoul"))
        end=datetime(2026,11,12,12,tzinfo=ZoneInfo("Asia/Seoul"))
        rows=[
          {"scheduleDateTime":"202611120900","flightId":"KE1","masterFlightId":"KE1","codeShare":"N","airportCode":"NRT","flightStatus":"출발"},
          {"scheduleDateTime":"202611120900","flightId":"JL5000","masterFlightId":"KE1","codeShare":"Y","airportCode":"NRT","flightStatus":"정상"},
          {"scheduleDateTime":"202611121000","flightId":"KE2","airportCode":"PUS","flightStatus":"출발"}]
        out=monitor.normalize(rows,"departure",start,end)
        self.assertEqual(len(out),1)
        self.assertEqual(out[0]["status"],"completed")
    def test_missing_airport_fails_closed(self):
        start=datetime(2026,11,12,8,tzinfo=ZoneInfo("Asia/Seoul"))
        end=datetime(2026,11,12,12,tzinfo=ZoneInfo("Asia/Seoul"))
        with self.assertRaises(monitor.DataError):
            monitor.normalize([{"scheduleDateTime":"202611120900","flightId":"KE1"}],"departure",start,end)
    def test_four_hour_window(self):
        asof=datetime(2026,11,12,12,5,tzinfo=ZoneInfo("Asia/Seoul"))
        end=asof.replace(hour=12,minute=0,second=0,microsecond=0)
        start=end.replace(hour=8)
        self.assertEqual((end-start).total_seconds(),14400)

if __name__=="__main__": unittest.main()
