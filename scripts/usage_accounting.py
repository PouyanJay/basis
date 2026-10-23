"""Allowlisted CLI telemetry, never reconstructed billing or token estimates.

Claude: https://code.claude.com/docs/en/agent-sdk/cost-tracking
Codex: https://learn.chatgpt.com/docs/non-interactive-mode
Input tokens here EXCLUDE cache reads/writes; output includes reasoning where reported.
"""
from decimal import Decimal
import math

FIELDS = ('inputTokens', 'outputTokens', 'cacheReadTokens', 'cacheWriteTokens')


def number(value, integer=False):
    if type(value) not in (int, float) or value < 0 or value > 2**53 - 1 or not math.isfinite(value):
        return None
    if integer and (not float(value).is_integer() or value > 2**53 - 1):
        return None
    return int(value) if integer else value


def add(values):
    values = list(values)
    return float(sum((Decimal(str(v)) for v in values), Decimal(0)))


def aggregate(records):
    """Return recorded subtotals AND coverage; unknown is never silently zero."""
    result = {'attempts': len(records)}
    for field in (*FIELDS, 'estimatedCostUsd'):
        measured = [r for r in records if number(r.get(field), field != 'estimatedCostUsd') is not None]
        values = [r[field] for r in measured]
        complete = sum(r.get('tokenStatus' if field != 'estimatedCostUsd' else 'costStatus') == 'complete' for r in measured)
        result[field] = {'value': (add(values) if field == 'estimatedCostUsd' else sum(values)) if values else None,
                         'recorded': len(values), 'complete': complete, 'total': len(records)}
    return result


def summaries(job):
    results = list(job.get('results', []))
    active = job.get('activeUsage')
    if active and not any(r.get('candidateId') == active.get('candidateId') and r.get('taskIndex') == active.get('taskIndex') for r in results):
        results.append(active)
    candidate = lambda r: r.get('candidateId', r.get('agent', r.get('id')))
    # Candidate and judge ledgers never share a denominator or cost total.
    return {'candidates': aggregate([r.get('usage') or {} for r in results]),
            'models': {candidate(p): aggregate([r.get('usage') or {} for r in results if candidate(r) == candidate(p)])
                       for p in job.get('plan', {}).get('services', [])},
            'judge': aggregate([r.get('usage') or {} for r in job.get('judgeRuns', [])])}


class UsageTracker:
    def __init__(self, agent):
        self.agent = agent
        self.messages = {}
        self.final = None
        self.models = {}
        self.cost = None
        self.turn = 0
        self.turns = {}
        self.dropped = False
        self.version = None

    @staticmethod
    def claude_tokens(value, model=False):
        names = ('inputTokens','outputTokens','cacheReadInputTokens','cacheCreationInputTokens') if model else ('input_tokens','output_tokens','cache_read_input_tokens','cache_creation_input_tokens')
        return {field: number(value.get(name), True) for field, name in zip(FIELDS, names)}

    def consume(self, event):
        if not isinstance(event, dict):
            return
        kind = event.get('type')
        if self.agent == 'claude' and kind == 'system' and event.get('subtype') == 'init' and isinstance(event.get('claude_code_version'), str):
            self.version = event['claude_code_version'][:100]
        if self.agent == 'claude':
            if kind == 'assistant':
                message = event.get('message') or {}
                if isinstance(message, dict) and isinstance(message.get('usage'), dict) and isinstance(message.get('id'), str):
                    row = self.claude_tokens(message['usage'])
                    # Per-step output is a placeholder, not a measured output total.
                    row['outputTokens'] = None
                    previous = self.messages.get(message['id'], {})
                    self.messages[message['id']] = {f: max(v for v in (previous.get(f), row[f]) if v is not None) if any(v is not None for v in (previous.get(f),row[f])) else None for f in FIELDS}
            elif kind == 'result':
                models = event.get('modelUsage')
                if isinstance(models, dict) and models:
                    parsed = {name: {**self.claude_tokens(v, True), 'estimatedCostUsd':number(v.get('costUSD'))} for name,v in models.items() if isinstance(name,str) and isinstance(v,dict)}
                    if parsed:
                        self.models = parsed
                        self.final = {f: sum(r[f] for r in parsed.values()) if all(r[f] is not None for r in parsed.values()) else None for f in FIELDS}
                elif isinstance(event.get('usage'), dict):
                    self.final = self.claude_tokens(event['usage'])
                    self.models = {} # Main loop only; cannot claim whole-tree coverage.
                self.cost = number(event.get('total_cost_usd'))
                # Some crash results zero telemetry. Preserve observed input as partial.
                if event.get('subtype') == 'error_during_execution' and self.cost == 0 and self.messages:
                    self.final = None
                    self.models = {}
                    self.cost = None
        elif self.agent == 'codex':
            if kind == 'turn.started':
                self.turn += 1
            elif kind == 'turn.completed' and isinstance(event.get('usage'), dict):
                usage = event['usage']
                total = number(usage.get('input_tokens'), True)
                cached = number(usage.get('cached_input_tokens'), True)
                write = number(usage.get('cache_write_input_tokens'), True)
                # Codex input includes cached tokens; do not add cache a second time.
                self.turns[self.turn] = {'inputTokens': total-cached-(write or 0) if total is not None and cached is not None and total >= cached+(write or 0) else None,
                                        'outputTokens': number(usage.get('output_tokens'),True),
                                        'cacheReadTokens': cached, 'cacheWriteTokens': write}
        elif self.agent == 'opencode' and kind == 'step_finish':
            part = event.get('part') or {}
            tokens = part.get('tokens') or {}
            if isinstance(part.get('id'), str) and isinstance(tokens,dict):
                cache = tokens.get('cache') or {}
                output = number(tokens.get('output'),True)
                reasoning = number(tokens.get('reasoning'),True)
                self.messages[part['id']] = {'inputTokens': number(tokens.get('input'),True),
                                             'outputTokens': output+reasoning if output is not None and reasoning is not None else None,
                                             'cacheReadTokens': number(cache.get('read'),True),
                                             'cacheWriteTokens': number(cache.get('write'),True),
                                             'estimatedCostUsd': number(part.get('cost'))}

    def snapshot(self, finished=False):
        rows = list((self.turns if self.agent == 'codex' else self.messages).values())
        tokens = self.final or {f: sum(r[f] for r in rows) if rows and all(r.get(f) is not None for r in rows) else None for f in FIELDS}
        cost = self.cost
        if self.agent == 'opencode' and rows and all(r.get('estimatedCostUsd') is not None for r in rows):
            cost = add(r['estimatedCostUsd'] for r in rows)
        # A zero client price for consumed tokens may mean the model has no known pricing.
        if cost == 0 and any(v for v in tokens.values() if v is not None):
            cost = None
        complete = not self.dropped and (bool(self.models) if self.agent == 'claude' else self.agent == 'codex' and finished and bool(rows))
        return {'schemaVersion':1, **tokens, 'estimatedCostUsd':cost,
                'tokenStatus':'complete' if complete else 'partial' if any(v is not None for v in tokens.values()) else 'unavailable',
                'costStatus': ('complete' if not self.dropped and self.agent != 'opencode' and (self.final is not None or finished) else 'partial') if cost is not None else 'unavailable',
                'source': self.agent + '-cli', 'cliVersion':self.version, 'costSource': 'cli-estimate' if cost is not None else None,
                'modelUsage': self.models,
                'scope': 'agent-and-subagents' if self.models else 'reported-turns' if self.agent == 'codex' else 'observed-steps',
                'note': 'CLI estimates are not invoices. Missing fields are not zero. Interrupted streams may omit billed usage.'}
