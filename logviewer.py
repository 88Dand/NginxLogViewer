#!/usr/bin/env python3
import argparse
import html
import json
import os
import re
import subprocess
import sys
from collections import deque
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

DEFAULT_LOG_FILE = "/var/www/api/nginx-logs/site.access.log"
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8080
MAX_HISTORY = 10000

LOG_PATTERN = re.compile(
    r'(?P<ip>\S+) \S+ \S+ \[(?P<timestamp>[^\]]+)\] '
    r'"(?P<request>[^"]*)" (?P<status>\d{3}) (?P<size>\S+) '
    r'"(?P<referer>[^"]*)" "(?P<agent>[^"]*)"'
)

REQUEST_PATTERN = re.compile(r"(?P<method>\S+)\s+(?P<url>\S+)(?:\s+HTTP/\S+)?")


def parse_nginx_time(value):
    try:
        return datetime.strptime(value, "%d/%b/%Y:%H:%M:%S %z")
    except ValueError:
        return None


def parse_log_line(line):
    match = LOG_PATTERN.search(line)
    if not match:
        return None

    data = match.groupdict()
    request_match = REQUEST_PATTERN.match(data["request"])

    method = ""
    url = data["request"]

    if request_match:
        method = request_match.group("method")
        url = request_match.group("url")

    dt = parse_nginx_time(data["timestamp"])
    if dt:
        formatted_time = dt.strftime("%d.%m.%Y %H:%M:%S")
        sort_time = dt.timestamp()
    else:
        formatted_time = data["timestamp"]
        sort_time = 0

    try:
        status = int(data["status"])
    except ValueError:
        status = 0

    size = data["size"]
    if size == "-":
        size = "0"

    return {
        "raw": line.rstrip("\n"),
        "ip": data["ip"],
        "timestamp": formatted_time,
        "sort_time": sort_time,
        "method": method,
        "url": url,
        "status": status,
        "size": size,
        "referer": data["referer"],
        "agent": data["agent"],
    }


def read_last_parsed_lines(log_file, limit=MAX_HISTORY):
    result = []

    try:
        with open(log_file, "r", encoding="utf-8", errors="replace") as file:
            lines = deque(file, maxlen=limit)

        for line in reversed(lines):
            parsed = parse_log_line(line)
            if parsed:
                result.append(parsed)

    except FileNotFoundError:
        print(f"Файл лога не найден: {log_file}", file=sys.stderr)
    except PermissionError:
        print(f"Нет прав на чтение файла: {log_file}", file=sys.stderr)
    except Exception as exc:
        print(f"Ошибка чтения лога: {exc}", file=sys.stderr)

    return result


