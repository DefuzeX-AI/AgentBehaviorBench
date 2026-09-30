"""Rule-order regressions for the fail-closed interceptor namespace."""
import unittest
from unittest.mock import patch

from defuzex_model_interceptor.proxy import netfilter


class NetfilterRulesTest(unittest.TestCase):
    def rules(self):
        with patch.object(netfilter.subprocess, "run") as run:
            netfilter.configure_netfilter()
        return [call.args[0] for call in run.call_args_list]

    def test_admitted_connection_replies_precede_the_final_reject(self):
        rules = self.rules()
        output = [rule for rule in rules if rule[:3] == ["iptables", "-A", "OUTPUT"]]
        replies = ["iptables", "-A", "OUTPUT", "-m", "conntrack", "--ctstate", "ESTABLISHED,RELATED", "-j", "ACCEPT"]
        self.assertIn(replies, output)
        self.assertEqual(output[-1], ["iptables", "-A", "OUTPUT", "-j", "REJECT"])
        self.assertLess(output.index(replies), len(output) - 1)

    def test_new_non_root_connections_are_still_redirected_to_the_proxy(self):
        rules = self.rules()
        redirect = [rule for rule in rules if "REDIRECT" in rule]
        self.assertEqual(len(redirect), 1)
        self.assertIn("!", redirect[0])
        self.assertEqual(redirect[0][redirect[0].index("--to-ports") + 1], str(netfilter.PROXY_PORT))

    def test_loopback_exemptions_precede_redirect_and_rejection(self):
        rules = self.rules()
        local_nat = ["iptables", "-t", "nat", "-A", "OUTPUT", "-o", "lo", "-d", "127.0.0.0/8", "-j", "RETURN"]
        redirect = next(rule for rule in rules if "REDIRECT" in rule)
        self.assertLess(rules.index(local_nat), rules.index(redirect))
        for command, destination in (("iptables", "127.0.0.0/8"), ("ip6tables", "::1/128")):
            allow = [command, "-A", "OUTPUT", "-o", "lo", "-d", destination, "-j", "ACCEPT"]
            reject = next(rule for rule in rules if rule[0] == command and "REJECT" in rule)
            self.assertLess(rules.index(allow), rules.index(reject))


if __name__ == "__main__":
    unittest.main()
