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
        
        # Парсим URL и параметры
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

# HTML с модальным окном
html_template = '''<!DOCTYPE html>
<html>
<head>
    <title>🔍 Nginx Log Analyzer Pro</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { box-sizing: border-box; }
        body {
            background: #0a0e14;
            color: #e6e6e6;
            font-family: 'JetBrains Mono', 'Fira Code', 'Courier New', monospace;
            margin: 0;
            padding: 20px;
            font-size: 13px;
        }
        .container { max-width: 2000px; margin: 0 auto; }
        .header {
            background: #1a1f2a;
            padding: 20px;
            border-radius: 12px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
            border: 1px solid #2c313a;
        }
        h1 {
            margin: 0 0 20px 0;
            font-size: 24px;
            display: flex;
            align-items: center;
            gap: 10px;
            color: #a9b1d6;
        }
        .file-info {
            background: #0f1319;
            padding: 10px 15px;
            border-radius: 8px;
            font-size: 14px;
            margin-bottom: 20px;
            border-left: 4px solid #7aa2f7;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .filters {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }
        .filter-group {
            display: flex;
            flex-direction: column;
            gap: 5px;
        }
        .filter-group label {
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: #7aa2f7;
            font-weight: bold;
        }
        input, select {
            background: #0f1319;
            border: 1px solid #2c313a;
            color: #e6e6e6;
            padding: 10px 12px;
            border-radius: 6px;
            font-family: inherit;
            font-size: 13px;
        }
        input:focus, select:focus {
            outline: none;
            border-color: #7aa2f7;
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }
        .stat-card {
            background: #0f1319;
            padding: 15px;
            border-radius: 8px;
            border: 1px solid #2c313a;
        }
        .stat-value {
            font-size: 24px;
            font-weight: bold;
            color: #7aa2f7;
        }
        .stat-label {
            font-size: 11px;
            color: #88909f;
            text-transform: uppercase;
        }
        .controls {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }
        .button {
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
        }
        .button:hover {
            background: #2c313a;
            border-color: #7aa2f7;
        }
        .button.primary {
            background: #7aa2f7;
            color: #0a0e14;
        }
        .pagination {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 15px 20px;
            background: #1a1f2a;
            border-bottom: 1px solid #2c313a;
        }
        .pagination-controls {
            display: flex;
            gap: 10px;
            align-items: center;
        }
        .log-container {
            background: #0f1319;
            border-radius: 12px;
            border: 1px solid #2c313a;
            overflow: hidden;
        }
        .log-header {
            display: grid;
            grid-template-columns: 150px 180px 70px 1fr 70px 100px;
            background: #1a1f2a;
            padding: 12px 20px;
            font-weight: bold;
            color: #a9b1d6;
            border-bottom: 1px solid #2c313a;
            cursor: pointer;
        }
        .log-header span:hover { color: #7aa2f7; }
        .log-entries {
            height: 60vh;
            overflow-y: auto;
        }
        .log-line {
            display: grid;
            grid-template-columns: 150px 180px 70px 1fr 70px 100px;
            padding: 8px 20px;
            border-bottom: 1px solid #1a1f2a;
            font-size: 12px;
            cursor: pointer;
            transition: background 0.2s;
        }
        .log-line:hover {
            background: #1a1f2a;
            transform: scale(1.01);
        }
        .status-badge {
            padding: 2px 8px;
            border-radius: 4px;
            font-weight: bold;
            display: inline-block;
            text-align: center;
            width: 100%;
        }
        .method-badge {
            padding: 2px 8px;
            border-radius: 4px;
            background: #2c313a;
            text-align: center;
            width: 100%;
            display: inline-block;
        }
        .ip-address {
            color: #7aa2f7;
            font-family: monospace;
            font-weight: bold;
        }
        .error-404 { background: rgba(255, 217, 61, 0.1); }
        .error-500 { background: rgba(255, 107, 107, 0.1); }
        
        /* Модальное окно */
        .modal {
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0,0,0,0.8);
            animation: fadeIn 0.3s;
        }
        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }
        .modal-content {
            background: #1a1f2a;
            margin: 5% auto;
            padding: 0;
            width: 90%;
            max-width: 900px;
            border-radius: 16px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.5);
            animation: slideIn 0.3s;
        }
        @keyframes slideIn {
            from { transform: translateY(-50px); opacity: 0; }
            to { transform: translateY(0); opacity: 1; }
        }
        .modal-header {
            padding: 20px 25px;
            background: #0f1319;
            border-bottom: 2px solid #7aa2f7;
            border-radius: 16px 16px 0 0;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .modal-header h2 {
            margin: 0;
            color: #7aa2f7;
            font-size: 20px;
        }
        .close {
            color: #88909f;
            font-size: 32px;
            font-weight: bold;
            cursor: pointer;
            transition: 0.2s;
            line-height: 1;
        }
        .close:hover {
            color: #ff6b6b;
            transform: scale(1.1);
        }
        .modal-body {
            padding: 25px;
            max-height: 60vh;
            overflow-y: auto;
        }
        .detail-section {
            margin-bottom: 20px;
            background: #0f1319;
            border-radius: 8px;
            padding: 15px;
            border-left: 3px solid #7aa2f7;
        }
        .detail-label {
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: #7aa2f7;
            margin-bottom: 8px;
            font-weight: bold;
        }
        .detail-value {
            font-family: monospace;
            font-size: 13px;
            word-break: break-all;
            color: #e6e6e6;
            line-height: 1.5;
        }
        .detail-value pre {
            background: #0a0e14;
            padding: 12px;
            border-radius: 6px;
            overflow-x: auto;
            margin: 8px 0 0 0;
            font-size: 12px;
        }
        .filter-ip-btn {
            background: #2c313a;
            border: none;
            color: #7aa2f7;
            padding: 4px 12px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 11px;
            margin-left: 10px;
        }
        .filter-ip-btn:hover {
            background: #7aa2f7;
            color: #0a0e14;
        }
        .footer {
            margin-top: 20px;
            text-align: center;
            color: #88909f;
            font-size: 11px;
        }
        .time-range {
            display: flex;
            flex-direction: column;
            gap: 10px;
        }
        .time-presets {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }
        .time-preset-btn {
            background: #1f2430;
            border: 1px solid #2c313a;
            color: #e6e6e6;
            padding: 6px 12px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
        }
        .time-preset-btn:hover {
            background: #2c313a;
            border-color: #7aa2f7;
        }
        .time-preset-btn.active {
            background: #7aa2f7;
            color: #0a0e14;
        }
        .custom-time-range {
            display: grid;
            grid-template-columns: 1fr 1fr auto auto;
            gap: 10px;
            align-items: center;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔍 Nginx Live Log Analyzer Pro</h1>
            <div class="file-info">
                <span>📁 {log_file}</span>
                <span class="file-stats" id="total-file-entries">Загрузка...</span>
            </div>
            
            <div class="stats">
                <div class="stat-card">
                    <div class="stat-value" id="total-count">0</div>
                    <div class="stat-label">Отфильтровано</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="error-count">0</div>
                    <div class="stat-label">Ошибки</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="unique-ips">0</div>
                    <div class="stat-label">Уникальные IP</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="time-range-stats">-</div>
                    <div class="stat-label">Диапазон</div>
                </div>
            </div>
            
            <div class="filters">
                <div class="filter-group">
                    <label>🌐 Фильтр по IP</label>
                    <input type="text" id="filter-ip" placeholder="192.168.1.1">
                </div>
                <div class="filter-group">
                    <label>📊 Фильтр по статусу</label>
                    <select id="filter-status">
                        <option value="">Все статусы</option>
                        <option value="4xx">4xx (ошибки клиента)</option>
                        <option value="5xx">5xx (ошибки сервера)</option>
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
                    </select>
                </div>
                <div class="filter-group">
                    <label>🔍 Поиск в URL</label>
                    <input type="text" id="filter-url" placeholder="текст в URL...">
                </div>
                <div class="filter-group">
                    <label>⏰ Временной диапазон</label>
                    <div class="time-range">
                        <div class="time-presets">
                            <button class="time-preset-btn" data-minutes="5">5 мин</button>
                            <button class="time-preset-btn" data-minutes="30">30 мин</button>
                            <button class="time-preset-btn" data-minutes="60">1 час</button>
                            <button class="time-preset-btn" data-minutes="360">6 час</button>
                            <button class="time-preset-btn" data-minutes="1440">24 час</button>
                            <button class="time-preset-btn" id="custom-time-btn">📅 Свой</button>
                        </div>
                        <div id="custom-time-picker" style="display: none;">
                            <div class="custom-time-range">
                                <input type="datetime-local" id="start-time">
                                <input type="datetime-local" id="end-time">
                                <button class="button" onclick="applyCustomTime()">Применить</button>
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
                    📂 Загрузить лог
                </button>
                <button class="button" onclick="clearFilters()">
                    🧹 Очистить
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
                </div>
                <div class="pagination-controls">
                    <button class="button" onclick="prevPage()" id="prev-btn" disabled>←</button>
                    <span style="padding: 0 15px;" id="page-info">1/1</span>
                    <button class="button" onclick="nextPage()" id="next-btn" disabled>→</button>
                    <select id="page-size">
                        <option value="50">50</option>
                        <option value="100" selected>100</option>
                        <option value="200">200</option>
                        <option value="500">500</option>
                    </select>
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
            <div id="log-entries" class="log-entries"></div>
        </div>
        
        <div class="footer">
            ⚡ Real-time лог-анализатор | Обновлено: <span id="update-time"></span>
            <br>💡 Кликните по любой строке для просмотра деталей запроса
        </div>
    </div>

    <!-- Модальное окно -->
    <div id="detailModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h2>📋 Детали запроса</h2>
                <span class="close" onclick="closeModal()">&times;</span>
            </div>
            <div class="modal-body" id="modal-body">
                <!-- Данные будут вставлены здесь -->
            </div>
        </div>
    </div>

    <script>
        let logs = [];
        let filteredLogs = [];
        let isPaused = false;
        let sortField = 'sort_time';
        let sortDirection = 'desc';
        let currentPage = 1;
        let pageSize = 100;
        let startTimeFilter = null;
        let endTimeFilter = null;
        
        function formatTime(timestamp) { return timestamp || ''; }
        
        function showDetails(log) {
            const modal = document.getElementById('detailModal');
            const modalBody = document.getElementById('modal-body');
            
            const userAgentShort = log.agent.length > 100 ? log.agent.substring(0, 100) + '...' : log.agent;
            
            modalBody.innerHTML = `
                <div class="detail-section">
                    <div class="detail-label">🌐 IP АДРЕС</div>
                    <div class="detail-value">
                        <strong style="color:#7aa2f7;">${log.ip}</strong>
                        <button class="filter-ip-btn" onclick="filterByIP('${log.ip}'); closeModal();">🔍 Фильтровать по этому IP</button>
                    </div>
                </div>
                
                <div class="detail-section">
                    <div class="detail-label">⏰ ВРЕМЯ ЗАПРОСА</div>
                    <div class="detail-value">${log.full_date || log.timestamp} ${log.full_time ? 'в ' + log.full_time : ''}</div>
                </div>
                
                <div class="detail-section">
                    <div class="detail-label">🔧 МЕТОД И СТАТУС</div>
                    <div class="detail-value">
                        <span class="method-badge" style="display: inline-block; width: auto; margin-right: 10px;">${log.method}</span>
                        <span class="status-badge" style="${log.color} display: inline-block; width: auto;">${log.status}</span>
                    </div>
                </div>
                
                <div class="detail-section">
                    <div class="detail-label">📌 URL (ПОЛНЫЙ ПУТЬ)</div>
                    <div class="detail-value">
                        <strong>Путь:</strong> ${log.url_path || log.url}
                        ${log.url_params ? `<div style="margin-top: 10px;"><strong>Параметры:</strong><pre>${log.url_params.replace(/&/g, '&amp;').replace(/</g, '&lt;')}</pre></div>` : ''}
                    </div>
                </div>
                
                <div class="detail-section">
                    <div class="detail-label">📦 РАЗМЕР ОТВЕТА</div>
                    <div class="detail-value">${log.size} байт (${(log.size/1024).toFixed(2)} KB)</div>
                </div>
                
                <div class="detail-section">
                    <div class="detail-label">🔗 REFERER (ОТКУДА ПРИШЛИ)</div>
                    <div class="detail-value">${log.referer || '<em style="color:#88909f;">— прямой переход или не указан —</em>'}</div>
                </div>
                
                <div class="detail-section">
                    <div class="detail-label">💻 USER-AGENT (БРАУЗЕР/УСТРОЙСТВО)</div>
                    <div class="detail-value">
                        <details>
                            <summary style="cursor: pointer; color:#7aa2f7;">${userAgentShort}</summary>
                            <pre style="margin-top: 10px;">${log.agent}</pre>
                        </details>
                    </div>
                </div>
                
                <div class="detail-section">
                    <div class="detail-label">📄 ПОЛНАЯ СТРОКА ЛОГА</div>
                    <div class="detail-value">
                        <pre style="font-size: 11px; overflow-x: auto;">${log.raw.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')}</pre>
                    </div>
                </div>
            `;
            
            modal.style.display = 'block';
        }
        
        function filterByIP(ip) {
            document.getElementById('filter-ip').value = ip;
            applyFilters();
        }
        
        function closeModal() {
            document.getElementById('detailModal').style.display = 'none';
        }
        
        window.onclick = function(event) {
            const modal = document.getElementById('detailModal');
            if (event.target === modal) {
                closeModal();
            }
        }
        
        function applyFilters() {
            const ipFilter = document.getElementById('filter-ip').value.toLowerCase();
            const statusFilter = document.getElementById('filter-status').value;
            const methodFilter = document.getElementById('filter-method').value;
            const urlFilter = document.getElementById('filter-url').value.toLowerCase();
            
            filteredLogs = logs.filter(log => {
                if (!log) return false;
                if (ipFilter && !log.ip.toLowerCase().includes(ipFilter)) return false;
                if (statusFilter) {
                    if (statusFilter === '4xx' && (log.status < 400 || log.status >= 500)) return false;
                    if (statusFilter === '5xx' && (log.status < 500 || log.status >= 600)) return false;
                    if (!isNaN(statusFilter) && log.status != parseInt(statusFilter)) return false;
                }
                if (methodFilter && log.method !== methodFilter) return false;
                if (urlFilter && !log.url.toLowerCase().includes(urlFilter)) return false;
                if (startTimeFilter && log.sort_time < startTimeFilter) return false;
                if (endTimeFilter && log.sort_time > endTimeFilter) return false;
                return true;
            });
            
            sortLogs();
            updateStats();
            currentPage = 1;
            renderLogs();
        }
        
        function sortLogs() {
            filteredLogs.sort((a, b) => {
                let valA = a[sortField], valB = b[sortField];
                if (sortField === 'status' || sortField === 'size') {
                    valA = parseInt(valA) || 0;
                    valB = parseInt(valB) || 0;
                }
                return sortDirection === 'asc' ? (valA > valB ? 1 : -1) : (valA < valB ? 1 : -1);
            });
        }
        
        function sortBy(field) {
            if (sortField === field) {
                sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
            } else {
                sortField = field;
                sortDirection = 'desc';
            }
            sortLogs();
            renderLogs();
        }
        
        function renderLogs() {
            const container = document.getElementById('log-entries');
            if (!container) return;
            
            if (filteredLogs.length === 0) {
                container.innerHTML = '<div style="padding: 40px; text-align: center;">🔍 Нет записей</div>';
                return;
            }
            
            const start = (currentPage - 1) * pageSize;
            const end = Math.min(start + pageSize, filteredLogs.length);
            const pageLogs = filteredLogs.slice(start, end);
            
            container.innerHTML = pageLogs.map(log => `
                <div class="log-line ${log.status >= 500 ? 'error-500' : log.status >= 400 ? 'error-404' : ''}" onclick="showDetails(${JSON.stringify(log).replace(/</g, '\\u003c')})">
                    <span style="color: #88909f;">${log.timestamp}</span>
                    <span class="ip-address">${log.ip}</span>
                    <span><span class="method-badge">${log.method}</span></span>
                    <span style="word-break: break-all;">${log.url.substring(0, 80)}${log.url.length > 80 ? '...' : ''}</span>
                    <span><span class="status-badge" style="${log.color}">${log.status}</span></span>
                    <span style="text-align: right;">${log.size} B</span>
                </div>
            `).join('');
            
            const totalPages = Math.ceil(filteredLogs.length / pageSize);
            document.getElementById('showing-entries').innerHTML = `Показано ${start+1}-${end} из ${filteredLogs.length}`;
            document.getElementById('page-info').innerHTML = `${currentPage}/${totalPages || 1}`;
            document.getElementById('prev-btn').disabled = currentPage === 1;
            document.getElementById('next-btn').disabled = currentPage >= totalPages;
            document.getElementById('update-time').textContent = new Date().toLocaleTimeString();
        }
        
        function updateStats() {
            document.getElementById('total-count').textContent = filteredLogs.length;
            document.getElementById('error-count').textContent = filteredLogs.filter(l => l.status >= 400).length;
            document.getElementById('unique-ips').textContent = new Set(filteredLogs.map(l => l.ip)).size;
        }
        
        function prevPage() { if (currentPage > 1) { currentPage--; renderLogs(); } }
        function nextPage() { if (currentPage < Math.ceil(filteredLogs.length / pageSize)) { currentPage++; renderLogs(); } }
        function togglePause() {
            isPaused = !isPaused;
            document.getElementById('pause-icon').textContent = isPaused ? '▶️' : '⏸️';
            document.getElementById('pause-text').textContent = isPaused ? 'Возобновить' : 'Пауза';
        }
        
        function loadFullLog() {
            const container = document.getElementById('log-entries');
            container.innerHTML = '<div style="padding: 40px; text-align: center;">🔄 Загрузка лога...</div>';
            fetch('/full-log')
                .then(res => res.json())
                .then(data => { logs = data; applyFilters(); })
                .catch(err => { container.innerHTML = '<div style="padding: 40px; text-align: center; color:#ff6b6b;">❌ Ошибка загрузки</div>'; });
        }
        
        function clearFilters() {
            document.getElementById('filter-ip').value = '';
            document.getElementById('filter-status').value = '';
            document.getElementById('filter-method').value = '';
            document.getElementById('filter-url').value = '';
            startTimeFilter = null;
            endTimeFilter = null;
            document.querySelectorAll('.time-preset-btn').forEach(btn => btn.classList.remove('active'));
            document.getElementById('custom-time-picker').style.display = 'none';
            applyFilters();
        }
        
        function exportFiltered() {
            let csv = 'Timestamp,IP,Method,URL,Status,Size,Referer,User Agent\\n';
            filteredLogs.forEach(log => {
                csv += `"${log.timestamp}","${log.ip}","${log.method}","${log.url}","${log.status}","${log.size}","${log.referer}","${log.agent}"\\n`;
            });
            const blob = new Blob([csv], { type: 'text/csv' });
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = `nginx_logs_${new Date().toISOString().slice(0,10)}.csv`;
            a.click();
        }
        
        function applyCustomTime() {
            const start = document.getElementById('start-time').value;
            const end = document.getElementById('end-time').value;
            if (start) startTimeFilter = new Date(start).getTime() / 1000;
            if (end) endTimeFilter = new Date(end).getTime() / 1000;
            applyFilters();
        }
        
        window.onload = () => {
            document.querySelectorAll('.time-preset-btn[data-minutes]').forEach(btn => {
                btn.onclick = () => {
                    const minutes = parseInt(btn.dataset.minutes);
                    const now = Date.now() / 1000;
                    startTimeFilter = now - (minutes * 60);
                    endTimeFilter = null;
                    document.querySelectorAll('.time-preset-btn').forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    document.getElementById('custom-time-picker').style.display = 'none';
                    applyFilters();
                };
            });
            document.getElementById('custom-time-btn').onclick = () => {
                const picker = document.getElementById('custom-time-picker');
                picker.style.display = picker.style.display === 'none' ? 'block' : 'none';
                document.querySelectorAll('.time-preset-btn').forEach(b => b.classList.remove('active'));
                startTimeFilter = null;
                endTimeFilter = null;
            };
            document.getElementById('filter-ip').addEventListener('input', applyFilters);
            document.getElementById('filter-status').addEventListener('change', applyFilters);
            document.getElementById('filter-method').addEventListener('change', applyFilters);
            document.getElementById('filter-url').addEventListener('input', applyFilters);
            document.getElementById('page-size').addEventListener('change', function() {
                pageSize = parseInt(this.value);
                currentPage = 1;
                renderLogs();
            });
            loadFullLog();
        };
        
        const evtSource = new EventSource('/stream');
        evtSource.onmessage = (e) => {
            if (!isPaused && e.data) {
                try {
                    const logData = JSON.parse(e.data);
                    logs.unshift(logData);
                    if (logs.length > 10000) logs.pop();
                    applyFilters();
                } catch(e) { console.error(e); }
            }
        };
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
    server.bind(('127.0.0.1', port))
    server.listen(10)
    
    print(f'\n🚀 Nginx Log Analyzer Pro запущен!')
    print(f'📁 Файл: {log_file}')
    print(f'🌐 Доступ: http://127.0.0.1:{port}')
    print(f'\n✨ НОВАЯ ФИЧА: Клик по любой строке → детальный просмотр запроса!')
    print('\n⏎ Ctrl+C для остановки\n')
    
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

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\n👋 Сервер остановлен')