def collect_status_codes(logs):
    statuses = {log["status"] for log in logs if log.get("status")}

    common = {
        200, 201, 204,
        301, 302, 304,
        400, 401, 403, 404, 405, 408, 429,
        500, 502, 503, 504,
    }

    return sorted(statuses | common)


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="utf-8">
    <title>Nginx Log Analyzer Pro</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">

    <style>
        * { box-sizing: border-box; }

        body {
            background: #0a0e14;
            color: #e6e6e6;
            font-family: "JetBrains Mono", "Fira Code", "Courier New", monospace;
            margin: 0;
            padding: 20px;
            font-size: 13px;
        }

        .container {
            max-width: 2000px;
            margin: 0 auto;
        }

        .header {
            background: #1a1f2a;
            padding: 20px;
            border-radius: 12px;
            margin-bottom: 20px;
            border: 1px solid #2c313a;
        }

        h1 {
            margin: 0 0 20px 0;
            font-size: 24px;
            color: #a9b1d6;
        }

        .file-info {
            background: #0f1319;
            padding: 10px 15px;
            border-radius: 8px;
            font-size: 14px;
            margin-bottom: 20px;
            border-left: 4px solid #7aa2f7;
            word-break: break-all;
            display: flex;
            justify-content: space-between;
            gap: 20px;
        }

        .file-stats {
            color: #7aa2f7;
            font-weight: bold;
            white-space: nowrap;
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

        .filters {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
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

        .time-preset-btn,
        .button {
            background: #1f2430;
            border: 1px solid #2c313a;
            color: #e6e6e6;
            padding: 8px 12px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 12px;
            font-family: inherit;
        }

        .button {
            padding: 10px 20px;
            font-size: 13px;
        }

        .button:hover,
        .time-preset-btn:hover {
            background: #2c313a;
        }

        .button.primary,
        .time-preset-btn.active {
            background: #7aa2f7;
            color: #0a0e14;
        }

        .controls {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }

        .custom-time-range {
            display: grid;
            grid-template-columns: 1fr 1fr auto auto;
            gap: 10px;
            align-items: center;
        }

        .log-container {
            background: #0f1319;
            border-radius: 12px;
            border: 1px solid #2c313a;
            overflow: hidden;
        }

        .pagination {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 15px 20px;
            background: #1a1f2a;
            border-bottom: 1px solid #2c313a;
            gap: 15px;
            flex-wrap: wrap;
        }

        .pagination-info {
            color: #88909f;
        }

        .pagination-controls {
            display: flex;
            gap: 10px;
            align-items: center;
            flex-wrap: wrap;
        }

        .log-header,
        .log-line {
            display: grid;
            grid-template-columns: 170px 180px 80px minmax(300px, 1fr) 80px 100px;
            gap: 10px;
            align-items: center;
        }

        .log-header {
            background: #1a1f2a;
            padding: 12px 20px;
            font-weight: bold;
            color: #a9b1d6;
            border-bottom: 1px solid #2c313a;
        }

        .log-header span {
            cursor: pointer;
        }

        .log-header span:hover {
            color: #7aa2f7;
        }

        .log-entries {
            height: 60vh;
            overflow-y: auto;
            background: #0f1319;
        }

        .log-line {
            padding: 8px 20px;
            border-bottom: 1px solid #1a1f2a;
            font-size: 12px;
            word-break: break-word;
        }

        .log-line:hover {
            background: #1a1f2a;
        }

        .status-badge,
        .method-badge {
            padding: 2px 8px;
            border-radius: 4px;
            font-weight: bold;
            display: inline-block;
            text-align: center;
            width: 100%;
        }

        .method-badge {
            background: #2c313a;
            color: #e6e6e6;
        }

        .status-2xx {
            color: #69db7e;
            background: #1a2c1a;
        }

        .status-3xx {
            color: #6bafff;
            background: #1a1f2c;
        }

        .status-4xx {
            color: #ffd93d;
            background: #2c261a;
        }

        .status-5xx {
            color: #ff6b6b;
            background: #2c1a1a;
        }

        .error-4xx {
            background: rgba(255, 217, 61, 0.08);
        }

        .error-5xx {
            background: rgba(255, 107, 107, 0.08);
        }

        .ip-address {
            color: #7aa2f7;
            font-weight: bold;
        }

        .footer {
            margin-top: 20px;
            text-align: center;
            color: #88909f;
            font-size: 11px;
        }

        .empty {
            padding: 40px;
            text-align: center;
            color: #88909f;
        }
    </style>
</head>

<body>
<div class="container">
    <div class="header">
        <h1>🔍 Nginx Live Log Analyzer Pro</h1>

        <div class="file-info">
            <span>📁 <span id="log-file"></span></span>
            <span class="file-stats" id="total-file-entries">Загрузка...</span>
        </div>

        <div class="stats">
            <div class="stat-card">
                <div class="stat-value" id="total-count">0</div>
                <div class="stat-label">Отфильтровано</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="error-count">0</div>
                <div class="stat-label">Ошибки 4xx/5xx</div>
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
                <label>🌐 IP</label>
                <input type="text" id="filter-ip" placeholder="например: 192.168.1.1" autocomplete="off">
            </div>

            <div class="filter-group">
                <label>📊 Статус</label>
                <select id="filter-status">
                    <option value="">Все статусы</option>
                    <option value="4xx">4xx</option>
                    <option value="5xx">5xx</option>
                </select>
            </div>

            <div class="filter-group">
                <label>🔧 Метод</label>
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
                <label>🔍 URL</label>
                <input type="text" id="filter-url" placeholder="текст в URL..." autocomplete="off">
            </div>
        </div>

        <div class="controls">
            <button class="button" onclick="togglePause()">
                <span id="pause-icon">⏸️</span>
                <span id="pause-text">Пауза</span>
            </button>
            <button class="button" onclick="loadFullLog()">📂 Обновить лог</button>
            <button class="button" onclick="clearFilters()">🧹 Очистить фильтры</button>
            <button class="button" onclick="copyCurrentPage()">📋 Копировать страницу</button>
            <button class="button primary" onclick="exportFiltered()">💾 Экспорт CSV</button>
        </div>
    </div>

    <div class="log-container">
        <div class="pagination">
            <div class="pagination-info">
                <span id="showing-entries">Показано 0-0 из 0</span>
                <span style="margin-left:15px;" id="filtered-percent"></span>
            </div>

            <div class="pagination-controls">
                <button class="button" onclick="firstPage()" id="first-btn">⏮️</button>
                <button class="button" onclick="prevPage()" id="prev-btn">←</button>
                <span id="page-info">1/1</span>
                <button class="button" onclick="nextPage()" id="next-btn">→</button>
                <button class="button" onclick="lastPage()" id="last-btn">⏭️</button>

                <select id="page-size">
                    <option value="50">50</option>
                    <option value="100" selected>100</option>
                    <option value="200">200</option>
                    <option value="500">500</option>
                    <option value="1000">1000</option>
                </select>
            </div>
        </div>

        <div class="log-header">
            <span onclick="sortBy('sort_time')">⏰ Дата</span>
            <span onclick="sortBy('ip')">🌐 IP</span>
            <span onclick="sortBy('method')">🔧 Метод</span>
            <span onclick="sortBy('url')">📌 URL</span>
            <span onclick="sortBy('status')">📊 Статус</span>
            <span onclick="sortBy('size')">📦 Размер</span>
        </div>

        <div id="log-entries" class="log-entries">
            <div class="empty">🔄 Загрузка лог-файла...</div>
        </div>
    </div>

    <div class="footer">
        ⚡ Real-time Nginx Log Analyzer |
        Обновлено: <span id="update-time"></span> |
        Всего записей: <span id="total-file-count">0</span>
    </div>
</div>

<script>
    const LOG_FILE = "__LOG_FILE__";

    let logs = [];
    let filteredLogs = [];
    let isPaused = false;
    let sortField = "sort_time";
    let sortDirection = "desc";
    let currentPage = 1;
    let pageSize = 100;
    let evtSource = null;

    const logContainer = document.getElementById("log-entries");

    document.getElementById("log-file").textContent = LOG_FILE;

    function statusClass(status) {
        if (status >= 500) return "status-5xx";
        if (status >= 400) return "status-4xx";
        if (status >= 300) return "status-3xx";
        return "status-2xx";
    }

    function rowClass(status) {
        if (status >= 500) return "log-line error-5xx";
        if (status >= 400) return "log-line error-4xx";
        return "log-line";
    }

    function applyFilters() {
        const ipFilter = document.getElementById("filter-ip").value.toLowerCase();
        const statusFilter = document.getElementById("filter-status").value;
        const methodFilter = document.getElementById("filter-method").value;
        const urlFilter = document.getElementById("filter-url").value.toLowerCase();

        filteredLogs = logs.filter(log => {
            if (!log) return false;
            if (ipFilter && !String(log.ip || "").toLowerCase().includes(ipFilter)) return false;

            if (statusFilter) {
                if (statusFilter === "4xx" && (log.status < 400 || log.status >= 500)) return false;
                if (statusFilter === "5xx" && (log.status < 500 || log.status >= 600)) return false;
                if (!isNaN(statusFilter) && log.status !== parseInt(statusFilter)) return false;
            }

            if (methodFilter && log.method !== methodFilter) return false;
            if (urlFilter && !String(log.url || "").toLowerCase().includes(urlFilter)) return false;

            return true;
        });

        sortLogs();
        updateStats();
        currentPage = 1;
        renderLogs();
    }

    function sortLogs() {
        filteredLogs.sort((a, b) => {
            let valA = a[sortField];
            let valB = b[sortField];

            if (sortField === "status" || sortField === "size" || sortField === "sort_time") {
                valA = parseFloat(valA) || 0;
                valB = parseFloat(valB) || 0;
            } else {
                valA = String(valA || "");
                valB = String(valB || "");
            }

            if (valA === valB) return 0;

            if (sortDirection === "asc") {
                return valA > valB ? 1 : -1;
            }

            return valA < valB ? 1 : -1;
        });
    }

    function sortBy(field) {
        if (sortField === field) {
            sortDirection = sortDirection === "asc" ? "desc" : "asc";
        } else {
            sortField = field;
            sortDirection = field === "sort_time" ? "desc" : "asc";
        }

        sortLogs();
        renderLogs();
    }

    function renderLogs() {
        logContainer.replaceChildren();

        if (filteredLogs.length === 0) {
            const empty = document.createElement("div");
            empty.className = "empty";
            empty.textContent = "🔍 Нет записей, соответствующих фильтрам";
            logContainer.appendChild(empty);
            updatePagination(0, 0, 0, 0);
            return;
        }

        const start = (currentPage - 1) * pageSize;
        const end = Math.min(start + pageSize, filteredLogs.length);
        const pageLogs = filteredLogs.slice(start, end);

        const fragment = document.createDocumentFragment();

        for (const log of pageLogs) {
            const row = document.createElement("div");
            row.className = rowClass(log.status);

            const time = document.createElement("span");
            time.style.color = "#88909f";
            time.textContent = log.timestamp || "";

            const ip = document.createElement("span");
            ip.className = "ip-address";
            ip.textContent = log.ip || "";

            const methodWrap = document.createElement("span");
            const method = document.createElement("span");
            method.className = "method-badge";
            method.textContent = log.method || "";
            methodWrap.appendChild(method);

            const url = document.createElement("span");
            url.style.color = "#e6e6e6";
            url.style.wordBreak = "break-all";
            url.textContent = log.url || "";

            const statusWrap = document.createElement("span");
            const status = document.createElement("span");
            status.className = "status-badge " + statusClass(log.status);
            status.textContent = log.status || "";
            statusWrap.appendChild(status);

            const size = document.createElement("span");
            size.style.color = "#88909f";
            size.style.textAlign = "right";
            size.textContent = `${log.size || "0"} B`;

            row.append(time, ip, methodWrap, url, statusWrap, size);
            fragment.appendChild(row);
        }

        logContainer.appendChild(fragment);

        const totalPages = Math.ceil(filteredLogs.length / pageSize);
        updatePagination(start + 1, end, filteredLogs.length, totalPages);
        document.getElementById("update-time").textContent = new Date().toLocaleTimeString();
    }

    function updatePagination(start, end, total, totalPages) {
        document.getElementById("showing-entries").textContent = `Показано ${start}-${end} из ${total}`;
        document.getElementById("page-info").textContent = totalPages ? `${currentPage}/${totalPages}` : "0/0";

        const percent = logs.length ? ((filteredLogs.length / logs.length) * 100).toFixed(1) : "0.0";
        document.getElementById("filtered-percent").textContent = `(${percent}% от общего)`;

        document.getElementById("prev-btn").disabled = currentPage <= 1;
        document.getElementById("next-btn").disabled = currentPage >= totalPages;
        document.getElementById("first-btn").disabled = currentPage <= 1;
        document.getElementById("last-btn").disabled = currentPage >= totalPages;
    }

    function firstPage() {
        currentPage = 1;
        renderLogs();
    }

    function prevPage() {
        if (currentPage > 1) {
            currentPage--;
            renderLogs();
        }
    }

    function nextPage() {
        const totalPages = Math.ceil(filteredLogs.length / pageSize);
        if (currentPage < totalPages) {
            currentPage++;
            renderLogs();
        }
    }

    function lastPage() {
        currentPage = Math.ceil(filteredLogs.length / pageSize) || 1;
        renderLogs();
    }

    function updateStats() {
        document.getElementById("total-count").textContent = filteredLogs.length;

        const errors = filteredLogs.filter(l => l.status >= 400).length;
        document.getElementById("error-count").textContent = errors;

        const uniqueIPs = new Set(filteredLogs.map(l => l.ip)).size;
        document.getElementById("unique-ips").textContent = uniqueIPs;

        if (filteredLogs.length > 0) {
            const times = filteredLogs.map(l => l.sort_time).filter(Boolean);

            if (times.length) {
                const oldest = new Date(Math.min(...times) * 1000);
                const newest = new Date(Math.max(...times) * 1000);

                document.getElementById("time-range-stats").innerHTML =
                    `${oldest.toLocaleDateString()} ${oldest.toLocaleTimeString()}<br>→ ${newest.toLocaleDateString()} ${newest.toLocaleTimeString()}`;
            } else {
                document.getElementById("time-range-stats").textContent = "-";
            }
        } else {
            document.getElementById("time-range-stats").textContent = "-";
        }
    }

    function togglePause() {
        isPaused = !isPaused;
        document.getElementById("pause-icon").textContent = isPaused ? "▶️" : "⏸️";
        document.getElementById("pause-text").textContent = isPaused ? "Возобновить" : "Пауза";
    }

    function updateStatusOptions(statuses) {
        const select = document.getElementById("filter-status");
        const current = select.value;

        select.replaceChildren();

        const all = document.createElement("option");
        all.value = "";
        all.textContent = "Все статусы";
        select.appendChild(all);

        const four = document.createElement("option");
        four.value = "4xx";
        four.textContent = "4xx";
        select.appendChild(four);

        const five = document.createElement("option");
        five.value = "5xx";
        five.textContent = "5xx";
        select.appendChild(five);

        for (const code of statuses) {
            const option = document.createElement("option");
            option.value = String(code);
            option.textContent = String(code);
            select.appendChild(option);
        }

        select.value = current;
    }

    function loadFullLog() {
        logContainer.replaceChildren();

        const loading = document.createElement("div");
        loading.className = "empty";
        loading.textContent = "🔄 Загрузка лог-файла...";
        logContainer.appendChild(loading);

        fetch("/full-log")
            .then(response => {
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                return response.json();
            })
            .then(data => {
                logs = data.logs || [];
                updateStatusOptions(data.statuses || []);

                document.getElementById("total-file-count").textContent = logs.length;
                document.getElementById("total-file-entries").textContent = `📊 Загружено записей: ${logs.length}`;

                applyFilters();
            })
            .catch(error => {
                logContainer.replaceChildren();

                const div = document.createElement("div");
                div.className = "empty";
                div.style.color = "#ff6b6b";
                div.textContent = "❌ Ошибка загрузки лога";
                logContainer.appendChild(div);

                console.error(error);
            });
    }

    function clearFilters() {
        document.getElementById("filter-ip").value = "";
        document.getElementById("filter-status").value = "";
        document.getElementById("filter-method").value = "";
        document.getElementById("filter-url").value = "";
        applyFilters();
    }

    function currentPageLogs() {
        const start = (currentPage - 1) * pageSize;
        const end = Math.min(start + pageSize, filteredLogs.length);
        return filteredLogs.slice(start, end);
    }

    function copyCurrentPage() {
        const text = currentPageLogs().map(l => l.raw).join("\n");
        navigator.clipboard.writeText(text);
        alert(`📋 Скопировано строк: ${currentPageLogs().length}`);
    }

    function safeCsvCell(value) {
        value = String(value ?? "");

        if (/^[=+\-@]/.test(value)) {
            value = "'" + value;
        }

        return value;
    }

    function exportFiltered() {
        const rows = [
            ["Timestamp", "IP", "Method", "URL", "Status", "Size", "Referer", "User Agent"]
        ];

        for (const log of filteredLogs) {
            rows.push([
                log.timestamp,
                log.ip,
                log.method,
                log.url,
                log.status,
                log.size,
                log.referer,
                log.agent
            ].map(safeCsvCell));
        }

        const csv = rows.map(row =>
            row.map(value => `"${String(value).replaceAll('"', '""')}"`).join(",")
        ).join("\n");

        const blob = new Blob([csv], {type: "text/csv;charset=utf-8"});
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");

        a.href = url;
        a.download = `nginx_logs_${new Date().toISOString().slice(0, 10)}.csv`;
        a.click();

        window.URL.revokeObjectURL(url);
    }

    function connectStream() {
        if (evtSource) {
            evtSource.close();
        }

        evtSource = new EventSource("/stream");

        evtSource.onmessage = function(event) {
            if (isPaused || !event.data) return;

            try {
                const logData = JSON.parse(event.data);
                logs.unshift(logData);

                if (logs.length > __MAX_HISTORY__) {
                    logs.pop();
                }

                applyFilters();
            } catch (error) {
                console.error("SSE parse error:", error);
            }
        };

        evtSource.onerror = function() {
            console.log("SSE reconnecting...");
        };
    }

    window.onload = function() {
        document.getElementById("filter-ip").addEventListener("input", applyFilters);
        document.getElementById("filter-status").addEventListener("change", applyFilters);
        document.getElementById("filter-method").addEventListener("change", applyFilters);
        document.getElementById("filter-url").addEventListener("input", applyFilters);

        document.getElementById("page-size").addEventListener("change", function() {
            pageSize = parseInt(this.value);
            currentPage = 1;
            renderLogs();
        });

        loadFullLog();
        connectStream();
    };
</script>
</body>
</html>
"""


class LogViewerHandler(BaseHTTPRequestHandler):
    server_version = "NginxLogAnalyzer/2.1"

    def log_message(self, fmt, *args):
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))

    @property
    def log_file(self):
        return self.server.log_file

    @property
    def max_history(self):
        return self.server.max_history

    def send_json(self, payload, status=200):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/":
            self.handle_index()
        elif path == "/full-log":
            self.handle_full_log()
        elif path == "/stream":
            self.handle_stream()
        elif path == "/health":
            self.handle_health()
        else:
            self.send_error(404, "Not found")

    def handle_index(self):
        page = HTML_TEMPLATE
        page = page.replace("__LOG_FILE__", html.escape(self.log_file))
        page = page.replace("__MAX_HISTORY__", str(self.max_history))
        data = page.encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def handle_full_log(self):
        logs = read_last_parsed_lines(self.log_file, self.max_history)
        statuses = collect_status_codes(logs)

        self.send_json({
            "logs": logs,
            "statuses": statuses,
            "limit": self.max_history,
            "log_file": self.log_file,
        })

    def handle_health(self):
        readable = os.path.isfile(self.log_file) and os.access(self.log_file, os.R_OK)

        self.send_json({
            "ok": readable,
            "log_file": self.log_file,
            "readable": readable,
        }, status=200 if readable else 503)

    def handle_stream(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        proc = None

        try:
            proc = subprocess.Popen(
                ["tail", "-n", "0", "-F", self.log_file],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )

            for line in proc.stdout:
                parsed = parse_log_line(line)
                if not parsed:
                    continue

                payload = json.dumps(parsed, ensure_ascii=False)
                message = f"data: {payload}\n\n".encode("utf-8")

                try:
                    self.wfile.write(message)
                    self.wfile.flush()
                except BrokenPipeError:
                    break
                except ConnectionResetError:
                    break

        except FileNotFoundError:
            error = json.dumps({"error": "tail command not found"}, ensure_ascii=False)

            try:
                self.wfile.write(f"event: error\ndata: {error}\n\n".encode("utf-8"))
                self.wfile.flush()
            except Exception:
                pass

        except Exception as exc:
            print(f"Ошибка SSE-потока: {exc}", file=sys.stderr)

        finally:
            if proc and proc.poll() is None:
                proc.terminate()


def parse_args():
    parser = argparse.ArgumentParser(description="Nginx live log viewer")

    parser.add_argument(
        "log_file",
        nargs="?",
        default=os.getenv("LOG_PATH", DEFAULT_LOG_FILE),
        help=f"Путь к access.log nginx. По умолчанию: {DEFAULT_LOG_FILE}",
    )

    parser.add_argument(
        "port",
        nargs="?",
        type=int,
        default=int(os.getenv("PORT", DEFAULT_PORT)),
        help=f"Порт сервиса. По умолчанию: {DEFAULT_PORT}",
    )

    parser.add_argument(
        "--host",
        default=os.getenv("HOST", DEFAULT_HOST),
        help=f"Адрес прослушивания. По умолчанию: {DEFAULT_HOST}",
    )

    parser.add_argument(
        "--max-history",
        type=int,
        default=int(os.getenv("MAX_HISTORY", MAX_HISTORY)),
        help=f"Максимум строк для загрузки в интерфейс. По умолчанию: {MAX_HISTORY}",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    if not os.path.exists(args.log_file):
        print(f"⚠️  Файл лога пока не найден: {args.log_file}", file=sys.stderr)
    elif not os.access(args.log_file, os.R_OK):
        print(f"⚠️  Нет прав на чтение файла: {args.log_file}", file=sys.stderr)

    server = ThreadingHTTPServer((args.host, args.port), LogViewerHandler)
    server.log_file = args.log_file
    server.max_history = args.max_history

    print()
    print("🚀 Nginx Log Analyzer Pro запущен")
    print(f"📁 Файл: {args.log_file}")
    print(f"🌐 Адрес: http://{args.host}:{args.port}")
    print(f"📚 Лимит истории: {args.max_history}")
    print()
    print("Ctrl+C для остановки")
    print()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Сервер остановлен")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
