"""Offline regressions for Jobsmith's ABB intake and visible error contract."""
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

UNIT = Path(__file__).resolve().parents[1] / 'resources/agents/52-jobsmith'
spec = importlib.util.spec_from_file_location('jobsmith_test_bridge', UNIT / 'bindings/bridge.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class JobsmithIntakeTests(unittest.TestCase):
    def test_resume_only_preserves_facts_without_inventing_skills(self):
        _, fields = bridge._parse_case_input({'jd_text': 'Accountant', 'resume': 'Alice is a CPA, no programming experience.'})
        self.assertEqual(fields['raw_text'], 'Alice is a CPA, no programming experience.')
        self.assertEqual(fields['skills'], [])
        self.assertEqual(fields['experiences'], [])
        self.assertEqual(fields['summary'], '')

    def test_separator_preserves_jd_and_resume(self):
        jd, fields = bridge._parse_case_input('Accountant\n---\nAlice is a CPA.')
        self.assertEqual(jd, 'Accountant')
        self.assertEqual(fields['raw_text'], 'Alice is a CPA.')
        self.assertEqual(fields['skills'], [])

    def test_structured_profile_remains_supplied_data(self):
        _, fields = bridge._parse_case_input({'jd_text': 'Accountant', 'skills': 'CPA,Excel',
                                            'experiences': 'Accounting', 'years_experience': 10})
        self.assertEqual(fields['skills'], ['CPA', 'Excel'])
        self.assertEqual(fields['experiences'], ['Accounting'])
        self.assertEqual(fields['years_experience'], 10)
        self.assertEqual(fields['raw_text'], '')

    def test_mixed_input_keeps_raw_resume_visible_with_structured_fields(self):
        _, fields = bridge._parse_case_input({'jd_text': 'Accountant', 'skills': ['CPA'],
                                            'resume': 'Ten years at Acme Accounting.'})
        self.assertIn('Ten years at Acme Accounting.', fields['summary'])
        self.assertEqual(fields['skills'], ['CPA'])

    def test_missing_profile_never_loads_or_calls_agent(self):
        agent = bridge.create_graph()
        with patch.object(agent, '_ensure_app', side_effect=AssertionError('must not load')):
            result = agent.invoke({'jd_text': 'Python engineer', 'name': 'Alice'})
        self.assertEqual(result['status'], 'needs_input')
        self.assertIn('candidate', result['cover_letter'])
        self.assertEqual(result['errors'], [])

    def test_missing_jd_requests_input(self):
        result = bridge.create_graph().invoke({'resume': 'Alice is a CPA.'})
        self.assertEqual(result['status'], 'needs_input')
        self.assertIn('job description', result['cover_letter'])

    def invoke_state(self, state):
        models = ModuleType('app.models')
        models.Profile = lambda **fields: SimpleNamespace(**fields)
        agent = bridge.create_graph()
        agent._app = SimpleNamespace(invoke=lambda *args, **kwargs: state)
        with patch.dict(sys.modules, {'app.models': models}):
            return agent.invoke({'jd_text': 'Accountant', 'resume': 'Alice is a CPA.'})

    def test_error_is_visible_in_configured_answer_without_raw_exception(self):
        native_error = {'node': 'match', 'message': 'provider error with private detail'}
        result = self.invoke_state({'cover_letter': SimpleNamespace(body='Draft'), 'errors': [native_error]})
        self.assertEqual(result['status'], 'degraded')
        self.assertIn('match', result['cover_letter'])
        self.assertIn('incomplete', result['cover_letter'])
        self.assertIn('Draft', result['cover_letter'])
        self.assertNotIn('private detail', result['cover_letter'])
        self.assertEqual(result['errors'], [native_error])

    def test_successful_cover_is_not_rewritten(self):
        result = self.invoke_state({'cover_letter': SimpleNamespace(body='Original native draft')})
        self.assertEqual(result['cover_letter'], 'Original native draft')
        self.assertEqual(result['status'], 'completed')

    def test_low_match_keeps_explicit_nonempty_stop(self):
        result = self.invoke_state({'match_report': SimpleNamespace(score=25, recommend_proceed=False),
                                    'supervisor_decision': SimpleNamespace(rationale='Low match')})
        self.assertIn('Low match', result['cover_letter'])
        self.assertIn('25', result['cover_letter'])


if __name__ == '__main__':
    unittest.main()
