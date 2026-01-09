import unittest
from video_clipper import VideoClipper


class TimeParserTests(unittest.TestCase):
    def test_seconds_only(self):
        self.assertEqual(VideoClipper.time_to_seconds(None, '75'), 75)

    def test_minutes_seconds(self):
        self.assertEqual(VideoClipper.time_to_seconds(None, '1:23'), 83)

    def test_padded_hms(self):
        self.assertEqual(VideoClipper.time_to_seconds(None, '00:01:05'), 65)

    def test_hours_minutes_seconds(self):
        self.assertEqual(VideoClipper.time_to_seconds(None, '2:00:00'), 7200)

    def test_fractional_seconds(self):
        self.assertEqual(VideoClipper.time_to_seconds(None, '1:02:03.456'), 3723)

    def test_invalid_format(self):
        with self.assertRaises(ValueError):
            VideoClipper.time_to_seconds(None, 'abc')


if __name__ == '__main__':
    unittest.main()
