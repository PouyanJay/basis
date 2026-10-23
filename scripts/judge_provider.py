"""Bounded, non-retrying judge API calls. No tools execute; only structured reports."""
import json
import urllib.error
import urllib.request
from decimal import Decimal
from usage_accounting import number, FIELDS

# Standard global API list prices per million tokens, checked 2026-10-22.
# Exact IDs only; unknown IDs/tier/context pricing stay unavailable.
PRICES = {
    'openai': {'gpt-6-astra': (10, 50, 1), 'gpt-6.1-sol': (2, 10, .1), 'gpt-6-luna': (.1, .5, .01)},
    'anthropic': {'claude-sonnet-4-6': (3, 15, .3), 'claude-opus-4-6': (5, 25, .5),
                  'claude-sonnet-5-5': (2, 10, .1), 'claude-opus-5-5': (4, 20, .2)}
}
SOURCES = {'openai':'https://developers.openai.com/api/docs/pricing',
           'anthropic':'https://platform.claude.com/docs/en/about-claude/pricing'}


def usage(provider, model, response):
    raw = response.get('usage') or {}
    total = number(raw.get('input_tokens'), True)
    cached = number((raw.get('input_tokens_details') or {}).get('cached_tokens'), True) if provider == 'openai' else number(raw.get('cache_read_input_tokens', 0), True)
    write = number((raw.get('input_tokens_details') or {}).get('cache_creation_tokens', 0), True) if provider == 'openai' else number(raw.get('cache_creation_input_tokens', 0), True)
    inp = (total-cached-write if all(v is not None for v in (total,cached,write)) and total >= cached+write else None) if provider == 'openai' else total
    row = {'inputTokens':inp, 'outputTokens':number(raw.get('output_tokens'),True), 'cacheReadTokens':cached if raw else None,
           'cacheWriteTokens':write if raw else None, 'estimatedCostUsd':None, 'source':provider+'-api', 'costStatus':'unavailable'}
    row['tokenStatus'] = 'complete' if all(row[k] is not None for k in FIELDS) else 'partial' if any(row[k] is not None for k in FIELDS) else 'unavailable'
    rate = PRICES[provider].get(model)
    # Do not guess cache-write duration, long-context premiums, or nonstandard tiers.
    if rate and row['tokenStatus']=='complete' and write == 0 and (total or 0)+(cached or 0) <= 100_000 and response.get('service_tier','default') in ('default','standard',None):
        row['estimatedCostUsd'] = float(sum(Decimal(str(n))*Decimal(str(r)) for n,r in zip((inp,row['outputTokens'],cached),rate))/Decimal(1_000_000))
        row['costStatus'] = 'complete'
        row['costSource'] = 'versioned-list-price'
        row['pricing'] = {'checkedAt':'2026-10-22','source':SOURCES[provider],'usdPerMillion':dict(zip(('input','output','cacheRead'),rate)), 'tier':'standard','model':model}
    else:
        row['note'] = 'No verified price for this model, tier, context length, or cache-write duration. Cost is unknown.'
    return row


class ProviderError(RuntimeError):
    pass


def request(provider, model, key, instructions, evidence, schema):
    content = json.dumps(evidence, ensure_ascii=False)
    if provider == 'openai':
        url = 'https://api.openai.com/v1/responses'
        headers = {'Authorization':'Bearer '+key}
        body = {'model':model,'store':False,'instructions':instructions,'input':content,'max_output_tokens':8000,
                'service_tier':'default','text':{'format':{'type':'json_schema','name':'basis_assessment','strict':True,'schema':schema}}}
    else:
        url = 'https://api.anthropic.com/v1/messages'
        headers = {'x-api-key':key,'anthropic-version':'2023-06-01'}
        body = {'model':model,'max_tokens':8000,'system':instructions,'messages':[{'role':'user','content':content}],
                'tools':[{'name':'report','description':'Return the assessment. This tool only records JSON; it does not execute code.','input_schema':schema}],
                'tool_choice':{'type':'tool','name':'report'}}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={**headers,'Content-Type':'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            data = response.read(2_000_001)
        if len(data)>2_000_000: raise ProviderError('Judge response exceeded the size limit.')
        result = json.loads(data)
        if not isinstance(result,dict): raise ProviderError('The judge returned an invalid response.')
        return result
    except urllib.error.HTTPError as error:
        # Never persist provider bodies: they may echo source text or credentials.
        reasons = {401:'Judge credential was rejected. Update it in Settings.',403:'Judge access was denied.',404:'Judge model is unavailable for this API.',429:'Judge rate limit reached. Wait, then retry.',400:'Judge rejected the request. Check model support or reduce the evidence size.'}
        raise ProviderError(reasons.get(error.code,'Judge provider failed (HTTP '+str(error.code)+'). Retry explicitly.')) from None
    except (OSError, ValueError, urllib.error.URLError):
        raise ProviderError('Judge connection failed or timed out. Usage may have been incurred but was not reported.') from None


def output(provider, response):
    if provider == 'openai':
        if response.get('status') != 'completed': raise ProviderError('Judge response was incomplete. Recorded usage is preserved; retry explicitly.')
        texts = [c['text'] for item in response.get('output',[]) if item.get('type')=='message' for c in item.get('content',[]) if c.get('type')=='output_text']
        try: return json.loads(''.join(texts))
        except (ValueError,TypeError): raise ProviderError('Judge did not return a valid structured assessment.') from None
    if response.get('stop_reason') != 'tool_use': raise ProviderError('Judge response was incomplete or refused. Recorded usage is preserved.')
    reports = [c.get('input') for c in response.get('content',[]) if c.get('type')=='tool_use' and c.get('name')=='report']
    if len(reports)!=1: raise ProviderError('Judge did not return a valid structured assessment.')
    return reports[0]
