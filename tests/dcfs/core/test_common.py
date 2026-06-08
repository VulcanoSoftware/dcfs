
import pytest


class TestValidateName:
    def test_validate_name_valid(self):
        from dcfs.core.model.common import validate_name

        validate_name("valid_name")
        validate_name("valid-name123")
        validate_name("ValidName")

    def test_validate_name_starts_with_dash(self):
        from dcfs.core.model.common import validate_name
        from dcfs.errors import InvalidName

        with pytest.raises(InvalidName):
            validate_name("-invalid")

    def test_validate_name_contains_slash(self):
        from dcfs.core.model.common import validate_name
        from dcfs.errors import InvalidName

        with pytest.raises(InvalidName):
            validate_name("invalid/name")
        with pytest.raises(InvalidName):
            validate_name("path/to/file")
