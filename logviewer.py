#!/usr/bin/env python3
import os
import socket
import subprocess
import threading
import sys
import json
from datetime import datetime
import re

log_file = sys.argv[1] if len(sys.argv) > 1 else '/var/www/api/nginx-logs/site.access.log'
port = 8080

def parse_log_line(line):
    pattern = r'(\S+) \S+ \S+ \[([^\]]+)\] "(\S+) (\S+) [^"]+" (\d+) (\d+) "([^"]*)" "([^"]*)"'
    match = re.search(pattern, line)
    if match:
        ip, timestamp, method, url, status, size, referer, agent = match.groups()
        try:
            dt = datetime.strptime(timestamp.split(' ')[0], '%d/%b/%Y:%H:%M:%S')
            formatted_time = dt.strftime('%d.%m.%Y %H:%M:%S')
            sort_time = dt.timestamp()
            full_date = dt.strftime('%d.%m.%Y')
            full_time = dt.strftime('%H:%M:%S')
        except:
            formatted_time = timestamp
            sort_time = 0
            full_date = ''
            full_time = ''
        
        url_parts = url.split('?')
        url_path = url_parts[0]
        url_params = url_parts[1] if len(url_parts) > 1 else ''
        
        return {
            'raw': line,
            'ip': ip,
            'timestamp': formatted_time,
            'full_date': full_date,
            'full_time': full_time,
            'sort_time': sort_time,
            'method': method,
            'url': url,
            'url_path': url_path,
            'url_params': url_params,
            'status': int(status),
            'size': size,
            'referer': referer,
            'agent': agent,
            'color': '#ff6b6b;background:#2c1a1a' if int(status) >= 500 else '#ffd93d;background:#2c261a' if int(status) >= 400 else '#6bafff;background:#1a1f2c' if int(status) >= 300 else '#69db7e;background:#1a2c1a'
        }
    return None

def collect_status_codes():
    statuses = set()
    try:
        with open(log_file, 'r') as f:
            for line in f:
                m = re.search(r'" (\d{3}) ', line)
                if m:
                    statuses.add(int(m.group(1)))
    except:
        pass
    for s in [200, 201, 301, 302, 304, 400, 401, 403, 404, 405, 429, 500, 502, 503, 504]:
        statuses.add(s)
    return sorted(statuses)

def load_full_log():
    logs = []
    try:
        with open(log_file, 'r') as f:
            lines = f.readlines()
            print(f"📚 Загружено {len(lines)} строк")
            for line in reversed(lines):
                p = parse_log_line(line)
                if p:
                    logs.append(p)
                    if len(logs) >= 10000:
                        break
    except Exception as e:
        print(f"Ошибка загрузки: {e}")
    return logs

