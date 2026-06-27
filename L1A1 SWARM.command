#!/bin/zsh
# L1A1 Swarm Orchestrator Suite (mit Original L1A1 UI)

source ~/.zshrc

clear
printf '\e[3J'

COLS=$(tput cols 2>/dev/null || echo 80)
printf "["
printf "%0.s " $(seq 1 $((COLS - 2)))
printf "]\n\n"

print_centered() {
    local text="$1"
    local clean_text=$(echo -e "$text" | sed 's/\x1b\[[0-9;]*[a-zA-Z]//g')
    local visual_len=${#clean_text}
    local cols=$(tput cols 2>/dev/null || echo 80)
    local spaces=$(( (cols - visual_len) / 2 ))
    if [ $spaces -lt 0 ]; then spaces=0; fi
    printf "%${spaces}s" ""
    echo -e "$text"
}

c_cyan="\033[1;36m"
c_blue="\033[1;34m"
c_purple="\033[1;35m"
c_magenta="\033[38;5;201m"
c_rst="\033[0m"

print_centered "  ${c_cyan}● ●    ${c_rst}   ${c_blue}  ● ●  ${c_rst}   ${c_purple}   ● ●   ${c_rst}   ${c_magenta}  ● ●  ${c_rst}"
print_centered "  ${c_cyan}● ●    ${c_rst}   ${c_blue} ● ● ● ${c_rst}   ${c_purple} ● ● ● ● ${c_rst}   ${c_magenta} ● ● ● ${c_rst}"
print_centered "  ${c_cyan}● ●    ${c_rst}   ${c_blue}  ● ●  ${c_rst}   ${c_purple}● ●   ● ●${c_rst}   ${c_magenta}  ● ●  ${c_rst}"
print_centered "  ${c_cyan}● ●    ${c_rst}   ${c_blue}  ● ●  ${c_rst}   ${c_purple}● ● ● ● ●${c_rst}   ${c_magenta}  ● ●  ${c_rst}"
print_centered "  ${c_cyan}● ● ● ●${c_rst}   ${c_blue}● ● ● ●${c_rst}   ${c_purple}● ●   ● ●${c_rst}   ${c_magenta}● ● ● ●${c_rst}"
echo ""

print_centered "L1A1 Swarm Orchestrator"
echo ""

printf "     │  🚀 Initialisiere Swarm Kernel...\n"
printf "     │  Verbinde mit Provider (Groq / NVIDIA)...\n"
printf "     │\n"

cd "/Users/arbenhajdini/Desktop/L1A1-Swarm-Orchestrator"
if [ ! -f "app.py" ]; then
    printf "     │  ❌ Fehler: app.py nicht gefunden!\n"
    read
    exit 1
fi

sleep 1

printf "     │  ✅ Swarm bereit!\n"
printf "     │  Öffne das Chat-Interface...\n"
printf "     │\n"

python3 app.py

printf "     │\n"
printf "     │  🛑 Beende Swarm Orchestrator...\n"
printf "     │  Auf Wiedersehen!\n"
printf "     │\n"
