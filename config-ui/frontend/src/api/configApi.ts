const API_BASE = '/api';

export const configApi = {
  getConfig: () => fetch(`${API_BASE}/config`).then(r => r.json()),
  getModels: () => fetch(`${API_BASE}/config/models`).then(r => r.json()),
  getModel: (type: string) => fetch(`${API_BASE}/config/models/${type}`).then(r => r.json()),
  updateModel: (type: string, config: any) =>
    fetch(`${API_BASE}/config/models/${type}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config)
    }).then(r => r.json()),
  testModel: (type: string) =>
    fetch(`${API_BASE}/config/models/${type}/test`, { method: 'POST' }).then(r => r.json()),
  getEnvironments: () => fetch(`${API_BASE}/config/environments`).then(r => r.json()),
  activateEnv: (env: string) =>
    fetch(`${API_BASE}/config/environments/${env}/activate`, { method: 'POST' }).then(r => r.json()),
  exportConfig: () => fetch(`${API_BASE}/config/export`, { method: 'POST' }).then(r => r.json()),
  importConfig: (config: any) =>
    fetch(`${API_BASE}/config/import`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config)
    }).then(r => r.json()),
};