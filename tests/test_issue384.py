"""Self-contained regression fixtures for output argument wiring and model budgets."""
import asyncio
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BINDING = Path(os.environ.get('TSCI_TEST_BINDING', ROOT / 'resources/agents/50-timeseriesscientist/bindings/tsci_workflow.py'))

class SDKClient:
    def __init__(self, timeout=600, max_retries=2):
        self.timeout = timeout
        self.max_retries = max_retries
        self.chat = types.SimpleNamespace(completions=object())
    def with_options(self, **options):
        return SDKClient(**options)

class Client:
    def __init__(self):
        self.max_tokens = None
        self.max_retries = 2
        self.request_timeout = None
        self.extra_body = None
        self.calls = 0
        self.root_client = SDKClient()
        self.root_async_client = SDKClient()
    def with_structured_output(self, *args, **kwargs):
        return self
    def invoke(self, messages, *args, **kwargs):
        self.calls += 1
        return 'real-client-fixture-result'

class Preprocess:
    def __init__(self):
        self.llm = Client()
        self.tools = types.SimpleNamespace(llm=self.llm)
        self.output_dir = None
    def run(self, data, output_dir=None):
        path = Path(output_dir)
        path.mkdir(parents=True, exist_ok=True)
        self.output_dir = str(path)
        return {'cleaned_data': data}

class Forecast:
    def __init__(self):
        self.llm = Client()
        self.arguments = None
    def run(self, selected_models, best_hyperparameters, validation_data, test_data,
            output_dir=None, validation_metrics=None):
        self.arguments = dict(validation_data=validation_data, test_data=test_data,
                              output_dir=output_dir, validation_metrics=validation_metrics)
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        return {'ensemble_predictions': [1.0]}

class Native:
    def __init__(self, config, model, debug):
        self.config = config
        self.preprocess_agent = Preprocess()
        self.forecast_agent = Forecast()
        for name in ('analysis_agent', 'validation_agent', 'report_agent'):
            setattr(self, name, types.SimpleNamespace(llm=Client()))
    # These argument calls reproduce the inspected native orchestration defects.
    def _preprocess_node(self, state):
        result = self.preprocess_agent.run(state['validation_data'])
        state['preprocessed_data'] = result.get('cleaned_data', state['validation_data'])
        state['preprocess_result'] = result
        return state
    def _forecast_node(self, state):
        state['forecast_result'] = self.forecast_agent.run(
            state['selected_models'], state['best_hyperparameters'], state['test_data'])
        return state

