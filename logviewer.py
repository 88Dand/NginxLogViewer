import os
import socket
import subprocess
import threading
import sys
import json
from datetime import datetime, timedelta
import re
from collections import Counter

log_file = sys.argv[1] if len(sys.argv) > 1 else '/var/www/api/nginx-logs/site.access.log'
port = 8080

# Хранилище последних логов
log_history = []
max_history = 10000  # Увеличим для всего файла

def parse_log_line(line):
    """Парсит строку лога Nginx в структурированный объект"""
    # Формат combined: $remote_addr - $remote_user [$time_local] "$request" $status $body_bytes_sent "$http_referer" "$http_user_agent"
    pattern = r'(\S+) \S+ \S+ \[([^\]]+)\] "(\S+) (\S+) [^"]+" (\d+) (\d+) "([^"]*)" "([^"]*)"'
    match = re.search(pattern, line)
    
    if match:
        ip, timestamp, method, url, status, size, referer, agent = match.groups()
        
        # Конвертируем timestamp в datetime объект
        try:
            # Формат: 11/Feb/2026:13:43:22 +0000
            dt = datetime.strptime(timestamp.split(' ')[0], '%d/%b/%Y:%H:%M:%S')
            formatted_time = dt.strftime('%d.%m.%Y %H:%M')
            sort_time = dt.timestamp()
        except:
            formatted_time = timestamp
            sort_time = 0
        
        return {
            'raw': line,
            'ip': ip,
            'timestamp': formatted_time,
            'sort_time': sort_time,
            'method': method,
            'url': url,
            'status': int(status),
            'size': size,
            'referer': referer,
            'agent': agent,
            'color': get_status_color(int(status))
        }
    return None

def get_status_color(status):
    if status >= 500:
        return 'color: #ff6b6b; background: #2c1a1a; font-weight: bold;'
    elif status >= 400:
        return 'color: #ffd93d; background: #2c261a; font-weight: bold;'
    elif status >= 300:
        return 'color: #6bafff; background: #1a1f2c;'
    else:
        return 'color: #69db7e; background: #1a2c1a;'

def collect_status_codes():
    """Собирает все уникальные статусы из всего лог-файла"""
    statuses = set()
    try:
        with open(log_file, 'r') as f:
            # Читаем файл построчно для экономии памяти
            for line in f:
                match = re.search(r'" (\d{3}) ', line)
                if match:
                    statuses.add(int(match.group(1)))
    except Exception as e:
        print(f"Ошибка при сборе статусов: {e}")
    
    # Добавляем самые частые статусы на всякий случай
    common_statuses = [200, 201, 301, 302, 304, 400, 401, 403, 404, 405, 429, 500, 502, 503, 504]
    for status in common_statuses:
        statuses.add(status)
    
    return sorted(statuses)

def load_full_log():
    """Загружает ВЕСЬ лог-файл с пагинацией"""
    logs = []
    try:
        with open(log_file, 'r') as f:
            # Читаем весь файл
            lines = f.readlines()
            print(f"📚 Загружено {len(lines)} строк из лог-файла")
            
            # Парсим все строки с конца (новые сверху)
            for line in reversed(lines):
                parsed = parse_log_line(line)
                if parsed:
                    logs.append(parsed)
                    if len(logs) >= max_history:
                        break
    except Exception as e:
        print(f"Ошибка при загрузке лога: {e}")
    
    return logs