html_template = '''<!DOCTYPE html>
<html>
<head>
    <title>🔍 Nginx Log Analyzer Pro</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            background: #0a0e14;
            color: #e6e6e6;
            font-family: 'JetBrains Mono', 'Fira Code', monospace;
            margin: 0;
            padding: 20px;
            font-size: 13px;
        }}
        .container {{ max-width: 2000px; margin: 0 auto; }}
        .header {{
            background: #1a1f2a;
            padding: 20px;
            border-radius: 12px;
            margin-bottom: 20px;
            border: 1px solid #2c313a;
        }}
        h1 {{
            margin: 0 0 20px 0;
            font-size: 24px;
            color: #a9b1d6;
        }}
        .file-info {{
            background: #0f1319;
            padding: 10px 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            border-left: 4px solid #7aa2f7;
        }}
        .filters {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }}
        .filter-group {{
            display: flex;
            flex-direction: column;
            gap: 5px;
        }}
        .filter-group label {{
            font-size: 11px;
            text-transform: uppercase;
            color: #7aa2f7;
            font-weight: bold;
        }}
        input, select {{
            background: #0f1319;
            border: 1px solid #2c313a;
            color: #e6e6e6;
            padding: 10px 12px;
            border-radius: 6px;
            font-family: inherit;
        }}
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }}
        .stat-card {{
            background: #0f1319;
            padding: 15px;
            border-radius: 8px;
            border: 1px solid #2c313a;
        }}
        .stat-value {{
            font-size: 24px;
            font-weight: bold;
            color: #7aa2f7;
        }}
        .stat-label {{
            font-size: 11px;
            color: #88909f;
            text-transform: uppercase;
        }}
        .controls {{
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }}
        .button {{
            background: #1f2430;
            border: 1px solid #2c313a;
            color: #e6e6e6;
            padding: 10px 20px;
            border-radius: 6px;
            cursor: pointer;
        }}
        .button:hover {{
            background: #2c313a;
            border-color: #7aa2f7;
        }}
        .button.primary {{
            background: #7aa2f7;
            color: #0a0e14;
        }}
        .pagination {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 15px 20px;
            background: #1a1f2a;
            border-bottom: 1px solid #2c313a;
        }}
        .log-container {{
            background: #0f1319;
            border-radius: 12px;
            border: 1px solid #2c313a;
            overflow: hidden;
        }}
        .log-header {{
            display: grid;
            grid-template-columns: 150px 180px 70px 1fr 70px 100px;
            background: #1a1f2a;
            padding: 12px 20px;
            font-weight: bold;
            border-bottom: 1px solid #2c313a;
            cursor: pointer;
        }}
        .log-header span:hover {{ color: #7aa2f7; }}
        .log-entries {{ height: 60vh; overflow-y: auto; }}
        .log-line {{
            display: grid;
            grid-template-columns: 150px 180px 70px 1fr 70px 100px;
            padding: 8px 20px;
            border-bottom: 1px solid #1a1f2a;
            cursor: pointer;
            transition: background 0.2s;
        }}
        .log-line:hover {{ background: #1a1f2a; }}
        .status-badge {{
            padding: 2px 8px;
            border-radius: 4px;
            font-weight: bold;
            text-align: center;
        }}
        .method-badge {{
            padding: 2px 8px;
            border-radius: 4px;
            background: #2c313a;
            text-align: center;
        }}
        .ip-address {{ color: #7aa2f7; font-family: monospace; font-weight: bold; }}
        .modal {{
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0,0,0,0.8);
        }}
        .modal-content {{
            background: #1a1f2a;
            margin: 5% auto;
            width: 90%;
            max-width: 900px;
            border-radius: 16px;
        }}
        .modal-header {{
            padding: 20px 25px;
            background: #0f1319;
            border-bottom: 2px solid #7aa2f7;
            border-radius: 16px 16px 0 0;
            display: flex;
            justify-content: space-between;
        }}
        .modal-header h2 {{ margin: 0; color: #7aa2f7; }}
        .close {{
            color: #88909f;
            font-size: 32px;
            cursor: pointer;
        }}
        .close:hover {{ color: #ff6b6b; }}
        .modal-body {{ padding: 25px; max-height: 60vh; overflow-y: auto; }}
        .detail-section {{
            margin-bottom: 20px;
            background: #0f1319;
            border-radius: 8px;
            padding: 15px;
            border-left: 3px solid #7aa2f7;
        }}
        .detail-label {{
            font-size: 11px;
            text-transform: uppercase;
            color: #7aa2f7;
            margin-bottom: 8px;
            font-weight: bold;
        }}
        .detail-value {{ font-family: monospace; font-size: 13px; word-break: break-all; }}
        .detail-value pre {{
            background: #0a0e14;
            padding: 12px;
            border-radius: 6px;
            overflow-x: auto;
        }}
        .filter-ip-btn {{
            background: #2c313a;
            border: none;
            color: #7aa2f7;
            padding: 4px 12px;
            border-radius: 4px;
            cursor: pointer;
            margin-left: 10px;
        }}
        .time-presets {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }}
        .time-preset-btn {{
            background: #1f2430;
            border: 1px solid #2c313a;
            color: #e6e6e6;
            padding: 6px 12px;
            border-radius: 4px;
            cursor: pointer;
        }}
        .custom-time-range {{
            display: grid;
            grid-template-columns: 1fr 1fr auto auto;
            gap: 10px;
            margin-top: 10px;
        }}
        .footer {{
            margin-top: 20px;
            text-align: center;
            color: #88909f;
            font-size: 11px;
        }}
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>🔍 Nginx Log Analyzer Pro</h1>
        <div class="file-info">📁 {log_file}</div>
        
        <div class="stats">
            <div class="stat-card"><div class="stat-value" id="total-count">0</div><div class="stat-label">Отфильтровано</div></div>
            <div class="stat-card"><div class="stat-value" id="error-count">0</div><div class="stat-label">Ошибки</div></div>
            <div class="stat-card"><div class="stat-value" id="unique-ips">0</div><div class="stat-label">Уникальные IP</div></div>
        </div>
        
        <div class="filters">
            <div class="filter-group"><label>🌐 Фильтр по IP</label><input type="text" id="filter-ip" placeholder="192.168.1.1"></div>
            <div class="filter-group">
                <label>📊 Фильтр по статусу</label>
                <select id="filter-status">
                    <option value="">Все статусы</option>
                    <option value="4xx">4xx ошибки</option>
                    <option value="5xx">5xx ошибки</option>
                    {status_options}
                </select>
            </div>
            <div class="filter-group">
                <label>🔧 Фильтр по методу</label>
                <select id="filter-method">
                    <option value="">Все методы</option>
                    <option value="GET">GET</option>
                    <option value="POST">POST</option>
                    <option value="PUT">PUT</option>
                    <option value="DELETE">DELETE</option>
                </select>
            </div>
            <div class="filter-group"><label>🔍 Поиск в URL</label><input type="text" id="filter-url" placeholder="текст в URL..."></div>
        </div>
        
        <div class="controls">
            <button class="button" onclick="togglePause()" id="pauseBtn">⏸️ Пауза</button>
            <button class="button" onclick="loadFullLog()">📂 Загрузить лог</button>
            <button class="button" onclick="clearFilters()">🧹 Очистить</button>
            <button class="button primary" onclick="exportFiltered()">💾 Экспорт CSV</button>
        </div>
    </div>
    
    <div class="log-container">
        <div class="pagination">
            <span id="showing-entries">Показано 0-0 из 0</span>
            <div>
                <button class="button" onclick="prevPage()" id="prev-btn" disabled>←</button>
                <span id="page-info" style="margin:0 15px;">1/1</span>
                <button class="button" onclick="nextPage()" id="next-btn" disabled>→</button>
                <select id="page-size"><option value="50">50</option><option value="100" selected>100</option><option value="200">200</option><option value="500">500</option></select>
            </div>
        </div>
        <div class="log-header">
            <span onclick="sortBy('sort_time')">⏰ Дата и время</span>
            <span onclick="sortBy('ip')">🌐 IP адрес</span>
            <span onclick="sortBy('method')">🔧 Метод</span>
            <span onclick="sortBy('url')">📌 URL</span>
            <span onclick="sortBy('status')">📊 Статус</span>
            <span onclick="sortBy('size')">📦 Размер</span>
        </div>
        <div id="log-entries" class="log-entries">Загрузка...</div>
    </div>
    <div class="footer">💡 Кликните по строке для просмотра деталей</div>
</div>

<div id="modal" class="modal"><div class="modal-content"><div class="modal-header"><h2>📋 Детали запроса</h2><span class="close" onclick="closeModal()">&times;</span></div><div id="modal-body" class="modal-body"></div></div></div>

<script>
let logs=[], filteredLogs=[], isPaused=false, sortField='sort_time', sortDirection='desc', currentPage=1, pageSize=100, startTimeFilter=null, endTimeFilter=null;

function showDetails(log) {{
    document.getElementById('modal-body').innerHTML = `
        <div class="detail-section"><div class="detail-label">🌐 IP АДРЕС</div><div class="detail-value"><strong style="color:#7aa2f7;">${{log.ip}}</strong> <button class="filter-ip-btn" onclick="filterByIP('${{log.ip}}');closeModal();">🔍 Фильтровать</button></div></div>
        <div class="detail-section"><div class="detail-label">⏰ ВРЕМЯ</div><div class="detail-value">${{log.timestamp}}</div></div>
        <div class="detail-section"><div class="detail-label">🔧 МЕТОД И СТАТУС</div><div class="detail-value"><span class="method-badge">${{log.method}}</span> <span class="status-badge" style="${{log.color}}">${{log.status}}</span></div></div>
        <div class="detail-section"><div class="detail-label">📌 URL</div><div class="detail-value">${{log.url}}</div></div>
        <div class="detail-section"><div class="detail-label">📦 РАЗМЕР</div><div class="detail-value">${{log.size}} B</div></div>
        <div class="detail-section"><div class="detail-label">🔗 REFERER</div><div class="detail-value">${{log.referer || '—'}}</div></div>
        <div class="detail-section"><div class="detail-label">💻 USER-AGENT</div><div class="detail-value"><details><summary style="cursor:pointer;color:#7aa2f7;">Смотреть</summary><pre>${{log.agent}}</pre></details></div></div>
    `;
    document.getElementById('modal').style.display = 'block';
}}
function closeModal() {{ document.getElementById('modal').style.display = 'none'; }}
function filterByIP(ip) {{ document.getElementById('filter-ip').value = ip; applyFilters(); }}
window.onclick = function(e) {{ if (e.target === document.getElementById('modal')) closeModal(); }}

function applyFilters() {{
    let ip = document.getElementById('filter-ip').value.toLowerCase();
    let status = document.getElementById('filter-status').value;
    let method = document.getElementById('filter-method').value;
    let url = document.getElementById('filter-url').value.toLowerCase();
    filteredLogs = logs.filter(l => {{
        if (!l) return false;
        if (ip && !l.ip.toLowerCase().includes(ip)) return false;
        if (status && (status==='4xx' && (l.status<400||l.status>=500)) || (status==='5xx' && (l.status<500||l.status>=600)) || (!isNaN(status) && l.status!=parseInt(status))) return false;
        if (method && l.method!==method) return false;
        if (url && !l.url.toLowerCase().includes(url)) return false;
        if (startTimeFilter && l.sort_time<startTimeFilter) return false;
        if (endTimeFilter && l.sort_time>endTimeFilter) return false;
        return true;
    }});
    filteredLogs.sort((a,b) => {{
        let va=a[sortField], vb=b[sortField];
        if (sortField==='status'||sortField==='size') {{ va=parseInt(va)||0; vb=parseInt(vb)||0; }}
        return sortDirection==='asc' ? (va>vb?1:-1) : (va<vb?1:-1);
    }});
    document.getElementById('total-count').innerText = filteredLogs.length;
    document.getElementById('error-count').innerText = filteredLogs.filter(l=>l.status>=400).length;
    document.getElementById('unique-ips').innerText = new Set(filteredLogs.map(l=>l.ip)).size;
    currentPage = 1;
    renderLogs();
}}

function renderLogs() {{
    let start = (currentPage-1)*pageSize;
    let end = Math.min(start+pageSize, filteredLogs.length);
    let container = document.getElementById('log-entries');
    if (!filteredLogs.length) {{ container.innerHTML = '<div style="padding:40px;text-align:center;">🔍 Нет записей</div>'; return; }}
    container.innerHTML = filteredLogs.slice(start,end).map(l => `<div class="log-line ${l.status>=500?'error-500':l.status>=400?'error-404':''}" onclick='showDetails(${JSON.stringify(l).replace(/'/g, "\\'")})'><span style="color:#88909f;">${l.timestamp}</span><span class="ip-address">${l.ip}</span><span class="method-badge">${l.method}</span><span style="word-break:break-all;">${l.url.substring(0,80)}${l.url.length>80?'...':''}</span><span class="status-badge" style="${l.color}">${l.status}</span><span style="text-align:right;">${l.size} B</span></div>`).join('');
    let totalPages = Math.ceil(filteredLogs.length/pageSize)||1;
    document.getElementById('showing-entries').innerText = `Показано ${start+1}-${end} из ${filteredLogs.length}`;
    document.getElementById('page-info').innerText = `${currentPage}/${totalPages}`;
    document.getElementById('prev-btn').disabled = currentPage===1;
    document.getElementById('next-btn').disabled = currentPage>=totalPages;
}}
function prevPage() {{ if (currentPage>1) {{ currentPage--; renderLogs(); }} }}
function nextPage() {{ if (currentPage<Math.ceil(filteredLogs.length/pageSize)) {{ currentPage++; renderLogs(); }} }}
function togglePause() {{ isPaused=!isPaused; document.getElementById('pauseBtn').innerHTML = isPaused ? '▶️ Возобновить' : '⏸️ Пауза'; }}
function loadFullLog() {{ fetch('/full-log').then(r=>r.json()).then(d=>{{ logs=d; applyFilters(); }}); }}
function clearFilters() {{
    document.getElementById('filter-ip').value='';
    document.getElementById('filter-status').value='';
    document.getElementById('filter-method').value='';
    document.getElementById('filter-url').value='';
    startTimeFilter=endTimeFilter=null;
    applyFilters();
}}
function exportFiltered() {{
    let csv='Timestamp,IP,Method,URL,Status,Size\\n';
    filteredLogs.forEach(l=>{{ csv+=`"${l.timestamp}","${l.ip}","${l.method}","${l.url}","${l.status}","${l.size}"\\n`; }});
    let a=document.createElement('a');
    a.href=URL.createObjectURL(new Blob([csv]));
    a.download=`logs_${new Date().toISOString().slice(0,10)}.csv`;
    a.click();
}}
document.getElementById('filter-ip').addEventListener('input',applyFilters);
document.getElementById('filter-status').addEventListener('change',applyFilters);
document.getElementById('filter-method').addEventListener('change',applyFilters);
document.getElementById('filter-url').addEventListener('input',applyFilters);
document.getElementById('page-size').addEventListener('change',function(){{ pageSize=parseInt(this.value); currentPage=1; renderLogs(); }});
for(let btn of document.querySelectorAll('[data-minutes]')) btn.onclick=function(){{ startTimeFilter=Date.now()/1000-parseInt(this.dataset.minutes)*60; endTimeFilter=null; applyFilters(); }};
window.onload=loadFullLog;
new EventSource('/stream').onmessage=e=>{{ if(!isPaused && e.data){{ try{{ let d=JSON.parse(e.data); logs.unshift(d); if(logs.length>10000) logs.pop(); applyFilters(); }}catch(e){{}} }}}};
</script>
</body>
</html>
'''