class Issue384(unittest.TestCase):
    def setUp(self):
        fake = types.ModuleType('graph.agent_graph')
        fake.TimeSeriesAgentGraph = Native
        self.modules = patch.dict(sys.modules, {'graph.agent_graph': fake})
        self.modules.start()
        self.env = patch.dict(os.environ, {'TSCI_MODEL_OUTPUT_LIMIT': '1024',
                                         'TSCI_MODEL_MAX_CALLS': '3',
                                         'TSCI_REASONING_EFFORT': 'low'})
        self.env.start()
        spec = importlib.util.spec_from_file_location('issue384_binding', BINDING)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.directory = tempfile.TemporaryDirectory()
        self.workflow = self.module.create_graph()
        self.native = self.workflow._load_native({'output_dir': self.directory.name,
                                                  'llm_model': 'test-fixture', 'debug': False})
    def tearDown(self):
        self.workflow.close()
        self.directory.cleanup()
        self.env.stop()
        self.modules.stop()
    def test_preprocess_receives_writable_output_directory(self):
        data = object()
        state = self.native._preprocess_node({'validation_data': data})
        self.assertIs(state['preprocessed_data'], data)
        self.assertEqual(self.native.preprocess_agent.output_dir, self.directory.name)
    def test_forecast_receives_both_datasets_and_directory(self):
        validation, test = object(), object()
        state = {'selected_models': ['RandomWalk'], 'best_hyperparameters': {},
                 'preprocessed_data': validation, 'test_data': test,
                 'model_validation_scores': {'RandomWalk': 1.0}}
        result = self.native._forecast_node(state)
        args = self.native.forecast_agent.arguments
        self.assertIs(args['validation_data'], validation)
        self.assertIs(args['test_data'], test)
        self.assertEqual(args['output_dir'], self.directory.name)
        self.assertEqual(result['forecast_result'], {'ensemble_predictions': [1.0]})
    def test_reconfiguring_native_graph_does_not_reset_case_call_budget(self):
        self.native.preprocess_agent.llm.invoke(['fixture'])
        first_budget = self.workflow._model_budget
        newer = dict(self.workflow._native_config, horizon=6)
        reloaded = self.workflow._load_native(newer)
        self.assertIs(self.workflow._model_budget, first_budget)
        self.assertEqual(first_budget.used, 1)
        reloaded.analysis_agent.llm.invoke(['fixture'])
        reloaded.forecast_agent.llm.invoke(['fixture'])
        with self.assertRaisesRegex(RuntimeError, 'budget exceeded'):
            reloaded.report_agent.llm.invoke(['blocked fixture'])

    def test_input_contract_rejects_bad_types_fields_duplicates_and_ranges(self):
        invalid = [None, [], '', '{bad json', '{"horizon": true}',
                   '{"horizon": 0}', '{"horizon": 10001}',
                   '{"horizon": 6, "horizon": 7}', '{"output_dir": "/tmp/other"}',
                   {'request': '{"horizon":6}', 'horizon': 7},
                   'horizon: 6\nThis is not an option line']
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.module.request_from_input(value)

    def test_numeric_overrides_and_plain_text_are_preserved(self):
        text, overrides = self.module.request_from_input(
            {'request': '{"num_slices":1,"input_length":160,"horizon":6,"k_models":1}'})
        self.assertEqual(overrides, {'num_slices':1,'input_length':160,'horizon':6,'k_models':1})
        self.assertIn('horizon', text)
        self.assertEqual(self.module.request_from_input('Run the forecasting workflow'),
                         ('Run the forecasting workflow', {}))

    def test_explicit_case_parameters_override_deployment_defaults(self):
        fake = types.ModuleType('config.default_config')
        fake.DEFAULT_CONFIG = {'llm_model':'fixture','debug':False,'num_slices':10,
                               'input_length':512,'horizon':96,'k_models':3}
        with patch.dict(sys.modules, {'config.default_config': fake}), \
             patch.dict(os.environ, {'OPENAI_API_KEY':'fixture', 'TSCI_DEPLOY_HORIZON':'12',
                                     'TSCI_DEPLOY_INPUT_LENGTH':'128'}), \
             patch.object(self.module, '_resolve_data_path', return_value='/fixture.csv'):
            config = self.workflow._build_config({'horizon':6,'input_length':160})
        self.assertEqual(config['horizon'],6)
        self.assertEqual(config['input_length'],160)
        self.assertNotEqual(config['output_dir'], '/tmp/other')
        self.assertEqual(fake.DEFAULT_CONFIG['horizon'],96)

    def _config_fixture(self, deployment=None, overrides=None):
        fake = types.ModuleType('config.default_config')
        fake.DEFAULT_CONFIG = {'llm_model':'fixture','debug':False,'num_slices':10,
                               'input_length':512,'horizon':96,'k_models':3}
        # Isolate deployment controls from the invoking shell.
        env = {k:v for k,v in os.environ.items() if not k.startswith('TSCI_DEPLOY_')}
        env.update({'OPENAI_API_KEY':'fixture', **(deployment or {})})
        with patch.dict(sys.modules, {'config.default_config': fake}), \
             patch.dict(os.environ, env, clear=True), \
             patch.object(self.module, '_resolve_data_path', return_value='/fixture.csv'):
            config = self.workflow._build_config(overrides or {})
        self.assertEqual(fake.DEFAULT_CONFIG['num_slices'],10)
        return config

    def test_default_workflow_uses_one_slice_and_preserves_other_native_defaults(self):
        config = self._config_fixture()
        self.assertEqual(config['num_slices'],1)
        self.assertEqual((config['input_length'],config['horizon'],config['k_models']),
                         (512,96,3))

    def test_deployment_slice_count_overrides_bounded_default(self):
        self.assertEqual(self._config_fixture({'TSCI_DEPLOY_NUM_SLICES':'2'})['num_slices'],2)
        with self.assertRaises(ValueError):
            self._config_fixture({'TSCI_DEPLOY_NUM_SLICES':'0'})

    def test_case_slice_count_wins_over_deployment_and_bounded_defaults(self):
        self.assertEqual(self._config_fixture(overrides={'num_slices':4})['num_slices'],4)
        self.assertEqual(self._config_fixture({'TSCI_DEPLOY_NUM_SLICES':'2'},
                                             {'num_slices':4})['num_slices'],4)

    def test_unused_credential_snapshot_is_not_forwarded_to_model_facing_config(self):
        fake=types.ModuleType('config.default_config')
        snapshot={'OPENAI_API_KEY':'offline-fixture-key','GOOGLE_API_KEY':None}
        fake.DEFAULT_CONFIG={'llm_model':'fixture','debug':False,'num_slices':10,
                             'input_length':512,'horizon':96,'k_models':3,
                             'env_vars':snapshot}
        with patch.dict(sys.modules,{'config.default_config':fake}), \
             patch.dict(os.environ,{'OPENAI_API_KEY':'offline-fixture-key'}), \
             patch.object(self.module,'_resolve_data_path',return_value='/fixture.csv'):
            config=self.workflow._build_config({})
            self.assertEqual(os.environ['OPENAI_API_KEY'],'offline-fixture-key')
        self.assertNotIn('env_vars',config)
        self.assertIs(fake.DEFAULT_CONFIG['env_vars'],snapshot)

    def test_closed_workflow_rejects_later_invocation(self):
        self.workflow.close()
        with self.assertRaisesRegex(RuntimeError, 'closed'):
            self.workflow.invoke('Run the forecasting workflow')

    def test_direct_truncated_output_is_rejected_and_recorded(self):
        llm = self.native.analysis_agent.llm
        response = types.SimpleNamespace(content='incomplete text', response_metadata={'finish_reason':'length'})
        with patch.object(llm.client, 'invoke', return_value=response):
            with self.assertRaisesRegex(RuntimeError, 'output truncated'):
                llm.invoke(['fixture'])
        self.assertTrue(self.workflow._model_budget.truncated)
        self.assertEqual(self.workflow._model_budget.used, 1)

    def test_truncation_stops_later_calls_without_spending(self):
        llm=self.native.analysis_agent.llm
        response=types.SimpleNamespace(response_metadata={'finish_reason':'length'})
        with patch.object(llm.client, 'invoke', return_value=response):
            with self.assertRaisesRegex(RuntimeError, 'output truncated'):
                llm.invoke(['fixture'])
        with self.assertRaisesRegex(RuntimeError, 'further calls rejected'):
            self.native.report_agent.llm.invoke(['must not call'])
        self.assertEqual(self.native.report_agent.llm.client.calls, 0)
        self.assertEqual(self.workflow._model_budget.used, 1)

    def test_async_truncated_output_is_rejected(self):
        llm = self.native.analysis_agent.llm
        async def answer(*args, **kwargs):
            return types.SimpleNamespace(response_metadata={'finish_reason':'length'})
        with patch.object(llm.client, 'ainvoke', answer, create=True):
            with self.assertRaisesRegex(RuntimeError, 'output truncated'):
                asyncio.run(llm.ainvoke(['fixture']))
        self.assertTrue(self.workflow._model_budget.truncated)

    def _structured_fixture(self, raw_reason='stop', parsed=None, error=None):
        llm = self.native.validation_agent.llm
        raw = types.SimpleNamespace(content='fixture', response_metadata={'finish_reason':raw_reason})
        runnable = types.SimpleNamespace(invoke=lambda *args, **kwargs:
                                         {'raw':raw, 'parsed':parsed, 'parsing_error':error})
        return llm, runnable

    def test_structured_truncation_is_visible_before_parsed_result(self):
        llm, runnable = self._structured_fixture('length', {'model':'fixture'})
        with patch.object(llm.client, 'with_structured_output', return_value=runnable) as make:
            structured = llm.with_structured_output(dict)
            self.assertTrue(make.call_args.kwargs['include_raw'])
            with self.assertRaisesRegex(RuntimeError, 'output truncated'):
                structured.invoke(['fixture'])
        self.assertTrue(self.workflow._model_budget.truncated)

    def test_structured_success_preserves_parsed_return_contract(self):
        parsed = object();llm, runnable = self._structured_fixture(parsed=parsed)
        with patch.object(llm.client, 'with_structured_output', return_value=runnable):
            self.assertIs(llm.with_structured_output(dict).invoke(['fixture']), parsed)

    def test_structured_default_uses_function_calling_without_changing_schema_or_budget(self):
        schema=object();parsed=object();llm,runnable=self._structured_fixture(parsed=parsed)
        with patch.object(llm.client,'with_structured_output',return_value=runnable) as make:
            structured=llm.with_structured_output(schema)
            self.assertEqual(make.call_args.args,(schema,))
            self.assertEqual(make.call_args.kwargs,
                             {'method':'function_calling','include_raw':True})
            self.assertIs(structured.budget,llm.budget)
            self.assertIs(structured.invoke(['fixture']),parsed)
            self.assertEqual(llm.budget.used,1)

    def test_explicit_structured_method_is_preserved(self):
        llm,runnable=self._structured_fixture(parsed={'model':'fixture'})
        with patch.object(llm.client,'with_structured_output',return_value=runnable) as make:
            llm.with_structured_output(dict,method='json_schema',strict=True)
            self.assertEqual(make.call_args.kwargs['method'],'json_schema')
            self.assertTrue(make.call_args.kwargs['strict'])

    def test_explicit_structured_raw_contract_is_preserved(self):
        error=ValueError('fixture parse error');llm, runnable = self._structured_fixture(error=error)
        with patch.object(llm.client, 'with_structured_output', return_value=runnable):
            result=llm.with_structured_output(dict, include_raw=True).invoke(['fixture'])
        self.assertIs(result['parsing_error'], error)

    def test_structured_parse_error_propagates_without_repair_call(self):
        error=ValueError('fixture parse error');llm, runnable=self._structured_fixture(error=error)
        with patch.object(llm.client, 'with_structured_output', return_value=runnable):
            with self.assertRaises(ValueError) as caught:
                llm.with_structured_output(dict).invoke(['fixture'])
        self.assertIs(caught.exception, error)
        self.assertEqual(self.workflow._model_budget.used, 1)

    def test_native_catch_does_not_turn_truncation_into_success(self):
        llm=self.native.analysis_agent.llm
        response=types.SimpleNamespace(response_metadata={'finish_reason':'length'})
        def native_run():
            try:
                llm.invoke(['fixture'])
            except RuntimeError:
                pass  # reproduce upstream fallback/catch behavior
            return {'aggregated_results':{'fixture':'nonempty'}}
        with patch.object(llm.client, 'invoke', return_value=response), \
             patch.object(self.workflow, '_build_config', return_value=self.workflow._native_config), \
             patch.object(self.native, 'run', native_run, create=True):
            with self.assertRaisesRegex(RuntimeError, 'output truncated'):
                self.workflow.invoke('Run forecasting')

    def test_output_limit_uses_non_secret_deployment_variable(self):
        with patch.dict(os.environ, {'TSCI_MODEL_OUTPUT_LIMIT':'1777'}):
            cfg=dict(self.workflow._native_config,horizon=6)
            native=self.workflow._load_native(cfg)
            self.assertEqual(native.analysis_agent.llm.max_tokens,1777)

    def test_manifest_pins_git_source_and_keeps_numeric_limit_public(self):
        import tomllib
        manifest=tomllib.loads((ROOT/'resources/agents/50-timeseriesscientist/agent.toml').read_text())
        self.assertEqual(manifest['source']['method'],'git')
        self.assertEqual(len(manifest['source']['revision']),40)
        self.assertIn('TSCI_MODEL_OUTPUT_LIMIT',manifest['runtime']['env_keys'])
        self.assertNotIn('TSCI_MODEL_OUTPUT_LIMIT',manifest['runtime'].get('secret_env_keys',[]))

    def test_input_budget_blocks_before_client_call(self):
        llm = self.native.preprocess_agent.llm
        with self.assertRaisesRegex(RuntimeError, 'input budget exceeded'):
            llm.invoke(['x' * 60001])
        self.assertEqual(llm.client.calls, 0)

    def test_invalid_deployment_budget_is_rejected(self):
        with patch.dict(os.environ, {'TSCI_MODEL_MAX_CALLS': '101'}):
            with self.assertRaises(ValueError):
                self.module._deployment_int('TSCI_MODEL_MAX_CALLS', 24, 1, 100)

    def test_structured_output_cannot_bypass_shared_budget(self):
        llm = self.native.validation_agent.llm
        structured = llm.with_structured_output(dict)
        budget = self.workflow._model_budget
        budget.used = budget.maximum
        with self.assertRaisesRegex(RuntimeError, 'budget exceeded'):
            structured.invoke(['fixture'])
        self.assertEqual(llm.client.calls, 0)

    def test_all_model_clients_share_budget_and_actual_request_limits(self):
        llm = self.native.preprocess_agent.llm
        self.assertEqual(llm.max_tokens, 1024)
        self.assertEqual(llm.max_retries, 0)
        self.assertEqual(llm.root_client.max_retries, 0)
        self.assertEqual(llm.root_async_client.max_retries, 0)
        self.assertEqual(llm.root_client.timeout, 60)
        self.assertEqual(llm.root_async_client.timeout, 60)
        self.assertEqual(llm.extra_body['reasoning_effort'], 'low')
        self.assertIs(self.native.preprocess_agent.tools.llm, llm)
        for name in ('preprocess_agent', 'analysis_agent', 'forecast_agent'):
            self.assertEqual(getattr(self.native, name).llm.invoke(['tiny fixture']),
                             'real-client-fixture-result')
        with self.assertRaisesRegex(RuntimeError, 'budget exceeded'):
            self.native.report_agent.llm.invoke(['another fixture'])
        self.assertTrue(self.workflow._model_budget.exhausted)

if __name__ == '__main__':
    unittest.main()
