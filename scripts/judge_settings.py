"""Local judge configuration. Keys are isolated from candidate credentials."""
import datetime
import json
import os
import threading
from pathlib import Path
from model_discovery import discover, ID

PROVIDERS = {'openai':'codex', 'anthropic':'claude'}


class JudgeSettings:
    def __init__(self, folder, vault):
        self.path = Path(folder) / 'judge-settings.json'
        self.vault = vault
        self.lock = threading.RLock()

    def provider(self, value):
        if value not in PROVIDERS:
            raise ValueError('Choose a supported judge provider.')
        return value

    def status(self, provider=None):
        config = json.loads(self.path.read_text()) if self.path.exists() else {'provider':'openai','model':''}
        chosen = self.provider(provider or config['provider'])
        try:
            configured = bool(self.vault().get_password('basis-judge', chosen))
        except Exception:
            raise RuntimeError('Unlock the OS credential store to configure the judge.') from None
        return {'provider':chosen, 'model':config.get('model','') if config['provider']==chosen else '',
                'configured':configured, 'savedAt':config.get('savedAt') if config['provider']==chosen else None}

    def models(self, provider, key=None):
        with self.lock:
            return self._models(provider,key)

    def _models(self, provider, key=None):
        provider = self.provider(provider)
        if key is not None and (not isinstance(key,str) or not 8 <= len(key) <= 8000 or any(c in key for c in '\r\n\x00')):
            raise ValueError('Enter a valid single-line judge API key.')
        try:
            store = self.vault()
            secret = key if key is not None else store.get_password('basis-judge',provider)
        except Exception:
            raise RuntimeError('Unlock the OS credential store to configure the judge.') from None
        if not secret:
            raise ValueError('Enter the judge API key first.')
        class JudgeVault:
            def get_password(self, *_): return secret
        catalog = discover(PROVIDERS[provider], provider, JudgeVault())
        if key is not None:
            try: store.set_password('basis-judge',provider,secret)
            except Exception: raise RuntimeError('Could not save the judge key in the OS credential store.') from None
        return {**catalog, 'configured':True, 'provider':provider}

    def save(self, provider, model):
        with self.lock:
            provider = self.provider(provider)
            if not isinstance(model,str) or not ID.fullmatch(model):
                raise ValueError('Select a fetched judge model.')
            catalog = self.models(provider)
            if model not in {row['id'] for row in catalog['models']}:
                raise ValueError('This model is not available to the saved judge credential. Refresh the model list.')
            config = {'provider':provider,'model':model,'savedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                      'catalogSource':catalog['source'],'catalogFetchedAt':catalog['fetchedAt']}
            self.path.parent.mkdir(parents=True,exist_ok=True)
            tmp=self.path.with_suffix('.tmp')
            with open(os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600),'w') as stream: json.dump(config,stream)
            tmp.replace(self.path)
            return self.status(provider)
