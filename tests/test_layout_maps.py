import unittest

from core.common.layout_maps import field_candidates, resolve_profile


class LayoutMapTests(unittest.TestCase):
    def test_resolve_profile_and_field_candidates(self):
        layout_map = {
            "defaultProfile": "standard",
            "profiles": {
                "standard": {
                    "fields": {
                        "campoA": ["id1", "id2"]
                    }
                }
            },
        }
        profile_name, profile = resolve_profile(layout_map)
        self.assertEqual(profile_name, "standard")
        self.assertEqual(field_candidates(profile, "fields", "campoA"), ["id1", "id2"])


if __name__ == "__main__":
    unittest.main()
