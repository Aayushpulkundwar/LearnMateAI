from unittest import TestCase

from scripts.bootstrap_initial_admin import bootstrap_allowed, validated_email


class BootstrapInitialAdminTests(TestCase):
    def test_only_local_and_staging_environments_are_allowed(self):
        self.assertTrue(bootstrap_allowed("development"))
        self.assertTrue(bootstrap_allowed("local"))
        self.assertTrue(bootstrap_allowed("staging"))
        self.assertFalse(bootstrap_allowed("production"))

    def test_email_is_normalized(self):
        self.assertEqual(validated_email(" Admin@Example.COM "), "admin@example.com")
