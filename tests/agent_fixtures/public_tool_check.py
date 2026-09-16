"""Probe one real public data lookup; never call Kuma or an LLM."""
import json
import sys
sys.path.insert(0, '/opt/agent/agent')
agent_id = sys.argv[1]
if agent_id == 'trading-agents':
    from tradingagents.dataflows.y_finance import get_YFin_data_online
    result = get_YFin_data_online('AAPL', '2026-09-01', '2026-09-11')
    assert isinstance(result, str) and '2026-09-' in result, str(result)[:500]
    evidence = {'characters': len(result), 'has_requested_dates': True}
else:
    from gpt_researcher.retrievers.pubmed_central.pubmed_central import PubMedCentralSearch
    result = PubMedCentralSearch('retrieval augmented generation').search(max_results=1)
    assert result and result[0]['raw_content'], 'Native PMC search returned no article full text'
    evidence = {'results': len(result), 'source': result[0]['href'],
                'body_characters': len(result[0]['raw_content'])}
print(json.dumps({'agent_id':agent_id, 'probe':'native-public-tool', 'status':'passed',
                  'model_requests':0,'case_generation_requests':0,'judge_requests':0,**evidence}))