html_template = '''<!DOCTYPE html>
<html>
<head>
    <title>🔍 Nginx Log</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {{
            box-sizing: border-box;
        }}
        body {{
            background: #0a0e14;
            color: #e6e6e6;
            font-family: 'JetBrains Mono', 'Fira Code', 'Courier New', monospace;
            margin: 0;
            padding: 20px;
            font-size: 13px;
        }}
        
        .container {{
            max-width: 2000px;
            margin: 0 auto;
        }}
        
        .header {{
            background: #1a1f2a;
            padding: 20px;
            border-radius: 12px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
            border: 1px solid #2c313a;
        }}
        
        h1 {{
            margin: 0 0 20px 0;
            font-size: 24px;
            display: flex;
            align-items: center;
            gap: 10px;
            color: #a9b1d6;
        }}
        
        .file-info {{
            background: #0f1319;
            padding: 10px 15px;
            border-radius: 8px;
            font-size: 14px;
            margin-bottom: 20px;
            border-left: 4px solid #7aa2f7;
            word-break: break-all;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        
        .file-stats {{
            color: #7aa2f7;
            font-weight: bold;
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
            letter-spacing: 1px;
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
            font-size: 13px;
            transition: all 0.2s;
        }}
        
        input:hover, select:hover {{
            border-color: #7aa2f7;
        }}
        
        input:focus, select:focus {{
            outline: none;
            border-color: #7aa2f7;
            box-shadow: 0 0 0 3px rgba(122,162,247,0.1);
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
            font-size: 13px;
            display: flex;
            align-items: center;
            gap: 8px;
            transition: all 0.2s;
            border: none;
        }}
        
        .button:hover {{
            background: #2c313a;
            border-color: #7aa2f7;
        }}
        
        .button.primary {{
            background: #7aa2f7;
            color: #0a0e14;
        }}
        
        .button.primary:hover {{
            background: #88b4ff;
        }}
        
        .pagination {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 15px 20px;
            background: #1a1f2a;
            border-bottom: 1px solid #2c313a;
        }}
        
        .pagination-info {{
            color: #88909f;
        }}
        
        .pagination-controls {{
            display: flex;
            gap: 10px;
            align-items: center;
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
            color: #a9b1d6;
            border-bottom: 1px solid #2c313a;
            cursor: pointer;
        }}
        
        .log-header span:hover {{
            color: #7aa2f7;
        }}
        
        .log-entries {{
            height: 60vh;
            overflow-y: auto;
            padding: 0;
            margin: 0;
            font-family: inherit;
            background: #0f1319;
        }}
        
        .log-line {{
            display: grid;
            grid-template-columns: 150px 180px 70px 1fr 70px 100px;
            padding: 8px 20px;
            border-bottom: 1px solid #1a1f2a;
            font-size: 12px;
            transition: background 0.2s;
            word-break: break-word;
        }}
        
        .log-line:hover {{
            background: #1a1f2a;
        }}
        
        .status-badge {{
            padding: 2px 8px;
            border-radius: 4px;
            font-weight: bold;
            display: inline-block;
            text-align: center;
            width: 100%;
        }}
        
        .method-badge {{
            padding: 2px 8px;
            border-radius: 4px;
            background: #2c313a;
            color: #e6e6e6;
            font-weight: bold;
            display: inline-block;
            text-align: center;
            width: 100%;
        }}
        
        .ip-address {{
            color: #7aa2f7;
            font-family: monospace;
            font-weight: bold;
        }}
        
        .error-404 {{
            background: rgba(255, 217, 61, 0.1);
        }}
        
        .error-500 {{
            background: rgba(255, 107, 107, 0.1);
        }}
        
        .footer {{
            margin-top: 20px;
            text-align: center;
            color: #88909f;
            font-size: 11px;
        }}
        
        ::-webkit-scrollbar {{
            width: 8px;
            height: 8px;
        }}
        
        ::-webkit-scrollbar-track {{
            background: #0f1319;
        }}
        
        ::-webkit-scrollbar-thumb {{
            background: #2c313a;
            border-radius: 4px;
        }}
        
        ::-webkit-scrollbar-thumb:hover {{
            background: #7aa2f7;
        }}
        
        .time-range {{
            display: flex;
            flex-direction: column;
            gap: 10px;
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
            font-size: 12px;
            transition: all 0.2s;
        }}
        
        .time-preset-btn:hover {{
            background: #2c313a;
            border-color: #7aa2f7;
        }}
        
        .time-preset-btn.active {{
            background: #7aa2f7;
            color: #0a0e14;
            border-color: #7aa2f7;
        }}
        
        .custom-time-range {{
            display: grid;
            grid-template-columns: 1fr 1fr auto auto;
            gap: 10px;
            align-items: center;
        }}
        
        .total-entries {{
            color: #7aa2f7;
            font-weight: bold;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔍 Nginx Live Log </h1>
            <div class="file-info">
                <span>📁 {log_file}</span>
                <span class="file-stats" id="total-file-entries">Загрузка...</span>
            </div>
            
            <div class="stats" id="stats">
                <div class="stat-card">
                    <div class="stat-value" id="total-count">0</div>
                    <div class="stat-label">Отфильтровано</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="error-count">0</div>
                    <div class="stat-label">Ошибки (4xx/5xx)</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="unique-ips">0</div>
                    <div class="stat-label">Уникальные IP</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="time-range-stats">-</div>
                    <div class="stat-label">Временной диапазон</div>
                </div>
            </div>
            
            <div class="filters">
                <div class="filter-group">
                    <label>🌐 Фильтр по IP</label>
                    <input type="text" id="filter-ip" placeholder="например: 192.168.1.1" autocomplete="off">
                </div>
                
                <div class="filter-group">
                    <label>📊 Фильтр по статусу</label>
                    <select id="filter-status">
                        <option value="">Все статусы</option>
                        <option value="4xx">4xx (все ошибки клиента)</option>
                        <option value="5xx">5xx (все ошибки сервера)</option>
                        <option disabled>──────────</option>
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
                        <option value="PATCH">PATCH</option>
                        <option value="HEAD">HEAD</option>
                        <option value="OPTIONS">OPTIONS</option>
                    </select>
                </div>
                
                <div class="filter-group">
                    <label>🔍 Поиск в URL</label>
                    <input type="text" id="filter-url" placeholder="текст в URL..." autocomplete="off">
                </div>
                
                <div class="filter-group">
                    <label>⏰ Временной диапазон</label>
                    <div class="time-range">
                        <div class="time-presets" id="time-presets">
                            <button class="time-preset-btn" data-minutes="5">5 мин</button>
                            <button class="time-preset-btn" data-minutes="10">10 мин</button>
                            <button class="time-preset-btn" data-minutes="30">30 мин</button>
                            <button class="time-preset-btn" data-minutes="60">1 час</button>
                            <button class="time-preset-btn" data-minutes="180">3 часа</button>
                            <button class="time-preset-btn" data-minutes="360">6 часов</button>
                            <button class="time-preset-btn" data-minutes="720">12 часов</button>
                            <button class="time-preset-btn" data-minutes="1440">24 часа</button>
                            <button class="time-preset-btn" data-minutes="4320">3 дня</button>
                            <button class="time-preset-btn" data-minutes="10080">7 дней</button>
                            <button class="time-preset-btn" id="custom-time-btn">📅 Свой</button>
                        </div>
                        <div id="custom-time-picker" style="display: none;">
                            <div class="custom-time-range">
                                <input type="datetime-local" id="start-time" placeholder="Начало">
                                <input type="datetime-local" id="end-time" placeholder="Конец">
                                <button class="button" onclick="applyCustomTimeRange()">Применить</button>
                                <button class="button" onclick="clearCustomTimeRange()">Очистить</button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="controls">
                <button class="button" onclick="togglePause()">
                    <span id="pause-icon">⏸️</span> <span id="pause-text">Пауза</span>
                </button>
                <button class="button" onclick="loadFullLog()">
                    📂 Загрузить весь лог
                </button>
                <button class="button" onclick="clearFilters()">
                    🧹 Очистить фильтры
                </button>
                <button class="button" onclick="copyVisible()">
                    📋 Копировать видимые
                </button>
                <button class="button primary" onclick="exportFiltered()">
                    💾 Экспорт CSV
                </button>
            </div>
        </div>
        
        <div class="log-container">
            <div class="pagination">
                <div class="pagination-info">
                    <span id="showing-entries">Показано 0-0 из 0</span>
                    <span style="margin-left: 15px;" id="filtered-percent"></span>
                </div>
                <div class="pagination-controls">
                    <button class="button" onclick="firstPage()" id="first-btn" title="Первая страница">⏮️</button>
                    <button class="button" onclick="prevPage()" id="prev-btn" disabled>←</button>
                    <span style="padding: 0 15px; color: #a9b1d6;" id="page-info">1/1</span>
                    <button class="button" onclick="nextPage()" id="next-btn" disabled>→</button>
                    <button class="button" onclick="lastPage()" id="last-btn" title="Последняя страница">⏭️</button>
                    <select id="page-size" style="width: 80px;">
                        <option value="50">50</option>
                        <option value="100" selected>100</option>
                        <option value="200">200</option>
                        <option value="500">500</option>
                        <option value="1000">1000</option>
                    </select>
                </div>
            </div>
            <div class="log-header">
                <span onclick="sortBy('sort_time')">⏰ Дата и время ⬇️</span>
                <span onclick="sortBy('ip')">🌐 IP адрес</span>
                <span onclick="sortBy('method')">🔧 Метод</span>
                <span onclick="sortBy('url')">📌 URL</span>
                <span onclick="sortBy('status')">📊 Статус</span>
                <span onclick="sortBy('size')">📦 Размер</span>
            </div>
            <div id="log-entries" class="log-entries">
                <div style="padding: 40px; text-align: center; color: #88909f;">
                    🔄 Загрузка лог-файла...
                </div>
            </div>
        </div>
        
        <div class="footer">
            ⚡ Real-time Nginx лог-анализатор | 
            Обновлено: <span id="update-time"></span> | 
            Всего записей в файле: <span id="total-file-count">0</span>
        </div>
    </div>

    <script>
        let logs = [];
        let filteredLogs = [];
        let isPaused = false;
        let sortField = 'sort_time';
        let sortDirection = 'desc';
        
        // Пагинация
        let currentPage = 1;
        let pageSize = 100;
        
        // Временные фильтры
        let startTimeFilter = null;
        let endTimeFilter = null;
        let activePreset = null;
        
        const logContainer = document.getElementById('log-entries');
        
        function formatTime(timestamp) {{
            return timestamp || '';
        }}
        
        function applyFilters() {{
            const ipFilter = document.getElementById('filter-ip').value.toLowerCase();
            const statusFilter = document.getElementById('filter-status').value;
            const methodFilter = document.getElementById('filter-method').value;
            const urlFilter = document.getElementById('filter-url').value.toLowerCase();
            
            filteredLogs = logs.filter(log => {{
                if (!log) return false;
                
                // IP фильтр
                if (ipFilter && !log.ip.toLowerCase().includes(ipFilter)) return false;
                
                // Статус фильтр
                if (statusFilter) {{
                    if (statusFilter === '4xx' && (log.status < 400 || log.status >= 500)) return false;
                    else if (statusFilter === '5xx' && (log.status < 500 || log.status >= 600)) return false;
                    else if (!isNaN(statusFilter) && log.status != parseInt(statusFilter)) return false;
                }}
                
                // Метод фильтр
                if (methodFilter && log.method !== methodFilter) return false;
                
                // URL фильтр
                if (urlFilter && !log.url.toLowerCase().includes(urlFilter)) return false;
                
                // Временной фильтр
                if (startTimeFilter && log.sort_time < startTimeFilter) return false;
                if (endTimeFilter && log.sort_time > endTimeFilter) return false;
                
                return true;
            }});
            
            sortLogs();
            updateStats();
            currentPage = 1;
            renderLogs();
        }}
        
        function sortLogs() {{
            filteredLogs.sort((a, b) => {{
                let valA = a[sortField];
                let valB = b[sortField];
                
                if (sortField === 'status' || sortField === 'size') {{
                    valA = parseInt(valA) || 0;
                    valB = parseInt(valB) || 0;
                }}
                
                if (sortDirection === 'asc') {{
                    return valA > valB ? 1 : -1;
                }} else {{
                    return valA < valB ? 1 : -1;
                }}
            }});
        }}
        
        function sortBy(field) {{
            if (sortField === field) {{
                sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
            }} else {{
                sortField = field;
                sortDirection = 'desc';
            }}
            sortLogs();
            renderLogs();
        }}
        
        function renderLogs() {{
            if (!logContainer) return;
            
            if (filteredLogs.length === 0) {{
                logContainer.innerHTML = '<div style="padding: 40px; text-align: center; color: #88909f;">🔍 Нет записей, соответствующих фильтрам</div>';
                document.getElementById('showing-entries').innerHTML = 'Показано 0-0 из 0';
                document.getElementById('page-info').innerHTML = '0/0';
                document.getElementById('prev-btn').disabled = true;
                document.getElementById('next-btn').disabled = true;
                document.getElementById('first-btn').disabled = true;
                document.getElementById('last-btn').disabled = true;
                return;
            }}
            
            const start = (currentPage - 1) * pageSize;
            const end = Math.min(start + pageSize, filteredLogs.length);
            const pageLogs = filteredLogs.slice(start, end);
            
            const html = pageLogs.map(log => `
                <div class="log-line ${{log.status >= 500 ? 'error-500' : log.status >= 400 ? 'error-404' : ''}}">
                    <span style="color: #88909f;">${{formatTime(log.timestamp)}}</span>
                    <span class="ip-address">${{log.ip || ''}}</span>
                    <span><span class="method-badge">${{log.method || ''}}</span></span>
                    <span style="color: #e6e6e6; word-break: break-all;">${{log.url || ''}}</span>
                    <span><span class="status-badge" style="${{log.color || ''}}">${{log.status || ''}}</span></span>
                    <span style="color: #88909f; text-align: right;">${{log.size || '0'}} B</span>
                </div>
            `).join('');
            
            logContainer.innerHTML = html;
            
            // Обновляем информацию о пагинации
            const totalPages = Math.ceil(filteredLogs.length / pageSize);
            document.getElementById('showing-entries').innerHTML = 
                `Показано ${{start+1}}-${{end}} из ${{filteredLogs.length}}`;
            document.getElementById('page-info').innerHTML = 
                `${{currentPage}}/${{totalPages}}`;
            document.getElementById('filtered-percent').innerHTML = 
                `(${{((filteredLogs.length / logs.length) * 100).toFixed(1)}}% от общего)`;
            
            document.getElementById('prev-btn').disabled = currentPage === 1;
            document.getElementById('next-btn').disabled = currentPage >= totalPages;
            document.getElementById('first-btn').disabled = currentPage === 1;
            document.getElementById('last-btn').disabled = currentPage >= totalPages;
            
            document.getElementById('update-time').textContent = new Date().toLocaleTimeString();
        }}
        
        function firstPage() {{
            currentPage = 1;
            renderLogs();
        }}
        
        function prevPage() {{
            if (currentPage > 1) {{
                currentPage--;
                renderLogs();
            }}
        }}
        
        function nextPage() {{
            if (currentPage < Math.ceil(filteredLogs.length / pageSize)) {{
                currentPage++;
                renderLogs();
            }}
        }}
        
        function lastPage() {{
            currentPage = Math.ceil(filteredLogs.length / pageSize);
            renderLogs();
        }}
        
        function updateStats() {{
            document.getElementById('total-count').textContent = filteredLogs.length;
            
            const errors = filteredLogs.filter(l => l.status >= 400).length;
            document.getElementById('error-count').textContent = errors;
            
            const uniqueIPs = new Set(filteredLogs.map(l => l.ip)).size;
            document.getElementById('unique-ips').textContent = uniqueIPs;
            
            // Временной диапазон
            if (filteredLogs.length > 0) {{
                const oldest = new Date(Math.min(...filteredLogs.map(l => l.sort_time)) * 1000);
                const newest = new Date(Math.max(...filteredLogs.map(l => l.sort_time)) * 1000);
                document.getElementById('time-range-stats').innerHTML = 
                    `${{oldest.toLocaleDateString()}} ${{oldest.toLocaleTimeString()}}<br>→ ${{newest.toLocaleDateString()}} ${{newest.toLocaleTimeString()}}`;
            }} else {{
                document.getElementById('time-range-stats').textContent = '-';
            }}
        }}
        
        function togglePause() {{
            isPaused = !isPaused;
            document.getElementById('pause-icon').textContent = isPaused ? '▶️' : '⏸️';
            document.getElementById('pause-text').textContent = isPaused ? 'Возобновить' : 'Пауза';
        }}
        
        function loadFullLog() {{
            logContainer.innerHTML = '<div style="padding: 40px; text-align: center; color: #88909f;">🔄 Загрузка лог-файла...</div>';
            
            fetch('/full-log')
                .then(response => response.json())
                .then(data => {{
                    logs = data;
                    document.getElementById('total-file-count').textContent = logs.length;
                    document.getElementById('total-file-entries').innerHTML = 
                        `📊 Всего записей: ${{logs.length}}`;
                    applyFilters();
                }})
                .catch(error => {{
                    logContainer.innerHTML = '<div style="padding: 40px; text-align: center; color: #ff6b6b;">❌ Ошибка загрузки лога</div>';
                    console.error('Error loading log:', error);
                }});
        }}
        
        function clearFilters() {{
            document.getElementById('filter-ip').value = '';
            document.getElementById('filter-status').value = '';
            document.getElementById('filter-method').value = '';
            document.getElementById('filter-url').value = '';
            
            // Сброс временных фильтров
            startTimeFilter = null;
            endTimeFilter = null;
            activePreset = null;
            document.querySelectorAll('.time-preset-btn').forEach(btn => {{
                btn.classList.remove('active');
            }});
            document.getElementById('custom-time-picker').style.display = 'none';
            
            applyFilters();
        }}
        
        function copyVisible() {{
            const text = filteredLogs.map(l => l.raw).join('\\n');
            navigator.clipboard.writeText(text);
            alert(`📋 Скопировано ${{filteredLogs.length}} строк`);
        }}
        
        function exportFiltered() {{
            let csv = 'Timestamp,IP,Method,URL,Status,Size,Referer,User Agent\\n';
            filteredLogs.forEach(log => {{
                csv += `"${{log.timestamp}}","${{log.ip}}","${{log.method}}","${{log.url}}","${{log.status}}","${{log.size}}","${{log.referer}}","${{log.agent}}"\\n`;
            }});
            
            const blob = new Blob([csv], {{ type: 'text/csv' }});
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `nginx_logs_${{new Date().toISOString().slice(0,10)}}.csv`;
            a.click();
        }}
        
        // Временные фильтры
        function setTimePreset(minutes) {{
            const now = Date.now() / 1000;
            startTimeFilter = now - (minutes * 60);
            endTimeFilter = null;
            
            // Обновляем UI
            document.querySelectorAll('.time-preset-btn').forEach(btn => {{
                btn.classList.remove('active');
            }});
            event.target.classList.add('active');
            
            document.getElementById('custom-time-picker').style.display = 'none';
            activePreset = minutes;
            
            applyFilters();
        }}
        
        function applyCustomTimeRange() {{
            const startInput = document.getElementById('start-time').value;
            const endInput = document.getElementById('end-time').value;
            
            if (startInput) {{
                startTimeFilter = new Date(startInput).getTime() / 1000;
            }}
            if (endInput) {{
                endTimeFilter = new Date(endInput).getTime() / 1000;
            }}
            
            document.querySelectorAll('.time-preset-btn').forEach(btn => {{
                btn.classList.remove('active');
            }});
            activePreset = null;
            
            applyFilters();
        }}
        
        function clearCustomTimeRange() {{
            document.getElementById('start-time').value = '';
            document.getElementById('end-time').value = '';
            startTimeFilter = null;
            endTimeFilter = null;
            applyFilters();
        }}
        
        // Инициализация обработчиков
        window.onload = function() {{
            // Обработчики пресетов времени
            document.querySelectorAll('.time-preset-btn[data-minutes]').forEach(btn => {{
                btn.addEventListener('click', function(e) {{
                    const minutes = parseInt(this.dataset.minutes);
                    setTimePreset(minutes);
                }});
            }});
            
            // Обработчик кнопки "Свой"
            document.getElementById('custom-time-btn').addEventListener('click', function() {{
                const picker = document.getElementById('custom-time-picker');
                picker.style.display = picker.style.display === 'none' ? 'block' : 'none';
                
                // Убираем активный пресет
                document.querySelectorAll('.time-preset-btn').forEach(btn => {{
                    btn.classList.remove('active');
                }});
                activePreset = null;
            }});
            
            // Подключаем фильтры
            document.getElementById('filter-ip').addEventListener('input', applyFilters);
            document.getElementById('filter-status').addEventListener('change', applyFilters);
            document.getElementById('filter-method').addEventListener('change', applyFilters);
            document.getElementById('filter-url').addEventListener('input', applyFilters);
            
            // Пагинация
            document.getElementById('page-size').addEventListener('change', function() {{
                pageSize = parseInt(this.value);
                currentPage = 1;
                renderLogs();
            }});
            
            // Автоматически загружаем лог
            loadFullLog();
        }};
        
        // WebSocket для реального времени
        const evtSource = new EventSource('/stream');
        evtSource.onmessage = function(e) {{
            if (!isPaused && e.data) {{
                try {{
                    const logData = JSON.parse(e.data);
                    logs.unshift(logData);
                    if (logs.length > 10000) logs.pop();
                    applyFilters();
                }} catch(e) {{
                    console.error('Parse error:', e);
                }}
            }}
        }};
        
        evtSource.onerror = function() {{
            console.log('Reconnecting...');
        }};
    </script>
</body>
</html>
'''

