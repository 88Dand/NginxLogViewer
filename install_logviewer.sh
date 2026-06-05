#!/bin/bash

# === Конфигурация ===
SERVICE_NAME="nginx-log-analyzer"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
INSTALL_DIR="/home/rps"
SCRIPT_NAME="logviewer.py"
SCRIPT_PATH="${INSTALL_DIR}/${SCRIPT_NAME}"
LOG_PATH_DEFAULT="/var/www/api/nginx-logs/site.access.log"
GITHUB_RAW_URL="https://raw.githubusercontent.com/88Dand/NginxLogViewer/main/logviewer.py"
PORT=8080
VERSION="2.0"

# === Цветной вывод ===
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# === Глобальные переменные ===
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# === Функции ===
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

print_header() {
    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}  $1${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
}

# === Проверка зависимостей ===
check_dependencies() {
    print_info "Проверка зависимостей..."
    local missing_deps=()
    
    # Проверка Python3
    if ! command -v python3 &> /dev/null; then
        missing_deps+=("python3")
    else
        print_success "Python3 установлен: $(python3 --version)"
    fi
    
    # Проверка pip3
    if ! command -v pip3 &> /dev/null; then
        missing_deps+=("pip3")
    else
        print_success "pip3 установлен"
    fi
    
    # Проверка curl/wget
    if ! command -v curl &> /dev/null && ! command -v wget &> /dev/null; then
        missing_deps+=("curl или wget")
    else
        print_success "curl/wget установлен"
    fi
    
    # Проверка systemctl
    if ! command -v systemctl &> /dev/null; then
        missing_deps+=("systemd")
    else
        print_success "systemd установлен"
    fi
    
    # Проверка git (опционально)
    if command -v git &> /dev/null; then
        print_success "git установлен"
    else
        print_warning "git не установлен (опционально)"
    fi
    
    if [ ${#missing_deps[@]} -ne 0 ]; then
        print_error "Отсутствуют зависимости: ${missing_deps[*]}"
        echo ""
        print_info "Установите недостающие зависимости:"
        echo "  sudo apt update"
        echo "  sudo apt install -y python3 python3-pip curl wget"
        exit 1
    fi
    
    # Проверка Python модулей
    print_info "Проверка Python модулей..."
    local missing_modules=()
    
    if ! python3 -c "import json" 2>/dev/null; then
        missing_modules+=("json")
    fi
    
    if ! python3 -c "import socket" 2>/dev/null; then
        missing_modules+=("socket")
    fi
    
    if [ ${#missing_modules[@]} -ne 0 ]; then
        print_warning "Отсутствуют модули: ${missing_modules[*]} (должны быть в стандартной библиотеке)"
    else
        print_success "Все необходимые Python модули доступны"
    fi
    
    echo ""
}

# === Очистка старых файлов ===
clean_old_files() {
    print_info "Очистка старых файлов..."
    
    # Останавливаем сервис если он запущен
    if systemctl is-active --quiet "${SERVICE_NAME}" 2>/dev/null; then
        print_info "Останавливаем сервис..."
        systemctl stop "${SERVICE_NAME}"
    fi
    
    # Удаляем старый скрипт
    if [ -f "${SCRIPT_PATH}" ]; then
        rm -f "${SCRIPT_PATH}"
        print_success "Удалён старый скрипт: ${SCRIPT_PATH}"
    fi
    
    # Удаляем кэш Python
    if [ -d "${INSTALL_DIR}/__pycache__" ]; then
        rm -rf "${INSTALL_DIR}/__pycache__"
        print_success "Удалён кэш Python"
    fi
    
    # Удаляем старые .pyc файлы
    find "${INSTALL_DIR}" -name "*.pyc" -delete 2>/dev/null
    print_success "Удалены скомпилированные файлы"
    
    # Очищаем кэш pip
    if command -v pip3 &> /dev/null; then
        pip3 cache purge 2>/dev/null && print_success "Очищен кэш pip"
    fi
    
    print_success "Очистка завершена"
}

# === Скачивание с GitHub ===
download_from_github() {
    print_info "Скачивание с GitHub..."
    
    local temp_file="${INSTALL_DIR}/temp_${SCRIPT_NAME}"
    
    # Пытаемся скачать с GitHub
    if command -v curl &> /dev/null; then
        curl -sL "${GITHUB_RAW_URL}" -o "${temp_file}"
    elif command -v wget &> /dev/null; then
        wget -q "${GITHUB_RAW_URL}" -O "${temp_file}"
    else
        print_error "Не найден curl или wget"
        return 1
    fi
    
    # Проверяем, что файл скачался и не пустой
    if [ -f "${temp_file}" ] && [ -s "${temp_file}" ]; then
        local file_size=$(stat -c%s "${temp_file}")
        if [ ${file_size} -gt 10000 ]; then
            mv "${temp_file}" "${SCRIPT_PATH}"
            print_success "Файл скачан с GitHub (${file_size} байт)"
            return 0
        else
            print_warning "Файл слишком маленький (${file_size} байт), возможно обрезан"
            rm -f "${temp_file}"
            return 1
        fi
    else
        print_error "Не удалось скачать файл"
        return 1
    fi
}

# === Создание рабочего скрипта ===
create_working_script() {
    print_info "Создание рабочего скрипта..."
    
    # Проверяем, есть ли у нас локальная рабочая копия
    if [ -f "${SCRIPT_DIR}/logviewer.py" ] && [ -s "${SCRIPT_DIR}/logviewer.py" ]; then
        local local_size=$(stat -c%s "${SCRIPT_DIR}/logviewer.py")
        if [ ${local_size} -gt 30000 ]; then
            cp "${SCRIPT_DIR}/logviewer.py" "${SCRIPT_PATH}"
            print_success "Использована локальная копия (${local_size} байт)"
            return 0
        fi
    fi
    
    # Пробуем скачать с GitHub
    if download_from_github; then
        return 0
    fi
    
    # Если не удалось, используем встроенную минимальную версию
    print_warning "Использую встроенную версию скрипта"
    cat > "${SCRIPT_PATH}" << 'EOF'
#!/usr/bin/env python3
import os, socket, subprocess, threading, sys, json
from datetime import datetime
import re

log_file = sys.argv[1] if len(sys.argv) > 1 else '/var/www/api/nginx-logs/site.access.log'
port = 8080

def parse_log_line(line):
    pattern = r'(\S+) \S+ \S+ \[([^\]]+)\] "(\S+) (\S+) [^"]+" (\d+) (\d+) "([^"]*)" "([^"]*)"'
    m = re.search(pattern, line)
    if m:
        ip, ts, method, url, status, size, ref, agent = m.groups()
        try:
            dt = datetime.strptime(ts.split()[0], '%d/%b/%Y:%H:%M:%S')
            ft = dt.strftime('%d.%m.%Y %H:%M:%S')
            st = dt.timestamp()
        except:
            ft, st = ts, 0
        return {'raw': line, 'ip': ip, 'timestamp': ft, 'sort_time': st,
                'method': method, 'url': url, 'status': int(status), 'size': size,
                'referer': ref, 'agent': agent}
    return None

def handle_client(c):
    c.send(b'HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n')
    c.send(b'<h1>Nginx Log Analyzer</h1><pre>Server is running</pre>')
    c.close()

def handle_stream(c):
    c.send(b'HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nCache-Control: no-cache\r\n\r\n')
    p = subprocess.Popen(['tail', '-f', log_file], stdout=subprocess.PIPE, text=True)
    try:
        while True:
            line = p.stdout.readline()
            if line:
                parsed = parse_log_line(line)
                if parsed:
                    c.send(f'data: {json.dumps(parsed)}\n\n'.encode())
    except: p.kill()
    c.close()

def main():
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('0.0.0.0', port))
    s.listen(10)
    print(f'Server on port {port}')
    while True:
        c, _ = s.accept()
        req = c.recv(1024).decode()
        if '/stream' in req:
            threading.Thread(target=handle_stream, args=(c,)).start()
        else:
            threading.Thread(target=handle_client, args=(c,)).start()

if __name__ == '__main__':
    try: main()
    except: pass
EOF
    
    print_success "Создана минимальная рабочая версия"
    return 0
}

# === Создание systemd сервиса ===
create_systemd_service() {
    print_info "Создание systemd сервиса..."
    
    cat > "${SERVICE_FILE}" << EOF
[Unit]
Description=Nginx Log Analyzer Pro
After=network.target nginx.service
Wants=nginx.service

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=${INSTALL_DIR}
ExecStart=/usr/bin/python3 ${SCRIPT_PATH} ${LOG_PATH_DEFAULT}
ExecStop=/bin/kill -TERM \$MAINPID
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${SERVICE_NAME}
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
EOF

    print_success "Сервис создан: ${SERVICE_FILE}"
}

# === Установка и запуск ===
install_and_start() {
    print_info "Установка и запуск сервиса..."
    
    systemctl daemon-reload
    systemctl enable "${SERVICE_NAME}"
    systemctl restart "${SERVICE_NAME}"
    sleep 2
    
    if systemctl is-active --quiet "${SERVICE_NAME}"; then
        print_success "Сервис успешно запущен"
        return 0
    else
        print_error "Сервис не запустился"
        journalctl -u "${SERVICE_NAME}" -n 20 --no-pager
        return 1
    fi
}

# === Показать статус ===
show_status() {
    print_header "СТАТУС СЕРВИСА"
    
    if systemctl is-active --quiet "${SERVICE_NAME}"; then
        print_success "Сервис активен"
    else
        print_error "Сервис не активен"
    fi
    
    echo ""
    systemctl status "${SERVICE_NAME}" --no-pager | head -n 15
    
    echo ""
    print_info "Порт: ${PORT}"
    ss -tlnp | grep ":${PORT}" 2>/dev/null || echo "Порт не слушается"
    
    echo ""
    print_info "Последние логи:"
    journalctl -u "${SERVICE_NAME}" -n 10 --no-pager
}

# === Показать логи в реальном времени ===
show_logs() {
    print_header "ЛОГИ В РЕАЛЬНОМ ВРЕМЕНИ (Ctrl+C для выхода)"
    journalctl -u "${SERVICE_NAME}" -f
}

# === Перезапуск сервиса ===
restart_service() {
    print_info "Перезапуск сервиса..."
    systemctl restart "${SERVICE_NAME}"
    sleep 2
    show_status
}

# === Остановка сервиса ===
stop_service() {
    print_info "Остановка сервиса..."
    systemctl stop "${SERVICE_NAME}"
    print_success "Сервис остановлен"
}

# === Полное удаление ===
full_uninstall() {
    print_header "ПОЛНОЕ УДАЛЕНИЕ"
    
    print_warning "Вы уверены? (y/N)"
    read -r confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        print_info "Отмена"
        return
    fi
    
    print_info "Останавливаем и отключаем сервис..."
    systemctl stop "${SERVICE_NAME}" 2>/dev/null
    systemctl disable "${SERVICE_NAME}" 2>/dev/null
    
    print_info "Удаляем файлы сервиса..."
    rm -f "${SERVICE_FILE}"
    
    print_info "Удаляем скрипты..."
    rm -f "${SCRIPT_PATH}"
    rm -rf "${INSTALL_DIR}/__pycache__"
    
    print_info "Перезагружаем systemd..."
    systemctl daemon-reload
    
    print_success "Полное удаление завершено"
}

# === Меню ===
show_menu() {
    clear
    print_header "NGINX LOG ANALYZER PRO v${VERSION}"
    echo ""
    echo -e "  ${GREEN}1${NC}) 🚀 Полная установка (очистка + загрузка + запуск)"
    echo -e "  ${GREEN}2${NC}) 🔄 Только обновление скрипта (с GitHub)"
    echo -e "  ${GREEN}3${NC}) 📊 Показать статус сервиса"
    echo -e "  ${GREEN}4${NC}) 📜 Показать логи в реальном времени"
    echo -e "  ${GREEN}5${NC}) 🔄 Перезапустить сервис"
    echo -e "  ${GREEN}6${NC)} ⏹️ Остановить сервис"
    echo -e "  ${GREEN}7${NC}) 🧹 Очистить кэш и старые файлы"
    echo -e "  ${GREEN}8${NC}) 🗑️ Полное удаление"
    echo -e "  ${GREEN}0${NC}) 🚪 Выход"
    echo ""
    echo -e "${CYAN}────────────────────────────────────────${NC}"
    echo -n -e "${BLUE}Выберите действие [0-8]: ${NC}"
}

# === Полная установка ===
full_install() {
    print_header "ПОЛНАЯ УСТАНОВКА"
    
    check_dependencies
    clean_old_files
    create_working_script
    
    # Проверяем, что файл создался и не пустой
    if [ ! -f "${SCRIPT_PATH}" ] || [ ! -s "${SCRIPT_PATH}" ]; then
        print_error "Не удалось создать скрипт"
        return 1
    fi
    
    print_success "Скрипт создан: ${SCRIPT_PATH} ($(stat -c%s ${SCRIPT_PATH}) байт)"
    
    create_systemd_service
    
    if install_and_start; then
        print_header "УСТАНОВКА ЗАВЕРШЕНА"
        
        # Получаем IP
        LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
        if [ -z "${LOCAL_IP}" ]; then
            LOCAL_IP=$(curl -s ifconfig.me 2>/dev/null)
        fi
        
        echo ""
        echo -e "${GREEN}🔗 ДОСТУП:${NC}"
        echo -e "   Локально:  ${BLUE}http://127.0.0.1:${PORT}${NC}"
        echo -e "   По сети:   ${BLUE}http://${LOCAL_IP}:${PORT}${NC}"
        echo ""
        echo -e "${YELLOW}💡 Совет:${NC} Настройте Nginx reverse proxy для доступа из интернета"
        echo ""
    else
        print_error "Установка не завершена"
        return 1
    fi
}

# === Обновление скрипта ===
update_script() {
    print_header "ОБНОВЛЕНИЕ СКРИПТА"
    
    # Останавливаем сервис
    if systemctl is-active --quiet "${SERVICE_NAME}"; then
        print_info "Останавливаем сервис..."
        systemctl stop "${SERVICE_NAME}"
    fi
    
    # Очищаем старые файлы
    clean_old_files
    
    # Скачиваем новый скрипт
    if download_from_github; then
        print_success "Новый скрипт загружен"
    else
        print_warning "Не удалось загрузить с GitHub, использую встроенную версию"
        create_working_script
    fi
    
    # Запускаем сервис
    systemctl start "${SERVICE_NAME}"
    sleep 2
    
    if systemctl is-active --quiet "${SERVICE_NAME}"; then
        print_success "Сервис перезапущен с новым скриптом"
    else
        print_error "Сервис не запустился"
        journalctl -u "${SERVICE_NAME}" -n 20 --no-pager
    fi
}

# === Главный цикл ===
main() {
    # Если есть аргумент командной строки
    case "$1" in
        install)
            full_install
            exit 0
            ;;
        update)
            update_script
            exit 0
            ;;
        status)
            show_status
            exit 0
            ;;
        logs)
            show_logs
            exit 0
            ;;
        restart)
            restart_service
            exit 0
            ;;
        stop)
            stop_service
            exit 0
            ;;
        uninstall)
            full_uninstall
            exit 0
            ;;
    esac
    
    # Интерактивное меню
    while true; do
        show_menu
        read -r choice
        echo ""
        
        case $choice in
            1) full_install ;;
            2) update_script ;;
            3) show_status ;;
            4) show_logs ;;
            5) restart_service ;;
            6) stop_service ;;
            7) clean_old_files ;;
            8) full_uninstall ;;
            0) 
                print_info "До свидания!"
                exit 0
                ;;
            *)
                print_error "Неверный выбор. Попробуйте снова."
                ;;
        esac
        
        echo ""
        echo -n "Нажмите Enter для продолжения..."
        read -r
    done
}

# === Запуск ===
main "$1"
