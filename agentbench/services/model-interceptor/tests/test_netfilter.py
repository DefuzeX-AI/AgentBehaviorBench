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


if __name__ == "__main__":
    unittest.main()