def handle_client(client):
    client.send(b'HTTP/1.1 200 OK\r\n')
    client.send(b'Content-Type: text/html; charset=utf-8\r\n')
    client.send(b'Connection: close\r\n')
    client.send(b'\r\n')
    
    # Собираем уникальные статусы из всего лога
    status_codes = collect_status_codes()
    status_options = ''
    for code in status_codes:
        status_options += f'<option value="{code}">{code}</option>\n'
    
    html = html_template.format(log_file=log_file, status_options=status_options)
    client.send(html.encode())
    client.close()

def handle_stream(client):
    client.send(b'HTTP/1.1 200 OK\r\n')
    client.send(b'Content-Type: text/event-stream\r\n')
    client.send(b'Cache-Control: no-cache\r\n')
    client.send(b'Connection: keep-alive\r\n')
    client.send(b'\r\n')
    
    proc = subprocess.Popen(['tail', '-f', log_file], 
                          stdout=subprocess.PIPE, 
                          stderr=subprocess.PIPE,
                          text=True,
                          bufsize=1)
    
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
    """Отдаёт ВЕСЬ лог-файл для начальной загрузки"""
    client.send(b'HTTP/1.1 200 OK\r\n')
    client.send(b'Content-Type: application/json\r\n')
    client.send(b'Connection: close\r\n')
    client.send(b'\r\n')
    
    logs = load_full_log()
    client.send(json.dumps(logs).encode())
    client.close()

