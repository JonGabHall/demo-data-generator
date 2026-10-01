import unittest

from indoors_demo_generator.schema import _source_text_field_length


class _Field:
    def __init__(self, name: str, field_type: str, length: int) -> None:
        self.name = name
        self.type = field_type
        self.length = length


class _ArcPy:
    @staticmethod
    def ListFields(dataset: str):
        if dataset == "levels":
            return [_Field("LEVEL_ID", "String", 255)]
        return []


class SourceTextFieldLengthTests(unittest.TestCase):
    def test_uses_matching_source_text_field_length(self):
        self.assertEqual(
            _source_text_field_length(_ArcPy, "levels", "LEVEL_ID", default=64),
            255,
        )

    def test_uses_default_when_source_field_is_absent(self):
        self.assertEqual(
            _source_text_field_length(_ArcPy, "facilities", "SITE_ID", default=64),
            64,
        )


if __name__ == "__main__":
    unittest.main()