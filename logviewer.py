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
        except:
            formatted_time = timestamp
            sort_time = 0
        return {
            'raw': line, 'ip': ip, 'timestamp': formatted_time, 'sort_time': sort_time,
            'method': method, 'url': url, 'status': int(status), 'size': size,
            'referer': referer, 'agent': agent,
            'color': '#ff6b6b;background:#2c1a1a' if int(status) >= 500 else
                     '#ffd93d;background:#2c261a' if int(status) >= 400 else
                     '#6bafff;background:#1a1f2c' if int(status) >= 300 else
                     '#69db7e;background:#1a2c1a'
        }
    return None

def collect_status_codes():
    statuses = set()
    try:
        with open(log_file, 'r') as f:
            for line in f:
                m = re.search(r'" (\d{3}) ', line)
                if m: statuses.add(int(m.group(1)))
    except: pass
    for s in [200,201,301,302,304,400,401,403,404,405,429,500,502,503,504]:
        statuses.add(s)
    return sorted(statuses)

def load_full_log():
    logs = []
    try:
        with open(log_file, 'r') as f:
            for line in reversed(f.readlines()):
                p = parse_log_line(line)
                if p:
                    logs.append(p)
                    if len(logs) >= 10000: break
    except: pass
    return logs

html_template = '''<!DOCTYPE html>
<html>
<head>
    <title>🔍 Nginx Log Analyzer Pro</title>
    <meta charset="utf-8">
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            background: #0a0e14;
            color: #e6e6e6;
            font-family: monospace;
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
        }}
        h1 {{ margin: 0 0 20px 0; font-size: 24px; color: #a9b1d6; }}
        .file-info {{
            background: #0f1319;
            padding: 10px;
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
        }}
        input, select {{
            background: #0f1319;
            border: 1px solid #2c313a;
            color: #e6e6e6;
            padding: 10px;
            border-radius: 6px;
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
        }}
        .stat-value {{ font-size: 24px; font-weight: bold; color: #7aa2f7; }}
        .stat-label {{ font-size: 11px; color: #88909f; }}
        .controls {{ display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap; }}
        .button {{
            background: #1f2430;
            border: 1px solid #2c313a;
            color: #e6e6e6;
            padding: 10px 20px;
            border-radius: 6px;
            cursor: pointer;
        }}
        .button:hover {{ background: #2c313a; }}
        .log-container {{
            background: #0f1319;
            border-radius: 12px;
            overflow: hidden;
        }}
        .log-header {{
            display: grid;
            grid-template-columns: 150px 180px 70px 1fr 70px 100px;
            background: #1a1f2a;
            padding: 12px 20px;
            font-weight: bold;
            cursor: pointer;
        }}
        .log-entries {{ height: 60vh; overflow-y: auto; }}
        .log-line {{
            display: grid;
            grid-template-columns: 150px 180px 70px 1fr 70px 100px;
            padding: 8px 20px;
            border-bottom: 1px solid #1a1f2a;
            cursor: pointer;
        }}
        .log-line:hover {{ background: #1a1f2a; }}
        .status-badge {{ padding: 2px 8px; border-radius: 4px; text-align: center; }}
        .method-badge {{ padding: 2px 8px; border-radius: 4px; background: #2c313a; text-align: center; }}
        .ip-address {{ color: #7aa2f7; font-weight: bold; }}
        .modal {{
            display: none;
            position: fixed;
            background: rgba(0,0,0,0.8);
            left: 0; top: 0;
            width: 100%; height: 100%;
        }}
        .modal-content {{
            background: #1a1f2a;
            margin: 5% auto;
            width: 90%;
            max-width: 900px;
            border-radius: 16px;
        }}
        .modal-header {{
            padding: 20px;
            background: #0f1319;
            border-bottom: 2px solid #7aa2f7;
            display: flex;
            justify-content: space-between;
        }}
        .close {{ font-size: 32px; cursor: pointer; }}
        .modal-body {{ padding: 20px; max-height: 60vh; overflow-y: auto; }}
        .detail-section {{
            margin-bottom: 20px;
            background: #0f1319;
            padding: 15px;
            border-left: 3px solid #7aa2f7;
        }}
        .detail-label {{ font-size: 11px; text-transform: uppercase; color: #7aa2f7; }}
        .detail-value {{ font-family: monospace; word-break: break-all; }}
        .footer {{ margin-top: 20px; text-align: center; color: #88909f; }}
        .time-presets {{ display: flex; flex-wrap: wrap; gap: 8px; }}
        .time-preset-btn {{
            background: #1f2430;
            border: 1px solid #2c313a;
            padding: 6px 12px;
            border-radius: 4px;
            cursor: pointer;
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
                </select>
            </div>
            <div class="filter-group"><label>🔍 Поиск в URL</label><input type="text" id="filter-url"></div>
        </div>
        <div class="controls">
            <button class="button" onclick="togglePause()" id="pauseBtn">⏸️ Пауза</button>
            <button class="button" onclick="loadFullLog()">📂 Загрузить лог</button>
            <button class="button" onclick="clearFilters()">🧹 Очистить</button>
            <button class="button" onclick="exportFiltered()">💾 Экспорт CSV</button>
        </div>
    </div>
    <div class="log-container">
        <div class="log-header">
            <span onclick="sortBy('sort_time')">⏰ Дата</span>
            <span onclick="sortBy('ip')">🌐 IP</span>
            <span onclick="sortBy('method')">🔧 Метод</span>
            <span onclick="sortBy('url')">📌 URL</span>
            <span onclick="sortBy('status')">📊 Статус</span>
            <span onclick="sortBy('size')">📦 Размер</span>
        </div>
        <div id="log-entries" class="log-entries">Загрузка...</div>
    </div>
    <div class="footer">💡 Кликните по строке для деталей</div>
</div>

<div id="modal" class="modal"><div class="modal-content"><div class="modal-header"><h2>📋 Детали</h2><span class="close" onclick="closeModal()">&times;</span></div><div id="modal-body" class="modal-body"></div></div></div>

<script>
let logs=[], filtered=[], paused=false, sortF='sort_time', sortD='desc', page=1, pageSize=100;

function showDetails(l) {{
    document.getElementById('modal-body').innerHTML = `
        <div class="detail-section"><div class="detail-label">🌐 IP</div><div class="detail-value"><strong>${{l.ip}}</strong> <button onclick="filterByIP('${{l.ip}}')">🔍</button></div></div>
        <div class="detail-section"><div class="detail-label">⏰ Время</div><div class="detail-value">${{l.timestamp}}</div></div>
        <div class="detail-section"><div class="detail-label">📌 URL</div><div class="detail-value">${{l.url}}</div></div>
        <div class="detail-section"><div class="detail-label">💻 User-Agent</div><div class="detail-value"><pre>${{l.agent}}</pre></div></div>
    `;
    document.getElementById('modal').style.display='block';
}}
function closeModal() {{ document.getElementById('modal').style.display='none'; }}
function filterByIP(ip) {{ document.getElementById('filter-ip').value=ip; applyFilters(); closeModal(); }}

function applyFilters() {{
    let ip = document.getElementById('filter-ip').value.toLowerCase();
    let st = document.getElementById('filter-status').value;
    let mt = document.getElementById('filter-method').value;
    let url = document.getElementById('filter-url').value.toLowerCase();
    filtered = logs.filter(l => {{
        if(ip && !l.ip.includes(ip)) return false;
        if(st && (st==='4xx'&&(l.status<400||l.status>=500)) || (st==='5xx'&&(l.status<500||l.status>=600)) || (!isNaN(st)&&l.status!=parseInt(st))) return false;
        if(mt && l.method!==mt) return false;
        if(url && !l.url.toLowerCase().includes(url)) return false;
        return true;
    }});
    filtered.sort((a,b)=>{{
        let va=a[sortF], vb=b[sortF];
        if(sortF==='status'||sortF==='size') {{ va=parseInt(va)||0; vb=parseInt(vb)||0; }}
        return sortD==='asc'?(va>vb?1:-1):(va<vb?1:-1);
    }});
    document.getElementById('total-count').innerText=filtered.length;
    document.getElementById('error-count').innerText=filtered.filter(l=>l.status>=400).length;
    document.getElementById('unique-ips').innerText=new Set(filtered.map(l=>l.ip)).size;
    page=1;
    render();
}}

function render() {{
    let start=(page-1)*pageSize, end=Math.min(start+pageSize, filtered.length);
    let container=document.getElementById('log-entries');
    if(!filtered.length){{ container.innerHTML='<div style="padding:40px">Нет записей</div>'; return; }}
    container.innerHTML=filtered.slice(start,end).map(l=>`<div class="log-line" onclick="showDetails(${JSON.stringify(l).replace(/'/g,"\\'")})"><span>${l.timestamp}</span><span class="ip-address">${l.ip}</span><span class="method-badge">${l.method}</span><span>${l.url.substring(0,80)}</span><span class="status-badge" style="${l.color}">${l.status}</span><span>${l.size} B</span></div>`).join('');
}}

function loadFullLog() {{ fetch('/full-log').then(r=>r.json()).then(d=>{{ logs=d; applyFilters(); }}); }}
function clearFilters() {{
    document.getElementById('filter-ip').value='';
    document.getElementById('filter-status').value='';
    document.getElementById('filter-method').value='';
    document.getElementById('filter-url').value='';
    applyFilters();
}}
function togglePause() {{ paused=!paused; document.getElementById('pauseBtn').innerHTML=paused?'▶️ Возобновить':'⏸️ Пауза'; }}
function exportFiltered() {{
    let csv='Timestamp,IP,Method,URL,Status,Size\\n';
    filtered.forEach(l=>csv+=`"${l.timestamp}","${l.ip}","${l.method}","${l.url}","${l.status}","${l.size}"\\n`);
    let a=document.createElement('a');
    a.href=URL.createObjectURL(new Blob([csv]));
    a.download=`logs_${new Date().toISOString().slice(0,10)}.csv`;
    a.click();
}}
document.getElementById('filter-ip').addEventListener('input',applyFilters);
document.getElementById('filter-status').addEventListener('change',applyFilters);
document.getElementById('filter-method').addEventListener('change',applyFilters);
document.getElementById('filter-url').addEventListener('input',applyFilters);
window.onload=loadFullLog;
new EventSource('/stream').onmessage=e=>{{ if(!paused && e.data){{ try{{ let d=JSON.parse(e.data); logs.unshift(d); if(logs.length>10000) logs.pop(); applyFilters(); }}catch(e){{}} }}}};
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