def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('0.0.0.0', port))
    server.listen(10)
    
    print(f'\n🚀 Nginx Log Analyzer Pro запущен!')
    print(f'📁 Файл: {log_file}')
    print(f'🌐 Открой в браузере: http://localhost:{port}')
    print(f'\n✨ Новые возможности:')
    print('   • Все статусы ответов из лога')
    print('   • Дата в формате ДД.ММ.ГГГГ ЧЧ:ММ')
    print('   • Увеличенная колонка IP (180px)')
    print('   • Пагинация по 100 строк (можно менять)')
    print('   • Фильтр по времени: 5м,10м,30м,1ч,3ч,6ч,12ч,24ч,3д,7д')
    print('   • Произвольный интервал времени')
    print('   • Загрузка ВСЕГО лог-файла')
    print('   • Экспорт в CSV')
    print('\n⏎ Ctrl+C для остановки\n')
    
    try:
        while True:
            client, addr = server.accept()
            try:
                request = client.recv(1024).decode()
                if '/stream' in request:
                    threading.Thread(target=handle_stream, args=(client,)).start()
                elif '/full-log' in request:
                    threading.Thread(target=handle_full_log, args=(client,)).start()
                else:
                    threading.Thread(target=handle_client, args=(client,)).start()
            except:
                client.close()
    except KeyboardInterrupt:
        print('\n👋 Сервер остановлен')
    finally:
        server.close()

if __name__ == '__main__':
    main()
