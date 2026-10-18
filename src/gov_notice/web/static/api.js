// fetch 래퍼. 에러나면 그냥 alert 띄우고 던짐 — 별도 에러 핸들링 계층 안 둠.

async function apiGet(url) {
  const res = await fetch(url);
  if (!res.ok) { alert('요청 실패: ' + url); throw new Error(res.status); }
  return res.json();
}

async function apiPost(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) { alert('요청 실패: ' + url); throw new Error(res.status); }
  return res.json();
}

async function apiPut(url, body) {
  const res = await fetch(url, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) { alert('요청 실패: ' + url); throw new Error(res.status); }
  return res.json();
}

async function apiDelete(url) {
  const res = await fetch(url, { method: 'DELETE' });
  if (!res.ok) { alert('요청 실패: ' + url); throw new Error(res.status); }
  return res.json();
}
