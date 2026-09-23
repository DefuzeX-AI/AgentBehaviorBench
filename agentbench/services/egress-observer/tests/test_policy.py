"""Allowlist and configuration rules for non-model egress."""
import json
import unittest

from defuzex_egress_observer.config import ObserverConfig, ObserverConfigurationError
from defuzex_egress_observer.policy import AllowList, AllowRule


class AllowRuleTest(unittest.TestCase):
    def test_exact_host_matches_only_itself_on_listed_ports(self):
        rule = AllowRule("pypi.org", (443,))
        self.assertTrue(rule.matches("pypi.org", 443))
        self.assertTrue(rule.matches("PyPI.org.", 443))
        self.assertFalse(rule.matches("pypi.org", 80))
        self.assertFalse(rule.matches("evil-pypi.org", 443))
        self.assertFalse(rule.matches("files.pypi.org", 443))

    def test_wildcard_matches_strict_subdomains_only(self):
        rule = AllowRule("*.debian.org", (80, 443))
        self.assertTrue(rule.matches("deb.debian.org", 80))
        self.assertTrue(rule.matches("a.b.debian.org", 443))
        self.assertFalse(rule.matches("debian.org", 443))
        self.assertFalse(rule.matches("notdebian.org", 443))

    def test_unsafe_patterns_are_rejected(self):
        for host in ("*", "*.", "a*.org", "*.*.org", "host/path", "host:443", ""):
            with self.subTest(host=host), self.assertRaises(ValueError):
                AllowRule(host, (443,))

    def test_first_matching_rule_is_returned(self):
        allow = AllowList((AllowRule("registry.npmjs.org", (443,)), AllowRule("*.npmjs.org", (443,))))
        self.assertEqual(allow.match("registry.npmjs.org", 443).host, "registry.npmjs.org")
        self.assertIsNone(allow.match("example.com", 443))


class ObserverConfigTest(unittest.TestCase):
    def test_valid_configuration(self):
        config = ObserverConfig.from_json(json.dumps(
            {"agent_id": "a", "listen_port": 3128, "allow": [{"host": "pypi.org", "ports": [443]}]}))
        self.assertEqual(config.allow.rules, (AllowRule("pypi.org", (443,)),))

    def test_empty_allowlist_denies_everything(self):
        config = ObserverConfig.from_json(json.dumps({"agent_id": "a"}))
        self.assertIsNone(config.allow.match("pypi.org", 443))

    def test_invalid_configuration_is_rejected(self):
        for data in ({}, {"agent_id": "a", "listen_port": 80}, {"agent_id": "a", "allow": {}},
                     {"agent_id": "a", "allow": [{"host": "*", "ports": [443]}]},
                     {"agent_id": "a", "allow": [{"host": "pypi.org", "ports": []}]}):
            with self.subTest(data=data), self.assertRaises(ObserverConfigurationError):
                ObserverConfig.from_json(json.dumps(data))


if __name__ == "__main__":
    unittest.main()