def handle_client(client):
    client.send(b'HTTP/1.1 200 OK\r\n')
    client.send(b'Content-Type: text/html; charset=utf-8\r\n')
    client.send(b'Connection: close\r\n')
    client.send(b'\r\n')
    
    status_codes = collect_status_codes()
    status_options = ''.join(f'<option value="{c}">{c}</option>' for c in status_codes)
    
    html = html_template.format(log_file=log_file, status_options=status_options)
    client.send(html.encode())
    client.close()

def handle_stream(client):
    client.send(b'HTTP/1.1 200 OK\r\n')
    client.send(b'Content-Type: text/event-stream\r\n')
    client.send(b'Cache-Control: no-cache\r\n')
    client.send(b'Connection: keep-alive\r\n')
    client.send(b'\r\n')
    
    proc = subprocess.Popen(['tail', '-f', log_file], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
    try:
        while True:
            line = proc.stdout.readline()
            if line:
                parsed = parse_log_line(line)
                if parsed:
                    client.send(f'data: {json.dumps(parsed)}\n\n'.encode())
    except:
        proc.kill()
    finally:
        client.close()

def handle_full_log(client):
    client.send(b'HTTP/1.1 200 OK\r\n')
    client.send(b'Content-Type: application/json\r\n')
    client.send(b'Connection: close\r\n')
    client.send(b'\r\n')
    client.send(json.dumps(load_full_log()).encode())
    client.close()

def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('0.0.0.0', port))
    server.listen(10)
    print(f'\n🚀 Сервер запущен на порту {port}')
    print(f'🌐 Доступ: http://0.0.0.0:{port}')
    while True:
        client, addr = server.accept()
        req = client.recv(1024).decode()
        if '/stream' in req:
            threading.Thread(target=handle_stream, args=(client,)).start()
        elif '/full-log' in req:
            threading.Thread(target=handle_full_log, args=(client,)).start()
        else:
            threading.Thread(target=handle_client, args=(client,)).start()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\n👋 Сервер остановлен')
